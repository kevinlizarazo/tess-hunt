import numpy as np
from synthetic import box, make_lc

from tess_hunt.checks import Outcome
from tess_hunt.checks.holdout import holdout, season_labels
from tess_hunt.ephemeris import Ephemeris

CFG = {
    "season_gap_days": 60.0,
    "min_expected_snr": 4.0,
    "min_sigma": 2.0,
    "max_depth_tension": 3.0,
    "min_points": 5,
}
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


def test_underpowered_seasons_are_inconclusive_not_fail():
    lc = make_lc(sectors=SECTORS, noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 60e-6)], seed=4)
    result = holdout(lc, EPH, CFG, 0.5)
    assert result.outcome is Outcome.INCONCLUSIVE
    assert {s["status"] for s in result.evidence["seasons"]} == {"underpowered"}
