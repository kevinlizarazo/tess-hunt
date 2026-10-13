"""Vet: run every check on one signal and write the evidence."""

import sys
from collections.abc import Mapping
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs
from tess_hunt.checks import Outcome, inconclusive
from tess_hunt.checks.holdout import holdout
from tess_hunt.checks.photometry import (
    odd_even,
    red_noise_beta,
    secondary,
    sector_depths,
    with_red_noise,
)
from tess_hunt.checks.physical import density, shape
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.fit import FitResult, fit_transit
from tess_hunt.lightcurve import LightCurve
from tess_hunt.novelty import check_novelty
from tess_hunt.provenance import start_run


def other_known_transits(
    eph: Ephemeris,
    known: pd.DataFrame,
    tic: int,
    harmonics: tuple[float, ...],
    crit_search: dict,
) -> list[Ephemeris]:
    """The star's known transits to mask before vetting: every one except the signal under test."""
    match = crit_search["match"]
    fallback = crit_search["detrend"]["fallback_duration_days"]
    # Matching on period alone, as novelty does for the star's own rows: a stale catalog epoch can
    # sit out of phase with a rediscovery yet close enough that its mask cuts the transits under
    # test (docs/decisions/0003-novelty-stale-ephemerides.md). A full match is also a period match.
    return [
        k
        for k in known_ephemerides(known, tic, fallback)
        if ephemeris_match(
            eph, replace(k, t0=float("nan")), harmonics, match["sigma_p"], match["sigma_t"]
        )
        is None
    ]


def vet_signal(
    lc: LightCurve,
    star: Mapping,
    eph: Ephemeris,
    known: pd.DataFrame,
    crit_search: dict,
    crit_vet: dict,
    seed: int | None,
) -> tuple[dict, FitResult | None]:
    tic = int(star["tic"])
    harmonics = tuple(crit_vet["novelty"]["harmonics"])
    match = crit_search["match"]
    others = other_known_transits(eph, known, tic, harmonics, crit_search)
    flat = detrend(lc, crit_search["detrend"], others)
    core = crit_vet["depth"]["core_fraction"]
    # Detrended errors are each sector's white scatter, but a bright star's residuals stay
    # correlated over a transit, so depth errors would come out too small. The depth checks get
    # errors scaled by each sector's time-averaging beta at the core timescale (Pont et al. 2006;
    # Winn et al. 2008; docs/decisions/0006-red-noise-depth-errors.md). The fit keeps white errors.
    betas = red_noise_beta(flat, eph, core * eph.duration)
    noisy = with_red_noise(flat, betas)
    results = [
        check_novelty(
            tic,
            float(star["ra"]),
            float(star["dec"]),
            eph,
            known,
            crit_vet["novelty"]["neighbour_arcmin"],
            harmonics,
            match["sigma_p"],
            match["sigma_t"],
        ),
        odd_even(
            noisy, eph, core, crit_vet["odd_even"]["max_sigma"], crit_vet["odd_even"]["min_points"]
        ),
        secondary(
            noisy, eph, crit_vet["secondary"]["max_sigma"], crit_vet["secondary"]["min_points"]
        ),
        sector_depths(
            noisy,
            eph,
            core,
            crit_vet["sector_depth"]["min_p_value"],
            crit_vet["sector_depth"]["min_points"],
        ),
        holdout(noisy, eph, crit_vet["holdout"], core),
    ]
    fit = None
    try:
        fit = fit_transit(flat, eph, crit_vet["fit"], rho_prior=None, seed=seed)
    except ValueError as exc:
        results += [
            inconclusive("shape", f"no fit: {exc}"),
            inconclusive("density", f"no fit: {exc}"),
        ]
    if fit is not None:
        results += [
            shape(fit, crit_vet["shape"]["max_grazing_probability"]),
            density(
                fit,
                star.get("rho"),
                star.get("e_rho"),
                crit_vet["density"]["max_sigma"],
                crit_vet["density"]["default_log_rho_error"],
            ),
        ]
    report = {
        "tic": tic,
        "ephemeris": asdict(eph),
        "masked": [asdict(k) for k in others],
        "red_noise": betas,
        "checks": [r.to_dict() for r in results],
        "fit": fit.summary() if fit else None,
        "advances": all(r.outcome is Outcome.PASS for r in results),
    }
    return report, fit


def add_parser(sub) -> None:
    p = sub.add_parser("vet", help="run every check on one signal")
    p.add_argument("--tic", type=int, required=True)
    p.add_argument("--period", type=float, required=True)
    p.add_argument("--t0", type=float, required=True, help="BTJD")
    p.add_argument("--duration", type=float, required=True, help="days")
    p.add_argument("--depth", type=float, default=float("nan"), help="fractional")
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument("--catalogs", type=Path, required=True)
    p.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v1.toml"))
    p.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v1.toml"))
    p.add_argument("--production", action="store_true")
    p.set_defaults(func=cmd)


def cmd(args) -> int:
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    run = start_run("vet", [crit_search, crit_vet], args.production, sys.argv)
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    stars = pd.read_parquet(args.targets)
    star = stars[stars["tic"] == args.tic].to_dict("records")
    if not star:
        raise SystemExit(f"TIC {args.tic} is not in {args.targets.name}")
    lc_path = lc_dir() / f"{args.tic}.npz"
    run.record_input("light_curve", lc_path)
    eph = Ephemeris(args.period, args.t0, args.duration, args.depth)
    report, fit = vet_signal(
        LightCurve.load(lc_path),
        star[0],
        eph,
        load_known(args.catalogs),
        crit_search.values,
        crit_vet.values,
        crit_vet["fit"]["seed"],
    )
    run.write_json("checks.json", report)
    if fit is not None:
        np.savez_compressed(run.path / "fit_samples.npz", samples=fit.samples)
    for c in report["checks"]:
        print(f"{c['check']:13s} {c['outcome']:13s} {c['reason']}")
    print(f"advances: {report['advances']} -> {run.path}")
    run.finish(
        advances=report["advances"], outcomes={c["check"]: c["outcome"] for c in report["checks"]}
    )
    return 0
