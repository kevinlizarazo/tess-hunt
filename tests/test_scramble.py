from pathlib import Path

import numpy as np
from synthetic import make_lc

from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.scramble import scramble, segments
from tess_hunt.search import search_star

ROOT = Path(__file__).resolve().parents[1]
CRIT = load_criteria(ROOT / "criteria" / "search-v2.toml")
NULL = CRIT["null"]


def run(lc, seed=1):
    return scramble(lc, NULL["segment_gap_days"], NULL["placement_gap_days"], seed)


def test_segments_split_at_orbit_gaps_and_sector_changes():
    lc = make_lc(sectors=(1, 2))
    labels = segments(lc.time, lc.sector, 0.5)
    assert len(np.unique(labels)) == 4


def test_sector_without_gaps_is_one_segment():
    t = np.arange(0.0, 27.0, 0.02)
    assert len(np.unique(segments(t, np.full(len(t), 63), 0.5))) == 1


def test_scramble_is_a_permutation_with_increasing_time():
    lc = make_lc(sectors=(1, 2, 3, 4), seed=2)
    out, order = run(lc)
    assert sorted(order) == list(range(len(lc.time)))
    np.testing.assert_array_equal(out.flux, lc.flux[order])
    np.testing.assert_array_equal(out.sector, lc.sector[order])
    assert np.all(np.diff(out.time) > 0)
    assert not np.array_equal(order, np.arange(len(order)))


def test_same_seed_and_tic_give_the_same_scramble():
    lc = make_lc(sectors=(1, 2, 3, 4), seed=2)
    np.testing.assert_array_equal(run(lc)[1], run(lc)[1])
    assert not np.array_equal(run(lc, seed=1)[1], run(lc, seed=2)[1])
    other = make_lc(sectors=(1, 2, 3, 4), seed=2, tic=2)
    assert not np.array_equal(run(lc)[1], run(other)[1])


def test_single_sector_star_swaps_its_orbits():
    lc = make_lc(sectors=(1,), seed=3)
    second_orbit_start = np.flatnonzero(np.diff(lc.time) > 0.5)[0] + 1
    firsts = {int(run(lc, seed)[1][0]) for seed in range(1, 11)}
    assert firsts == {0, second_orbit_start}


def test_masks_follow_their_cadences():
    lc = make_lc(sectors=(1, 2, 3), seed=4)
    flagged = np.zeros(len(lc.time), dtype=bool)
    flagged[::97] = True
    lc.flux[flagged] = 2.0
    out, order = run(lc)
    np.testing.assert_array_equal(out.flux == 2.0, flagged[order])


def test_scramble_decoheres_a_planet():
    lc = make_lc(
        sectors=(1, 2, 3, 4, 5, 6, 7, 8),
        noise_ppm=300.0,
        signals=[(3.7, 1326.1, 0.12, 1500e-6)],
        seed=6,
    )
    cfg = CRIT["search"]
    plain = search_star(lc, 1.0, 1.0, cfg).signals
    truth = Ephemeris(3.7, 1326.1, 0.12)
    assert ephemeris_match(plain[0].ephemeris(), truth) is not None
    scrambled = search_star(run(lc)[0], 1.0, 1.0, cfg).signals
    assert scrambled[0].sde < 0.5 * plain[0].sde
