"""Snapshots of known planets and candidates, normalised into one table."""

import datetime as dt
import json
import shutil
import sys
from pathlib import Path

import astropy.units as u
import numpy as np
import pandas as pd
import requests
from astropy.coordinates import SkyCoord

from tess_hunt.config import catalogs_dir
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.provenance import start_run

TOI_URL = "https://exofop.ipac.caltech.edu/tess/download_toi.php?sort=toi&output=csv"
CTOI_URL = "https://exofop.ipac.caltech.edu/tess/download_ctoi.php?sort=ctoi&output=csv"
ARCHIVE_URL = "https://exoplanetarchive.ipac.caltech.edu/TAP/sync"
ARCHIVE_QUERY = (
    "select pl_name,tic_id,pl_orbper,pl_tranmid,pl_trandep,pl_trandur,ra,dec "
    "from pscomppars where tic_id is not null"
)
BJD_OFFSET = 2457000.0
# Community uploads include MJD-style epochs, misplaced decimals and multi-day durations. A wrong
# epoch would hide a known object from novelty, so values outside these bounds count as missing
# (docs/decisions/0002-catalog-data-quality.md).
MIN_T0_BTJD = -20000.0
MAX_T0_BTJD = 10000.0
MAX_DURATION_DAYS = 1.0
FILES = {"TOI": "toi.csv", "CTOI": "ctoi.csv", "archive": "pscomppars.csv"}
KNOWN_COLUMNS = [
    "source",
    "kind",
    "name",
    "tic",
    "ra",
    "dec",
    "period",
    "t0",
    "duration",
    "depth_ppm",
]
KIND_OF = {"TOI": "candidate", "CTOI": "candidate", "archive": "planet"}
KINDS = {"planet", "candidate", "community", "eb", "tce"}


class CatalogError(RuntimeError):
    pass


def refresh(
    root: Path,
    session=None,
    targets_run: Path | None = None,
    sources: list | None = None,
    now: dt.datetime | None = None,
) -> Path:
    """Download every novelty source into a staging directory, normalise each there, and rename the
    directory into place only when all succeeded: a snapshot is never partial and never
    overwritten."""
    from tess_hunt import sources as source_module  # sources imports this module's normalisers

    session = session or requests.Session()
    sources = source_module.SOURCES if sources is None else sources
    stamp = (now or dt.datetime.now(dt.UTC)).strftime("%Y-%m-%dT%H%M%SZ")
    dest = root / stamp
    if dest.exists():
        raise CatalogError(f"snapshot {dest} exists; snapshots are never overwritten")
    staging = root / f".staging-{stamp}"
    staging.mkdir(parents=True)
    try:
        ctx = source_module.Context(session, staging / "raw", targets_run)
        frames, counts = [], {}
        for source in sources:
            try:
                frame = source.fetch(ctx)
            except Exception as exc:  # any failure fails the snapshot, with the source named
                raise CatalogError(f"{source.name}: {type(exc).__name__}: {exc}") from exc
            if len(frame) == 0:
                raise CatalogError(f"{source.name} gave no rows")
            # Novelty fails every kind it is not told to soften, so a misspelt kind would turn a
            # TCE into a known planet.
            unknown = set(frame["kind"]) - KINDS
            if unknown:
                raise CatalogError(f"{source.name} gave unknown kinds {sorted(map(str, unknown))}")
            frames.append(frame[KNOWN_COLUMNS])
            kinds = frame["kind"].value_counts().sort_index()
            counts[source.name] = {
                "kinds": {str(k): int(n) for k, n in kinds.items()},
                "rows": len(frame),
            }
        known = source_module.fill_positions(pd.concat(frames, ignore_index=True), ctx=ctx)
        known.to_parquet(staging / "known.parquet")
        manifest = {
            "created": stamp,
            "sources": counts,
            "unplaced_tics": ctx.unplaced_tics,
            "files": ctx.files,
        }
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        )
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    staging.rename(dest)
    return dest


def number(series) -> np.ndarray:
    # The newer sources also pass arrays and lists, which pd.to_numeric hands back as arrays.
    return pd.to_numeric(pd.Series(series), errors="coerce").to_numpy(dtype=float)


def btjd(bjd) -> np.ndarray:
    # A few community uploads already give BTJD; only full BJD values carry the offset.
    bjd = number(bjd)
    out = np.where(bjd > 2_400_000.0, bjd - BJD_OFFSET, bjd)
    return np.where((out >= MIN_T0_BTJD) & (out <= MAX_T0_BTJD), out, np.nan)


def days(hours) -> np.ndarray:
    out = number(hours) / 24.0
    return np.where(out <= MAX_DURATION_DAYS, out, np.nan)


