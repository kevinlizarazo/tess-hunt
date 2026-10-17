"""Vet: run every check on one signal and write the evidence."""

import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path

import numpy as np
import pandas as pd

from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs
from tess_hunt.checks import CheckResult, Outcome, inconclusive
from tess_hunt.checks.families import good_timestamps, per_family, split
from tess_hunt.checks.holdout import holdout
from tess_hunt.checks.photometry import (
    odd_even,
    red_noise_beta,
    secondary,
    sector_depths,
    signal_present,
    with_red_noise,
)
from tess_hunt.checks.physical import density, radius, shape
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.fit import FitResult, fit_transit
from tess_hunt.lightcurve import LightCurve
from tess_hunt.novelty import check_novelty
from tess_hunt.provenance import start_run

# vet-v1 left these to the code (docs/decisions/0014-vet-constants-in-criteria.md). A vet-v1 file gets
# them back, so M1's vets reproduce.
VET_V1_CODE_VALUES = {
    "red_noise": {
        "exclude_width": 3.0,
        "min_bins": 20,
        "kept_bin_fraction": 0.8,
        "min_cadences_per_bin": 3.0,
    },
    "holdout": {
        "refit_resolutions": 5.0,
        "refit_points": 801,
        "refit_duration_factors": [0.75, 1.0, 1.25],
    },
    "fit": {"min_points": 20, "min_acceptance": 0.01, "max_rp_rs": 0.5},
    "novelty": {"inconclusive_kinds": []},
}


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def with_v1_code_values(crit_vet: dict) -> dict:
    """vet-v1 in vet-v2's layout: the values its code held, and its fit window under the new name."""
    out = {name: dict(section) for name, section in crit_vet.items()}
    for name, values in VET_V1_CODE_VALUES.items():
        # The code's value would win the merge and the file's would be dropped without a word.
        clash = sorted(set(values) & set(out.get(name, {})))
        if clash:
            raise ValueError(
                f"vet-v1 criteria (fit.window_durations) set [{name}] {', '.join(clash)}, "
                "which vet-v1 took from its code"
            )
        out[name] = {**out.get(name, {}), **values}
    out["fit"]["window_half_width_durations"] = out["fit"].pop("window_durations")
    return out


