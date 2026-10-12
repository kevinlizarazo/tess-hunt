"""Checks on the fitted transit: is it grazing, and does its duration fit the star?"""

import numpy as np

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.fit import FitResult
from tess_hunt.transit import RHO_SUN_GCC


def shape(fit: FitResult, max_grazing_probability: float) -> CheckResult:
    # The grazing fraction of a non-empty posterior is always finite; of an empty one it is NaN,
    # which compares False against the threshold and would pass.
    if len(fit.samples) == 0:
        return inconclusive("shape", "the posterior is empty", acceptance=fit.acceptance)
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
) -> CheckResult:
    if fit.rho_prior is not None:
        raise ValueError("the density check needs a fit with a flat density prior")
    if not (rho_tic_solar is not None and np.isfinite(rho_tic_solar) and rho_tic_solar > 0):
        return inconclusive("density", "the TIC gives no stellar density")
    log_fit = fit.column("log_rho")
    lo, mid, hi = np.percentile(log_fit, [16, 50, 84])
    log_tic = float(np.log10(rho_tic_solar * RHO_SUN_GCC))
    has_error = e_rho_tic_solar is not None and np.isfinite(e_rho_tic_solar) and e_rho_tic_solar > 0
    err_tic = e_rho_tic_solar / (rho_tic_solar * np.log(10)) if has_error else default_error_dex
    tension = abs(mid - log_tic) / np.hypot((hi - lo) / 2, err_tic)
    evidence = {
        "fit_rho_gcc": float(10**mid),
        "tic_rho_gcc": float(10**log_tic),
        "fit_log_rho": float(mid),
        "fit_log_rho_sd": float((hi - lo) / 2),
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
