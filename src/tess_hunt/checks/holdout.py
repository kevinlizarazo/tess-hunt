"""Held-out seasons: fit the ephemeris without one season, then look only where it predicts transits."""

import numpy as np
from astropy.timeseries import BoxLeastSquares

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.checks.photometry import box_depth
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.lightcurve import LightCurve


def season_labels(time: np.ndarray, gap_days: float) -> np.ndarray:
    order = np.argsort(time)
    labels_sorted = np.concatenate([[0], np.cumsum(np.diff(time[order]) > gap_days)])
    labels = np.empty(len(time), dtype=int)
    labels[order] = labels_sorted
    return labels


def refit_ephemeris(lc: LightCurve, eph: Ephemeris) -> Ephemeris:
    """Best period and epoch near `eph` from these cadences alone."""
    baseline = float(lc.time.max() - lc.time.min())
    # BLS period resolution is about P * duration / baseline; search five resolutions either side.
    half_width = 5.0 * eph.period * eph.duration / max(baseline, eph.period)
    periods = np.linspace(eph.period - half_width, eph.period + half_width, 801)
    durations = eph.duration * np.array([0.75, 1.0, 1.25])
    result = BoxLeastSquares(lc.time, lc.flux, dy=lc.flux_err).power(
        periods, durations, objective="likelihood"
    )
    i = int(np.argmax(result.power))
    return Ephemeris(
        float(result.period[i]),
        float(result.transit_time[i]),
        float(result.duration[i]),
        float(result.depth[i]),
    )


def holdout(lc: LightCurve, eph: Ephemeris, cfg: dict, core_fraction: float) -> CheckResult:
    labels = season_labels(lc.time, cfg["season_gap_days"])
    seasons = []
    for label in np.unique(labels):
        test, train = labels == label, labels != label
        training_seasons = len(np.unique(labels[train]))
        row = {
            "season": int(label),
            "start": float(lc.time[test].min()),
            "end": float(lc.time[test].max()),
            "training_seasons": training_seasons,
        }
        if training_seasons < cfg["min_training_seasons"]:
            # A period fitted on one season drifts out of the core window a year later.
            seasons.append(
                {
                    **row,
                    "status": "untestable",
                    "reason": f"{training_seasons} training season(s), need "
                    f"{cfg['min_training_seasons']}: one season can't predict a season a year away",
                }
            )
            continue
        predicted = refit_ephemeris(lc.select(train), eph)
        depth, err, n = box_depth(
            lc.time[test], lc.flux[test], lc.flux_err[test], predicted, core_fraction
        )
        # The reference comes from the training cadences only, so it is independent of the held-out depth.
        ref, ref_err, ref_n = box_depth(
            lc.time[train], lc.flux[train], lc.flux_err[train], predicted, core_fraction
        )
        row.update(
            predicted_period=predicted.period,
            predicted_t0=predicted.t0,
            depth=depth,
            err=err,
            n=n,
            ref=ref,
            ref_err=ref_err,
            ref_n=ref_n,
        )
        if n < cfg["min_points"]:
            row["status"] = "no_predicted_transit_in_data"
        elif ref_n < cfg["min_points"]:
            row.update(
                status="untestable",
                reason=f"fewer than {cfg['min_points']} training cadences in predicted transits",
            )
        elif ref / err < cfg["min_expected_snr"]:
            # Too few transits in this season to expect the dip to show; absence proves nothing.
            row.update(status="underpowered", expected_snr=ref / err)
        else:
            tension = abs(depth - ref) / np.hypot(err, ref_err)
            ok = depth / err >= cfg["min_sigma"] and tension <= cfg["max_depth_tension"]
            row.update(
                status="predicted" if ok else "missed",
                sigma=depth / err,
                tension=tension,
                expected_snr=ref / err,
            )
        seasons.append(row)
    tested = [s for s in seasons if s["status"] in ("predicted", "missed")]
    evidence = {"seasons": seasons}
    if len(tested) < 2:
        return inconclusive(
            "holdout", f"{len(tested)} season(s) could be tested; need 2", **evidence
        )
    missed = [s["season"] for s in tested if s["status"] == "missed"]
    if missed:
        return failed(
            "holdout", f"transits missing where predicted in season(s) {missed}", **evidence
        )
    return passed("holdout", f"{len(tested)} held-out seasons predicted", **evidence)
