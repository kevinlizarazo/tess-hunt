import json
from pathlib import Path

import numpy as np
import pytest
from synthetic import box, make_lc, with_products

from tess_hunt.checks import Outcome
from tess_hunt.checks.families import family_labels
from tess_hunt.checks.holdout import (
    holdout,
    judge,
    reference,
    refit_ephemeris,
    season_labels,
)
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, in_transit, phase_days
from tess_hunt.serialize import jsonable

CFG = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "vet-v2.toml")["holdout"]
FAMILIES = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "vet-v3.toml")[
    "families"
]
SECTORS = (1, 2, 3, 14, 15, 16, 28, 29, 30)  # three seasons about a year apart
EPH = Ephemeris(3.7, 1326.1, 0.12)


def test_season_labels():
    t = np.array([0.0, 10.0, 100.0, 101.0, 300.0])
    assert list(season_labels(t, 60.0)) == [0, 0, 1, 1, 2]


def test_planet_in_every_season_is_predicted():
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=1)
    result = holdout(lc, EPH, CFG, 0.5)
    assert result.outcome is Outcome.PASS
    assert sum(s["status"] == "predicted" for s in result.evidence["seasons"]) == 3


def test_negative_control_signal_missing_from_one_season():
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, seed=2)
    early = lc.sector < 28
    lc.flux[early] += box(lc.time[early], 3.7, 1326.1, 0.12, 1500e-6)
    result = holdout(lc, EPH, CFG, 0.5)
    assert result.outcome is Outcome.FAIL
    assert [s["status"] for s in result.evidence["seasons"]][2] == "missed"


def test_single_season_is_inconclusive():
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=3)
    assert holdout(lc, EPH, CFG, 0.5).outcome is Outcome.INCONCLUSIVE


def test_two_seasons_are_untestable_not_fail():
    lc = make_lc(
        sectors=(1, 2, 3, 28, 29, 30),
        noise_ppm=300.0,
        signals=[(3.7, 1326.1, 0.12, 1500e-6)],
        seed=0,
    )
    result = holdout(lc, EPH, CFG, 0.5)
    assert result.outcome is Outcome.INCONCLUSIVE
    assert [s["status"] for s in result.evidence["seasons"]] == ["untestable", "untestable"]


def last_season_with_one_transit(in_gap):
    """The planet in three seasons, the last cut to four days of S28 around one transit, which falls in a
    data gap when `in_gap`, as 441010857-1's only S11 transit did (docs/decisions/0035). At 30 min the
    transit holds 6 cadences, 3 of them in its core, as sparse as 438857197-1's S11."""
    lc = make_lc(
        sectors=(1, 2, 3, 14, 15, 16, 28),
        noise_ppm=300.0,
        signals=[(3.7, 1326.1, 0.12, 1500e-6)],
        seed=7,
    )
    near = np.abs(lc.time - (EPH.t0 + 202 * EPH.period))  # BTJD 2073.5, in S28's first orbit
    s28 = lc.sector == 28
    keep = ~s28 | (near < 2.0)
    if in_gap:
        keep &= ~(s28 & (near < 0.25))
    return lc.select(keep)


def test_a_training_season_whose_transit_falls_in_a_gap_does_not_count():
    result = holdout(last_season_with_one_transit(in_gap=True), EPH, CFG, 0.5)
    assert result.outcome is Outcome.INCONCLUSIVE
    first, second, last = result.evidence["seasons"]
    for season in (first, second):
        assert season["status"] == "untestable", season
        assert (season["training_seasons"], season["training_seasons_with_transits"]) == (2, 1)
        assert season["reason"] == (
            "1 of 2 training seasons hold a transit in their data, need 2: "
            "one season can't predict a season a year away"
        )
    assert last["status"] == "no_predicted_transit_in_data", last


def test_a_training_season_whose_transit_has_few_core_cadences_still_counts():
    result = holdout(last_season_with_one_transit(in_gap=False), EPH, CFG, 0.5)
    seasons = result.evidence["seasons"]
    assert [s["training_seasons_with_transits"] for s in seasons] == [2, 2, 2]
    statuses = [s["status"] for s in seasons]
    assert statuses == ["predicted", "predicted", "no_predicted_transit_in_data"], seasons
    # Too few core cadences to measure the season's own depth, enough to time its transit for the others.
    assert seasons[2]["n"] < CFG["min_points"]
    assert result.outcome is Outcome.PASS


def test_underpowered_seasons_are_inconclusive_not_fail():
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 60e-6)], seed=4)
    result = holdout(lc, EPH, CFG, 0.5)
    assert result.outcome is Outcome.INCONCLUSIVE
    assert {s["status"] for s in result.evidence["seasons"]} == {"underpowered"}


