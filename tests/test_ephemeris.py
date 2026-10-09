import numpy as np

from tess_hunt.ephemeris import (
    Ephemeris,
    ephemeris_match,
    in_transit,
    phase_days,
    transit_times_in_data,
)


def test_phase_days():
    eph = Ephemeris(2.0, 10.0, 0.2)
    np.testing.assert_allclose(phase_days(np.array([10.0, 10.9, 11.6]), eph), [0.0, 0.9, -0.4])


def test_in_transit_width():
    eph = Ephemeris(2.0, 10.0, 0.2)
    t = np.array([9.85, 9.95, 10.05, 10.15])
    assert list(in_transit(t, eph)) == [False, True, True, False]
    assert list(in_transit(t, eph, width=2.0)) == [True, True, True, True]


def test_transit_times_only_where_data_exists():
    t = np.arange(0.0, 10.0, 0.01)
    t = t[(t < 4.0) | (t >= 6.0)]
    times = transit_times_in_data(t, Ephemeris(1.0, 0.5, 0.1))
    np.testing.assert_allclose(times, [0.5, 1.5, 2.5, 3.5, 6.5, 7.5, 8.5, 9.5])


def test_match_identical_and_far_epochs():
    a = Ephemeris(3.0, 100.0, 0.1)
    assert ephemeris_match(a, a) == 1.0
    assert ephemeris_match(a, Ephemeris(3.0, 100.0 + 3.0 * 500, 0.1)) == 1.0


def test_match_rejects_other_period_or_phase():
    a = Ephemeris(3.0, 100.0, 0.1)
    assert ephemeris_match(a, Ephemeris(3.06, 100.0, 0.1)) is None
    assert ephemeris_match(a, Ephemeris(3.0, 100.9, 0.1)) is None


def test_match_harmonic_only_when_asked():
    a = Ephemeris(3.0, 100.0, 0.1)
    half = Ephemeris(1.5, 100.0, 0.1)
    assert ephemeris_match(a, half) is None
    assert ephemeris_match(a, half, harmonics=(1.0, 2.0)) == 2.0


def test_match_without_epoch_uses_period_only():
    assert ephemeris_match(Ephemeris(3.0, 100.0, 0.1), Ephemeris(3.0, float("nan"), 0.1)) == 1.0
