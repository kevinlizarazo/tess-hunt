"""Light-curve checks: a dip at all, odd and even depths, secondary eclipse, depth by sector."""

from dataclasses import replace

import numpy as np
from scipy.stats import chi2

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.ephemeris import Ephemeris, epoch_numbers, in_transit
from tess_hunt.lightcurve import LightCurve


def red_noise_beta(
    lc: LightCurve, eph: Ephemeris, timescale_days: float, cfg: dict
) -> dict[str, dict]:
    """Each sector's red-noise factor at `timescale_days` by the time-averaging method (Pont et al.
    2006; Winn et al. 2008): the scatter of out-of-transit bin means over what white noise gives."""
    outside = ~in_transit(lc.time, eph, cfg["exclude_width"])
    betas = {}
    for sector in np.unique(lc.sector):
        m = outside & (lc.sector == sector)
        time, flux, err = lc.time[m], lc.flux[m], lc.flux_err[m]
        if len(time) == 0:
            betas[str(int(sector))] = {
                "beta": 1.0,
                "n_bins": 0,
                "cadences_per_bin": 0.0,
                "note": "no cadences outside transits",
            }
            continue
        index = np.floor((time - time.min()) / timescale_days).astype(int)
        counts = np.bincount(index)
        sums = np.bincount(index, weights=flux)
        # Bins cut by a gap or an excluded transit hold fewer cadences and would read as noisier.
        kept = counts >= cfg["kept_bin_fraction"] * counts.max()
        n_bins = int(kept.sum())
        per_bin = float(np.median(counts[kept]))
        row = {"beta": 1.0, "n_bins": n_bins, "cadences_per_bin": per_bin}
        mean_count = float(counts[counts > 0].mean())
        if mean_count < cfg["min_cadences_per_bin"]:
            row["note"] = (
                f"{mean_count:.1f} cadences per bin on average, need {cfg['min_cadences_per_bin']:g}"
            )
        elif n_bins < cfg["min_bins"]:
            row["note"] = f"{n_bins} full bins, need {cfg['min_bins']}"
        else:
            means = sums[kept] / counts[kept]
            white = np.median(err) / np.sqrt(per_bin)
            row["beta"] = max(1.0, float(np.std(means, ddof=1) / white))
        betas[str(int(sector))] = row
    return betas


def with_red_noise(lc: LightCurve, betas: dict[str, dict]) -> LightCurve:
    """A copy with each sector's errors multiplied by its beta; sectors not in `betas` keep theirs."""
    scale = np.ones(len(lc.time))
    for sector, row in betas.items():
        scale[lc.sector == int(sector)] = row["beta"]
    return replace(lc, flux_err=lc.flux_err * scale)


def box_depth(time, flux, err, eph: Ephemeris, fraction: float) -> tuple[float, float, int]:
    """Depth below 1 from cadences within the central `fraction` of each transit, inverse-variance weighted."""
    inside = in_transit(time, eph, width=fraction)
    n = int(inside.sum())
    if n == 0:
        return float("nan"), float("nan"), 0
    w = 1.0 / err[inside] ** 2
    return float(1.0 - np.sum(w * flux[inside]) / np.sum(w)), float(1.0 / np.sqrt(np.sum(w))), n


def signal_present(
    lc: LightCurve, eph: Ephemeris, core_fraction: float, min_snr: float, min_points: int
) -> CheckResult:
    """Is there a dip at this ephemeris at all? The depth checks compare depths and pass when there is
    nothing to compare (the M1 final review's R9), so they are judged alongside this one."""
    depth, err, n = box_depth(lc.time, lc.flux, lc.flux_err, eph, core_fraction)
    snr = depth / err if n else float("nan")
    evidence = {"depth": depth, "err": err, "snr": snr, "n": n}
    if n < min_points:
        return inconclusive(
            "signal_present", f"fewer than {min_points} in-transit cadences", **evidence
        )
    if not np.isfinite(snr):
        return inconclusive("signal_present", "statistic is not finite", **evidence)
    if snr < min_snr:
        return inconclusive(
            "signal_present", f"combined depth is {snr:.1f} sigma, below {min_snr:g}", **evidence
        )
    return passed("signal_present", f"combined depth is {snr:.1f} sigma", **evidence)


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
    # A NaN statistic compares False against every threshold, so it would pass.
    if not np.isfinite(sigma):
        return inconclusive("odd_even", "statistic is not finite", **evidence)
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
    if not np.isfinite(sigma):
        return inconclusive("secondary", "statistic is not finite", **evidence)
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
    if not np.isfinite(p):
        return inconclusive("sector_depth", "statistic is not finite", **evidence)
    if p < min_p_value:
        return failed("sector_depth", f"depths disagree across sectors (p = {p:.1e})", **evidence)
    return passed(
        "sector_depth", f"depths agree across {len(rows)} sectors (p = {p:.2f})", **evidence
    )
