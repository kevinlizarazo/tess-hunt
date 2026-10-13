from pathlib import Path

import numpy as np
from synthetic import make_lc

from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend, known_mask
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


def test_exclude_drops_cadences_like_a_mask():
    lc = make_lc(sectors=(1,), noise_ppm=200.0, seed=4)
    exclude = (lc.time > 1330.0) & (lc.time < 1331.0)
    flat = detrend(lc, CFG, exclude=exclude)
    assert not np.any((flat.time > 1330.0) & (flat.time < 1331.0))
    assert len(flat.time) >= len(lc.time) - exclude.sum() - 200  # only orbit-edge cuts besides


def test_exclude_matches_an_ephemeris_mask():
    # The null maps the known-planet mask through the scramble and passes it as exclude.
    lc = make_lc(sectors=(1, 2), signals=[PLANET], seed=1)
    eph = Ephemeris(*PLANET[:3])
    by_mask = detrend(lc, CFG, [eph])
    by_exclude = detrend(lc, CFG, exclude=known_mask(lc.time, [eph], CFG["known_mask_width"]))
    for field in ("time", "flux", "flux_err", "sector"):
        np.testing.assert_array_equal(getattr(by_mask, field), getattr(by_exclude, field))


def test_hold_out_keeps_the_transit_and_its_depth():
    eph = Ephemeris(4.0, 1327.0, 0.4, 0.004)
    lc = make_lc(sectors=(1, 2), noise_ppm=100.0, signals=[(4.0, 1327.0, 0.4, 0.004)], seed=5)
    held = detrend(lc, CFG, hold_out=in_transit(lc.time, eph, 2.0))
    inside = in_transit(held.time, eph, 0.5)
    assert inside.sum() > 50
    assert abs((1.0 - np.median(held.flux[inside])) - 0.004) < 0.0004


def test_hold_out_stops_a_shallow_transit_bending_the_trend():
    # The biweight already rejects a deep dip; a shallow one bends the trend unless held out.
    eph = Ephemeris(4.0, 1327.0, 0.4, 0.0005)
    lc = make_lc(sectors=(1, 2), noise_ppm=100.0, signals=[(4.0, 1327.0, 0.4, 0.0005)], seed=5)

    def depth(**kw):
        flat = detrend(lc, CFG, **kw)
        return 1.0 - np.median(flat.flux[in_transit(flat.time, eph, 0.5)])

    assert abs(depth(hold_out=in_transit(lc.time, eph, 2.0)) - 0.0005) < 0.1 * 0.0005
    assert depth() < 0.9 * 0.0005
