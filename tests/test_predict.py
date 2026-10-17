from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from astropy.time import Time

from tess_hunt import predict
from tess_hunt.config import load_criteria
from tess_hunt.fit import NAMES

ROOT = Path(__file__).resolve().parents[1]
PREDICT = load_criteria(ROOT / "criteria" / "vet-v3.toml")["predict"]
S110 = {"sector": 110, "start_utc": "2026-10-31T00:00:00", "end_utc": "2026-11-26T00:00:00"}


def posterior(t0, period, n=200_000) -> np.ndarray:
    """Fit-shaped samples (fit.NAMES columns) holding only the ephemeris."""
    samples = np.zeros((n, len(NAMES)))
    samples[:, NAMES.index("t0")] = t0
    samples[:, NAMES.index("period")] = period
    return samples


def btjd(utc: str) -> float:
    return Time(utc, scale="utc").tdb.jd - 2457000


def test_windows_follow_the_posterior():
    rng = np.random.default_rng(5)
    t0, period, sd_t0, sd_p = 4300.0, 3.0, 0.002, 0.0005
    samples = posterior(rng.normal(t0, sd_t0, 200_000), rng.normal(period, sd_p, 200_000))
    rows = predict.windows(samples, pd.DataFrame([S110]), [110], 0.12, PREDICT["sigma"])

    start, end = btjd(S110["start_utc"]), btjd(S110["end_utc"])
    inside = [n for n in range(100) if start <= t0 + n * period < end]
    assert [r["epoch"] for r in rows] == inside and len(inside) == 9
    for r in rows:
        n = r["epoch"]
        expected = np.hypot(sd_t0, n * sd_p) * 1440
        assert r["sd_minutes"] == pytest.approx(expected, rel=0.05), r
        assert r["mid_btjd"] == pytest.approx(t0 + n * period, abs=1e-3)
        assert r["half_width_minutes"] == {
            f"{s:g}": pytest.approx(s * r["sd_minutes"]) for s in PREDICT["sigma"]
        }
        assert r["sector"] == 110 and r["duration_days"] == 0.12

    # Anti-correlated t0 and period pivot at epoch 19: the posterior's mid-times there are nearly
    # fixed, where a propagation that ignored the correlation would read 19.3 minutes.
    p = rng.normal(period, sd_p, 200_000)
    pivoted = posterior(t0 - 19 * (p - period) + rng.normal(0.0, 1e-5, 200_000), p)
    at_19 = next(
        r
        for r in predict.windows(pivoted, pd.DataFrame([S110]), [110], 0.12, [1.0])
        if r["epoch"] == 19
    )
    assert at_19["sd_minutes"] < 0.1, at_19


def test_sector_without_dates_is_listed_as_unknown():
    sectors = pd.DataFrame([S110, {"sector": 111, "start_utc": None, "end_utc": None}])
    rows = predict.windows(posterior(4300.0, 3.0, n=10), sectors, [110, 111, 115], 0.12, [1.0])
    assert {r["sector"] for r in rows if "epoch" in r} == {110}
    assert [r for r in rows if "epoch" not in r] == [
        {"sector": 111, "dates": "unknown"},
        {"sector": 115, "dates": "unknown"},
    ]


def test_sectors_file_is_read_from_the_repo_root(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sectors = predict.load_sectors(PREDICT["sectors_file"])
    assert sectors["sector"].tolist() == [110, 111, 112, 113, 114]
    assert list(sectors.columns) == ["sector", "start_utc", "end_utc", "source", "read_on"]
    # TESS points from one sector straight into the next.
    assert sectors["start_utc"].iloc[1:].tolist() == sectors["end_utc"].iloc[:-1].tolist()
    assert PREDICT["first_sector"] == 110


def test_upcoming_sectors_leave_out_observed_sectors_and_a_star_off_the_cameras(monkeypatch):
    found = {}

    def stars2px(tic, ra, dec):
        # tess-point's own layout: index 3 holds sectors, one row per camera hit, [-1] for none.
        return (None, None, None, np.array(found[tic]), None, None, None, None, None)

    monkeypatch.setattr(predict, "tess_stars2px_function_entry", stars2px)
    found.update({1: [35, 62, 110, 111, 111, 113], 2: [-1]})
    assert predict.upcoming_sectors(1, 0.0, 0.0, 110) == [110, 111, 113]
    assert predict.upcoming_sectors(2, 0.0, 0.0, 110) == []


@pytest.mark.network
def test_upcoming_sectors_for_44926986():
    # The TIC position from the targets run; tess-point's pointing tables are installed with it.
    assert predict.upcoming_sectors(44926986, 146.852182941572, -39.8797286285282, 110) == [
        110,
        111,
        112,
        113,
    ]
