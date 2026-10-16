"""Novelty sources beyond M1's three: what each is, where it lives and how its rows map to the known
table."""

import hashlib
import io
import json
import re
import zipfile
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
    MAX_DURATION_DAYS,
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
EUMEMIC_REPO = "eumemic/exoplanets"
EUMEMIC_FILES = (
    "candidates/ephemerides.csv",
    "results_public/candidates_allsky.csv",
    "results_public/all_signals_tce.csv.gz",
)
CAO = (23193828, "table1_catalog.csv")
RAVEN = (19661443, "nsfp09_table.csv")
T16_URL = "https://dataverse.harvard.edu/api/access/datafile/13605255"
PRSA_URL = "https://archive.stsci.edu/hlsps/tess-ebs/hlsp_tess-ebs_tess_lcf-ffi_s0001-s0026_tess_v1.0_cat.csv"
# Kostov 2025 tables 3 and 4, then Justesen and Albrecht 2021: (catalog, period column, epoch column).
VIZIER_EBS = (
    ("J/ApJS/279/50/table3", "Per", "T0-pri"),
    ("J/ApJS/279/50/table4", "Per-TESS", "T0-TESS"),
    ("J/ApJ/912/123/table2", "Per", "t1"),
)
TH0RGAL_REPO = "Th0rgal/open-exoplanet-hunt"
# Single-object community records: (Zenodo record, file, parser, TIC when the file doesn't carry it).
# tess-transit-hunter publishes HTML only; the literature search on shortlisted TICs covers it.
RECORDS = [
    (23271302, "candidate.json", "flat_json", None),
    (23271252, "candidate.json", "flat_json", None),
    (23293798, "TIC458191673_candidate.json", "nested_json", None),
    (23118499, "TIC257484419_ephemeris.csv", "quantity_value_csv", 257484419),
    (23289148, "TIC257484419_ephemeris.csv", "quantity_value_csv", 257484419),
    (23257784, "252721481_predicted_transits.csv", "predicted_csv", 252721481),
    (23257784, "370612437_predicted_transits.csv", "predicted_csv", 370612437),
    (23175179, "tic4206066_S110_prereg_final.zip", "rabtsevich_json", 4206066),
]


class SourceError(RuntimeError):
    pass


class _ServerError(RuntimeError):
    pass


@dataclass
class Context:
    """What a source's fetch works with; it lists every file kept in the snapshot, for the
    manifest."""

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
        # The query is part of what was fetched: archive and archive_ps share one TAP URL.
        fetched = requests.Request("GET", url, params=params).prepare().url
        if response.status_code != 200:
            raise SourceError(f"{source}: HTTP {response.status_code} for {fetched}")
        return self.keep(
            source, name, response.content, fetched, response.headers.get("Last-Modified")
        )

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
    duration = number(duration)
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
            "duration": np.where(duration <= MAX_DURATION_DAYS, duration, np.nan),
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


def _rows(path: Path, **kwargs) -> pd.DataFrame:
    """One file of a source built from several. An empty one would hide its rows from novelty while
    the source as a whole still has rows, so it fails the source."""
    table = _csv(path, **kwargs)
    if len(table) == 0:
        raise SourceError(f"{path.parent.name}: {path.name} has no rows")
    return table


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
        path = ctx.download("SPOC-TCE", TCE_INDEX + name, name)
        parts.append(normalise_spoc_tce(_rows(path, comment="#"), run))
    if not parts:
        raise SourceError("SPOC-TCE: the index lists no TCE files")
    return pd.concat(parts, ignore_index=True)


def fetch_exominer(ctx: Context) -> pd.DataFrame:
    record, name = EXOMINER_V1
    path = ctx.download("ExoMiner-v1", ZENODO_FILE.format(record=record, name=name), name)
    parts = [normalise_exominer_v1(_rows(path))]
    record, names = EXOMINER_V2
    for name in names:
        path = ctx.download("ExoMiner-v2", ZENODO_FILE.format(record=record, name=name), name)
        parts.append(normalise_exominer_v2(_rows(path, comment="#"), name.removesuffix(".csv")))
    return pd.concat(parts, ignore_index=True)


def _github_head(ctx: Context, repo: str) -> str:
    # Raw files are read at one commit, so the snapshot names exactly what it read.
    path = ctx.download(
        repo.replace("/", "_"), f"https://api.github.com/repos/{repo}/commits/main", "head.json"
    )
    return json.loads(path.read_text())["sha"]


