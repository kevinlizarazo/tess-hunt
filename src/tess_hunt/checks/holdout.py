"""Held-out seasons: fit the ephemeris without one season, then look only where it predicts transits."""

import numpy as np
from astropy.timeseries import BoxLeastSquares

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.checks.families import family_labels
from tess_hunt.checks.photometry import box_depth
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve


def season_labels(time: np.ndarray, gap_days: float) -> np.ndarray:
    order = np.argsort(time)
    labels_sorted = np.concatenate([[0], np.cumsum(np.diff(time[order]) > gap_days)])
    labels = np.empty(len(time), dtype=int)
    labels[order] = labels_sorted
    return labels


def refit_ephemeris(lc: LightCurve, eph: Ephemeris, cfg: dict) -> Ephemeris:
    """Best period and epoch from these cadences alone, searching periods near `eph`'s; BLS scans every epoch."""
    baseline = float(lc.time.max() - lc.time.min())
    # BLS period resolution is about P * duration / baseline; search that many resolutions either side.
    half_width = cfg["refit_resolutions"] * eph.period * eph.duration / max(baseline, eph.period)
    periods = np.linspace(eph.period - half_width, eph.period + half_width, cfg["refit_points"])
    durations = eph.duration * np.asarray(cfg["refit_duration_factors"], dtype=float)
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


def reference(
    lc: LightCurve,
    families: np.ndarray | None,
    train: np.ndarray,
    predicted: Ephemeris,
    core_fraction: float,
) -> dict:
    """The training depths a held-out season is judged against, in `predicted`'s transit cores: over every
    training cadence, and with `families` for each family the training cadences hold. They come from the
    training cadences only, so they are independent of the held-out depth."""
    ref, ref_err, ref_n = box_depth(
        lc.time[train], lc.flux[train], lc.flux_err[train], predicted, core_fraction
    )
    by_family = {}
    if families is not None:
        for name in np.unique(families[train]):
            trained = train & (families == name)
            family_ref, family_err, family_n = box_depth(
                lc.time[trained], lc.flux[trained], lc.flux_err[trained], predicted, core_fraction
            )
            by_family[str(name)] = {
                "ref": family_ref,
                "ref_err": family_err,
                "ref_n": family_n,
                "training_cadences": int(trained.sum()),
            }
    return {"ref": ref, "ref_err": ref_err, "ref_n": ref_n, "families": by_family}


# A held-out family the training cadences don't hold: what box_depth gives on no cadences.
NO_TRAINING = {"ref": float("nan"), "ref_err": float("nan"), "ref_n": 0, "training_cadences": 0}


def family_depths(
    lc: LightCurve,
    families: np.ndarray,
    test: np.ndarray,
    predicted: Ephemeris,
    references: dict[str, dict],
    core_fraction: float,
    min_points: int,
) -> list[dict]:
    """Each product family's held-out depth beside the same family's training depth from `references`,
    and their tension where both have `min_points` cadences in predicted transits
    (docs/decisions/0023-product-families.md)."""
    rows = []
    for name in np.unique(families[test]):
        held = test & (families == name)
        depth, err, n = box_depth(
            lc.time[held], lc.flux[held], lc.flux_err[held], predicted, core_fraction
        )
        trained = references.get(str(name), NO_TRAINING)
        row = {
            "family": str(name),
            "depth": depth,
            "err": err,
            "n": n,
            "ref": trained["ref"],
            "ref_err": trained["ref_err"],
            "ref_n": trained["ref_n"],
            "training_cadences": trained["training_cadences"],
        }
        if min(n, row["ref_n"]) >= min_points:
            row["tension"] = abs(depth - row["ref"]) / np.hypot(err, row["ref_err"])
        rows.append(row)
    return rows


def family_expected_depth(rows: list[dict], min_points: int) -> tuple[float, str | None]:
    """The depth the held-out season should show: each family's own training depth, weighted as
    box_depth weights that family's held-out cadences in predicted transits. A training depth over
    every family would overstate it for a season mostly in a diluted family. Returns a reason instead
    when a family in the held-out transits has no training depth of its own."""
    present = [r for r in rows if r["n"] > 0]
    for r in present:
        if r["training_cadences"] == 0:
            return float(
                "nan"
            ), f"no training cadences in the held-out season's {r['family']} family"
        if r["ref_n"] < min_points:
            return float("nan"), (
                f"fewer than {min_points} training cadences of the {r['family']} family "
                "in predicted transits"
            )
    weights = np.array([r["err"] ** -2 for r in present])
    refs = np.array([r["ref"] for r in present])
    return float(np.sum(weights * refs) / np.sum(weights)), None