def other_known_transits(
    eph: Ephemeris,
    known: pd.DataFrame,
    tic: int,
    harmonics: tuple[float, ...],
    crit_search: dict,
    sources: tuple[str, ...] | None = None,
) -> list[Ephemeris]:
    """The star's known transits to mask before vetting: every one except the signal under test,
    from `sources` only when given."""
    match = crit_search["match"]
    fallback = crit_search["detrend"]["fallback_duration_days"]
    # Matching on period alone, as novelty does for the star's own rows: a stale catalog epoch can
    # sit out of phase with a rediscovery yet close enough that its mask cuts the transits under
    # test (docs/decisions/0003-novelty-stale-ephemerides.md). A full match is also a period match.
    return [
        k
        for k in known_ephemerides(known, tic, fallback, sources)
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
    include_suspect: bool = False,
) -> tuple[dict, FitResult | None]:
    """`include_suspect` keeps vet-v3's timing-suspect sectors in, for an evidence-only vet that never
    makes the call (docs/decisions/0022-vet-without-timing-suspect-sectors.md)."""
    tic = int(star["tic"])
    # Only vet-v1 names the fit window `window_durations` (docs/decisions/0015-fit-window-half-width.md).
    v1 = "window_durations" in crit_vet["fit"]
    if v1:
        crit_vet = with_v1_code_values(crit_vet)
    # vet-v3 is the criteria with a [families] section; under vet-v1 and vet-v2 none of its rules run.
    families = crit_vet.get("families")
    v3 = families is not None
    harmonics = tuple(crit_vet["novelty"]["harmonics"])
    match = crit_search["match"]
    mask_sources = tuple(crit_vet["masks"]["sources"]) if v3 else None
    others = other_known_transits(eph, known, tic, harmonics, crit_search, mask_sources)
    dropped = []
    if v3 and crit_vet["timing"]["exclude_timing_suspect"] and not include_suspect:
        good = good_timestamps(lc)
        dropped = sorted(set(np.unique(lc.sector).tolist()) - set(np.unique(good.sector).tolist()))
        lc = good
    flat = detrend(lc, crit_search["detrend"], others)
    core = crit_vet["depth"]["core_fraction"]
    # Detrended errors are each sector's white scatter, but a bright star's residuals stay
    # correlated over a transit, so depth errors would come out too small. The depth checks get
    # errors scaled by each sector's time-averaging beta at the core timescale (Pont et al. 2006;
    # Winn et al. 2008; docs/decisions/0006-red-noise-depth-errors.md). The fit keeps white errors.
    betas = red_noise_beta(flat, eph, core * eph.duration, crit_vet["red_noise"])
    noisy = with_red_noise(flat, betas)

    def depths_compared(check: str, run: Callable[[LightCurve], CheckResult]) -> CheckResult:
        # QLP depths are diluted on crowded stars, so vet-v3 compares depths only within one product
        # family (docs/decisions/0023-product-families.md).
        if not v3:
            return run(noisy)
        return per_family(check, {name: run(part) for name, part in split(noisy, families).items()})

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
            tuple(crit_vet["novelty"]["inconclusive_kinds"]),
        ),
        depths_compared(
            "odd_even",
            lambda part: odd_even(
                part,
                eph,
                core,
                crit_vet["odd_even"]["max_sigma"],
                crit_vet["odd_even"]["min_points"],
            ),
        ),
        secondary(
            noisy, eph, crit_vet["secondary"]["max_sigma"], crit_vet["secondary"]["min_points"]
        ),
        depths_compared(
            "sector_depth",
            lambda part: sector_depths(
                part,
                eph,
                core,
                crit_vet["sector_depth"]["min_p_value"],
                crit_vet["sector_depth"]["min_points"],
            ),
        ),
        holdout(noisy, eph, crit_vet["holdout"], core, families),
    ]
    # vet-v1 has neither section, so M1's vets keep their seven checks (decisions 0017 and 0018).
    if "signal_present" in crit_vet:
        results.append(
            signal_present(
                noisy,
                eph,
                core,
                crit_vet["signal_present"]["min_snr"],
                crit_vet["signal_present"]["min_points"],
            )
        )
    with_radius = "radius" in crit_vet
    parts = split(flat, families) if v3 else None
    # vet-v3 fits one family alone: a diluted depth would bias Rp/R* and with it b and the density.
    fit_lc = parts.get(families["fit"]) if v3 else flat
    fit, no_fit = None, None
    if fit_lc is None:
        no_fit = f"no {families['fit']} data to fit"
    else:
        try:
            fit = fit_transit(fit_lc, eph, crit_vet["fit"], rho_prior=None, seed=seed)
        except ValueError as exc:
            no_fit = f"no fit: {exc}"
    if no_fit is not None:
        results += [inconclusive("shape", no_fit), inconclusive("density", no_fit)]
        if with_radius:
            results.append(inconclusive("radius", no_fit))
    if fit is not None:
        results += [
            shape(fit, crit_vet["shape"]["max_grazing_probability"]),
            density(
                fit,
                star.get("rho"),
                star.get("e_rho"),
                crit_vet["density"]["max_sigma"],
                crit_vet["density"]["default_log_rho_error"],
                symmetric_error=v1,
            ),
        ]
        if with_radius:
            results.append(radius(fit, _number(star.get("rad")), crit_vet["radius"]["max_rearth"]))
    report = {
        "tic": tic,
        "ephemeris": asdict(eph),
        "masked": [asdict(k) for k in others],
        "red_noise": betas,
        "checks": [r.to_dict() for r in results],
        "fit": fit.summary() if fit else None,
        "advances": all(r.outcome is Outcome.PASS for r in results),
    }
    if v3:
        report.update(
            criteria_version="vet-v3",
            evidence_only=include_suspect,
            families={name: np.unique(part.sector).tolist() for name, part in parts.items()},
            dropped_suspect=dropped,
        )
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
    p.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    p.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v2.toml"))
    p.add_argument("--production", action="store_true")
    p.set_defaults(func=cmd)


def cmd(args) -> int:
    # A BJD would fold the light curve at an epoch thousands of years away, and vet would run anyway.
    if not -20000 < args.t0 < 10000:
        raise SystemExit(f"--t0 {args.t0} is not a BTJD (BJD - 2457000)")
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Checked before the run starts, so a refusal leaves no unfinished run directory.
    stars = pd.read_parquet(args.targets)
    star = stars[stars["tic"] == args.tic].to_dict("records")
    if not star:
        raise SystemExit(f"TIC {args.tic} is not in {args.targets.name}")
    lc_path = lc_dir() / f"{args.tic}.npz"
    if not lc_path.exists():
        raise SystemExit(f"no light curve for TIC {args.tic}; fetch it first")
    run = start_run("vet", [crit_search, crit_vet], args.production, sys.argv)
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
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
        print(f"{c['check']:14s} {c['outcome']:13s} {c['reason']}")
    print(f"advances: {report['advances']} -> {run.path}")
    run.finish(
        advances=report["advances"], outcomes={c["check"]: c["outcome"] for c in report["checks"]}
    )
    return 0
