"""Detrend: remove stellar and instrumental trends sector by sector."""

import numpy as np
from wotan import flatten

from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve


def known_mask(time, mask: list[Ephemeris], width: float) -> np.ndarray:
    known = np.zeros(len(time), dtype=bool)
    for eph in mask:
        known |= in_transit(time, eph, width)
    return known


def detrend(
    lc: LightCurve,
    cfg: dict,
    mask: list[Ephemeris] = (),
    exclude: np.ndarray | None = None,
    hold_out: np.ndarray | None = None,
) -> LightCurve:
    """Flatten each sector with a time-windowed biweight. Cadences inside `mask` transits or flagged in
    `exclude` are left out of the trend and dropped after flattening, so known planets neither bend the trend
    nor reach the search. Cadences flagged in `hold_out` are left out of the trend but kept, so a transit
    under test keeps its depth (wotan evaluates the trend at masked times from their neighbours)."""
    dropped = known_mask(lc.time, mask, cfg["known_mask_width"])
    if exclude is not None:
        dropped |= exclude
    untrended = dropped | hold_out if hold_out is not None else dropped
    parts = []
    for sector in np.unique(lc.sector):
        m = lc.sector == sector
        if (m & ~dropped).sum() < cfg["min_points_per_sector"]:
            continue
        time = lc.time[m]
        # Masked cadences stay in the time array: deleting them would leave gaps that wotan
        # treats as segment breaks, each with its own edge cut.
        flat = flatten(
            time,
            lc.flux[m],
            method="biweight",
            window_length=cfg["window_days"],
            edge_cutoff=cfg["edge_cutoff_days"],
            break_tolerance=cfg["break_tolerance_days"],
            mask=untrended[m],
        )
        ok = np.isfinite(flat) & ~dropped[m]
        time, flat = time[ok], flat[ok]
        if len(flat) < cfg["min_points_per_sector"]:
            continue
        resid = flat - np.median(flat)
        scatter = 1.4826 * np.median(np.abs(resid))
        if not scatter > 0:
            continue
        # Transits are dips, so only upward outliers are clipped.
        ok = resid < cfg["clip_sigma"] * scatter
        # Products report errors on different scales; the sector's own scatter is what the search
        # should weight by.
        parts.append(
            (
                time[ok],
                flat[ok],
                np.full(ok.sum(), scatter),
                np.full(ok.sum(), sector, dtype=np.int16),
            )
        )
    if not parts:
        empty = np.array([], dtype=float)
        return LightCurve(lc.tic, empty, empty, empty, np.array([], dtype=np.int16), lc.sources)
    time, flux, err, sector = (np.concatenate(c) for c in zip(*parts, strict=True))
    order = np.argsort(time, kind="stable")
    return LightCurve(lc.tic, time[order], flux[order], err[order], sector[order], lc.sources)
