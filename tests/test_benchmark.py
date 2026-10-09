from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc

from tess_hunt.benchmark import classify, completeness, injection_job, md_table
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.search import Signal

ROOT = Path(__file__).resolve().parents[1]
CRIT = load_criteria(ROOT / "criteria" / "search-v1.toml").values
MATCH = CRIT["match"]


def sig(period, t0=100.0, sde=20.0, rank=1):
    return Signal(1, rank, period, t0, 0.1, 1e-3, 10.0, sde, 5)


def test_classify_recovered():
    out = classify(Ephemeris(3.0, 100.0, 0.1), [sig(3.0)], MATCH, 9.0)
    assert out["recovered"] and not out["alias"]


def test_classify_below_threshold_is_not_recovery():
    assert not classify(Ephemeris(3.0, 100.0, 0.1), [sig(3.0, sde=8.0)], MATCH, 9.0)["recovered"]


def test_classify_alias_is_not_recovery():
    out = classify(Ephemeris(3.0, 100.0, 0.1), [sig(6.0)], MATCH, 9.0)
    assert out["alias"] and not out["recovered"]


def test_classify_missed():
    out = classify(Ephemeris(3.0, 100.0, 0.1), [sig(4.4)], MATCH, 9.0)
    assert not out["recovered"] and not out["alias"]


def test_completeness_fractions():
    rows = pd.DataFrame(
        {
            "status": "ok",
            "engine": "bls30",
            "expected_snr": [6.0, 6.0, 12.0, 12.0],
            "recovered": [False, True, True, True],
        }
    )
    table = completeness(rows, "expected_snr", [0, 10, 20])
    assert list(table["fraction"]) == [0.5, 1.0] and list(table["count"]) == [2, 2]


def test_md_table():
    assert (
        md_table(pd.DataFrame({"a": [1.23456], "b": ["x"]})) == "| a | b |\n|---|---|\n| 1.23 | x |"
    )


@pytest.mark.slow
def test_injection_job_recovers_a_large_planet(tmp_path):
    path = tmp_path / "1.npz"
    make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=3).save(path)
    crit = {
        **CRIT,
        "benchmark": {
            **CRIT["benchmark"],
            "inject_rp_min_rearth": 8.0,
            "inject_rp_max_rearth": 10.0,
        },
    }
    star = {"tic": 1, "rad": 1.0, "mass": 1.0}
    rows = injection_job((star, path, [], crit, ["bls30"], 1, 11))
    assert len(rows) == 1 and rows[0]["recovered"] and rows[0]["expected_snr"] > 20
    assert np.isfinite(rows[0]["runtime_s"])
