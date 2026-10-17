from pathlib import Path

import numpy as np
from synthetic import make_lc, with_products

from tess_hunt.checks import Outcome, failed, inconclusive, passed
from tess_hunt.checks.families import family_of, good_timestamps, per_family, split
from tess_hunt.config import load_criteria

FAMILIES = load_criteria(Path(__file__).resolve().parents[1] / "criteria" / "vet-v3.toml")[
    "families"
]


def test_family_of_known_and_unknown_provenance():
    assert family_of({"provenance": "SPOC"}, FAMILIES) == "pdcsap"
    assert family_of({"provenance": "TESS-SPOC"}, FAMILIES) == "pdcsap"
    assert family_of({"provenance": "QLP"}, FAMILIES) == "qlp"
    assert family_of({"provenance": "synthetic"}, FAMILIES) == "synthetic"
    # `fit` names the fitted family; it lists no provenances, so a substring of it is no member.
    assert family_of({"provenance": "dcs"}, FAMILIES) == "dcs"


def test_split_groups_sectors_by_family():
    lc = with_products(make_lc(sectors=(1, 2, 3, 4)), {1: "SPOC", 2: "QLP", 3: "TESS-SPOC"})
    parts = split(lc, FAMILIES)
    assert {name: np.unique(part.sector).tolist() for name, part in parts.items()} == {
        "pdcsap": [1, 3],
        "qlp": [2],
        "synthetic": [4],
    }
    assert sum(len(part.time) for part in parts.values()) == len(lc.time)


def test_good_timestamps_drops_flagged_sectors():
    lc = with_products(make_lc(sectors=(98, 99, 100, 101)), {98: "QLP", 99: "QLP"}, suspect={99})
    lc.sources["100"]["timing_suspect"] = True
    good = good_timestamps(lc)
    assert np.unique(good.sector).tolist() == [98, 101]
    assert sorted(good.sources) == ["101", "98"]
    keep = np.isin(lc.sector, [98, 101])
    assert np.array_equal(good.time, lc.time[keep]) and np.array_equal(good.flux, lc.flux[keep])


def test_per_family_fail_beats_pass_and_none_passing_is_inconclusive():
    ok = passed("odd_even", "agree")
    bad = failed("odd_even", "differ")
    unsure = inconclusive("odd_even", "too few cadences")
    result = per_family("odd_even", {"pdcsap": bad, "qlp": ok})
    assert result.check == "odd_even" and result.outcome is Outcome.FAIL
    assert result.evidence["families"] == {"pdcsap": bad.to_dict(), "qlp": ok.to_dict()}
    assert per_family("odd_even", {"pdcsap": unsure, "qlp": ok}).outcome is Outcome.PASS
    assert per_family("odd_even", {"pdcsap": unsure, "qlp": unsure}).outcome is Outcome.INCONCLUSIVE
    assert per_family("odd_even", {}).outcome is Outcome.INCONCLUSIVE