def normalise_toi(df: pd.DataFrame) -> pd.DataFrame:
    coords = SkyCoord(
        df["RA"].astype(str).to_numpy(), df["Dec"].astype(str).to_numpy(), unit=(u.hourangle, u.deg)
    )
    return pd.DataFrame(
        {
            "source": "TOI",
            "kind": KIND_OF["TOI"],
            "name": [f"TOI-{v:.2f}" for v in df["TOI"]],
            "tic": df["TIC ID"].astype(int).to_numpy(),
            "ra": coords.ra.deg,
            "dec": coords.dec.deg,
            "period": number(df["Period (days)"]),
            "t0": btjd(df["Epoch (BJD)"]),
            "duration": days(df["Duration (hours)"]),
            "depth_ppm": number(df["Depth (ppm)"]),
        },
        columns=KNOWN_COLUMNS,
    )


def normalise_ctoi(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": "CTOI",
            "kind": KIND_OF["CTOI"],
            "name": [f"CTOI-{v:.2f}" for v in df["CTOI"]],
            "tic": df["TIC ID"].astype(int).to_numpy(),
            "ra": number(df["RA"]),
            "dec": number(df["Dec"]),
            "period": number(df["Period (days)"]),
            "t0": btjd(df["Transit Epoch (BJD)"]),
            "duration": days(df["Duration (hrs)"]),
            "depth_ppm": number(df["Depth ppm"]),
        },
        columns=KNOWN_COLUMNS,
    )


def normalise_archive(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": "archive",
            "kind": KIND_OF["archive"],
            "name": df["pl_name"].astype(str).to_numpy(),
            "tic": [int(str(v).split()[-1]) for v in df["tic_id"]],
            "ra": number(df["ra"]),
            "dec": number(df["dec"]),
            "period": number(df["pl_orbper"]),
            "t0": btjd(df["pl_tranmid"]),
            "duration": days(df["pl_trandur"]),
            "depth_ppm": number(df["pl_trandep"]) * 1e4,  # the archive gives percent
        },
        columns=KNOWN_COLUMNS,
    )


def load_known(snapshot: Path) -> pd.DataFrame:
    if (snapshot / "known.parquet").exists():
        return pd.read_parquet(snapshot / "known.parquet")[KNOWN_COLUMNS]
    parts = []
    for source, normalise in (
        ("TOI", normalise_toi),
        ("CTOI", normalise_ctoi),
        ("archive", normalise_archive),
    ):
        path = snapshot / FILES[source]
        if not path.exists():
            raise CatalogError(f"missing {path.name} in snapshot {snapshot.name}")
        frame = normalise(pd.read_csv(path))
        if len(frame) == 0:
            raise CatalogError(f"{path.name} is empty")
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)[KNOWN_COLUMNS]


def snapshot_inputs(snapshot: Path) -> dict[str, Path]:
    """The files that identify a snapshot in a run's provenance."""
    if (snapshot / "known.parquet").exists():
        return {"known": snapshot / "known.parquet", "catalog_manifest": snapshot / "manifest.json"}
    return {name: snapshot / name for name in FILES.values()}


def known_ephemerides(
    known: pd.DataFrame, tic: int, fallback_duration: float, sources: tuple[str, ...] | None = None
) -> list[Ephemeris]:
    rows = known[
        (known["tic"] == tic)
        & np.isfinite(known["period"])
        & (known["period"] > 0)
        & np.isfinite(known["t0"])
    ]
    if sources is not None:
        rows = rows[rows["source"].isin(sources)]
    return [
        Ephemeris(
            float(r.period),
            float(r.t0),
            float(r.duration) if np.isfinite(r.duration) and r.duration > 0 else fallback_duration,
        )
        for r in rows.itertuples()
    ]


def add_parser(sub) -> None:
    p = sub.add_parser("catalogs", help="snapshot known planets and candidates")
    modes = p.add_subparsers(dest="mode", required=True)
    r = modes.add_parser("refresh", help="download every novelty source into a new snapshot")
    r.add_argument(
        "--targets", type=Path, help="targets run directory, for the sample's Gaia and VSX binaries"
    )
    r.add_argument("--production", action="store_true")
    r.set_defaults(func=cmd_refresh)


def cmd_refresh(args) -> int:
    run = start_run("catalogs", [], args.production, sys.argv)
    dest = refresh(catalogs_dir(), targets_run=args.targets)
    for name, path in snapshot_inputs(dest).items():
        run.record_input(name, path)
    manifest = json.loads((dest / "manifest.json").read_text())
    counts = manifest["sources"]
    run.finish(snapshot=dest.name, **{f"rows_{k}": v["rows"] for k, v in counts.items()})
    for name, entry in counts.items():
        kinds = ", ".join(f"{kind} {n}" for kind, n in entry["kinds"].items())
        print(f"{name}: {entry['rows']} rows ({kinds})")
    print(f"TICs without a position: {manifest['unplaced_tics']}")
    print(f"catalogs: {dest}")
    return 0