def normalise_eumemic(eph: pd.DataFrame, allsky: pd.DataFrame, tce: pd.DataFrame, commit: str):
    return (
        frame(
            "eumemic",
            "community",
            eph["TIC"],
            [f"eumemic {commit[:7]} {t}" for t in eph["TIC"]],
            eph["period_d"],
            eph["T0_BJD_TDB"],
            days(eph["duration_h"]),
            eph["depth_ppm"],
            number(eph["ra"]),
            number(eph["dec"]),
        ),
        frame(
            "eumemic",
            "community",
            allsky["TIC"],
            [f"eumemic-allsky {commit[:7]} {t}" for t in allsky["TIC"]],
            allsky["P_d"],
            allsky["T0_BJD"],
            days(allsky["T14_h"]),
            allsky["depth_ppm"],
        ),
        frame(
            "eumemic-tce",
            "tce",
            tce["tic"],
            [f"eumemic-tce {commit[:7]} {t}" for t in tce["tic"]],
            tce["period"],
            tce["t0"],
            days(tce["duration_h"]),
            tce["bls_depth_ppm"],
        ),
    )


def fetch_eumemic(ctx: Context) -> pd.DataFrame:
    commit = _github_head(ctx, EUMEMIC_REPO)
    tables = [
        _rows(
            ctx.download(
                "eumemic",
                f"https://raw.githubusercontent.com/{EUMEMIC_REPO}/{commit}/{name}",
                name.replace("/", "_"),
            )
        )
        for name in EUMEMIC_FILES
    ]
    return pd.concat(normalise_eumemic(*tables, commit), ignore_index=True)


def normalise_cao(table: pd.DataFrame) -> pd.DataFrame:
    # The table's epoch errors are order-of-magnitude estimates (median 0.36 d), too loose for the
    # epoch test, so the rows match on period alone, which errs toward calling a signal known
    # (decision 0002).
    nan = np.full(len(table), np.nan)
    return frame(
        "Cao",
        "community",
        table["tic_id"],
        table["dossier_name"],
        table["period_days"],
        nan,
        nan,
        table["depth_ppm"],
    )


def fetch_cao(ctx: Context) -> pd.DataFrame:
    record, name = CAO
    path = ctx.download("Cao", ZENODO_FILE.format(record=record, name=name), name)
    return normalise_cao(_csv(path, comment="#"))


def normalise_raven(table: pd.DataFrame) -> pd.DataFrame:
    # bls_tdur is in hours: read as days, over a third of the rows would last as long as their
    # period.
    return frame(
        "RAVEN",
        "candidate",
        table["ticid"],
        [f"RAVEN {t}" for t in table["ticid"]],
        table["bls_per"],
        table["bls_t0"],
        days(table["bls_tdur"]),
        table["bls_depth"],
        number(table["ra"]),
        number(table["dec"]),
    )


def fetch_raven(ctx: Context) -> pd.DataFrame:
    record, name = RAVEN
    return normalise_raven(
        _csv(ctx.download("RAVEN", ZENODO_FILE.format(record=record, name=name), name))
    )


def normalise_t16(table: pd.DataFrame) -> pd.DataFrame:
    period = number(table["P_med"])
    return frame(
        "T16",
        "candidate",
        table["TICID"],
        [f"T16 {t}" for t in table["TICID"]],
        period,
        table["Tc_med"],
        number(table["qtran"]) * period,
        np.full(len(table), np.nan),
        number(table["ra"]),
        number(table["dec"]),
    )


def fetch_t16(ctx: Context) -> pd.DataFrame:
    return normalise_t16(_csv(ctx.download("T16", T16_URL, "candidate_table.tab"), sep="\t"))


def _row(tic, period, t0, duration_days=np.nan, depth_ppm=np.nan, name=None) -> dict:
    return {
        "tic": int(tic),
        "period": float(period),
        "t0": float(t0),
        "duration": duration_days,
        "depth_ppm": depth_ppm,
        "name": name or f"TIC {int(tic)}",
    }


