"""Gaia DR3 stars near a target, each with the eclipse depth it would need to make the observed dip
(docs/decisions/0025-neighbours.md)."""

from functools import partial

import numpy as np
import pandas as pd

from tess_hunt.checks import CheckResult, inconclusive, passed
from tess_hunt.gaia import launch_gaia
from tess_hunt.retry import retry

CHECK = "neighbours"
COLUMNS = ["source_id", "ra", "dec", "phot_g_mean_mag", "bp_rp", "sep_arcsec"]
QUERY = """
SELECT source_id, ra, dec, phot_g_mean_mag, bp_rp,
       DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra:.10f}, {dec:.10f})) * 3600 AS sep_arcsec
FROM gaiadr3.gaia_source
WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.10f}, {dec:.10f}, {radius_deg:.10f}))
"""
# Stassun et al. 2019 (AJ 158, 138), section 2.3.1, eq. 1: T = G - 0.00522555 c^3 + 0.0891337 c^2 - 0.633923 c
# + 0.0324473 with c = BP - RP, valid for -0.2 < c < 3.5. The TIC applies it to de-reddened magnitudes; here it
# takes the observed ones.
TESS_COLOUR_TERM = np.polynomial.Polynomial([0.0324473, -0.633923, 0.0891337, -0.00522555])
# Without the target's source id, the nearest Gaia star this close to its TIC position is taken to be the target.
TARGET_MATCH_ARCSEC = 1.0


class NeighbourError(RuntimeError):
    pass


def gaia_cone(
    ra: float,
    dec: float,
    radius_arcmin: float,
    launch=launch_gaia,
    attempts: int = 3,
    backoff: float = 30.0,
) -> pd.DataFrame:
    """Every Gaia DR3 source within the radius, nearest first."""
    query = QUERY.format(ra=float(ra), dec=float(dec), radius_deg=radius_arcmin / 60.0)
    raw = retry(
        partial(launch, query, None),
        attempts=attempts,
        backoff=backoff,
        # The archive answers outages with assorted exception types.
        retry_on=Exception,
        error=NeighbourError,
        what="Gaia archive",
    )
    # The archive names some gaia_source columns in upper case (SOURCE_ID).
    raw.columns = [str(c).lower() for c in raw.columns]
    return raw[COLUMNS].sort_values("sep_arcsec").reset_index(drop=True)


def tess_mag(g: float, bp_rp: float) -> float:
    return float(g + TESS_COLOUR_TERM(bp_rp))


def tess_mag_bright(g: float, bp_rp_range) -> float:
    """The brightest TESS magnitude eq. 1 gives over the colour range. Stassun et al.'s eq. 2 for a star without a
    colour (T = G - 0.430, a solar colour) is a guess that could make a red neighbour too faint to host the signal."""
    lo, hi = bp_rp_range
    # A cubic is smallest at an end of the range or at a turning point inside it. Eq. 1's turning points are
    # complex, so the red end decides, but the range is a criterion and could move.
    turns = [r.real for r in TESS_COLOUR_TERM.deriv().roots() if np.isreal(r) and lo < r.real < hi]
    return min(tess_mag(g, c) for c in (lo, hi, *turns))


def required_depths(
    table: pd.DataFrame,
    depth: float,
    t_target: float,
    target_source_id: int | None,
    cfg: dict,
) -> pd.DataFrame:
    """The cone without the target, each star with its TESS magnitude and the eclipse depth it would need to make
    the observed `depth` (a fraction); `cfg` is the criteria's `[neighbours]`. The required depth counts the
    target's light and the neighbour's whole light in the aperture and nothing else, so it is the smallest depth the
    neighbour could need."""
    if target_source_id is not None:
        out = table[table["source_id"] != target_source_id]
    else:
        close = table[table["sep_arcsec"] <= TARGET_MATCH_ARCSEC]
        out = table.drop(close["sep_arcsec"].idxmin()) if len(close) else table
    out = out.copy()
    colour = out["bp_rp"].notna()
    out["tmag"] = [
        tess_mag(g, c) if has else tess_mag_bright(g, cfg["bp_rp_range"])
        for g, c, has in zip(out["phot_g_mean_mag"], out["bp_rp"], colour, strict=True)
    ]
    has_g = out["phot_g_mean_mag"].notna()
    out["tmag_from"] = np.select([has_g & colour, has_g], ["colour", "g_only"], default="none")
    out["required_depth"] = depth * 10 ** (0.4 * (out["tmag"] - t_target))
    out["possible"] = out["required_depth"] <= cfg["max_required_depth"]
    return out.reset_index(drop=True)


def neighbour_check(table: pd.DataFrame | None, error: str | None) -> CheckResult:
    """Never fails (decision 0025): a neighbour that could host the signal is evidence for TRICERATOPS and the
    review, not a verdict on its own."""
    if table is None or error is not None:
        return inconclusive(CHECK, f"the Gaia DR3 query failed: {error}", error=error)
    rows = table.to_dict("records")
    hosts = [
        {
            "source_id": r["source_id"],
            "sep_arcsec": r["sep_arcsec"],
            "required_depth": r["required_depth"],
        }
        for r in rows
        if r["possible"]
    ]
    no_g = table.loc[table["phot_g_mean_mag"].isna(), "source_id"].tolist()
    if no_g:
        return inconclusive(
            CHECK,
            f"{len(no_g)} Gaia DR3 star(s) within the radius have no G magnitude",
            no_g=no_g,
            possible_hosts=hosts,
            table=rows,
        )
    # A missing observed depth or target magnitude would leave every star unable to host the signal.
    if not np.isfinite(table["required_depth"].to_numpy(dtype=float)).all():
        return inconclusive(
            CHECK,
            "the required depths are not finite: the observed depth or the target's TESS magnitude is missing",
            possible_hosts=hosts,
            table=rows,
        )
    return passed(
        CHECK,
        f"{len(hosts)} of {len(rows)} neighbours could host the signal",
        possible_hosts=hosts,
        table=rows,
    )
