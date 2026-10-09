from pathlib import Path

import numpy as np
from synthetic import make_lc

from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit

CFG = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "search-v1.toml")["detrend"]
PLANET = (3.7, 1326.1, 0.12, 1000e-6)


def test_removes_trend_and_keeps_transit_depth():
    lc = make_lc(sectors=(1,), cadence_min=2.0, noise_ppm=300.0, signals=[PLANET], seed=9)
    lc.flux = lc.flux * (1.0 + 0.002 * np.sin(2 * np.pi * lc.time / 10.0))
    flat = detrend(lc, CFG)
    eph = Ephemeris(*PLANET[:3])
    core = in_transit(flat.time, eph, width=0.5)
    out = ~in_transit(flat.time, eph, width=2.0)
    assert np.std(flat.flux[out]) < 1.3 * 300e-6
    assert abs((1 - np.mean(flat.flux[core])) - 1000e-6) < 0.25 * 1000e-6


def test_masked_transits_are_removed():
    lc = make_lc(sectors=(1, 2), signals=[PLANET], seed=1)
    eph = Ephemeris(*PLANET[:3])
    flat = detrend(lc, CFG, mask=[eph])
    assert not in_transit(flat.time, eph).any()


def test_long_masked_transits_do_not_split_segments():
    planet = (3.0, 1326.0, 0.3, 1000e-6)
    lc = make_lc(sectors=(1,), cadence_min=2.0, noise_ppm=300.0, signals=[planet], seed=6)
    lc.flux = lc.flux * (1.0 + 0.002 * np.sin(2 * np.pi * lc.time / 10.0))
    eph = Ephemeris(*planet[:3])
    flat = detrend(lc, CFG, mask=[eph])
    masked = in_transit(lc.time, eph, CFG["known_mask_width"])
    # Edge cuts belong only at the sector ends and the orbit gap, never beside a masked transit.
    gap = np.argmax(np.diff(lc.time)) + 1
    ends = lc.time[[0, gap - 1, gap, -1]]
    near_end = np.min(np.abs(lc.time[:, None] - ends), axis=1) < CFG["edge_cutoff_days"]
    expected = np.sum(~masked & ~near_end)
    assert abs(len(flat.time) - expected) < 0.02 * expected
    assert not in_transit(flat.time, eph, CFG["known_mask_width"]).any()
    assert np.std(flat.flux) < 1.3 * 300e-6


def test_upward_outlier_clipped():
    lc = make_lc(sectors=(1,), noise_ppm=200.0, seed=2)
    lc.flux[300] += 0.01
    flat = detrend(lc, CFG)
    assert flat.flux.max() < 1.0 + 5 * 200e-6


def test_tiny_sector_dropped():
    lc = make_lc(sectors=(1, 2), seed=3)
    keep = (lc.sector == 1) | (np.arange(len(lc.time)) % 20 == 0)
    flat = detrend(lc.select(keep), CFG)
    assert set(np.unique(flat.sector)) == {1}


def test_errors_follow_each_sectors_scatter():
    lc = make_lc(sectors=(1, 2), cadences={1: 2.0, 2: 30.0}, noise_ppm={1: 800.0, 2: 200.0}, seed=4)
    flat = detrend(lc, CFG)
    for sector, noise in ((1, 800e-6), (2, 200e-6)):
        err = flat.flux_err[flat.sector == sector]
        assert np.allclose(err, err[0]) and abs(err[0] - noise) < 0.15 * noise


def test_nothing_usable_gives_empty_light_curve():
    lc = make_lc(sectors=(1,), seed=5)
    flat = detrend(lc.select(np.arange(len(lc.time)) < 50), CFG)
    assert len(flat.time) == 0
