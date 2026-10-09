from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, write_catalog_snapshot

from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.search import bin_lightcurve, search_star, star_params

ROOT = Path(__file__).resolve().parents[1]
CFG = load_criteria(ROOT / "criteria" / "search-v1.toml")["search"]


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
    signals = search_star(lc, 1.0, 1.0, CFG)
    assert found(signals[:1], 3.7, 1326.1) and signals[0].sde > 15
    assert signals[0].n_transits >= 15


def test_finds_two_planets():
    lc = make_lc(
        sectors=(1, 2, 3),
        noise_ppm=300.0,
        signals=[(3.7, 1326.1, 0.12, 1000e-6), (11.3, 1330.0, 0.2, 1500e-6)],
        seed=2,
    )
    signals = search_star(lc, 1.0, 1.0, CFG)
    assert found(signals, 3.7, 1326.1) and found(signals, 11.3, 1330.0, 0.2)


@pytest.mark.parametrize("seed", [3, 4, 5])
def test_noise_stops_after_one_weak_signal(seed):
    signals = search_star(make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=seed), 1.0, 1.0, CFG)
    assert len(signals) == 1 and signals[0].sde < CFG["continue_sde"]


def test_mixed_cadence_star():
    lc = make_lc(
        sectors=(1, 2, 3, 4),
        cadences={1: 2.0, 2: 2.0, 3: 30.0, 4: 30.0},
        noise_ppm={1: 1100.0, 2: 1100.0, 3: 300.0, 4: 300.0},
        signals=[(4.3, 1327.0, 0.15, 700e-6)],
        seed=6,
    )
    assert found(search_star(lc, 1.0, 1.0, CFG)[:1], 4.3, 1327.0, 0.15)


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
    signals = search_star(lc, 1.0, 1.0, CFG)
    assert found(signals[:1], 5.3, 1327.0, 0.15) and signals[0].sde > 15


@pytest.mark.slow
def test_tls_engine_finds_planet():
    lc = make_lc(sectors=(1,), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=7)
    assert found(search_star(lc, 1.0, 1.0, {**CFG, "engine": "tls"})[:1], 3.7, 1326.1)


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
