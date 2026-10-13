"""Empirical dilution check: QLP sap_flux transit depth against SPOC PDCSAP (crowding-corrected) depth, in every
sector with both, for five crowded TOI hosts. Sectors from S94 are QLP's TGLC era, earlier ones its FIPHOT era. A
QLP/SPOC depth ratio near 1 means the two agree. SPOC's CROWDSAP is printed for context only: it describes SPOC's
aperture, not QLP's, so it does not predict QLP's dilution.

Usage: uv run python benchmarks/qlp_dilution.py > results/benchmarks/qlp-dilution-2026-10-13.txt
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt import mast
from tess_hunt.catalogs import normalise_toi
from tess_hunt.config import catalogs_dir
from tess_hunt.fetch import read_product

TICS = [243641947, 168936945, 22560356, 68081952, 208719443]
SECTORS = range(1, 105)
toi = normalise_toi(pd.read_csv(catalogs_dir() / "2026-10-09" / "toi.csv"))
deep = toi[
    (toi["depth_ppm"] > 3000)
    & toi["period"].between(1, 15)
    & toi["t0"].notna()
    & toi["duration"].notna()
]
deep = deep.sort_values("depth_ppm", ascending=False).drop_duplicates("tic").head(300)
products = mast.discover(TICS)
late = products[products["sector"].isin(SECTORS)]
kinds = late.groupby(["tic", "sector"])["provenance"].agg(set)
pairs = [key for key, k in kinds.items() if {"SPOC", "QLP"} <= k]
pairs = sorted(pairs)
session = requests.Session()


def series(tic, sector, provenance):
    row = late[
        (late["tic"] == tic) & (late["sector"] == sector) & (late["provenance"] == provenance)
    ].iloc[0]
    blob, _ = mast.download(row["s3_key"], int(row["size"]), session, data_uri=row["data_uri"])
    with tempfile.NamedTemporaryFile(suffix=".fits") as fh:
        fh.write(blob)
        fh.flush()
        return read_product(Path(fh.name), provenance)


def segments(time, flux, epochs, duration):
    dt, ff = [], []
    for e in epochs:
        near = np.abs(time - e) < 2.0 * duration
        t, f = time[near], flux[near]
        out = np.abs(t - e) > 0.75 * duration
        if len(t) < 20 or out.sum() < 5:
            continue
        dt.append(t - e)
        ff.append(f / np.polyval(np.polyfit(t[out] - e, f[out], 1), t - e))
    return (np.concatenate(dt), np.concatenate(ff)) if dt else (np.array([]), np.array([]))


def centre(dt, ff, duration, span_min):
    best, best_cost = 0.0, np.inf
    for s in np.arange(-span_min, span_min + 0.5, 1.0) / 1440.0:
        inside = np.abs(dt - s) < duration / 2
        if inside.sum() < 5:
            continue
        depth = 1.0 - ff[inside].mean()
        cost = np.sum((ff - np.where(inside, 1.0 - depth, 1.0)) ** 2)
        if cost < best_cost:
            best, best_cost = s, cost
    return best


def depth(dt, ff, duration):
    # Central half of the transit, so ingress and egress (and cadence smearing) don't bias it.
    inside = np.abs(dt) < duration / 4
    outside = np.abs(dt) > 0.75 * duration
    return 1.0 - np.median(ff[inside]) / np.median(ff[outside]), int(inside.sum())


measured, checked = 0, 0
for tic, sector in pairs:
    if checked >= 60:
        break
    checked += 1
    eph = deep[deep["tic"] == tic].iloc[0]
    try:
        ts, fs, _, facts = series(tic, sector, "SPOC")
    except Exception as exc:  # noqa: BLE001
        print(f"TIC {tic} S{sector}: SPOC failed ({type(exc).__name__})", file=sys.stderr)
        continue
    crowd = facts.get("crowdsap")
    if crowd is None:
        continue
    tq, fq, _, _ = series(tic, sector, "QLP")
    period, duration = eph["period"], eph["duration"]
    lo, hi = max(ts.min(), tq.min()), min(ts.max(), tq.max())
    epochs = [
        eph["t0"] + n * period
        for n in np.arange(
            np.ceil((lo - eph["t0"]) / period) - 1, np.floor((hi - eph["t0"]) / period) + 2
        )
    ]
    span = min(0.25 * period, 0.25) * 1440.0
    shift = centre(*segments(ts, fs, epochs, duration + span / 1440.0), duration, span)
    epochs = [e + shift for e in epochs if lo <= e + shift <= hi]
    ds, ns = depth(*segments(ts, fs, epochs, duration), duration)
    dq, nq = depth(*segments(tq, fq, epochs, duration), duration)
    if ns < 5 or nq < 3 or ds <= 0:
        continue
    measured += 1
    print(
        f"TIC {tic} S{sector}: SPOC CROWDSAP {crowd:.3f}; depth SPOC PDCSAP {ds * 1e6:.0f} ppm, "
        f"QLP sap_flux {dq * 1e6:.0f} ppm; QLP/SPOC {dq / ds:.3f}"
    )
print(f"checked {checked} pairs, {measured} with CROWDSAP and both depths measured")
