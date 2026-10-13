"""LEO-Vetter's flux-level tests (Kunimoto et al. 2025, arXiv 2509.10619) in the paper's configuration,
with outcomes that never let a missing metric pass."""

import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field

import numpy as np
from leo_vetter import thresholds as lt
from leo_vetter.main import TCELightCurve
from leo_vetter.stellar import quadratic_ldc

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve

Inputs = Callable[[dict], list[str]]

# Each test with the metrics its comparison reads. LEO-Vetter compares metrics directly and a NaN compares
# False, so a test that reads a non-finite metric has not passed, it is unknown. NaNs a test handles itself
# are left out: transit_aic in bad_fit, sig_sec in unphysical_duration, sig_ter and sig_pos in secondary.
# So are secondary's planet-like escape (Rp, albedo, dep_sec, dep, transit_b): a NaN there can only make
# the test fire, and albedo is NaN whenever no secondary is seen.
FA_TESTS: list[tuple[str, Callable, Inputs]] = [
    ("weak", lt.weak, lambda m: ["MES"]),
    ("invalid_transits", lt.invalid_transits, lambda m: ["new_MES", "new_N_transit"]),
    ("bad_shape", lt.bad_shape, lambda m: ["SHP"]),
    (
        "non_unique",
        lt.non_unique,
        lambda m: ["sig_pri", "Fred", "FA1", "sig_ter", "FA2", "sig_pos"],
    ),
    (
        "chases",
        lt.chases,
        lambda m: ["N_transit"] + (["mean_chases"] if m["N_transit"] <= 5 else []),
    ),
    ("dmm", lt.dmm, lambda m: ["DMM"]),
    (
        "single_event",
        lt.single_event,
        lambda m: ["N_transit"] + (["max_SES", "MES"] if m["N_transit"] <= 10 else []),
    ),
    (
        "bad_fit",
        lt.bad_fit,
        lambda m: (
            ["N_transit"]
            + ([] if np.isnan(m["transit_aic"]) else ["transit_chisqr", "line_chisqr", "line_aic"])
        ),
    ),
    ("sinusoidal", lt.sinusoidal, lambda m: ["per"] + (["sine_sig"] if m["per"] < 10 else [])),
    (
        "unphysical_duration",
        lt.unphysical_duration,
        lambda m: ["transit_aRs", "aRs", "q", "trap_qtran"],
    ),
    (
        "asymmetric",
        lt.asymmetric,
        lambda m: [
            "trap_qtran_left",
            "trap_qtran_right",
            "trap_qtran_err_left",
            "trap_qtran_err_right",
        ],
    ),
    ("chi", lt.chi, lambda m: ["CHI"]),
    ("data_gapped", lt.data_gapped, lambda m: ["N_gap_2.0", "N_transit"]),
]
FP_TESTS: list[tuple[str, Callable, Inputs]] = [
    (
        "odd_even",
        lt.odd_even,
        lambda m: (
            ["sig_dep", "trap_sig_epo", "transit_sig_epo"]
            + (["trap_sig_dep", "transit_sig_dep"] if m["sig_dep"] > 3 else [])
        ),
    ),
    ("vshaped", lt.vshaped, lambda m: ["transit_b", "transit_RpRs"]),
    ("large", lt.large, lambda m: ["Rp"]),
    ("secondary", lt.secondary, lambda m: ["sig_sec", "Fred", "FA1", "FA2"]),
]


@dataclass(frozen=True)
class LeoOutcome:
    disposition: str | None
    fa_failed: list[str] = field(default_factory=list)
    fp_failed: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)

    @property
    def passes_fa(self) -> bool:
        return not self.fa_failed


def _finite(value) -> bool:
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _run(tests, metrics: dict, thresholds: dict) -> tuple[list[str], list[str]]:
    fails, unknown = [], []
    for name, test, inputs in tests:
        try:
            needed = inputs(metrics)
            flag, _ = test(metrics, thresholds)
        except (KeyError, TypeError, ValueError, ZeroDivisionError) as exc:
            unknown.append(f"{name}: {type(exc).__name__}")
            continue
        if bool(flag):
            fails.append(name)
        elif not all(_finite(metrics[k]) for k in needed):
            unknown.append(name)
    return fails, unknown


