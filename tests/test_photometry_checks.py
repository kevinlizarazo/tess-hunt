import numpy as np
from synthetic import box, make_lc

from tess_hunt.checks import Outcome
from tess_hunt.checks.photometry import box_depth, odd_even, secondary, sector_depths
from tess_hunt.ephemeris import Ephemeris, in_transit

EPH = Ephemeris(3.7, 1326.1, 0.12)
PLANET = (3.7, 1326.1, 0.12, 2000e-6)


def test_box_depth_of_a_box():
    lc = make_lc(signals=[PLANET], noise_ppm=1.0)
    depth, err, n = box_depth(lc.time, lc.flux, lc.flux_err, EPH, 0.5)
    assert abs(depth - 2000e-6) < 1e-6 and n > 0 and err > 0


def test_odd_even_negative_control_eclipsing_binary_at_twice_the_period():
    eb = [(7.4, 1326.1, 0.12, 3000e-6), (7.4, 1326.1 + 3.7, 0.12, 1500e-6)]
    result = odd_even(make_lc(noise_ppm=300.0, signals=eb, seed=1), EPH, 0.5, 3.0, 5)
    assert result.outcome is Outcome.FAIL and result.evidence["sigma"] > 3.0


def test_odd_even_planet_passes():
    assert (
        odd_even(make_lc(noise_ppm=300.0, signals=[PLANET], seed=2), EPH, 0.5, 3.0, 5).outcome
        is Outcome.PASS
    )


def test_odd_even_without_transit_data_is_inconclusive():
    lc = make_lc(noise_ppm=300.0, signals=[PLANET], seed=3)
    lc = lc.select(~in_transit(lc.time, EPH, width=3.0))
    assert odd_even(lc, EPH, 0.5, 3.0, 5).outcome is Outcome.INCONCLUSIVE


def test_secondary_negative_control_eclipse_at_half_phase():
    eb = [PLANET, (3.7, 1326.1 + 1.85, 0.12, 1000e-6)]
    result = secondary(make_lc(noise_ppm=300.0, signals=eb, seed=4), EPH, 3.0, 5)
    assert result.outcome is Outcome.FAIL


def test_secondary_planet_passes():
    assert (
        secondary(make_lc(noise_ppm=300.0, signals=[PLANET], seed=5), EPH, 3.0, 5).outcome
        is Outcome.PASS
    )


def test_secondary_without_half_phase_coverage_is_inconclusive():
    lc = make_lc(noise_ppm=300.0, signals=[PLANET], seed=6)
    half = Ephemeris(3.7, 1326.1 + 1.85, 0.12)
    lc = lc.select(~in_transit(lc.time, half, width=3.0))
    assert secondary(lc, EPH, 3.0, 5).outcome is Outcome.INCONCLUSIVE


def test_sector_depth_negative_control_depth_changes_between_sectors():
    lc = make_lc(
        sectors=(1, 2, 3, 4, 5, 6), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 300e-6)], seed=7
    )
    early = lc.sector <= 3
    lc.flux[early] += box(lc.time[early], 3.7, 1326.1, 0.12, 1700e-6)
    result = sector_depths(lc, EPH, 0.5, 0.001, 5)
    assert result.outcome is Outcome.FAIL and result.evidence["p_value"] < 0.001


def test_sector_depth_constant_passes():
    lc = make_lc(sectors=(1, 2, 3, 4), noise_ppm=300.0, signals=[PLANET], seed=8)
    assert sector_depths(lc, EPH, 0.5, 0.001, 5).outcome is Outcome.PASS


def test_sector_depth_mixed_cadence_planet_passes():
    lc = make_lc(
        sectors=(1, 2, 3, 4),
        cadences={1: 2.0, 2: 2.0, 3: 30.0, 4: 30.0},
        noise_ppm={1: 1100.0, 2: 1100.0, 3: 300.0, 4: 300.0},
        signals=[(3.7, 1326.1, 0.125, 2000e-6)],
        seed=9,
    )
    assert sector_depths(lc, Ephemeris(3.7, 1326.1, 0.125), 0.5, 0.001, 5).outcome is Outcome.PASS


def test_sector_depth_single_sector_is_inconclusive():
    lc = make_lc(sectors=(1,), noise_ppm=300.0, signals=[PLANET], seed=10)
    assert sector_depths(lc, EPH, 0.5, 0.001, 5).outcome is Outcome.INCONCLUSIVE


def test_box_depth_empty_is_nan():
    depth, err, n = box_depth(np.array([]), np.array([]), np.array([]), EPH, 0.5)
    assert n == 0 and np.isnan(depth) and np.isnan(err)
