"""Checks on the fitted transit: is it grazing, does its duration fit the star, how big is it?"""

import numpy as np

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.fit import FitResult
from tess_hunt.transit import RHO_SUN_GCC

R_EARTH_PER_R_SUN = 109.076


def shape(fit: FitResult, max_grazing_probability: float) -> CheckResult:
    # The grazing fraction of an empty posterior is NaN, and a NaN sample counts as non-grazing; either
    # would pass.
    if len(fit.samples) == 0:
        return inconclusive("shape", "the posterior is empty", acceptance=fit.acceptance)
    if not np.isfinite(fit.samples).all():
        return inconclusive(
            "shape", "the posterior has non-finite samples", acceptance=fit.acceptance
        )
    grazing = float(np.mean(fit.column("b") + fit.column("rp_rs") > 1.0))
    evidence = {
        "grazing_probability": grazing,
        "b_median": float(np.median(fit.column("b"))),
        "rp_rs_median": float(np.median(fit.column("rp_rs"))),
        "acceptance": fit.acceptance,
    }
    if grazing > max_grazing_probability:
        return failed("shape", f"V-shaped: grazing in {grazing:.0%} of samples", **evidence)
    return passed("shape", f"U-shaped: grazing in {grazing:.0%} of samples", **evidence)


def density(
    fit: FitResult,
    rho_tic_solar: float,
    e_rho_tic_solar: float,
    max_sigma: float,
    default_error_dex: float,
    symmetric_error: bool = False,
) -> CheckResult:
    """`symmetric_error` is vet-v1's rule, half the 16th to 84th percentile spread, kept so M1's vets
    reproduce."""
    if fit.rho_prior is not None:
        raise ValueError("the density check needs a fit with a flat density prior")
    if not (rho_tic_solar is not None and np.isfinite(rho_tic_solar) and rho_tic_solar > 0):
        return inconclusive("density", "the TIC gives no stellar density")
    # A NaN sample anywhere means the fit went wrong, and a NaN tension would pass (decision 0016).
    if len(fit.samples) == 0 or not np.isfinite(fit.samples).all():
        return inconclusive(
            "density",
            "the posterior is empty or has non-finite samples",
            acceptance=fit.acceptance,
        )
    lo, mid, hi = np.percentile(fit.column("log_rho"), [16, 50, 84])
    log_tic = float(np.log10(rho_tic_solar * RHO_SUN_GCC))
    has_error = e_rho_tic_solar is not None and np.isfinite(e_rho_tic_solar) and e_rho_tic_solar > 0
    err_tic = e_rho_tic_solar / (rho_tic_solar * np.log(10)) if has_error else default_error_dex
    if symmetric_error:
        err_fit = (hi - lo) / 2
    else:
        # Log-density posteriors are skewed; the side facing the TIC value is the one that measures
        # the tension (decision 0016).
        err_fit = (mid - lo) if log_tic < mid else (hi - mid)
    tension = abs(mid - log_tic) / np.hypot(err_fit, err_tic)
    evidence = {
        "fit_rho_gcc": float(10**mid),
        "tic_rho_gcc": float(10**log_tic),
        "fit_log_rho": float(mid),
        "fit_log_rho_sd": float(err_fit),
        "fit_log_rho_minus": float(mid - lo),
        "fit_log_rho_plus": float(hi - mid),
        "tic_log_rho": log_tic,
        "tic_log_rho_sd": float(err_tic),
        "tension_sigma": float(tension),
        "acceptance": fit.acceptance,
    }
    if tension > max_sigma:
        return failed(
            "density",
            f"transit implies {10**mid:.3g} g/cm3, the TIC gives {10**log_tic:.3g} ({tension:.1f} sigma)",
            **evidence,
        )
    return passed("density", f"transit and TIC densities agree ({tension:.1f} sigma)", **evidence)


def radius(fit: FitResult, rad_tic_solar: float | None, max_rearth: float) -> CheckResult:
    if not (rad_tic_solar is not None and np.isfinite(rad_tic_solar) and rad_tic_solar > 0):
        return inconclusive("radius", "the TIC gives no stellar radius")
    rp_rs = fit.column("rp_rs")
    if len(rp_rs) == 0 or not np.isfinite(rp_rs).all():
        return inconclusive("radius", "the Rp/R* posterior is empty or has non-finite samples")
    median = float(np.median(rp_rs))
    rp = median * rad_tic_solar * R_EARTH_PER_R_SUN
    evidence = {"rp_rearth": rp, "rp_rs_median": median, "rad_tic": float(rad_tic_solar)}
    if rp > max_rearth:
        return failed("radius", f"{rp:.1f} Earth radii, above {max_rearth:g}", **evidence)
    return passed("radius", f"{rp:.1f} Earth radii", **evidence)
