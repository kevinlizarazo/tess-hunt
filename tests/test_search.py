import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, write_catalog_snapshot

from tess_hunt import search as search_module
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.search import (
    allowed_durations,
    bin_lightcurve,
    central_duration,
    search_star,
    star_params,
    stellar_density,
)

ROOT = Path(__file__).resolve().parents[1]
CFG = load_criteria(ROOT / "criteria" / "search-v2.toml")["search"]
DURATIONS = np.sort(np.asarray(CFG["durations_hours"]) / 24.0)


def found(signals, period, t0, duration=0.12) -> bool:
    truth = Ephemeris(period, t0, duration)
    return any(ephemeris_match(s.ephemeris(), truth) is not None for s in signals)


def test_bin_never_merges_sectors():
    lc = make_lc(sectors=(1, 2), cadence_min=2.0, noise_ppm=100.0)
    binned = bin_lightcurve(lc, 30.0)
    for sector in (1, 2):
        b, raw = binned.time[binned.sector == sector], lc.time[lc.sector == sector]
        assert b.min() >= raw.min() and b.max() <= raw.max()
    assert np.isclose(binned.flux_err, 100e-6 / np.sqrt(15)).mean() > 0.9


def test_finds_planet():
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], seed=1)
    signals = search_star(lc, 1.0, 1.0, CFG).signals
    assert found(signals[:1], 3.7, 1326.1) and signals[0].sde > 15
    assert signals[0].n_transits >= 15


def test_finds_two_planets():
    lc = make_lc(
        sectors=(1, 2, 3),
        noise_ppm=300.0,
        signals=[(3.7, 1326.1, 0.12, 1000e-6), (11.3, 1330.0, 0.2, 1500e-6)],
        seed=2,
    )
    signals = search_star(lc, 1.0, 1.0, CFG).signals
    assert found(signals, 3.7, 1326.1) and found(signals, 11.3, 1330.0, 0.2)


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_noise_stops_after_one_weak_signal(seed):
    signals = search_star(
        make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=seed), 1.0, 1.0, CFG
    ).signals
    assert len(signals) == 1 and signals[0].sde < CFG["continue_sde"]


def test_mixed_cadence_star():
    lc = make_lc(
        sectors=(1, 2, 3, 4),
        cadences={1: 2.0, 2: 2.0, 3: 30.0, 4: 30.0},
        noise_ppm={1: 1100.0, 2: 1100.0, 3: 300.0, 4: 300.0},
        signals=[(4.3, 1327.0, 0.15, 700e-6)],
        seed=6,
    )
    assert found(search_star(lc, 1.0, 1.0, CFG).signals[:1], 4.3, 1327.0, 0.15)


def test_star_params_fall_back_to_solar():
    assert star_params({"rad": 1.2, "mass": 1.1}) == (1.2, 1.1, False)
    assert star_params({"rad": np.nan, "mass": 1.1}) == (1.0, 1.1, True)
    assert star_params({}) == (1.0, 1.0, True)


@pytest.mark.slow
def test_shallow_planet_over_long_baseline():
    lc = make_lc(
        sectors=(1, 2, 3, 28, 29, 68),
        noise_ppm=300.0,
        signals=[(5.3, 1327.0, 0.15, 250e-6)],
        seed=5,
    )
    signals = search_star(lc, 1.0, 1.0, CFG).signals
    assert found(signals[:1], 5.3, 1327.0, 0.15) and signals[0].sde > 15


def test_search_cli_writes_signals_and_records_missing_stars(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], tic=11).save(
        tmp_path / "data" / "lc" / "11.npz"
    )
    targets = tmp_path / "targets.parquet"
    pd.DataFrame(
        {
            "tic": [11, 12],
            "ra": [1.0, 2.0],
            "dec": [-70.0, -70.0],
            "rad": [1.0, 1.0],
            "mass": [1.0, 1.0],
        }
    ).to_parquet(targets)
    snap = write_catalog_snapshot(tmp_path / "snap")
    monkeypatch.chdir(ROOT)
    assert (
        main(["search", "--targets", str(targets), "--catalogs", str(snap), "--workers", "1"]) == 0
    )
    run = sorted((tmp_path / "data" / "runs").iterdir())[-1]
    stars = pd.read_parquet(run / "stars.parquet").set_index("tic")
    assert stars.loc[11, "status"] == "ok" and stars.loc[12, "status"] == "no_light_curve"
    signals = pd.read_parquet(run / "signals.parquet")
    assert abs(signals.iloc[0]["period"] - 3.7) < 0.01


