"""Probe for the M2 null threshold (decision 0019): which peaks of a scrambled light curve pass LEO-Vetter's
false-alarm tests?

Each case is searched as search._search_job searches a null star (search_input, detrend, search_star; search-v2,
continue_sde 9.0, masks off) for scramble seeds 1 to 5 and once unscrambled. Every emitted signal is judged as the
plan's Task 14 _leo_job judges a null signal: leo_flux on the scrambled native-cadence light curve, the star's other
signals dropped, fa_only=True.

First run at e4047f1. Run from the repo root (it reads criteria/ and tests/synthetic.py there); the two real
stars' light curves must be in the cache and the TIC query needs the network:
    nice -n 19 uv run python benchmarks/scramble_leo_probe.py --out results/benchmarks/<name>.json --workers 2
"""

import argparse
import json
import math
import multiprocessing
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import numpy as np  # noqa: E402

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT / "tests"))

from synthetic import make_lc  # noqa: E402

from tess_hunt.config import lc_dir, load_criteria  # noqa: E402
from tess_hunt.detrend import detrend, known_mask  # noqa: E402
from tess_hunt.ephemeris import Ephemeris  # noqa: E402
from tess_hunt.leo import leo_flux  # noqa: E402
from tess_hunt.lightcurve import LightCurve  # noqa: E402
from tess_hunt.scramble import scramble  # noqa: E402
from tess_hunt.search import search_input, search_star, star_params, stellar_density  # noqa: E402

HARMONICS = {"1": 1.0, "1/2": 0.5, "2": 2.0, "1/3": 1 / 3, "3": 3.0}
TOLERANCE = math.erfc(2.5 / math.sqrt(2.0))  # [match] sigma_p as a fraction of the period: 1.24%
SEEDS = [None, 1, 2, 3, 4, 5]
# test_leo.py's Sun, for the decoherence test's synthetic star (tests/test_scramble.py).
SUN = {
    "tic": 1,
    "ra": 10.0,
    "dec": -60.0,
    "rad": 1.0,
    "e_rad": 0.05,
    "mass": 1.0,
    "e_mass": 0.05,
    "teff": 5770.0,
    "e_teff": 100.0,
    "logg": 4.44,
}
SYNTHETIC = dict(noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=6)
# Periods from benchmarks/eb_control.csv and benchmarks/known_planets.csv.
REAL = {
    "TOI-188.01 EB": (280830734, 1.1619448085327084),
    "Pi Men c": (261136679, 6.267813919637232),
}


def tic_stars(tics: list[int]) -> dict[int, dict]:
    from tess_hunt.targets import query_tic_ids

    return {int(row["tic"]): row for row in query_tic_ids(tics).to_dict("records")}


def light_curve(case: dict) -> LightCurve:
    if case["sectors"]:
        return make_lc(sectors=tuple(case["sectors"]), **SYNTHETIC)
    return LightCurve.load(lc_dir() / f"{case['tic']}.npz")


def harmonic(period: float, true: float) -> str:
    for label, h in HARMONICS.items():
        if abs(period - true * h) / period < TOLERANCE:
            return label
    return ""


def judge(lc_raw, star, signal, others, seed, crit, triage) -> dict:
    """Task 14's _leo_job; seed None is the unscrambled reference."""
    exclude = known_mask(lc_raw.time, [], crit["detrend"]["known_mask_width"])
    if seed is None:
        lc, order = lc_raw, np.arange(len(lc_raw.time))
    else:
        null = crit["null"]
        lc, order = scramble(lc_raw, null["segment_gap_days"], null["placement_gap_days"], seed)
    eph = Ephemeris(signal.period, signal.t0, signal.duration, signal.depth)
    others = [Ephemeris(o.period, o.t0, o.duration) for o in others]
    started = time.perf_counter()
    try:
        result, outcome, tlc = leo_flux(
            lc, star, eph, others, exclude[order], crit["detrend"], triage, fa_only=True
        )
    except Exception as exc:  # _leo_job counts a crash as passing
        return {
            "fa": "unjudged",
            "why": f"crash {type(exc).__name__}: {exc}",
            "fa_failed": [],
            "unknown": [],
            "leo_s": time.perf_counter() - started,
            "metrics": {},
        }
    leo_s = time.perf_counter() - started
    if outcome is None:
        return {
            "fa": "unjudged",
            "why": result.reason,
            "fa_failed": [],
            "unknown": [],
            "leo_s": leo_s,
            "metrics": {},
        }
    if outcome.fa_failed:
        fa, why = "fail", ""
    elif outcome.unknown:
        fa, why = "unjudged", "unknown tests"
    else:
        fa, why = "pass", ""
    metrics = {k: float(v) for k, v in result.evidence.get("metrics", {}).items()}
    return {
        "fa": fa,
        "why": why,
        "fa_failed": outcome.fa_failed,
        "unknown": outcome.unknown,
        "leo_s": leo_s,
        "metrics": metrics,
    }


