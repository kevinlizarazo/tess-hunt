"""Novelty sources beyond M1's three: what each is, where it lives and how its rows map to the known
table."""

import hashlib
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import partial
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt.catalogs import (
    ARCHIVE_QUERY,
    ARCHIVE_URL,
    CTOI_URL,
    KNOWN_COLUMNS,
    TOI_URL,
    btjd,
    days,
    normalise_archive,
    normalise_ctoi,
    normalise_toi,
    number,
)
from tess_hunt.config import catalogs_dir
from tess_hunt.retry import retry
from tess_hunt.targets import query_tic_ids

TCE_INDEX = "https://archive.stsci.edu/missions/tess/catalogs/tce/"
_TCE_FILE = re.compile(r'href="(tess\d+-s\d{4}-s\d{4}_dvr-tcestats\.csv)"')
ZENODO_FILE = "https://zenodo.org/records/{record}/files/{name}?download=1"
EXOMINER_V1 = (
    15466293,
    "exominerplusplus_catalog_unk_tces_s1-s67_tess-spoc-2min_complete_1-16-2025_1014.csv",
)
EXOMINER_V2 = (17707413, ("vetting_catalog_2-min.csv", "vetting_catalog_FFI.csv"))
PS_QUERY = (
    "select pl_name,tic_id,pl_orbper,pl_tranmid,pl_trandep,pl_trandur,ra,dec "
    "from ps where tic_id is not null and pl_tranmid is not null"
)
TIC_LOOKUP = "mast:Catalogs.query_criteria(catalog=Tic, ID=<tics>)"


class SourceError(RuntimeError):
    pass


class _ServerError(RuntimeError):
    pass


@dataclass
class Context:
    """What a source's fetch works with; it lists every file kept in the snapshot for the manifest."""

    session: object
    raw: Path
    targets_run: Path | None
    files: list[dict] = field(default_factory=list)
    unplaced_tics: int = 0
    attempts: int = 3
    backoff: float = 10.0

    def _get(self, url: str, params: dict | None):
        response = self.session.get(url, timeout=600, params=params)
        if response.status_code == 429 or response.status_code >= 500:
            raise _ServerError(f"HTTP {response.status_code}")
        return response

    def download(self, source: str, url: str, name: str, params: dict | None = None) -> Path:
        # A refresh downloads over a hundred files; one server hiccup should not cost the snapshot.
        response = retry(
            partial(self._get, url, params),
            attempts=self.attempts,
            backoff=self.backoff,
            retry_on=(requests.RequestException, _ServerError),
            error=SourceError,
            what=f"{source}: {url}",
        )
        if response.status_code != 200:
            raise SourceError(f"{source}: HTTP {response.status_code} for {url}")
        return self.keep(source, name, response.content, url, response.headers.get("Last-Modified"))

    def keep(
        self, source: str, name: str, content: bytes, url: str, last_modified: str | None = None
    ) -> Path:
        """Write a file into the snapshot and list it in the manifest, however it was obtained."""
        path = self.raw / source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        self.files.append(
            {
                "source": source,
                "url": url,
                "file": f"{source}/{name}",
                "bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "last_modified": last_modified,
            }
        )
        return path


@dataclass(frozen=True)
class Source:
    name: str
    kind: str
    fetch: Callable[[Context], pd.DataFrame]


def frame(
    source: str, kind: str, tic, name, period, t0, duration, depth_ppm, ra=np.nan, dec=np.nan
) -> pd.DataFrame:
    """The known table's columns from one source's arrays; epochs and durations pass M1's bounds."""
    out = pd.DataFrame(
        {
            "source": source,
            "kind": kind,
            "name": name,
            "tic": np.asarray(tic, dtype=np.int64),
            "ra": ra,
            "dec": dec,
            "period": number(period),
            "t0": btjd(t0),
            "duration": duration,
            "depth_ppm": number(depth_ppm),
        }
    )
    return out[KNOWN_COLUMNS]


def tce_files(index_html: str) -> list[str]:
    return sorted(set(_TCE_FILE.findall(index_html)))


def normalise_spoc_tce(table: pd.DataFrame, run: str) -> pd.DataFrame:
    # tce_time0bt is BTJD with full precision; tce_time0 is rounded in some runs (S33).
    return frame(
        "SPOC-TCE",
        "tce",
        table["ticid"],
        [f"TCE {run} {t}" for t in table["tceid"]],
        table["tce_period"],
        table["tce_time0bt"],
        days(table["tce_duration"]),
        table["tce_depth"],
    )


def normalise_exominer_v1(table: pd.DataFrame) -> pd.DataFrame:
    return frame(
        "ExoMiner-v1",
        "tce",
        table["TIC ID"],
        [f"ExoMiner {t}" for t in table["TCE ID"]],
        table["Orbital Period [day]"],
        table["Transit Epoch [BTJD]"],
        days(table["Transit Duration [hour]"]),
        table["Transit Depth [ppm]"],
    )


def normalise_exominer_v2(table: pd.DataFrame, label: str) -> pd.DataFrame:
    return frame(
        "ExoMiner-v2",
        "tce",
        table["target_id"],
        [f"ExoMiner {label} {u}" for u in table["uid"]],
        table["tce_period"],
        table["tce_time0bt"],
        days(table["tce_duration"]),
        table["tce_depth"],
    )


def _csv(path: Path, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, **kwargs)


