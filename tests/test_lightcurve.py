import numpy as np
import pytest

from tess_hunt.lightcurve import LightCurve


def make() -> LightCurve:
    return LightCurve(
        42,
        np.linspace(1.0, 2.0, 4),
        np.ones(4),
        np.full(4, 1e-3),
        np.array([5, 5, 6, 6], dtype=np.int16),
        {
            "5": {"provenance": "SPOC", "cadence_s": 120.0},
            "6": {"provenance": "QLP", "cadence_s": 1800.0},
        },
    )


def test_round_trip_and_no_temp_file_left(tmp_path):
    lc = make()
    lc.save(tmp_path / "42.npz")
    back = LightCurve.load(tmp_path / "42.npz")
    assert back.tic == 42 and back.sources == lc.sources
    for name in ("time", "flux", "flux_err", "sector"):
        np.testing.assert_array_equal(getattr(back, name), getattr(lc, name))
    assert [p.name for p in tmp_path.iterdir()] == ["42.npz"]


def test_lengths_must_match():
    with pytest.raises(ValueError):
        LightCurve(1, np.ones(3), np.ones(2), np.ones(3), np.ones(3, dtype=np.int16))


def test_exposure_days_per_sector():
    expected = [120 / 86400, 120 / 86400, 1800 / 86400, 1800 / 86400]
    np.testing.assert_allclose(make().exposure_days(), expected)


def test_select_keeps_sources():
    lc = make()
    sub = lc.select(lc.sector == 6)
    assert len(sub.time) == 2 and sub.sources is lc.sources


def test_failed_write_leaves_nothing_that_globs_as_a_light_curve(tmp_path, monkeypatch):
    def broken(fh, **arrays):
        fh.write(b"partial")
        raise OSError("disk full")

    monkeypatch.setattr("tess_hunt.lightcurve.np.savez_compressed", broken)
    with pytest.raises(OSError):
        make().save(tmp_path / "42.npz")
    assert list(tmp_path.glob("*.npz")) == []