def run(job: dict) -> dict:
    case, seed, crit, triage = job["case"], job["seed"], job["crit"], job["triage"]
    lc_raw, star = light_curve(case), case["star"]
    started = time.perf_counter()
    # search._search_job, masks off.
    rstar, mstar, _ = star_params(star)
    rho = stellar_density(star, rstar, mstar)
    lc, exclude = search_input(lc_raw, [], crit, seed)
    flat = detrend(lc, crit["detrend"], exclude=exclude)
    result = search_star(flat, rstar, mstar, crit["search"], rho)
    search_s = time.perf_counter() - started
    rows = []
    for s in result.signals:
        others = [o for o in result.signals if o.rank != s.rank]
        rows.append(
            {
                "rank": s.rank,
                "period": s.period,
                "t0": s.t0,
                "duration": s.duration,
                "depth": s.depth,
                "sde": s.sde,
                "n_transits": s.n_transits,
                "harmonic": harmonic(s.period, case["period"]),
                **judge(lc_raw, star, s, others, seed, crit, triage),
            }
        )
    return {
        "case": case["name"],
        "seed": seed,
        "n_points": len(flat.time),
        "search_s": search_s,
        "diagnostics": result.diagnostics(),
        "signals": rows,
    }


def table(results: list[dict]) -> str:
    lines = [
        "| case | seed | rank | period (d) | SDE | SDE / unscr. top | harmonic | FA | failed | unknown | MES |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    tops = {
        r["case"]: r["signals"][0]["sde"] for r in results if r["seed"] is None and r["signals"]
    }
    for r in results:
        if not r["signals"]:
            lines.append(f"| {r['case']} | {r['seed'] or 'none'} | - | no signal | | | | | | | |")
        for s in r["signals"]:
            why = f" ({s['why']})" if s["why"] and s["why"] != "unknown tests" else ""
            lines.append(
                f"| {r['case']} | {r['seed'] or 'none'} | {s['rank']} | {s['period']:.5f} | {s['sde']:.2f} | "
                f"{s['sde'] / tops[r['case']]:.2f} | {s['harmonic'] or '-'} | {s['fa']}{why} | "
                f"{', '.join(s['fa_failed']) or '-'} | {', '.join(s['unknown']) or '-'} | "
                f"{s['metrics'].get('MES', float('nan')):.1f} |"
            )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--workers", type=int, default=4)
    args = ap.parse_args()
    crit = load_criteria(ROOT / "criteria" / "search-v2.toml").values
    triage = load_criteria(ROOT / "criteria" / "triage-v1.toml").values
    assert crit["search"]["continue_sde"] == 9.0
    stars = tic_stars([tic for tic, _ in REAL.values()])
    for tic, star in stars.items():
        print(
            tic,
            {
                k: star[k]
                for k in (
                    "rad",
                    "e_rad",
                    "mass",
                    "e_mass",
                    "teff",
                    "e_teff",
                    "logg",
                    "rho",
                    "e_rho",
                )
            },
            file=sys.stderr,
        )
    cases = [
        {"name": name, "tic": tic, "period": period, "star": stars[tic], "sectors": None}
        for name, (tic, period) in REAL.items()
    ] + [
        {
            "name": f"synthetic {n} sectors",
            "tic": 1,
            "period": 3.7,
            "star": SUN,
            "sectors": list(range(1, n + 1)),
        }
        for n in (8, 4)
    ]
    jobs = [
        {"case": c, "seed": seed, "crit": crit, "triage": triage} for c in cases for seed in SEEDS
    ]
    order = {
        (c["name"], seed): i for i, (c, seed) in enumerate((c, s) for c in cases for s in SEEDS)
    }
    results = []
    started = time.perf_counter()
    with ProcessPoolExecutor(args.workers, mp_context=multiprocessing.get_context("spawn")) as pool:
        futures = [pool.submit(run, job) for job in jobs]
        for future in as_completed(futures):
            r = future.result()
            results.append(r)
            print(
                f"{time.perf_counter() - started:7.0f}s {r['case']} seed {r['seed']}: search {r['search_s']:.0f}s, "
                f"{[(round(s['period'], 4), round(s['sde'], 1), s['fa']) for s in r['signals']]}",
                file=sys.stderr,
                flush=True,
            )
    results.sort(key=lambda r: order[(r["case"], r["seed"])])
    args.out.write_text(json.dumps({"stars": stars, "results": results}, indent=1, default=str))
    print(table(results))


if __name__ == "__main__":
    main()
