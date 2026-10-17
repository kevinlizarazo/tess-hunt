from pathlib import Path

import numpy as np
from synthetic import box, make_lc, with_products

from tess_hunt.checks import Outcome
from tess_hunt.checks.holdout import holdout, season_labels
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, in_transit

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


def test_underpowered_seasons_are_inconclusive_not_fail():
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 60e-6)], seed=4)
    result = holdout(lc, EPH, CFG, 0.5)
    assert result.outcome is Outcome.INCONCLUSIVE
    assert {s["status"] for s in result.evidence["seasons"]} == {"underpowered"}


def planet_with_qlp(qlp_sectors, depth=1500e-6, dilution=0.6, seed=5):
    """The planet in every season; the QLP sectors read its depth diluted, as on a crowded star
    (results/benchmarks/qlp-dilution-2026-10-13.txt)."""
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, seed=seed)
    for sector in SECTORS:
        m = lc.sector == sector
        scale = dilution if sector in qlp_sectors else 1.0
        lc.flux[m] += box(lc.time[m], 3.7, 1326.1, 0.12, depth * scale)
    products = {s: "QLP" if s in qlp_sectors else "SPOC" for s in SECTORS}
    return with_products(lc, products)


def test_family_tension_compares_like_with_like():
    lc = planet_with_qlp(qlp_sectors=(29, 30))
    # Mixed with QLP, the last season reads shallower than the all-PDCSAP seasons that train it.
    assert holdout(lc, EPH, CFG, 0.5).outcome is Outcome.FAIL
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.PASS, result.evidence
    seasons = result.evidence["seasons"]
    assert [s["status"] for s in seasons] == ["predicted"] * 3
    rows = {row["family"]: row for row in seasons[2]["family_tension"]}
    # The training seasons have no QLP, so only PDCSAP is compared.
    assert set(rows) == {"pdcsap", "qlp"} and "tension" not in rows["qlp"], rows
    assert seasons[2]["tension"] == rows["pdcsap"]["tension"]


def test_family_tension_still_fails_a_depth_change_inside_a_family():
    lc = planet_with_qlp(qlp_sectors=(29, 30))
    s28 = lc.sector == 28
    # S28's PDCSAP transits at half the depth.
    lc.flux[s28] -= box(lc.time[s28], 3.7, 1326.1, 0.12, 750e-6)
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.FAIL, result.evidence
    last = result.evidence["seasons"][2]
    assert last["status"] == "missed" and last["sigma"] >= CFG["min_sigma"], last


def test_tension_skipped_without_a_shared_family():
    lc = planet_with_qlp(qlp_sectors=(28, 29, 30))
    assert holdout(lc, EPH, CFG, 0.5).outcome is Outcome.FAIL
    result = holdout(lc, EPH, CFG, 0.5, FAMILIES)
    assert result.outcome is Outcome.PASS, result.evidence
    last = result.evidence["seasons"][2]
    assert last["tension_skipped"] == "no training cadences in the held-out season's family"
    assert "tension" not in last
    # Detection still uses every cadence of the season.
    assert last["status"] == "predicted" and last["sigma"] >= CFG["min_sigma"]


def test_a_season_without_cadences_in_predicted_transits_is_not_tested():
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=6)
    lc = lc.select(~((lc.sector >= 28) & in_transit(lc.time, EPH, 2.0)))
    result = holdout(lc, EPH, CFG, 0.5)
    statuses = [s["status"] for s in result.evidence["seasons"]]
    assert statuses == ["predicted", "predicted", "no_predicted_transit_in_data"], statuses
    assert result.outcome is Outcome.PASS