def fetch_toi(ctx: Context) -> pd.DataFrame:
    return normalise_toi(_csv(ctx.download("TOI", TOI_URL, "toi.csv")))


def fetch_ctoi(ctx: Context) -> pd.DataFrame:
    return normalise_ctoi(_csv(ctx.download("CTOI", CTOI_URL, "ctoi.csv")))


def fetch_archive(ctx: Context) -> pd.DataFrame:
    path = ctx.download(
        "archive", ARCHIVE_URL, "pscomppars.csv", {"query": ARCHIVE_QUERY, "format": "csv"}
    )
    return normalise_archive(_csv(path))


def fetch_archive_ps(ctx: Context) -> pd.DataFrame:
    # ps holds every published solution, so a planet's older ephemerides help the epoch test.
    path = ctx.download("archive_ps", ARCHIVE_URL, "ps.csv", {"query": PS_QUERY, "format": "csv"})
    out = normalise_archive(_csv(path)).assign(source="archive_ps")
    return out[KNOWN_COLUMNS]


def fetch_spoc_tce(ctx: Context) -> pd.DataFrame:
    index = ctx.download("SPOC-TCE", TCE_INDEX, "index.html").read_text()
    parts = []
    for name in tce_files(index):
        run = re.search(r"-(s\d{4}-s\d{4})_", name).group(1)
        parts.append(
            normalise_spoc_tce(
                _csv(ctx.download("SPOC-TCE", TCE_INDEX + name, name), comment="#"), run
            )
        )
    if not parts:
        raise SourceError("SPOC-TCE: the index lists no TCE files")
    return pd.concat(parts, ignore_index=True)


def fetch_exominer(ctx: Context) -> pd.DataFrame:
    record, name = EXOMINER_V1
    parts = [
        normalise_exominer_v1(
            _csv(ctx.download("ExoMiner-v1", ZENODO_FILE.format(record=record, name=name), name))
        )
    ]
    record, names = EXOMINER_V2
    for name in names:
        path = ctx.download("ExoMiner-v2", ZENODO_FILE.format(record=record, name=name), name)
        parts.append(normalise_exominer_v2(_csv(path, comment="#"), name.removesuffix(".csv")))
    return pd.concat(parts, ignore_index=True)


SOURCES: list[Source] = [
    Source("TOI", "candidate", fetch_toi),
    Source("CTOI", "candidate", fetch_ctoi),
    Source("archive", "planet", fetch_archive),
    Source("archive_ps", "planet", fetch_archive_ps),
    Source("SPOC-TCE", "tce", fetch_spoc_tce),
    Source("ExoMiner", "tce", fetch_exominer),
]


def tic_positions(
    tics: list[int],
    query=query_tic_ids,
    batch: int = 2000,
    attempts: int = 3,
    backoff: float = 10.0,
) -> pd.DataFrame:
    """TIC positions, cached across snapshots under the data directory: a star does not move between
    them. The cache only saves lookups; each snapshot keeps the positions it used."""
    cache_path = catalogs_dir() / "tic_positions.parquet"
    parts = [pd.read_parquet(cache_path)] if cache_path.exists() else []
    cached = set(parts[0]["tic"]) if parts else set()
    wanted = sorted({int(t) for t in tics} - cached)
    for start in range(0, len(wanted), batch):
        ids = wanted[start : start + batch]
        found = retry(
            partial(query, ids),
            attempts=attempts,
            backoff=backoff,
            # MAST answers outages with assorted exception types.
            retry_on=Exception,
            error=SourceError,
            what=f"TIC positions for {len(ids)} TICs",
        )
        parts.append(found[["tic", "ra", "dec"]])
    if not parts:
        return pd.DataFrame(
            {
                "tic": pd.Series(dtype="int64"),
                "ra": pd.Series(dtype=float),
                "dec": pd.Series(dtype=float),
            }
        )
    table = pd.concat(parts, ignore_index=True).drop_duplicates("tic")
    if wanted:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        # Written aside and renamed, so a killed refresh never leaves a broken cache behind.
        staged = cache_path.with_suffix(".tmp")
        table.to_parquet(staged, index=False)
        staged.replace(cache_path)
    return table[table["tic"].isin({int(t) for t in tics})].reset_index(drop=True)


def fill_positions(known: pd.DataFrame, lookup=None, ctx: Context | None = None) -> pd.DataFrame:
    """Positions for rows that came without one, so neighbour matching works for every source. Given
    the snapshot's context, the positions used go into the snapshot and the TICs the TIC could not
    place are counted: their rows can only match a signal on their own star."""
    missing = known["ra"].isna() | known["dec"].isna()
    if not missing.any():
        return known
    tics = sorted(set(known.loc[missing, "tic"].astype(int)))
    found = (lookup or tic_positions)(tics).drop_duplicates("tic").set_index("tic")
    out = known.copy()
    looked_up = out.loc[missing, "tic"].astype(int)
    out.loc[missing, "ra"] = looked_up.map(found["ra"]).to_numpy()
    out.loc[missing, "dec"] = looked_up.map(found["dec"]).to_numpy()
    if ctx is not None:
        positions = pd.DataFrame({"tic": tics}).join(found[["ra", "dec"]], on="tic")
        ctx.keep("TIC", "tic_positions.parquet", positions.to_parquet(index=False), TIC_LOOKUP)
        ctx.unplaced_tics = int((positions["ra"].isna() | positions["dec"].isna()).sum())
    return out