def planet_with_qlp(qlp_sectors, noise_ppm=300.0, seed=5, without_transits=()):
    """The planet in every sector but `without_transits`; the QLP sectors read its depth at 0.6, as on
    a crowded star (results/benchmarks/qlp-dilution-2026-10-13.txt)."""
    lc = make_lc(sectors=SECTORS, noise_ppm=noise_ppm, seed=seed)
    for sector in set(SECTORS) - set(without_transits):
        m = lc.sector == sector
        scale = 0.6 if sector in qlp_sectors else 1.0
        lc.flux[m] += box(lc.time[m], 3.7, 1326.1, 0.12, 1500e-6 * scale)
    products = {s: "QLP" if s in qlp_sectors else "SPOC" for s in SECTORS}
    return with_products(lc, products)


# QLP in the last two seasons, in different shares, so every family a season holds also trains it.
MIXED_QLP = (15, 16, 28, 29)


def test_family_tension_compares_like_with_like():
    lc = planet_with_qlp(qlp_sectors=MIXED_QLP)
    # Pooled, the all-PDCSAP first season reads deeper than the QLP-heavy seasons that train it.
    assert holdout(lc, EPH, CFG, 0.5).outcome is Outcome.FAIL
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.PASS, result.evidence
    seasons = result.evidence["seasons"]
    assert [s["status"] for s in seasons] == ["predicted"] * 3
    rows = {row["family"]: row for row in seasons[2]["family_depths"]}
    assert set(rows) == {"pdcsap", "qlp"}, rows
    assert seasons[2]["tension"] == max(row["tension"] for row in rows.values())


def test_family_tension_still_fails_a_depth_change_inside_a_family():
    lc = planet_with_qlp(qlp_sectors=MIXED_QLP)
    s30 = lc.sector == 30
    # S30's PDCSAP transits at half the depth.
    lc.flux[s30] -= box(lc.time[s30], 3.7, 1326.1, 0.12, 750e-6)
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.FAIL, result.evidence
    last = result.evidence["seasons"][2]
    assert last["status"] == "missed" and last["sigma"] >= CFG["min_sigma"], last


def test_expected_snr_stays_within_a_family():
    # The Task 3 review's case: the last season is all QLP, faint and diluted. Training on mostly
    # PDCSAP, the pooled expected SNR clears the power guard where QLP's own does not, and the
    # season's measured depth, here far below its expectation, reads as a miss.
    noise = {s: 300.0 for s in SECTORS} | {3: 600.0, 16: 600.0, 28: 2000.0, 29: 2000.0, 30: 2000.0}
    lc = planet_with_qlp(qlp_sectors=(3, 16, 28, 29, 30), noise_ppm=noise, seed=27)
    pooled = holdout(lc, EPH, CFG, 0.5)
    assert pooled.outcome is Outcome.FAIL
    last = pooled.evidence["seasons"][2]
    assert last["status"] == "missed" and last["expected_snr"] >= CFG["min_expected_snr"], last
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.PASS, result.evidence
    last = result.evidence["seasons"][2]
    assert last["status"] == "underpowered", last
    assert last["expected_snr"] < CFG["min_expected_snr"]
    qlp = last["family_depths"][0]
    assert qlp["family"] == "qlp" and np.isclose(last["expected_depth"], qlp["ref"])


def test_a_diluted_family_season_without_its_dip_is_still_missed():
    # QLP's own training depth shows the dip clearly, so its absence from an all-QLP season counts.
    lc = planet_with_qlp(qlp_sectors=(3, 16, 28, 29, 30), without_transits=(28, 29, 30))
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.FAIL, result.evidence
    last = result.evidence["seasons"][2]
    assert last["status"] == "missed" and last["expected_snr"] >= CFG["min_expected_snr"], last
    assert last["sigma"] < CFG["min_sigma"]


def test_a_held_out_family_without_training_cadences_is_untestable():
    lc = planet_with_qlp(qlp_sectors=(28, 29, 30))
    assert holdout(lc, EPH, CFG, 0.5).outcome is Outcome.FAIL
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.PASS, result.evidence
    last = result.evidence["seasons"][2]
    assert last["status"] == "untestable", last
    assert last["reason"] == "no training cadences in the held-out season's qlp family"


def test_tension_skipped_when_no_family_has_enough_held_out_cadences():
    lc = planet_with_qlp(qlp_sectors=(3, 16, 29))
    # The last season keeps three cadences near mid-transit in S28 (PDCSAP) and three in S29 (QLP):
    # six in all, enough to detect, under five in either family.
    central = np.abs(phase_days(lc.time, EPH)) < 0.015
    keep = ~((lc.sector >= 28) & in_transit(lc.time, EPH, 2.0))
    for sector in (28, 29):
        keep[np.flatnonzero((lc.sector == sector) & central)[:3]] = True
    result = holdout(lc.select(keep), EPH, CFG, 0.5, FAMILIES)
    last = result.evidence["seasons"][2]
    assert [row["n"] for row in last["family_depths"]] == [3, 3], last
    assert last["status"] == "predicted" and "tension" not in last, last
    assert last["tension_skipped"] == (
        "fewer than 5 held-out cadences in predicted transits in every family"
    )


