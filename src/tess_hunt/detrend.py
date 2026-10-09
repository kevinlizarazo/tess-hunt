"""Detrend: remove stellar and instrumental trends sector by sector."""

import numpy as np
from wotan import flatten

from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve


def detrend(lc: LightCurve, cfg: dict, mask: list[Ephemeris] = ()) -> LightCurve:
    """Flatten each sector with a time-windowed biweight. Cadences inside `mask` transits are
    dropped first, so known planets neither bend the trend nor reach the search."""
    keep = np.ones(len(lc.time), dtype=bool)
    for eph in mask:
        keep &= ~in_transit(lc.time, eph, cfg["known_mask_width"])
    lc = lc.select(keep)
    parts = []
    for sector in np.unique(lc.sector):
        m = lc.sector == sector
        if m.sum() < cfg["min_points_per_sector"]:
            continue
        time = lc.time[m]
        flat = flatten(
            time,
            lc.flux[m],
            method="biweight",
            window_length=cfg["window_days"],
            edge_cutoff=cfg["edge_cutoff_days"],
            break_tolerance=cfg["break_tolerance_days"],
        )
        ok = np.isfinite(flat)
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
