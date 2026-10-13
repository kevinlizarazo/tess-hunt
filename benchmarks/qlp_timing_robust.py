"""QLP minus SPOC 2-min transit mid-times in S99 to S104, with every reference time taken from the sector's own SPOC
data, so the TOI ephemeris only seeds the search and its drift can't enter the offsets.

Usage: uv run python benchmarks/qlp_timing_robust.py > results/benchmarks/qlp-timing-robust-2026-10-13.txt
"""

import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from astroquery.mast import Observations

from tess_hunt import mast
from tess_hunt.catalogs import normalise_toi
from tess_hunt.config import catalogs_dir
from tess_hunt.fetch import read_product

SECTORS = range(99, 105)
SPAN = 60.0  # minutes searched either side of the guess, for SPOC and for QLP alike
RELIABLE_SIGMA = 5.0  # minutes, predicted single-transit uncertainty of QLP minus SPOC
PER_SECTOR_RELIABLE = 4
PER_SECTOR_MAX = 7  # 6 sectors x 7 caps the run near 40 pairs
CANDIDATES_PER_SECTOR = 40

raw = pd.read_csv(catalogs_dir() / "2026-10-09" / "toi.csv")
toi = normalise_toi(raw).assign(tmag=pd.to_numeric(raw["TESS Mag"], errors="coerce").to_numpy())
toi = toi[
    (toi["depth_ppm"] > 1500)
    & toi["period"].between(0.5, 8)  # at least 3 transits in a sector
    & toi["t0"].notna()
    & (toi["duration"] > 0)
    & toi["tmag"].notna()
]
toi = toi.sort_values("depth_ppm", ascending=False).drop_duplicates("tic")
# Ranking proxy for single-transit timing precision: noise grows ~0.3 dex per magnitude here.
toi = toi.assign(
    rank=10 ** (0.3 * toi["tmag"]) / toi["depth_ppm"] * np.sqrt(toi["duration"])
).sort_values("rank")

candidates = {}
for sector in SECTORS:
    obs = Observations.query_criteria(
        obs_collection="TESS",
        dataproduct_type="timeseries",
        sequence_number=sector,
        provenance_name="SPOC",
    )
    two_min = {int(t) for t in obs["target_name"]}
    candidates[sector] = [int(t) for t in toi["tic"] if int(t) in two_min][:CANDIDATES_PER_SECTOR]
    print(
        f"S{sector}: {len(two_min)} SPOC targets, {sum(int(t) in two_min for t in toi['tic'])} usable TOIs",
        file=sys.stderr,
    )

products = mast.discover(sorted({t for tics in candidates.values() for t in tics}))
session = requests.Session()


def series(tic, sector, provenance):
    row = products[
        (products["tic"] == tic)
        & (products["sector"] == sector)
        & (products["provenance"] == provenance)
    ].iloc[0]
    blob, _ = mast.download(row["s3_key"], int(row["size"]), session, data_uri=row["data_uri"])
    with tempfile.NamedTemporaryFile(suffix=".fits") as fh:
        fh.write(blob)
        fh.flush()
        time, flux, _, _ = read_product(Path(fh.name), provenance)
    return time, flux


def mid_time(time, flux, guess, duration, span=SPAN):
    """The plan's box fit (local line through out-of-transit points, 0.25 min grid), with the depth fitted rather
    than fixed and the grid widened to +-span. NaN unless both edges and both baselines are covered and the best
    centre is off the grid's ends. Returns (mid-time, fitted depth)."""
    pad = span / 1440.0
    near = np.abs(time - guess) < duration / 2 + pad + duration
    t, f = time[near], flux[near]
    out = np.abs(t - guess) > duration / 2 + pad
    if (out & (t < guess)).sum() < 5 or (out & (t > guess)).sum() < 5:
        return np.nan, np.nan
    f = f / np.polyval(np.polyfit(t[out] - guess, f[out], 1), t - guess)
    shifts = np.arange(-span, span + 0.01, 0.25) / 1440.0
    best, best_cost, best_depth = np.nan, np.inf, np.nan
    for s in shifts:
        box = np.abs(t - guess - s) < duration / 2
        if box.sum() < 3:
            continue
        depth = 1.0 - f[box].mean()
        cost = np.sum((f - np.where(box, 1.0 - depth, 1.0)) ** 2)
        if cost < best_cost:
            best, best_cost, best_depth = s, cost, depth
    if not np.isfinite(best) or abs(best) * 1440.0 > span - 1.0:
        return np.nan, np.nan
    centre = guess + best
    edge = max(0.15 * duration, 2.5 * np.median(np.diff(t)))
    for side in (-1, 1):
        if (np.abs(t - (centre + side * duration / 2)) < edge).sum() < 2:
            return np.nan, np.nan
    return centre, best_depth


def fold_shift(time, flux, epochs, duration, span_min):
    """Common shift (minutes) of all transits in the sector from a box fit to the folded SPOC data."""
    dt, ff = [], []
    window = duration / 2 + span_min / 1440.0
    for e in epochs:
        near = np.abs(time - e) < window + duration
        t, f = time[near], flux[near]
        out = np.abs(t - e) > window
        if len(t) < 20 or out.sum() < 5:
            continue
        dt.append(t - e)
        ff.append(f / np.polyval(np.polyfit(t[out] - e, f[out], 1), t - e))
    if not dt:
        return np.nan
    dt, ff = np.concatenate(dt), np.concatenate(ff)
    best, best_cost = np.nan, np.inf
    for s in np.arange(-span_min, span_min + 0.5, 1.0) / 1440.0:
        box = np.abs(dt - s) < duration / 2
        if box.sum() < 5:
            continue
        depth = 1.0 - ff[box].mean()
        cost = np.sum((ff - np.where(box, 1.0 - depth, 1.0)) ** 2)
        if cost < best_cost:
            best, best_cost = s * 1440.0, cost
    return best


