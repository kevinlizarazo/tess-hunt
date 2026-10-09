"""Light-curve checks: odd and even depths, secondary eclipse, depth by sector."""

import numpy as np
from scipy.stats import chi2

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.ephemeris import Ephemeris, epoch_numbers, in_transit
from tess_hunt.lightcurve import LightCurve


def box_depth(time, flux, err, eph: Ephemeris, fraction: float) -> tuple[float, float, int]:
    """Depth below 1 from cadences within the central `fraction` of each transit, inverse-variance weighted."""
    inside = in_transit(time, eph, width=fraction)
    n = int(inside.sum())
    if n == 0:
        return float("nan"), float("nan"), 0
    w = 1.0 / err[inside] ** 2
    return float(1.0 - np.sum(w * flux[inside]) / np.sum(w)), float(1.0 / np.sqrt(np.sum(w))), n


def odd_even(
    lc: LightCurve, eph: Ephemeris, core_fraction: float, max_sigma: float, min_points: int
) -> CheckResult:
    odd = epoch_numbers(lc.time, eph) % 2 == 1
    d_odd, e_odd, n_odd = box_depth(
        lc.time[odd], lc.flux[odd], lc.flux_err[odd], eph, core_fraction
    )
    d_even, e_even, n_even = box_depth(
        lc.time[~odd], lc.flux[~odd], lc.flux_err[~odd], eph, core_fraction
    )
    evidence = {
        "depth_odd": d_odd,
        "err_odd": e_odd,
        "n_odd": n_odd,
        "depth_even": d_even,
        "err_even": e_even,
        "n_even": n_even,
    }
    if min(n_odd, n_even) < min_points:
        return inconclusive(
            "odd_even",
            f"fewer than {min_points} in-transit cadences on odd or even transits",
            **evidence,
        )
    sigma = abs(d_odd - d_even) / np.hypot(e_odd, e_even)
    evidence["sigma"] = sigma
    if sigma > max_sigma:
        return failed("odd_even", f"odd and even depths differ by {sigma:.1f} sigma", **evidence)
    return passed("odd_even", f"odd and even depths agree within {sigma:.1f} sigma", **evidence)


def secondary(lc: LightCurve, eph: Ephemeris, max_sigma: float, min_points: int) -> CheckResult:
    """A dip at phase 0.5 over the full transit duration, assuming a circular orbit."""
    half = Ephemeris(eph.period, eph.t0 + 0.5 * eph.period, eph.duration)
    depth, err, n = box_depth(lc.time, lc.flux, lc.flux_err, half, 1.0)
    evidence = {"depth": depth, "err": err, "n": n}
    if n < min_points:
        return inconclusive(
            "secondary", f"fewer than {min_points} cadences at phase 0.5", **evidence
        )
    sigma = depth / err
    evidence["sigma"] = sigma
    if sigma > max_sigma:
        return failed(
            "secondary", f"dip at phase 0.5 of {depth * 1e6:.0f} ppm, {sigma:.1f} sigma", **evidence
        )
    return passed("secondary", f"no dip at phase 0.5 ({sigma:.1f} sigma)", **evidence)


def sector_depths(
    lc: LightCurve, eph: Ephemeris, core_fraction: float, min_p_value: float, min_points: int
) -> CheckResult:
    rows = []
    for sector in np.unique(lc.sector):
        m = lc.sector == sector
        depth, err, n = box_depth(lc.time[m], lc.flux[m], lc.flux_err[m], eph, core_fraction)
        if n >= min_points:
            source = lc.sources.get(str(int(sector)), {})
            rows.append(
                {
                    "sector": int(sector),
                    "depth": depth,
                    "err": err,
                    "n": n,
                    "provenance": source.get("provenance"),
                }
            )
    if len(rows) < 2:
        return inconclusive(
            "sector_depth", "fewer than two sectors with in-transit data", sectors=rows
        )
    d = np.array([r["depth"] for r in rows])
    e = np.array([r["err"] for r in rows])
    w = 1.0 / e**2
    mean = float(np.sum(w * d) / np.sum(w))
    stat = float(np.sum(((d - mean) / e) ** 2))
    dof = len(rows) - 1
    p = float(chi2.sf(stat, dof))
    evidence = {"sectors": rows, "mean_depth": mean, "chi2": stat, "dof": dof, "p_value": p}
    if p < min_p_value:
        return failed("sector_depth", f"depths disagree across sectors (p = {p:.1e})", **evidence)
    return passed(
        "sector_depth", f"depths agree across {len(rows)} sectors (p = {p:.2f})", **evidence
    )
