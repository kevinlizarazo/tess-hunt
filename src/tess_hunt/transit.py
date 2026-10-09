"""Limb-darkened transit light curves, integrated over each cadence's exposure."""

import batman
import numpy as np

G = 6.674e-11
RHO_SUN_GCC = 1.408


def a_rs_from_density(rho_gcc: float, period_days: float) -> float:
    """Scaled semi-major axis from stellar density (Kepler's third law, planet mass neglected)."""
    return float(
        ((G * rho_gcc * 1000.0 * (period_days * 86400.0) ** 2) / (3.0 * np.pi)) ** (1.0 / 3.0)
    )


def density_from_duration(period_days: float, duration_days: float) -> float:
    """Stellar density (g/cm^3) implied by a central transit of this duration; a starting point, not a measurement."""
    a_rs = period_days / (np.pi * duration_days)
    return float(3.0 * np.pi * a_rs**3 / (G * (period_days * 86400.0) ** 2) / 1000.0)


def light_curve(time, exposure_days, t0, period, rp_rs, a_rs, b, u1, u2) -> np.ndarray:
    params = batman.TransitParams()
    params.t0, params.per, params.rp, params.a = t0, period, rp_rs, a_rs
    params.inc = float(np.degrees(np.arccos(b / a_rs)))
    params.ecc, params.w = 0.0, 90.0
    params.u, params.limb_dark = [u1, u2], "quadratic"
    time = np.asarray(time, dtype=float)
    exposure_days = np.asarray(exposure_days, dtype=float)
    flux = np.ones(len(time))
    for exposure in np.unique(exposure_days):
        m = exposure_days == exposure
        # Long cadences smear ingress and egress; integrate over the exposure as the detector did.
        supersample = max(1, int(np.ceil(exposure * 1440.0 / 2.0)))
        model = batman.TransitModel(
            params, time[m], supersample_factor=supersample, exp_time=exposure
        )
        flux[m] = model.light_curve(params)
    return flux