def parse_record(fmt: str, content: bytes, tic: int | None = None) -> list[dict]:
    """Rows of one community record; t0 comes back in BTJD."""
    if fmt == "flat_json":
        d = json.loads(content)
        t0 = btjd([d["t0_BJD_TDB"]])[0]
        return [_row(d["TIC"], d["period_d"], t0, d["duration_hr"] / 24.0, d["depth_ppm"])]
    if fmt == "nested_json":
        d = json.loads(content)
        e, t = d["ephemeris"], d["transit"]
        t0 = btjd([e["t0_bjd_tdb"]])[0]
        duration = t["duration_hr"] / 24.0
        return [_row(d["host"]["tic"], e["period_d"], t0, duration, t["depth_ppm"], d.get("name"))]
    if fmt == "quantity_value_csv":
        # The depth's quantity name holds an unquoted comma ("transit depth (model, fit B)"), so each
        # line splits from the right into quantity, value, uncertainty and unit.
        lines = content.decode().splitlines()[1:]
        values = dict(line.rsplit(",", 3)[:2] for line in lines if line)
        picked = []
        for prefix in ("period", "mid-transit time", "transit duration", "transit depth"):
            found = [v for k, v in values.items() if k.startswith(prefix)]
            if not found:
                raise SourceError(f"no quantity starting with '{prefix}'")
            picked.append(float(found[0]))
        period, t0, duration, depth = picked
        return [_row(tic, period, btjd([t0])[0], duration / 24.0, depth)]
    if fmt == "predicted_csv":
        p = pd.read_csv(io.BytesIO(content))
        period, intercept = np.polyfit(p["epoch"].astype(float), p["mid_BJD_TDB"].astype(float), 1)
        duration = float(p["duration_hr"].iloc[0]) / 24.0
        return [_row(tic, period, btjd([intercept])[0], duration, float(p["depth_ppm"].iloc[0]))]
    if fmt == "rabtsevich_json":
        d = json.loads(content)
        return [
            _row(tic, s["P"], s["T0"], s["T14"], np.nan, f"TIC {tic} signal {k}")
            for k, s in d.items()
            if isinstance(s, dict) and "P" in s
        ]
    if fmt == "certificate_json":
        d = json.loads(content)
        rows = []
        for signal in [d["primary_signal"], *d.get("secondary_candidates", [])]:
            e = signal["ephemeris"]
            duration, depth = e["duration_h"] / 24.0, e["bls_box_depth_ppm"]
            name = signal.get("label")
            rows.append(_row(d["tic_id"], e["period_d"], e["t0_btjd"], duration, depth, name))
        return rows
    raise SourceError(f"unknown record format {fmt}")


def _parse(saved: str, fmt: str, content: bytes, tic: int | None = None) -> list[dict]:
    try:
        rows = parse_record(fmt, content, tic)
    except Exception as exc:  # whatever breaks in a malformed record, the error names the record
        raise SourceError(f"records: {saved}: {type(exc).__name__}: {exc}") from exc
    # As with a multi-file source's empty file, a record without rows would hide its object.
    if not rows:
        raise SourceError(f"records: {saved} has no rows")
    return rows


def fetch_records(ctx: Context) -> pd.DataFrame:
    rows = []
    for record, name, fmt, tic in RECORDS:
        saved = f"{record}_{name}"
        path = ctx.download("records", ZENODO_FILE.format(record=record, name=name), saved)
        content = path.read_bytes()
        if name.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(content)) as z:
                members = [m for m in z.namelist() if m.endswith("ephemeris_final.json")]
                if not members:
                    raise SourceError(f"records: {saved} has no ephemeris_final.json")
                content = z.read(members[0])
        rows += [{**r, "source": f"zenodo-{record}"} for r in _parse(saved, fmt, content, tic)]
    head = _github_head(ctx, TH0RGAL_REPO)
    tree = ctx.download(
        "records",
        f"https://api.github.com/repos/{TH0RGAL_REPO}/git/trees/{head}?recursive=1",
        "th0rgal_tree.json",
    )
    listing = json.loads(tree.read_text())
    if listing["truncated"]:
        raise SourceError("records: GitHub truncated the Th0rgal tree listing")
    paths = sorted(p["path"] for p in listing["tree"] if p["path"].endswith("certificate.json"))
    if not paths:
        raise SourceError("records: the Th0rgal tree lists no certificates")
    for path in paths:
        url = f"https://raw.githubusercontent.com/{TH0RGAL_REPO}/{head}/{path}"
        saved = path.replace("/", "_")
        content = ctx.download("records", url, saved).read_bytes()
        rows += [{**r, "source": "th0rgal"} for r in _parse(saved, "certificate_json", content)]
    table = pd.DataFrame(rows)
    return frame(
        table["source"],
        "community",
        table["tic"],
        table["name"],
        table["period"],
        table["t0"],
        table["duration"],
        table["depth_ppm"],
    )


def normalise_prsa(table: pd.DataFrame) -> pd.DataFrame:
    nan = np.full(len(table), np.nan)
    return frame(
        "Prsa2022",
        "eb",
        table["tess_id"],
        [f"TESS EB {t}" for t in table["tess_id"]],
        table["period"],
        table["bjd0"],
        nan,
        nan,
        number(table["ra"]),
        number(table["dec"]),
    )


def _vizier(catalog: str, columns: list[str]) -> pd.DataFrame:
    from astroquery.vizier import Vizier

    return Vizier(columns=columns, row_limit=-1).get_catalogs(catalog)[0].to_pandas()


