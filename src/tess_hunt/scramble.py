"""Scrambled light curves for the null threshold, after Kunimoto et al. 2025 (arXiv 2509.10619,
section 5.4): the orbits inside each sector are shuffled, then the sectors, so real periodic signals
decohere while each segment keeps its own noise and systematics. Inversion is not used: scattered light
is not symmetric under it."""

import numpy as np

from tess_hunt.lightcurve import LightCurve


def segments(time: np.ndarray, sector: np.ndarray, gap_days: float) -> np.ndarray:
    """A label per cadence (time sorted): a new segment at every sector change or gap over gap_days."""
    new = np.r_[True, (np.diff(sector) != 0) | (np.diff(time) > gap_days)]
    return np.cumsum(new) - 1


def scramble(
    lc: LightCurve, gap_days: float, placement_gap_days: float, seed: int
) -> tuple[LightCurve, np.ndarray]:
    """Shuffle the segments within each sector, then the sectors, and shift each segment into its new
    slot. Returns the scrambled light curve and `order`, with scrambled.flux == lc.flux[order]."""
    rng = np.random.default_rng([seed, lc.tic])
    labels = segments(lc.time, lc.sector, gap_days)
    # Sectors are contiguous in a time-sorted light curve, so this is their chronological order.
    sectors = list(dict.fromkeys(lc.sector[np.r_[True, np.diff(lc.sector) != 0]].tolist()))
    slot_starts = [float(lc.time[lc.sector == s].min()) for s in sectors]
    order_parts, time_parts = [], []
    cursor = -np.inf
    for slot, k in enumerate(rng.permutation(len(sectors))):
        ids = np.unique(labels[lc.sector == sectors[k]])
        # Each sector keeps its slot's start, so the baseline and the season pattern stay as observed.
        cursor = max(cursor, slot_starts[slot])
        for seg in ids[rng.permutation(len(ids))]:
            idx = np.flatnonzero(labels == seg)
            shifted = lc.time[idx] - lc.time[idx[0]] + cursor
            order_parts.append(idx)
            time_parts.append(shifted)
            # A gap longer than detrend's break tolerance keeps the segments apart, as orbits are.
            cursor = shifted[-1] + placement_gap_days
    order = np.concatenate(order_parts)
    scrambled = LightCurve(
        lc.tic,
        np.concatenate(time_parts),
        lc.flux[order],
        lc.flux_err[order],
        lc.sector[order],
        lc.sources,
    )
    return scrambled, order
