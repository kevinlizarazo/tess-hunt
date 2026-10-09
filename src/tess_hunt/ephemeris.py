"""Transit ephemerides. Times are BTJD (BJD_TDB - 2457000); durations are in days."""

from dataclasses import dataclass

import numpy as np
from scipy.special import erfcinv


@dataclass(frozen=True)
class Ephemeris:
    period: float
    t0: float
    duration: float
    depth: float = float("nan")


def phase_days(time, eph: Ephemeris) -> np.ndarray:
    """Time from the nearest transit centre, in [-P/2, P/2)."""
    return (np.asarray(time) - eph.t0 + 0.5 * eph.period) % eph.period - 0.5 * eph.period


def in_transit(time, eph: Ephemeris, width: float = 1.0) -> np.ndarray:
    return np.abs(phase_days(time, eph)) < 0.5 * width * eph.duration


def epoch_numbers(time, eph: Ephemeris) -> np.ndarray:
    return np.round((np.asarray(time) - eph.t0) / eph.period).astype(int)


def transit_times_in_data(
    time, eph: Ephemeris, min_points: int = 1, width: float = 1.0
) -> np.ndarray:
    """Centres of the transits with at least min_points cadences within width x duration."""
    time = np.asarray(time)
    inside = in_transit(time, eph, width)
    epochs, counts = np.unique(epoch_numbers(time[inside], eph), return_counts=True)
    return eph.t0 + epochs[counts >= min_points] * eph.period


def _sigma(fraction: float) -> float:
    if fraction <= 0.0:
        return float("inf")
    return float(np.sqrt(2.0) * erfcinv(min(fraction, 1.0)))


def ephemeris_match(
    a: Ephemeris,
    b: Ephemeris,
    harmonics: tuple[float, ...] = (1.0,),
    sigma_p: float = 2.5,
    sigma_t: float = 2.0,
) -> float | None:
    """The ratio k for which `b` at period P_b * k matches `a` (Coughlin et al. 2014), or None.
    A `b` without an epoch matches on period alone."""
    for k in harmonics:
        if _sigma(abs(a.period - b.period * k) / a.period) <= sigma_p:
            continue
        if not np.isfinite(b.t0):
            return k
        # Harmonics share every transit of the shorter period, so compare phases on that period.
        wrap = min(a.period, b.period)
        offset = abs(((a.t0 - b.t0) / wrap + 0.5) % 1.0 - 0.5)
        if _sigma(offset) > sigma_t:
            return k
    return None
