"""Snapshots of known planets and candidates, normalised into one table."""

import datetime as dt
import io
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
FILES = {"TOI": "toi.csv", "CTOI": "ctoi.csv", "archive": "pscomppars.csv"}
KNOWN_COLUMNS = ["source", "name", "tic", "ra", "dec", "period", "t0", "duration", "depth_ppm"]


class CatalogError(RuntimeError):
    pass


def refresh(root: Path, session=None) -> Path:
    """Download today's TOI, CTOI and Exoplanet Archive tables into root/<UTC date>/."""
    session = session or requests.Session()
    dest = root / dt.datetime.now(dt.UTC).strftime("%Y-%m-%d")
    dest.mkdir(parents=True, exist_ok=True)
    sources = {
        "TOI": (TOI_URL, None),
        "CTOI": (CTOI_URL, None),
        "archive": (ARCHIVE_URL, {"query": ARCHIVE_QUERY, "format": "csv"}),
    }
    for source, (url, params) in sources.items():
        response = session.get(url, params=params, timeout=300)
        response.raise_for_status()
        if len(pd.read_csv(io.StringIO(response.text))) == 0:
            raise CatalogError(f"{source} download was empty")
        (dest / FILES[source]).write_text(response.text)
    return dest


def _number(series) -> np.ndarray:
    return pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)


def _btjd(bjd) -> np.ndarray:
    # A few community uploads already give BTJD; only full BJD values carry the offset.
    bjd = _number(bjd)
    return np.where(bjd > 2_400_000.0, bjd - BJD_OFFSET, bjd)


def normalise_toi(df: pd.DataFrame) -> pd.DataFrame:
    coords = SkyCoord(
        df["RA"].astype(str).to_numpy(), df["Dec"].astype(str).to_numpy(), unit=(u.hourangle, u.deg)
    )
    return pd.DataFrame(
        {
            "source": "TOI",
            "name": [f"TOI-{v:.2f}" for v in df["TOI"]],
            "tic": df["TIC ID"].astype(int).to_numpy(),
            "ra": coords.ra.deg,
            "dec": coords.dec.deg,
            "period": _number(df["Period (days)"]),
            "t0": _btjd(df["Epoch (BJD)"]),
            "duration": _number(df["Duration (hours)"]) / 24.0,
            "depth_ppm": _number(df["Depth (ppm)"]),
        },
        columns=KNOWN_COLUMNS,
    )


def normalise_ctoi(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": "CTOI",
            "name": [f"CTOI-{v:.2f}" for v in df["CTOI"]],
            "tic": df["TIC ID"].astype(int).to_numpy(),
            "ra": _number(df["RA"]),
            "dec": _number(df["Dec"]),
            "period": _number(df["Period (days)"]),
            "t0": _btjd(df["Transit Epoch (BJD)"]),
            "duration": _number(df["Duration (hrs)"]) / 24.0,
            "depth_ppm": _number(df["Depth ppm"]),
        },
        columns=KNOWN_COLUMNS,
    )


def normalise_archive(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "source": "archive",
            "name": df["pl_name"].astype(str).to_numpy(),
            "tic": [int(str(v).split()[-1]) for v in df["tic_id"]],
            "ra": _number(df["ra"]),
            "dec": _number(df["dec"]),
            "period": _number(df["pl_orbper"]),
            "t0": _btjd(df["pl_tranmid"]),
            "duration": _number(df["pl_trandur"]) / 24.0,
            "depth_ppm": _number(df["pl_trandep"]) * 1e4,  # the archive gives percent
        },
        columns=KNOWN_COLUMNS,
    )


def load_known(snapshot: Path) -> pd.DataFrame:
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


def known_ephemerides(known: pd.DataFrame, tic: int, fallback_duration: float) -> list[Ephemeris]:
    rows = known[
        (known["tic"] == tic)
        & np.isfinite(known["period"])
        & (known["period"] > 0)
        & np.isfinite(known["t0"])
    ]
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
    r = modes.add_parser("refresh", help="download today's TOI, CTOI and Exoplanet Archive tables")
    r.add_argument("--production", action="store_true")
    r.set_defaults(func=cmd_refresh)


def cmd_refresh(args) -> int:
    run = start_run("catalogs", [], args.production, sys.argv)
    dest = refresh(catalogs_dir())
    for name in FILES.values():
        run.record_input(name, dest / name)
    run.finish(snapshot=dest.name)
    print(f"catalogs: {dest}")
    return 0
