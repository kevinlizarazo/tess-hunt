"""QLP minus SPOC 2-min transit mid-times in the sectors whose QLP timestamps MAST says are wrong.

The plan's script (Task 6, Step 1). Each transit is fitted within +-40 min of the TOI ephemeris's prediction.

Usage: uv run python benchmarks/qlp_timing.py > results/benchmarks/qlp-timing-2026-10-13.txt
"""

import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt import mast
from tess_hunt.catalogs import normalise_toi
from tess_hunt.config import catalogs_dir
from tess_hunt.fetch import read_product

SECTORS = range(99, 105)
toi = normalise_toi(pd.read_csv(catalogs_dir() / "2026-10-09" / "toi.csv"))
deep = toi[
    (toi["depth_ppm"] > 3000)
    & toi["period"].between(1, 15)
    & toi["t0"].notna()
    & toi["duration"].notna()
]
deep = deep.sort_values("depth_ppm", ascending=False).drop_duplicates("tic").head(300)
products = mast.discover([int(t) for t in deep["tic"]])
late = products[products["sector"].isin(SECTORS)]
pairs = late.groupby(["tic", "sector"])["provenance"].agg(set)
pairs = [key for key, kinds in pairs.items() if {"SPOC", "QLP"} <= kinds][:8]
session = requests.Session()


def series(tic, sector, provenance):
    row = late[
        (late["tic"] == tic) & (late["sector"] == sector) & (late["provenance"] == provenance)
    ].iloc[0]
    blob, route = mast.download(row["s3_key"], int(row["size"]), session, data_uri=row["data_uri"])
    with tempfile.NamedTemporaryFile(suffix=".fits") as fh:
        fh.write(blob)
        fh.flush()
        time, flux, _, _ = read_product(Path(fh.name), provenance)
    return time, flux, row["filename"]


def mid_time(time, flux, guess, duration, depth):
    near = np.abs(time - guess) < 1.5 * duration
    t, f = time[near], flux[near]
    out = np.abs(t - guess) > 0.6 * duration
    if len(t) < 20 or out.sum() < 5:
        return np.nan
    f = f / np.polyval(np.polyfit(t[out] - guess, f[out], 1), t - guess)
    shifts = np.arange(-40.0, 40.01, 0.25) / 1440.0
    cost = [
        np.sum((f - np.where(np.abs(t - guess - s) < duration / 2, 1 - depth, 1.0)) ** 2)
        for s in shifts
    ]
    return guess + shifts[int(np.argmin(cost))]


for tic, sector in pairs:
    eph = deep[deep["tic"] == tic].iloc[0]
    ts, fs, _ = series(tic, sector, "SPOC")
    tq, fq, name = series(tic, sector, "QLP")
    lo, hi = max(ts.min(), tq.min()), min(ts.max(), tq.max())
    offsets = []
    for n in np.arange(
        np.ceil((lo - eph["t0"]) / eph["period"]), np.floor((hi - eph["t0"]) / eph["period"]) + 1
    ):
        guess = eph["t0"] + n * eph["period"]
        a = mid_time(ts, fs, guess, eph["duration"], eph["depth_ppm"] / 1e6)
        b = mid_time(tq, fq, guess, eph["duration"], eph["depth_ppm"] / 1e6)
        if np.isfinite(a) and np.isfinite(b):
            offsets.append((b - a) * 1440.0)
    if offsets:
        print(
            f"TIC {tic} S{sector} {name}: QLP minus SPOC {np.median(offsets):+.2f} min over {len(offsets)} transits (spread {np.std(offsets):.2f})"
        )