def evaluate(metrics: dict, thresholds: dict, fa_only: bool = False) -> LeoOutcome:
    fa_failed, fa_unknown = _run(FA_TESTS, metrics, thresholds)
    if fa_failed:
        return LeoOutcome("FA", fa_failed, [], fa_unknown)
    if fa_only:
        return LeoOutcome(None if fa_unknown else "PC", [], [], fa_unknown)
    fp_failed, fp_unknown = _run(FP_TESTS, metrics, thresholds)
    unknown = fa_unknown + fp_unknown
    if fp_failed:
        return LeoOutcome("FP", [], fp_failed, unknown)
    return LeoOutcome(None if unknown else "PC", [], [], unknown)


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def leo_star(star: Mapping, cfg_metrics: dict) -> dict | None:
    """LEO-Vetter's star from TIC values; None when a value it cannot do without is missing."""
    rad, mass, teff, logg = (_number(star.get(k)) for k in ("rad", "mass", "teff", "logg"))
    if not (np.isfinite([rad, mass, teff, logg]).all() and rad > 0 and mass > 0):
        return None
    u1, u2 = (float(u) for u in quadratic_ldc(teff, logg))
    if not np.isfinite([u1, u2]).all():
        return None

    def error(key: str, fallback: float) -> float:
        value = _number(star.get(key))
        return value if np.isfinite(value) and value > 0 else fallback

    e_rad = error("e_rad", cfg_metrics["default_e_rad_fraction"] * rad)
    e_mass = error("e_mass", cfg_metrics["default_e_mass_fraction"] * mass)
    rho, e_rho = _number(star.get("rho")), _number(star.get("e_rho"))
    # The TIC density goes in only with its own error; otherwise both come from the mass and radius.
    if not (np.isfinite([rho, e_rho]).all() and rho > 0 and e_rho > 0):
        rho = mass / rad**3
        e_rho = rho * float(np.hypot(e_mass / mass, 3 * e_rad / rad))
    return {
        "tic": int(star["tic"]),
        "ra": _number(star.get("ra")),
        "dec": _number(star.get("dec")),
        "rad": rad,
        "e_rad": e_rad,
        "mass": mass,
        "e_mass": e_mass,
        "Teff": teff,
        "e_Teff": error("e_teff", cfg_metrics["default_e_teff"]),
        "logg": logg,
        "rho": rho,
        "e_rho": e_rho,
        "u1": u1,
        "u2": u2,
    }


def prepare(
    lc: LightCurve,
    eph: Ephemeris,
    others: list[Ephemeris],
    known_exclude: np.ndarray,
    crit_detrend: dict,
    hold_width: float,
) -> LightCurve:
    """Native cadence, re-detrended with this signal's transits held out of the trend (the paper re-detrends
    with each TCE masked) and the star's other signals and known objects dropped."""
    drop = known_exclude.copy()
    for other in others:
        drop |= in_transit(lc.time, other, hold_width)
    return detrend(lc, crit_detrend, exclude=drop, hold_out=in_transit(lc.time, eph, hold_width))


def leo_flux(
    lc_raw: LightCurve,
    star: Mapping,
    eph: Ephemeris,
    others: list[Ephemeris],
    known_exclude: np.ndarray,
    crit_detrend: dict,
    crit_triage: dict,
    fa_only: bool = False,
) -> tuple[CheckResult, LeoOutcome | None, TCELightCurve | None]:
    cfg = crit_triage["leo_metrics"]
    params = leo_star(star, cfg)
    if params is None:
        # Star records carry pd.NA, which the evidence's JSON cannot hold.
        missing = {k: _number(star.get(k)) for k in ("rad", "mass", "teff", "logg")}
        return (
            inconclusive("leo_flux", "a stellar value LEO-Vetter needs is missing", star=missing),
            None,
            None,
        )
    started = time.perf_counter()
    try:
        flat = prepare(lc_raw, eph, others, known_exclude, crit_detrend, cfg["hold_out_durations"])
        if len(flat.time) == 0:
            return inconclusive("leo_flux", "no cadences left after detrending"), None, None
        # LEO-Vetter's averaging windows can be empty; evaluate() judges the NaNs they leave.
        with np.errstate(divide="ignore", invalid="ignore"):
            tlc = TCELightCurve(
                params["tic"],
                flat.time,
                flat.flux,
                flat.flux,
                flat.flux_err,
                eph.period,
                eph.t0,
                eph.duration,
            )
            tlc.compute_flux_metrics(
                params,
                verbose=False,
                cap_b=cfg["cap_b"],
                max_RpRs=cfg["max_RpRs"],
                frac=cfg["frac"],
                gap=cfg["gap"],
                chases=cfg["chases"],
                rubble=cfg["rubble"],
                redchi2=cfg["redchi2"],
                A=cfg["A"],
            )
    except Exception as exc:
        # LEO-Vetter's fits can raise on an odd light curve; that is not a pass.
        return (
            inconclusive("leo_flux", f"LEO-Vetter raised {type(exc).__name__}: {exc}"),
            None,
            None,
        )
    outcome = evaluate(tlc.metrics, crit_triage["leo"], fa_only=fa_only)
    evidence = {
        "disposition": outcome.disposition,
        "fa_only": fa_only,
        "fa_failed": outcome.fa_failed,
        "fp_failed": outcome.fp_failed,
        "unknown": outcome.unknown,
        "n_points": len(flat.time),
        "runtime_s": time.perf_counter() - started,
        "metrics": {
            k: v
            for k, v in tlc.metrics.items()
            if isinstance(v, (int, float, np.integer, np.floating))
        },
    }
    if outcome.disposition in ("FA", "FP"):
        failing = outcome.fa_failed + outcome.fp_failed
        return (
            failed("leo_flux", f"{outcome.disposition}: {', '.join(failing)}", **evidence),
            outcome,
            tlc,
        )
    if outcome.disposition is None:
        return (
            inconclusive("leo_flux", f"tests not judged: {', '.join(outcome.unknown)}", **evidence),
            outcome,
            tlc,
        )
    return passed("leo_flux", "planet candidate at flux level", **evidence), outcome, tlc
