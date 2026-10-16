"""Whether a search recovered a known ephemeris, for the benchmarks and the production controls."""

import numpy as np

from tess_hunt.ephemeris import Ephemeris, ephemeris_match

ALIASES = (0.5, 2.0, 1 / 3, 3.0)


def classify(truth: Ephemeris, signals, match_cfg: dict, threshold: float) -> dict:
    """Recovered: a signal at the true ephemeris at or above the threshold. Alias: only a harmonic matches."""
    sp, st = match_cfg["sigma_p"], match_cfg["sigma_t"]

    # Over a long baseline the catalog period can be the less precise one, so the epochs may line
    # up only when carried with the signal's period. ALIASES is closed under inversion, so the
    # reversed order keeps the alias test's meaning.
    def matches(s, ratios) -> bool:
        found = s.ephemeris()
        return (
            ephemeris_match(found, truth, ratios, sp, st) is not None
            or ephemeris_match(truth, found, ratios, sp, st) is not None
        )

    for s in signals:
        if matches(s, (1.0,)):
            return {
                "recovered": bool(s.sde >= threshold),
                "alias": False,
                "found_period": s.period,
                "sde": s.sde,
                "rank": s.rank,
            }
    for s in signals:
        if matches(s, ALIASES):
            return {
                "recovered": False,
                "alias": True,
                "found_period": s.period,
                "sde": s.sde,
                "rank": s.rank,
            }
    top = signals[0] if signals else None
    return {
        "recovered": False,
        "alias": False,
        "found_period": top.period if top else np.nan,
        "sde": top.sde if top else np.nan,
        "rank": 0,
    }
