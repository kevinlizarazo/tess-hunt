import numpy as np
import pandas as pd
import pytest

from tess_hunt.catalogs import KNOWN_COLUMNS
from tess_hunt.checks import Outcome
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.novelty import check_novelty

HARMONICS = (1.0, 0.5, 2.0, 1 / 3, 3.0)


@pytest.fixture
def known():
    rows = [
        ("TOI", "candidate", "TOI-500.01", 100, 10.0, -60.0, 3.0, 1500.0, 0.1, 1000.0),
        ("CTOI", "candidate", "CTOI-200.01", 200, 10.0, -60.03, 7.0, 1502.0, 0.15, 800.0),
        ("archive", "planet", "Far b", 300, 50.0, 10.0, 5.0, 1501.0, 0.1, 500.0),
        ("TOI", "candidate", "TOI-600.01", 400, 20.0, -50.0, np.nan, np.nan, np.nan, 700.0),
    ]
    return pd.DataFrame(rows, columns=KNOWN_COLUMNS)


def check(known, tic, ra, dec, eph):
    return check_novelty(tic, ra, dec, eph, known, 2.5, HARMONICS, 2.5, 2.0)


def test_known_toi_on_same_star_fails(known):
    result = check(known, 100, 10.0, -60.0, Ephemeris(3.0, 1500.0, 0.1))
    assert result.outcome is Outcome.FAIL
    assert result.evidence["matches"][0]["name"] == "TOI-500.01"


def test_new_period_on_known_star_passes(known):
    assert check(known, 100, 10.0, -60.0, Ephemeris(4.1, 1500.3, 0.1)).outcome is Outcome.PASS


def test_neighbour_within_blend_radius_fails(known):
    result = check(known, 999, 10.0, -60.0, Ephemeris(7.0, 1502.0, 0.15))
    assert result.outcome is Outcome.FAIL
    assert result.evidence["matches"][0]["name"] == "CTOI-200.01"


def test_neighbour_beyond_blend_radius_passes(known):
    assert check(known, 999, 10.0, -60.09, Ephemeris(7.0, 1502.0, 0.15)).outcome is Outcome.PASS


def test_half_period_harmonic_is_known(known):
    result = check(known, 100, 10.0, -60.0, Ephemeris(1.5, 1500.0, 0.1))
    assert result.outcome is Outcome.FAIL and result.evidence["matches"][0]["ratio"] == 0.5


def test_empty_catalog_is_inconclusive_not_pass(known):
    empty = known.iloc[0:0]
    assert (
        check(empty, 100, 10.0, -60.0, Ephemeris(9.9, 1500.0, 0.1)).outcome is Outcome.INCONCLUSIVE
    )


def test_missing_catalog_source_is_inconclusive(known):
    partial = known[known["source"] != "CTOI"]
    assert (
        check(partial, 100, 10.0, -60.0, Ephemeris(9.9, 1500.0, 0.1)).outcome
        is Outcome.INCONCLUSIVE
    )


def test_known_object_without_period_on_same_star_is_inconclusive(known):
    assert (
        check(known, 400, 20.0, -50.0, Ephemeris(9.9, 1500.0, 0.1)).outcome is Outcome.INCONCLUSIVE
    )


def test_same_star_period_match_out_of_phase_is_inconclusive(known):
    result = check(known, 100, 10.0, -60.0, Ephemeris(3.0, 1501.5, 0.1))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert result.evidence["period_matches"][0]["name"] == "TOI-500.01"


def test_neighbour_period_match_out_of_phase_is_inconclusive(known):
    result = check(known, 999, 10.0, -60.0, Ephemeris(7.0, 1505.5, 0.15))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert result.evidence["period_matches"][0]["name"] == "CTOI-200.01"


def test_neighbour_at_half_period_out_of_phase_passes(known):
    assert check(known, 999, 10.0, -60.0, Ephemeris(3.5, 1503.75, 0.15)).outcome is Outcome.PASS


def test_missing_candidate_position_is_inconclusive(known):
    # A NaN position finds no neighbours, so without the guard this copy of CTOI-200.01 would pass.
    result = check(known, 999, np.nan, -60.0, Ephemeris(7.0, 1502.0, 0.15))
    assert result.outcome is Outcome.INCONCLUSIVE
    assert result.reason == "candidate position or ephemeris missing"


def known_rows(*rows):
    base = {
        "source": "x",
        "kind": "candidate",
        "name": "n",
        "tic": 1,
        "ra": 10.0,
        "dec": -50.0,
        "period": 3.0,
        "t0": 100.0,
        "duration": 0.1,
        "depth_ppm": 500.0,
    }
    required = [
        {**base, "source": s, "tic": 999, "ra": 200.0, "dec": 60.0}
        for s in ("TOI", "CTOI", "archive")
    ]
    return pd.DataFrame([*required, *({**base, **r} for r in rows)])


def novelty(known):
    return check_novelty(
        1,
        10.0,
        -50.0,
        Ephemeris(3.0, 100.0, 0.1),
        known,
        2.5,
        HARMONICS,
        2.5,
        2.0,
        inconclusive_kinds=("tce",),
    )


def test_tce_only_match_is_inconclusive_known_to_spoc():
    result = novelty(known_rows({"source": "SPOC-TCE", "kind": "tce"}))
    assert result.outcome is Outcome.INCONCLUSIVE and result.evidence["category"] == "known_to_spoc"
    assert result.evidence["tce_matches"][0]["source"] == "SPOC-TCE"


def test_a_candidate_match_fails_even_beside_a_tce():
    result = novelty(
        known_rows(
            {"source": "SPOC-TCE", "kind": "tce"}, {"source": "eumemic", "kind": "community"}
        )
    )
    assert result.outcome is Outcome.FAIL and result.evidence["category"] == "known"


def test_an_eb_match_fails():
    assert novelty(known_rows({"source": "prsa2022", "kind": "eb"})).outcome is Outcome.FAIL


def test_nothing_known_passes():
    assert novelty(known_rows()).outcome is Outcome.PASS


def test_tce_period_match_out_of_phase_is_known_to_spoc():
    result = novelty(known_rows({"source": "ExoMiner-v2", "kind": "tce", "t0": 101.5}))
    assert result.outcome is Outcome.INCONCLUSIVE and result.evidence["category"] == "known_to_spoc"
    assert result.evidence["tce_period_matches"][0]["source"] == "ExoMiner-v2"


def test_tce_match_fails_unless_its_kind_is_listed_inconclusive():
    known = known_rows({"source": "SPOC-TCE", "kind": "tce"})
    result = check_novelty(
        1, 10.0, -50.0, Ephemeris(3.0, 100.0, 0.1), known, 2.5, HARMONICS, 2.5, 2.0
    )
    assert result.outcome is Outcome.FAIL and result.evidence["category"] == "known"


def test_every_non_pass_outcome_carries_a_category(known):
    cases = {
        "missing_input": check(known, 999, np.nan, -60.0, Ephemeris(7.0, 1502.0, 0.15)),
        "catalogs_not_loaded": check(
            known[known["source"] != "CTOI"], 100, 10.0, -60.0, Ephemeris(9.9, 1500.0, 0.1)
        ),
        "known": check(known, 100, 10.0, -60.0, Ephemeris(3.0, 1500.0, 0.1)),
        "stale_catalog_epoch": check(known, 100, 10.0, -60.0, Ephemeris(3.0, 1501.5, 0.1)),
        "no_period_object": check(known, 400, 20.0, -50.0, Ephemeris(9.9, 1500.0, 0.1)),
    }
    assert {name: r.evidence["category"] for name, r in cases.items()} == {c: c for c in cases}