def test_search_job_records_a_bad_star_row(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    make_lc(sectors=(1,), tic=5).save(tmp_path / "lc" / "5.npz")
    crit = load_criteria(ROOT / "criteria" / "search-v1.toml")
    status, signals = search_module._search_job(
        ({"tic": 5, "rad": "not a number"}, [], crit["detrend"], CFG)
    )
    assert status["status"] == "error" and status["error"].startswith("ValueError")
    assert signals == []


def sinusoid(lc, period, amplitude_ppm):
    """A pulsating or spotted star: a sinusoid stronger than the noise."""
    lc.flux = lc.flux + amplitude_ppm * 1e-6 * np.sin(2 * np.pi * lc.time / period + 0.3)
    return lc


def test_duration_bound_follows_the_star():
    periods = np.array([1.0, 3.0, 10.0, 40.0])
    # The Sun's central transit lasts 1.83 h at 1 d, so boxes up to 3.67 h: four of the eight.
    assert np.allclose(
        central_duration(periods, 1.0) * 24.0, [1.833, 2.624, 3.913, 6.209], atol=1e-3
    )
    assert list(allowed_durations(periods, DURATIONS, 1.0, 2.0)) == [4, 5, 6, 8]
    assert list(allowed_durations(periods, DURATIONS, 10.0, 2.0)) == [2, 3, 4, 5]
    # Denser than any star: the shortest box is still searched.
    assert list(allowed_durations(periods, DURATIONS, 1000.0, 2.0)) == [1, 1, 1, 1]


def test_density_falls_back_to_mass_and_radius_then_solar():
    assert stellar_density({"rho": 0.5}, 1.2, 1.1) == 0.5
    assert stellar_density({"rho": np.nan}, 2.0, 1.0) == 0.125
    assert stellar_density({}, *star_params({})[:2]) == 1.0


def test_variable_star_never_repeats_a_rank():
    lc = sinusoid(make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=1), 1.37, 3000.0)
    signals = search_star(lc, 1.0, 1.0, CFG).signals
    assert len(signals) >= 2
    harmonics = tuple(CFG["repeat_harmonics"])
    for i, later in enumerate(signals):
        for earlier in signals[:i]:
            assert (
                ephemeris_match(
                    later.ephemeris(), replace(earlier.ephemeris(), t0=math.nan), harmonics
                )
                is None
            )
    for s in signals:
        assert s.duration <= max(
            DURATIONS[0], CFG["duration_factor"] * central_duration(s.period, 1.0)
        )


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_single_eclipse_never_becomes_a_signal(seed):
    lc = make_lc(
        sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], seed=seed
    )
    lc.flux = np.where(np.abs(lc.time - 1340.0) < 0.1, lc.flux - 5000e-6, lc.flux)
    result = search_star(lc, 1.0, 1.0, CFG)
    assert result.few_transits >= 1 and not result.budget_exhausted
    assert all(s.n_transits >= CFG["min_transits"] for s in result.signals)
    assert found(result.signals, 3.7, 1326.1)


def test_few_transit_peak_is_masked_and_the_search_retried(monkeypatch):
    real = search_module.transit_times_in_data
    rejected = []

    def first_is_few(time, eph, min_points=1):
        if not rejected:
            rejected.append(eph)
            return np.zeros(2)
        return real(time, eph, min_points)

    monkeypatch.setattr(search_module, "transit_times_in_data", first_is_few)
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], seed=1)
    result = search_star(lc, 1.0, 1.0, CFG)
    assert result.few_transits == 1 and result.n_bls == 2
    assert abs(rejected[0].period - 3.7) < 0.01
    # Its transits were masked, so the retry cannot find the same planet again.
    assert not found(result.signals, 3.7, 1326.1)


def test_retry_budget_ends_a_search_of_few_transit_peaks(monkeypatch):
    monkeypatch.setattr(
        search_module, "transit_times_in_data", lambda time, eph, min_points=1: np.zeros(2)
    )
    result = search_star(make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=1), 1.0, 1.0, CFG)
    assert result.signals == [] and result.budget_exhausted
    assert result.few_transits == result.n_bls == CFG["max_retries"] + 1


def test_nan_sde_stops_the_search(monkeypatch):
    calls = []
    real = search_module._bls_spectrum

    def nan_power(*args):
        calls.append(1)
        return {**real(*args), "power": np.full(len(args[1]), np.nan)}

    monkeypatch.setattr(search_module, "_bls_spectrum", nan_power)
    result = search_star(make_lc(sectors=(1, 2), noise_ppm=300.0, seed=1), 1.0, 1.0, CFG)
    assert len(calls) == 1 and result.signals == []


def test_only_bls_is_searched():
    with pytest.raises(ValueError, match="tls"):
        search_star(make_lc(sectors=(1,)), 1.0, 1.0, {**CFG, "engine": "tls"})


def test_search_reports_its_diagnostics():
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], seed=1)
    out = search_star(lc, 1.0, 1.0, CFG).diagnostics()
    assert set(out) == {
        "n_bins",
        "few_transits",
        "budget_exhausted",
        "n_bls",
        "top_period",
        "top_q",
        "top_sde",
        "masked_fraction",
    }
    assert abs(out["top_period"] - 3.7) < 0.01 and out["top_sde"] > 15
    assert 0.0 < out["masked_fraction"] < 0.2


def test_too_few_bins_is_an_empty_result_with_its_count():
    lc = make_lc(sectors=(1,), cadence_min=2.0, noise_ppm=300.0)
    short = lc.select(lc.time < lc.time[0] + 0.5)
    result = search_star(short, 1.0, 1.0, CFG)
    # Enough raw cadences for the stage's own check, too few 30-minute bins to search (Task 8 marks it).
    assert len(short.time) >= CFG["min_points"] > result.n_bins > 0
    assert result.signals == [] and result.n_bls == 0
