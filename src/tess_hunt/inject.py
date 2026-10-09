"""Planted transits for injection-recovery tests (spec section 5.4)."""

from dataclasses import dataclass

import numpy as np

from tess_hunt.ephemeris import Ephemeris, transit_times_in_data
from tess_hunt.lightcurve import LightCurve
from tess_hunt.transit import light_curve

R_EARTH_PER_R_SUN = 0.0091577
AU_PER_R_SUN = 215.032


@dataclass(frozen=True)
class Injection:
    period: float
    t0: float
    rp_rearth: float
    b: float
    rp_rs: float
    a_rs: float
    duration: float

    def ephemeris(self) -> Ephemeris:
        return Ephemeris(self.period, self.t0, self.duration, self.rp_rs**2)


def semi_major_axis_rs(period_days: float, mstar: float, rstar: float) -> float:
    return (mstar * (period_days / 365.25) ** 2) ** (1.0 / 3.0) * AU_PER_R_SUN / rstar


def t14(period: float, a_rs: float, rp_rs: float, b: float) -> float:
    inc = np.arccos(b / a_rs)
    chord = np.sqrt(max((1.0 + rp_rs) ** 2 - b**2, 0.0)) / (a_rs * np.sin(inc))
    return float(period / np.pi * np.arcsin(min(chord, 1.0)))


def draw(
    rng: np.random.Generator,
    time: np.ndarray,
    rstar: float,
    mstar: float,
    period_range: tuple[float, float],
    rp_range: tuple[float, float],
    min_transits: int,
    tries: int = 100,
) -> Injection | None:
    """P uniform, Rp log-uniform, b uniform in [0, 1], epoch uniform in phase; redrawn until
    min_transits transits fall on data. None if no draw manages it."""
    for _ in range(tries):
        period = float(rng.uniform(*period_range))
        rp = float(np.exp(rng.uniform(np.log(rp_range[0]), np.log(rp_range[1]))))
        b = float(rng.uniform(0.0, 1.0))
        t0 = float(time.min() + rng.uniform(0.0, period))
        rp_rs = rp * R_EARTH_PER_R_SUN / rstar
        a_rs = semi_major_axis_rs(period, mstar, rstar)
        inj = Injection(period, t0, rp, b, rp_rs, a_rs, t14(period, a_rs, rp_rs, b))
        if len(transit_times_in_data(time, inj.ephemeris())) >= min_transits:
            return inj
    return None


def inject(lc: LightCurve, inj: Injection, u: tuple[float, float]) -> LightCurve:
    model = light_curve(
        lc.time, lc.exposure_days(), inj.t0, inj.period, inj.rp_rs, inj.a_rs, inj.b, *u
    )
    return LightCurve(lc.tic, lc.time, lc.flux * model, lc.flux_err, lc.sector, lc.sources)