def fetch_tess_eb(ctx: Context) -> pd.DataFrame:
    parts = [normalise_prsa(_rows(ctx.download("TESS-EB", PRSA_URL, "prsa2022.csv")))]
    for catalog, period, t0 in VIZIER_EBS:
        table = retry(
            partial(_vizier, catalog, ["TIC", period, t0]),
            attempts=ctx.attempts,
            backoff=ctx.backoff,
            # astroquery reports outages with assorted exception types.
            retry_on=Exception,
            error=SourceError,
            what=f"TESS-EB: VizieR {catalog}",
        )
        name = catalog.replace("/", "_") + ".csv"
        content = table.to_csv(index=False).encode()
        # Read back from the kept file, so the rows are exactly what the snapshot holds.
        table = _rows(ctx.keep("TESS-EB", name, content, f"vizier:{catalog}"))
        nan = np.full(len(table), np.nan)
        names = [f"{catalog} {t}" for t in table["TIC"]]
        parts.append(frame(catalog, "eb", table["TIC"], names, table[period], table[t0], nan, nan))
    return pd.concat(parts, ignore_index=True)


def _targets_file(ctx: Context, name: str) -> Path:
    if ctx.targets_run is None:
        raise SourceError(f"{name} needs the targets run: refresh with --targets <run dir>")
    path = Path(ctx.targets_run) / name
    if not path.exists():
        raise SourceError(f"{name} is not in targets run {path.parent.name}")
    return path


def normalise_gaia_eb(table: pd.DataFrame) -> pd.DataFrame:
    # The reference time is not an eclipse time, so the rows match on period alone.
    nan = np.full(len(table), np.nan)
    return frame(
        "Gaia-EB",
        "eb",
        table["tic"],
        [f"Gaia DR3 EB {t}" for t in table["tic"]],
        1.0 / number(table["eb_frequency"]),
        nan,
        nan,
        nan,
    )


def fetch_gaia_eb(ctx: Context) -> pd.DataFrame:
    path = _targets_file(ctx, "dr3_eb.parquet")
    ctx.keep(
        "Gaia-EB", "dr3_eb.parquet", path.read_bytes(), f"targets run {Path(ctx.targets_run).name}"
    )
    return normalise_gaia_eb(pd.read_parquet(path))


def normalise_vsx(table: pd.DataFrame) -> pd.DataFrame:
    # A type joins alternatives (|), components (+) and subtypes (/); a row stays when any token is
    # eclipsing. Tokens starting with E are, except ELL (ellipsoidal), EXOR (an EX Lupi eruptive) and
    # EP (a transiting planet, already in the planet tables).
    keep = table["Type"].fillna("").str.contains(r"(?:^|[|+/])\s*E(?!LL|XOR|P\b)")
    t = table.loc[keep]
    nan = np.full(len(t), np.nan)
    return frame(
        "VSX",
        "eb",
        t["tic"],
        [f"VSX {n}" for n in t["Name"]],
        t["Period"],
        nan,
        nan,
        nan,
        number(t["ra"]),
        number(t["dec"]),
    )


def fetch_vsx(ctx: Context) -> pd.DataFrame:
    import astropy.units as u
    from astropy.table import Table
    from astroquery.xmatch import XMatch

    targets = pd.read_parquet(_targets_file(ctx, "targets.parquet"), columns=["tic", "ra", "dec"])
    query = partial(
        XMatch.query,
        cat1=Table.from_pandas(targets),
        cat2="vizier:B/vsx/vsx",
        max_distance=5 * u.arcsec,
        colRA1="ra",
        colDec1="dec",
    )
    result = retry(
        query,
        attempts=ctx.attempts,
        backoff=ctx.backoff,
        retry_on=Exception,
        error=SourceError,
        what="VSX: CDS XMatch",
    ).to_pandas()
    ctx.keep(
        "VSX",
        "xmatch.csv",
        result.to_csv(index=False).encode(),
        "xmatch:vizier:B/vsx/vsx within 5 arcsec",
    )
    return normalise_vsx(result)


SOURCES: list[Source] = [
    Source("TOI", "candidate", fetch_toi),
    Source("CTOI", "candidate", fetch_ctoi),
    Source("archive", "planet", fetch_archive),
    Source("archive_ps", "planet", fetch_archive_ps),
    Source("SPOC-TCE", "tce", fetch_spoc_tce),
    Source("ExoMiner", "tce", fetch_exominer),
    Source("eumemic", "community", fetch_eumemic),
    Source("Cao", "community", fetch_cao),
    Source("RAVEN", "candidate", fetch_raven),
    Source("T16", "candidate", fetch_t16),
    Source("records", "community", fetch_records),
    Source("TESS-EB", "eb", fetch_tess_eb),
    Source("Gaia-EB", "eb", fetch_gaia_eb),
    Source("VSX", "eb", fetch_vsx),
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