def judge(
    lc: LightCurve,
    families: np.ndarray | None,
    test: np.ndarray,
    predicted: Ephemeris,
    reference: dict,
    cfg: dict,
    core_fraction: float,
) -> dict:
    """The held-out season's depth in `predicted`'s transit cores and its status against `reference`:
    the fields holdout sets on a season that passed its training gates."""
    depth, err, n = box_depth(
        lc.time[test], lc.flux[test], lc.flux_err[test], predicted, core_fraction
    )
    ref, ref_err, ref_n = reference["ref"], reference["ref_err"], reference["ref_n"]
    row = {"depth": depth, "err": err, "n": n, "ref": ref, "ref_err": ref_err, "ref_n": ref_n}
    expected, untestable = ref, None
    if families is not None and n >= cfg["min_points"]:
        row["family_depths"] = family_depths(
            lc, families, test, predicted, reference["families"], core_fraction, cfg["min_points"]
        )
        expected, untestable = family_expected_depth(row["family_depths"], cfg["min_points"])
        row["expected_depth"] = expected
    if n < cfg["min_points"]:
        row["status"] = "no_predicted_transit_in_data"
    elif ref_n < cfg["min_points"]:
        row.update(
            status="untestable",
            reason=f"fewer than {cfg['min_points']} training cadences in predicted transits",
        )
    elif untestable is not None:
        row.update(status="untestable", reason=untestable)
    elif expected / err < cfg["min_expected_snr"]:
        # Too few transits in this season to expect the dip to show; absence proves nothing.
        row.update(status="underpowered", expected_snr=expected / err)
    else:
        tension = abs(depth - ref) / np.hypot(err, ref_err)
        if families is not None:
            tensions = [r["tension"] for r in row["family_depths"] if "tension" in r]
            # np.max keeps a NaN, which then fails the season as vet-v2's single tension would.
            tension = float(np.max(tensions)) if tensions else None
        ok = depth / err >= cfg["min_sigma"] and (
            tension is None or tension <= cfg["max_depth_tension"]
        )
        row.update(status="predicted" if ok else "missed", sigma=depth / err)
        if tension is None:
            row["tension_skipped"] = (
                f"fewer than {cfg['min_points']} held-out cadences in predicted transits "
                "in every family"
            )
        else:
            row["tension"] = tension
        row["expected_snr"] = expected / err
    return row


def holdout(
    lc: LightCurve,
    eph: Ephemeris,
    cfg: dict,
    core_fraction: float,
    families_cfg: dict | None = None,
) -> CheckResult:
    """With `families_cfg` (vet-v3), the expected SNR and the depth tension compare each product family
    only with itself; detection still uses every held-out cadence."""
    labels = season_labels(lc.time, cfg["season_gap_days"])
    families = family_labels(lc, families_cfg) if families_cfg is not None else None
    # A season whose transits all fall in its gaps has cadences but gives the refit nothing to fit, so it
    # can't count toward min_training_seasons. Its cadences are counted over the whole transit, not the
    # core: the core is where depths are measured, and a sparsely sampled season still times its transits
    # (docs/decisions/0035-holdout-training-seasons.md).
    transits = in_transit(lc.time, eph)
    with_transits = {
        int(label)
        for label in np.unique(labels)
        if (transits & (labels == label)).sum() >= cfg["min_points"]
    }
    seasons = []
    for label in np.unique(labels):
        test, train = labels == label, labels != label
        training_seasons = len(np.unique(labels[train]))
        training_with_transits = len(with_transits - {int(label)})
        row = {
            "season": int(label),
            "start": float(lc.time[test].min()),
            "end": float(lc.time[test].max()),
            "training_seasons": training_seasons,
            "training_seasons_with_transits": training_with_transits,
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
        if training_with_transits < cfg["min_training_seasons"]:
            seasons.append(
                {
                    **row,
                    "status": "untestable",
                    "reason": f"{training_with_transits} of {training_seasons} training seasons hold a "
                    f"transit in their data, need {cfg['min_training_seasons']}: one season can't "
                    "predict a season a year away",
                }
            )
            continue
        predicted = refit_ephemeris(lc.select(train), eph, cfg)
        row.update(predicted_period=predicted.period, predicted_t0=predicted.t0)
        trained = reference(lc, families, train, predicted, core_fraction)
        row.update(judge(lc, families, test, predicted, trained, cfg, core_fraction))
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
