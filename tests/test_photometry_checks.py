from pathlib import Path

import numpy as np
from synthetic import box, correlated_noise, make_lc

from tess_hunt.checks import Outcome
from tess_hunt.checks.photometry import (
    box_depth,
    odd_even,
    red_noise_beta,
    secondary,
    sector_depths,
    with_red_noise,
)
from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit

EPH = Ephemeris(3.7, 1326.1, 0.12)
PLANET = (3.7, 1326.1, 0.12, 2000e-6)
DETREND = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "search-v1.toml").values[
    "detrend"
]


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


def test_red_noise_beta_is_one_on_white_noise():
    lc = make_lc(
        sectors=(1, 2, 3, 4),
        cadences={1: 2.0, 2: 2.0, 3: 30.0, 4: 30.0},
        noise_ppm=300.0,
        signals=[PLANET],
        seed=11,
    )
    three_hours = red_noise_beta(lc, EPH, 0.125)
    assert set(three_hours) == {"1", "2", "3", "4"}
    assert all(abs(row["beta"] - 1.0) < 0.15 and "note" not in row for row in three_hours.values())
    # 72 minutes is 36 two-minute cadences but under three 30-minute ones.
    short = red_noise_beta(lc, EPH, 0.05)
    assert all(abs(short[s]["beta"] - 1.0) < 0.15 and "note" not in short[s] for s in ("1", "2"))
    assert all(short[s]["beta"] == 1.0 and "note" in short[s] for s in ("3", "4"))
    too_few_bins = red_noise_beta(lc, EPH, 0.125, min_bins=10_000)
    assert all(row["beta"] == 1.0 and "note" in row for row in too_few_bins.values())


def red_noise_lc(signals=(), seed=12):
    """Detrended 2-min sectors whose residuals stay correlated over a transit."""
    lc = make_lc(
        sectors=tuple(range(1, 11)), cadence_min=2.0, noise_ppm=500.0, signals=signals, seed=seed
    )
    lc.flux += correlated_noise(lc, 200.0, 1.5, seed)
    return detrend(lc, DETREND)


def test_red_noise_beta_sees_correlated_noise():
    betas = red_noise_beta(red_noise_lc(), EPH, 0.5 * EPH.duration)
    assert all(row["beta"] > 1.3 for row in betas.values()), betas


def test_sector_depth_red_noise_fails_on_white_errors_and_passes_inflated():
    lc = red_noise_lc(signals=[PLANET])
    white = sector_depths(lc, EPH, 0.5, 0.001, 5)
    red = sector_depths(
        with_red_noise(lc, red_noise_beta(lc, EPH, 0.5 * EPH.duration)), EPH, 0.5, 0.001, 5
    )
    assert white.outcome is Outcome.FAIL, white.evidence["p_value"]
    assert red.outcome is Outcome.PASS, red.evidence["p_value"]


def test_with_red_noise_scales_each_sectors_errors():
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=13)
    noisy = with_red_noise(lc, {"1": {"beta": 2.0}, "2": {"beta": 1.5}})
    assert np.allclose(
        noisy.flux_err / lc.flux_err, np.select([lc.sector == 1, lc.sector == 2], [2.0, 1.5], 1.0)
    )
    assert np.array_equal(noisy.flux, lc.flux) and np.allclose(lc.flux_err, 300e-6)