def point_scatter(flux):
    return 1.4826 * np.median(np.abs(np.diff(flux))) / np.sqrt(2)


def timing_sigma(flux, time, depth, duration):
    """Carter et al. (2008) single-transit mid-time uncertainty, sigma/depth * sqrt(tau * cadence / 2), with the
    ingress tau set to its largest value, half the duration (a V shape), so the estimate is conservative. Minutes."""
    if not np.isfinite(depth) or depth <= 0:
        return np.inf
    cadence = np.median(np.diff(time))
    return point_scatter(flux) / depth * np.sqrt(duration * cadence) / 2 * 1440.0


def measure(tic, sector, other=None, shift_min=0.0):
    """Per-transit QLP minus SPOC (or SPOC minus SPOC, shifted, for the checks)."""
    eph = toi[toi["tic"] == tic].iloc[0]
    period, duration = eph["period"], eph["duration"]
    ts, fs = series(tic, sector, "SPOC")
    tq, fq = other if other is not None else series(tic, sector, "QLP")
    tq = tq + shift_min / 1440.0
    lo, hi = max(ts.min(), tq.min()), min(ts.max(), tq.max())
    n = np.arange(np.ceil((lo - eph["t0"]) / period) - 1, np.floor((hi - eph["t0"]) / period) + 2)
    epochs = eph["t0"] + n * period
    drift = fold_shift(ts, fs, epochs, duration, min(0.25 * period, 0.25) * 1440.0)
    if not np.isfinite(drift):
        return None
    offsets, depth_s, depth_q = [], [], []
    for guess in epochs + drift / 1440.0:
        if not lo <= guess <= hi:
            continue
        a, da = mid_time(ts, fs, guess, duration)
        if not np.isfinite(a):
            continue
        b, db = mid_time(tq, fq, a, duration)
        if np.isfinite(b):
            offsets.append((b - a) * 1440.0)
            depth_s.append(da)
            depth_q.append(db)
    if not offsets:
        return None
    sigma = np.hypot(
        timing_sigma(fs, ts, np.median(depth_s), duration),
        timing_sigma(fq, tq, np.median(depth_q), duration),
    )
    return {
        "tic": tic,
        "sector": sector,
        "tmag": eph["tmag"],
        "drift": drift,
        "offsets": offsets,
        "median": float(np.median(offsets)),
        "spread": float(np.std(offsets)),
        "sigma": float(sigma),
        "reliable": bool(sigma <= RELIABLE_SIGMA and len(offsets) >= 3),
        "spoc": (ts, fs),
    }


results = []
for sector in SECTORS:
    reliable = measured = 0
    for tic in candidates[sector]:
        if reliable >= PER_SECTOR_RELIABLE or measured >= PER_SECTOR_MAX:
            break
        kinds = set(
            products[(products["tic"] == tic) & (products["sector"] == sector)]["provenance"]
        )
        if not {"SPOC", "QLP"} <= kinds:
            continue
        try:
            r = measure(tic, sector)
        except Exception as exc:  # noqa: BLE001
            print(f"TIC {tic} S{sector}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if r is None:
            continue
        measured += 1
        reliable += r["reliable"]
        results.append(r)

print(
    "Rule: reliable when the predicted single-transit uncertainty of QLP minus SPOC is at most 5.0 min and there are"
)
print(
    "at least 3 transits. Prediction per pipeline: Carter et al. (2008), sigma_pt/depth * sqrt(tau * cadence / 2),"
)
print(
    "with tau = duration / 2 (the V-shape maximum, conservative); sigma_pt is the sector's point-to-point scatter"
)
print("and depth the median fitted box depth; the two pipelines are added in quadrature.")
print("Reference times are SPOC's own per-transit fits; the TOI ephemeris only seeds the search.\n")
print("Per pair")
for r in results:
    flag = "reliable" if r["reliable"] else "UNRELIABLE"
    print(
        f"TIC {r['tic']} S{r['sector']} (Tmag {r['tmag']:.1f}, TOI epoch drift {r['drift']:+.0f} min): "
        f"QLP minus SPOC {r['median']:+.2f} min over {len(r['offsets'])} transits (spread {r['spread']:.2f}, "
        f"predicted sigma {r['sigma']:.2f}) {flag}"
    )
    print(f"    each: {', '.join(f'{o:+.2f}' for o in r['offsets'])}")

print("\nPer sector (reliable pairs only)")
over = []
for sector in SECTORS:
    good = [r for r in results if r["sector"] == sector and r["reliable"]]
    total = sum(r["sector"] == sector for r in results)
    if good:
        medians = [r["median"] for r in good]
        worst = max(medians, key=abs)
        over += [m for m in medians if abs(m) > 10]
        print(
            f"S{sector}: {len(good)} reliable of {total} measured; median of medians {np.median(medians):+.2f} min; "
            f"largest absolute {worst:+.2f} min"
        )
    else:
        print(f"S{sector}: 0 reliable of {total} measured")
print(f"\nReliable medians above 10 min: {len(over)}")

check = next((r for r in results if r["reliable"]), None)
if check:
    tic, sector = check["tic"], check["sector"]
    print(f"\nChecks on TIC {tic} S{sector}")
    zero = measure(tic, sector, other=check["spoc"])
    print(
        f"SPOC against SPOC: {zero['median']:+.2f} min over {len(zero['offsets'])} transits (spread {zero['spread']:.2f})"
    )
    five = measure(tic, sector, other=check["spoc"], shift_min=5.0)
    print(
        f"SPOC against SPOC shifted +5.00 min: {five['median']:+.2f} min over {len(five['offsets'])} transits (spread {five['spread']:.2f})"
    )
