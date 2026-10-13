"""Transit fit: batman model sampled with emcee.

Parameters: t0, period, Rp/R*, impact parameter b, log10 stellar density (g/cm^3), and Kipping's q1, q2
limb-darkening coefficients."""

from dataclasses import dataclass

import emcee
import numpy as np

from tess_hunt.ephemeris import Ephemeris, in_transit, phase_days
from tess_hunt.lightcurve import LightCurve
from tess_hunt.transit import a_rs_from_density, density_from_duration, light_curve

NAMES = ("t0", "period", "rp_rs", "b", "log_rho", "q1", "q2")


@dataclass(frozen=True)
class FitResult:
    samples: np.ndarray
    acceptance: float
    rho_prior: tuple[float, float] | None

    def column(self, name: str) -> np.ndarray:
        return self.samples[:, NAMES.index(name)]

    def summary(self) -> dict:
        out = {}
        for name in NAMES:
            lo, mid, hi = np.percentile(self.column(name), [16, 50, 84])
            out[name] = {"median": float(mid), "minus": float(mid - lo), "plus": float(hi - mid)}
        out["acceptance"] = self.acceptance
        out["rho_prior"] = list(self.rho_prior) if self.rho_prior else None
        return out


def fit_transit(
    lc: LightCurve,
    eph: Ephemeris,
    cfg: dict,
    rho_prior: tuple[float, float] | None = None,
    seed: int | None = None,
) -> FitResult:
    """Sample the transit posterior. rho_prior is (log10 rho in g/cm^3, sigma in dex), or None for a
    flat prior on log10 rho in (-3, 2). The density check needs the flat prior, or it would only see
    its own prior."""
    if cfg["burn"] >= cfg["steps"]:
        raise ValueError(f"a burn-in of {cfg['burn']} leaves none of {cfg['steps']} steps")
    # A half-width: cadences within this many durations either side of mid-transit, unlike in_transit's
    # full-width convention (decision 0015).
    near = np.abs(phase_days(lc.time, eph)) < cfg["window_half_width_durations"] * eph.duration
    time, flux, err = lc.time[near], lc.flux[near], lc.flux_err[near]
    exposure = lc.exposure_days()[near]
    if len(time) < cfg["min_points"]:
        raise ValueError(f"only {len(time)} cadences near transit; need {cfg['min_points']} to fit")
    # With data around the transit but none in it, the posterior is the prior, which the shape and
    # density checks would read as a pass.
    if not in_transit(time, eph).any():
        raise ValueError("no cadences inside the transit")

    def log_prob(theta: np.ndarray) -> float:
        t0, period, rp_rs, b, log_rho, q1, q2 = theta
        if not (
            abs(t0 - eph.t0) < 0.5 * eph.duration
            and abs(period - eph.period) < 0.01 * eph.period
            and 0.001 < rp_rs < 0.5
            and 0.0 <= b < 1.0 + rp_rs
            and -3.0 < log_rho < 2.0
            and 0.0 < q1 < 1.0
            and 0.0 < q2 < 1.0
        ):
            return -np.inf
        a_rs = a_rs_from_density(10.0**log_rho, period)
        if b >= a_rs:
            return -np.inf
        u1, u2 = 2.0 * np.sqrt(q1) * q2, np.sqrt(q1) * (1.0 - 2.0 * q2)
        model = light_curve(time, exposure, t0, period, rp_rs, a_rs, b, u1, u2)
        lp = -0.5 * float(np.sum(((flux - model) / err) ** 2))
        if rho_prior is not None:
            lp -= 0.5 * ((log_rho - rho_prior[0]) / rho_prior[1]) ** 2
        return lp

    rng = np.random.default_rng(seed)
    depth = eph.depth if np.isfinite(eph.depth) and eph.depth > 0 else 1e-3
    # Start walkers at the density the duration implies; from a solar start a giant-star host
    # would leave them crawling two decades before burn-in ends.
    start_log_rho = np.clip(np.log10(density_from_duration(eph.period, eph.duration)), -2.9, 1.9)
    start = np.array(
        [
            eph.t0,
            eph.period,
            # An eclipse deeper than 25% would start every walker beyond the rp_rs < 0.5 bound.
            np.clip(np.sqrt(depth), 0.002, 0.45),
            0.3,
            rho_prior[0] if rho_prior else start_log_rho,
            0.36,
            0.36,
        ]
    )
    scale = np.array([1e-4, 1e-6 * eph.period, 1e-3, 1e-2, 1e-2, 1e-2, 1e-2])
    p0 = start + scale * rng.normal(size=(cfg["walkers"], len(NAMES)))
    p0[:, 3] = np.abs(p0[:, 3])
    sampler = emcee.EnsembleSampler(cfg["walkers"], len(NAMES), log_prob)
    if seed is not None:
        sampler.random_state = np.random.RandomState(seed).get_state()
    sampler.run_mcmc(p0, cfg["steps"], progress=False)
    acceptance = float(np.mean(sampler.acceptance_fraction))
    # emcee neither moves nor raises when every walker sits outside the prior; it hands back the
    # starting ball, which the checks would read as a posterior. A healthy fit accepts about 0.3.
    if acceptance < cfg["min_acceptance"]:
        raise ValueError(
            f"the walkers never moved (acceptance {acceptance:.3g}, need {cfg['min_acceptance']:g}); no fit"
        )
    samples = sampler.get_chain(discard=cfg["burn"], flat=True)
    return FitResult(samples, acceptance, rho_prior)
