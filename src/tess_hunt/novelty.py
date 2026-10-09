"""Novelty: is a signal already known on this star, or on a neighbour that could blend into it?"""

import numpy as np
import pandas as pd

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.ephemeris import Ephemeris, ephemeris_match

REQUIRED_SOURCES = {"TOI", "CTOI", "archive"}


def separation_arcmin(ra1, dec1, ra2, dec2):
    ra1, dec1, ra2, dec2 = (np.radians(np.asarray(x, dtype=float)) for x in (ra1, dec1, ra2, dec2))
    s = np.sin((dec2 - dec1) / 2) ** 2 + np.cos(dec1) * np.cos(dec2) * np.sin((ra2 - ra1) / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(s, 0.0, 1.0)))) * 60.0


def check_novelty(
    tic: int,
    ra: float,
    dec: float,
    eph: Ephemeris,
    known: pd.DataFrame,
    neighbour_arcmin: float,
    harmonics: tuple[float, ...],
    sigma_p: float,
    sigma_t: float,
) -> CheckResult:
    if not np.all(np.isfinite([ra, dec, eph.period, eph.t0])):
        # A NaN position finds no neighbours and a NaN ephemeris matches nothing: both would pass.
        return inconclusive(
            "novelty",
            "candidate position or ephemeris missing",
            ra=ra,
            dec=dec,
            period=eph.period,
            t0=eph.t0,
        )
    present = set(known["source"]) if len(known) else set()
    missing = REQUIRED_SOURCES - present
    if missing:
        # An empty or partial catalog would make every signal look new.
        return inconclusive(
            "novelty", f"catalogs not loaded: {sorted(missing)}", catalog_rows=len(known)
        )
    sep = separation_arcmin(ra, dec, known["ra"], known["dec"])
    near = known[(known["tic"] == tic) | (sep < neighbour_arcmin)]
    matches, period_matches, unknown_period = [], [], []
    for row in near.itertuples():
        if not (np.isfinite(row.period) and row.period > 0):
            if row.tic == tic:
                unknown_period.append(row.name)
            continue
        found = {
            "source": row.source,
            "name": row.name,
            "tic": int(row.tic),
            "period": float(row.period),
        }
        ratio = ephemeris_match(
            eph, Ephemeris(row.period, row.t0, row.duration), harmonics, sigma_p, sigma_t
        )
        if ratio is not None:
            matches.append({**found, "ratio": ratio})
            continue
        # A catalog period's error grows with every cycle since its epoch, so a rediscovery can land
        # out of phase with the catalog (docs/decisions/0003-novelty-stale-ephemerides.md).
        ratios = harmonics if row.tic == tic else (1.0,)
        ratio = ephemeris_match(
            eph, Ephemeris(row.period, float("nan"), row.duration), ratios, sigma_p, sigma_t
        )
        if ratio is not None:
            cycles = int(round((eph.t0 - row.t0) / row.period)) if np.isfinite(row.t0) else None
            period_matches.append({**found, "ratio": ratio, "cycles": cycles})
    evidence = {
        "catalog_rows": len(known),
        "nearby_rows": len(near),
        "neighbour_arcmin": neighbour_arcmin,
    }
    if matches:
        return failed("novelty", f"matches {matches[0]['name']}", matches=matches, **evidence)
    if period_matches:
        return inconclusive(
            "novelty",
            f"period matches {period_matches[0]['name']} but the epoch does not; "
            "the catalog ephemeris may be stale",
            period_matches=period_matches,
            **evidence,
        )
    if unknown_period:
        return inconclusive(
            "novelty",
            "this star has a known object with no period",
            objects=unknown_period,
            **evidence,
        )
    return passed("novelty", "no known object matches", **evidence)