def test_a_season_without_cadences_in_predicted_transits_is_not_tested():
    # A fourth season, so each season tested still trains on two that hold transits (decision 0035).
    lc = make_lc(
        sectors=SECTORS + (41, 42, 43),
        noise_ppm=300.0,
        signals=[(3.7, 1326.1, 0.12, 1500e-6)],
        seed=6,
    )
    lc = lc.select(~((lc.sector >= 41) & in_transit(lc.time, EPH, 2.0)))
    result = holdout(lc, EPH, CFG, 0.5)
    statuses = [s["status"] for s in result.evidence["seasons"]]
    assert statuses == ["predicted"] * 3 + ["no_predicted_transit_in_data"], statuses
    assert result.outcome is Outcome.PASS


SNAPSHOTS = Path(__file__).parent / "fixtures" / "m4-refactor"

# The light curves above, pinned before M4 lifted the reference and the judgement out of holdout.
HOLDOUT_CASES = {
    "planet_three_seasons": lambda: make_lc(
        sectors=SECTORS, noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=1
    ),
    "mixed_family": lambda: planet_with_qlp(qlp_sectors=MIXED_QLP),
    "untestable_family": lambda: planet_with_qlp(qlp_sectors=(28, 29, 30)),
    "underpowered_season": lambda: planet_with_qlp(
        qlp_sectors=(3, 16, 28, 29, 30),
        noise_ppm={s: 300.0 for s in SECTORS}
        | {3: 600.0, 16: 600.0, 28: 2000.0, 29: 2000.0, 30: 2000.0},
        seed=27,
    ),
    "training_transit_in_a_gap": lambda: last_season_with_one_transit(in_gap=True),
    "training_transit_with_few_core_cadences": lambda: last_season_with_one_transit(in_gap=False),
}


def as_json(value) -> str:
    return json.dumps(jsonable(value), sort_keys=True)


@pytest.mark.parametrize("split", ["pooled", "by_family"])
@pytest.mark.parametrize("case", list(HOLDOUT_CASES))
def test_holdout_evidence_is_unchanged(case, split):
    result = holdout(
        HOLDOUT_CASES[case](), EPH, CFG, 0.5, FAMILIES if split == "by_family" else None
    )
    expected = json.loads((SNAPSHOTS / "holdout.json").read_text())[case][split]
    assert as_json(result.to_dict()) == as_json(expected)


# The season row's fields holdout sets before it judges.
GATE_FIELDS = {
    "season",
    "start",
    "end",
    "training_seasons",
    "training_seasons_with_transits",
    "predicted_period",
    "predicted_t0",
}


@pytest.mark.parametrize("split", ["pooled", "by_family"])
@pytest.mark.parametrize("case", ["planet_three_seasons", "mixed_family"])
def test_judge_with_reference_equals_holdout_row(case, split):
    lc = HOLDOUT_CASES[case]()
    cfg_families = FAMILIES if split == "by_family" else None
    families = family_labels(lc, FAMILIES) if cfg_families else None
    labels = season_labels(lc.time, CFG["season_gap_days"])
    seasons = holdout(lc, EPH, CFG, 0.5, cfg_families).evidence["seasons"]
    tested = [s for s in seasons if s["status"] in ("predicted", "missed")]
    assert len(tested) == 3, seasons
    for row in tested:
        test = labels == row["season"]
        predicted = refit_ephemeris(lc.select(~test), EPH, CFG)
        assert (predicted.period, predicted.t0) == (row["predicted_period"], row["predicted_t0"])
        trained = reference(lc, families, ~test, predicted, 0.5)
        judged = judge(lc, families, test, predicted, trained, CFG, 0.5)
        assert set(row) - set(judged) == GATE_FIELDS
        assert as_json(judged) == as_json({name: row[name] for name in judged})


def test_judge_untestable_when_a_family_has_no_reference():
    # 241522065-1's new season: QLP beside 2-min sectors, with no QLP among the training seasons.
    lc = planet_with_qlp(qlp_sectors=(30,))
    families = family_labels(lc, FAMILIES)
    test = season_labels(lc.time, CFG["season_gap_days"]) == 2
    predicted = refit_ephemeris(lc.select(~test), EPH, CFG)
    trained = reference(lc, families, ~test, predicted, 0.5)
    assert set(trained["families"]) == {"pdcsap"}
    row = judge(lc, families, test, predicted, trained, CFG, 0.5)
    assert row["status"] == "untestable", row
    assert row["reason"] == "no training cadences in the held-out season's qlp family"
    qlp = next(r for r in row["family_depths"] if r["family"] == "qlp")
    assert (qlp["training_cadences"], qlp["ref_n"]) == (0, 0) and np.isnan(qlp["ref"]), qlp
    season = holdout(lc, EPH, CFG, 0.5, FAMILIES).evidence["seasons"][2]
    assert as_json(row) == as_json({name: season[name] for name in row})
