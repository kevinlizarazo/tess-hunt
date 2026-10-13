import json
import math
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.ndimage import median_filter
from synthetic import FAR_TOI, make_lc, relaxed_criteria, write_catalog_snapshot

from tess_hunt import search as search_module
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.provenance import sha256_file
from tess_hunt.search import (
    SEARCH_CODE,
    SearchResult,
    Signal,
    allowed_durations,
    bin_lightcurve,
    central_duration,
    read_threshold,
    repeat_periods,
    search_code_sha256,
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


PLANET_LC = dict(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)])


def cli_star(tmp_path, monkeypatch, tics=(11,), **lc):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    for tic in tics:
        make_lc(tic=tic, **(lc or PLANET_LC)).save(tmp_path / "data" / "lc" / f"{tic}.npz")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame(
        {"tic": [*tics, 12], "ra": 1.0, "dec": -70.0, "rad": 1.0, "mass": 1.0, "rho": 1.0}
    ).to_parquet(targets)
    monkeypatch.chdir(ROOT)
    return targets, write_catalog_snapshot(tmp_path / "snap")


def search_cli(tmp_path, targets, snap, *extra):
    argv = ["search", "--targets", str(targets), "--catalogs", str(snap), "--workers", "1"]
    code = main([*argv, "--criteria", str(relaxed_criteria(tmp_path)), *extra])
    run = sorted((tmp_path / "data" / "runs").iterdir())[-1]
    return code, run


def test_search_cli_writes_signals_and_records_missing_stars(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch)
    code, run = search_cli(tmp_path, targets, snap)
    assert code == 0
    stars = pd.read_parquet(run / "stars.parquet").set_index("tic")
    assert stars.loc[11, "status"] == "ok" and stars.loc[12, "status"] == "no_light_curve"
    assert stars.loc[11, "top_sde"] > 15 and stars.loc[11, "few_transits"] == 0
    # Every searched star records the search's diagnostics (decision 0008).
    assert set(SearchResult().diagnostics()) <= set(stars.columns)
    signals = pd.read_parquet(run / "signals.parquet")
    assert abs(signals.iloc[0]["period"] - 3.7) < 0.01 and not signals["control"].any()
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["search_code_sha256"] == search_code_sha256(ROOT)


def test_search_skips_a_star_not_covered_after_fetch(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch, sectors=(1, 2), noise_ppm=300.0)
    _, run = search_cli(tmp_path, targets, snap)
    assert (
        pd.read_parquet(run / "stars.parquet").set_index("tic").loc[11, "status"]
        == "not_covered_after_fetch"
    )


def test_scramble_run_records_its_seed_and_no_signal_matches_the_planets_ephemeris(
    tmp_path, monkeypatch
):
    targets, snap = cli_star(tmp_path, monkeypatch, **{**PLANET_LC, "sectors": (1, 2, 3, 4, 5, 6)})
    _, run = search_cli(tmp_path, targets, snap, "--scramble", "1")
    assert json.loads((run / "provenance.json").read_text())["scramble"] == 1
    signals = pd.read_parquet(run / "signals.parquet")
    # Each orbit keeps its own transits in phase, so a weaker peak can stay near 3.7 d; what the
    # scramble loses is the planet's ephemeris, period and epoch together.
    rows = signals[list(Signal.__dataclass_fields__)].to_dict("records")
    assert rows and not found([Signal(**r) for r in rows], 3.7, 1326.1)


def write_threshold(tmp_path, value, criteria_path, code_sha256=None):
    path = tmp_path / "threshold.json"
    path.write_text(
        json.dumps(
            {
                "threshold": value,
                "search_criteria_sha256": load_criteria(criteria_path).sha256,
                "search_code_sha256": code_sha256 or search_code_sha256(ROOT),
            }
        )
    )
    return path


def test_threshold_sets_continue_sde(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch)
    threshold = write_threshold(tmp_path, 1000.0, relaxed_criteria(tmp_path))
    _, run = search_cli(tmp_path, targets, snap, "--threshold", str(threshold))
    assert len(pd.read_parquet(run / "signals.parquet")) == 1
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["threshold"] == {
        "value": 1000.0,
        "file": "threshold.json",
        "run_id": tmp_path.name,
    }
    assert provenance["inputs"]["threshold"]["sha256"] == sha256_file(threshold)


def test_threshold_from_other_criteria_is_refused(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch)
    threshold = write_threshold(tmp_path, 12.0, ROOT / "criteria" / "search-v1.toml")
    with pytest.raises(SystemExit, match="criteria"):
        search_cli(tmp_path, targets, snap, "--threshold", str(threshold))


def test_threshold_from_other_search_code_is_refused(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch)
    threshold = write_threshold(tmp_path, 12.0, relaxed_criteria(tmp_path), code_sha256="0" * 64)
    with pytest.raises(SystemExit, match="other search code"):
        search_cli(tmp_path, targets, snap, "--threshold", str(threshold))


@pytest.mark.parametrize("value", [math.nan, math.inf, "12.0", None, True])
def test_a_threshold_that_is_not_a_finite_number_is_refused(tmp_path, value):
    path = write_threshold(tmp_path, value, relaxed_criteria(tmp_path))
    with pytest.raises(SystemExit, match="threshold.json has threshold"):
        read_threshold(path)
    assert (
        read_threshold(write_threshold(tmp_path, 12, relaxed_criteria(tmp_path)))["threshold"] == 12
    )


def controls(tmp_path, required_period):
    known = tmp_path / "known.csv"
    pd.DataFrame(
        [
            {
                "toi": "100.01",
                "tic": 21,
                "period": required_period,
                "t0": 1326.1,
                "duration": 0.12,
                "required": True,
            },
            {
                "toi": "200.01",
                "tic": 21,
                "period": 9.9,
                "t0": 1327.0,
                "duration": 0.12,
                "required": False,
            },
        ]
    ).to_csv(known, index=False)
    control_targets = tmp_path / "control_targets.parquet"
    pd.DataFrame(
        {"tic": [21], "ra": 5.0, "dec": -70.0, "rad": 1.0, "mass": 1.0, "rho": 1.0}
    ).to_parquet(control_targets)
    return ["--controls", str(known), "--control-targets", str(control_targets)]


def test_controls_found_make_a_valid_run(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch, tics=(11, 21))
    code, run = search_cli(tmp_path, targets, snap, *controls(tmp_path, 3.7))
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert code == 0 and summary["controls_valid"] and summary["controls_missed"] == ["200.01"]
    rows = pd.read_csv(run / "controls.csv", dtype={"toi": str}).set_index("toi")
    assert bool(rows.loc["100.01", "recovered"])
    signals = pd.read_parquet(run / "signals.parquet")
    assert signals["control"].any()
    # One row per sample target and one per control host; the summary counts the sample alone.
    stars = pd.read_parquet(run / "stars.parquet")
    assert sorted(stars.loc[~stars["control"], "tic"]) == [11, 12, 21]
    assert list(stars.loc[stars["control"], "tic"]) == [21]
    assert summary["stars"] == 3 and summary["control_rows"] == 1
    assert summary["status_ok"] == 2 and summary["status_no_light_curve"] == 1
    assert summary["signals"] == (~signals["control"]).sum()
    assert summary["control_signals"] == signals["control"].sum()


def test_controls_are_judged_at_the_threshold(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch, tics=(11, 21))
    threshold = write_threshold(tmp_path, 1000.0, relaxed_criteria(tmp_path))
    code, run = search_cli(
        tmp_path, targets, snap, *controls(tmp_path, 3.7), "--threshold", str(threshold)
    )
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert code == 1 and summary["controls_required_missed"] == ["100.01"]
    row = pd.read_csv(run / "controls.csv", dtype={"toi": str}).set_index("toi").loc["100.01"]
    # Found at its ephemeris, but below the run's threshold.
    assert row["sde"] > 15 and not row["recovered"]


def test_a_control_host_missing_from_control_targets_is_refused_before_the_run(
    tmp_path, monkeypatch
):
    targets, snap = cli_star(tmp_path, monkeypatch, tics=(11, 21))
    args = controls(tmp_path, 3.7)
    pd.DataFrame({"tic": [22], "ra": 5.0, "dec": -70.0, "rad": 1.0, "mass": 1.0}).to_parquet(
        args[-1]
    )
    with pytest.raises(SystemExit, match=r"control hosts \[21\]"):
        search_cli(tmp_path, targets, snap, *args)
    assert not (tmp_path / "data" / "runs").exists()


def test_a_missed_required_control_invalidates_the_run(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch, tics=(11, 21))
    code, run = search_cli(tmp_path, targets, snap, *controls(tmp_path, 5.1))
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert code == 1 and not summary["controls_valid"]
    assert summary["controls_required_missed"] == ["100.01"]


def test_a_control_host_without_a_light_curve_invalidates_the_run(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch, tics=())
    code, run = search_cli(tmp_path, targets, snap, *controls(tmp_path, 3.7))
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert code == 1 and not summary["controls_valid"]
    assert summary["signals"] == summary["control_signals"] == 0
    assert summary["controls_required_missed"] == ["100.01"]


def masked_snapshot(tmp_path):
    """The catalog lists TIC 21's planet (PLANET_LC's) as a TOI, so a sample search masks it."""
    toi = {
        **FAR_TOI,
        "TIC ID": 21,
        "TOI": 100.01,
        "Period (days)": 3.7,
        "Epoch (BJD)": 2457000.0 + 1326.1,
        "Duration (hours)": 0.12 * 24.0,
    }
    return write_catalog_snapshot(tmp_path / "masked", toi_rows=[toi])


def near_planet(signals, tic):
    rows = signals[(signals["tic"] == tic) & ~signals["control"]]
    return ((rows["period"] - 3.7).abs() < 0.03).any()


def test_a_sample_star_masks_its_known_planet_and_its_control_finds_it(tmp_path, monkeypatch):
    targets, _ = cli_star(tmp_path, monkeypatch, tics=(21,))
    code, run = search_cli(tmp_path, targets, masked_snapshot(tmp_path), *controls(tmp_path, 3.7))
    assert not near_planet(pd.read_parquet(run / "signals.parquet"), 21)
    rows = pd.read_csv(run / "controls.csv", dtype={"toi": str}).set_index("toi")
    assert code == 0 and bool(rows.loc["100.01", "recovered"])


def test_a_scrambled_star_keeps_its_known_planet_masked(tmp_path, monkeypatch):
    targets, _ = cli_star(tmp_path, monkeypatch, tics=(21,))
    _, run = search_cli(tmp_path, targets, masked_snapshot(tmp_path), "--scramble", "1")
    # A mask left on the unscrambled cadences lets the planet's transits back in (3.6969 d at SDE
    # 11.0 on this seed); masked, the top peak is noise below the provisional threshold (6.7).
    assert not near_planet(pd.read_parquet(run / "signals.parquet"), 21)
    top = pd.read_parquet(run / "stars.parquet").set_index("tic").loc[21, "top_sde"]
    assert top < CFG["continue_sde"]


def test_production_search_needs_threshold_and_controls(tmp_path, monkeypatch):
    targets, snap = cli_star(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="--threshold"):
        main(["search", "--targets", str(targets), "--catalogs", str(snap), "--production"])
    with pytest.raises(SystemExit, match="exclude each other"):
        main(
            [
                "search",
                "--targets",
                str(targets),
                "--catalogs",
                str(snap),
                "--scramble",
                "1",
                "--threshold",
                "x",
            ]
        )


def test_search_code_covers_the_search_path():
    assert {"search.py", "detrend.py", "scramble.py", "recovery.py", "targets.py"} <= set(
        SEARCH_CODE
    )


def search_job(tmp_path, star, control=False, crit=None):
    crit = crit or load_criteria(relaxed_criteria(tmp_path))
    job = {
        "star": star,
        "control": control,
        "known": [],
        "criteria": crit.values,
        "search": CFG,
        "scramble": None,
    }
    return search_module._search_job(job)


def test_search_job_records_a_bad_star_row(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    make_lc(sectors=(1,), tic=5).save(tmp_path / "lc" / "5.npz")
    crit = load_criteria(ROOT / "criteria" / "search-v2.toml")
    status, signals = search_job(tmp_path, {"tic": 5, "rad": "not a number"}, crit=crit)
    assert status["status"] == "error" and status["error"].startswith("ValueError")
    assert signals == []


def test_a_nonfinite_top_sde_is_never_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    make_lc(tic=5, **PLANET_LC).save(tmp_path / "lc" / "5.npz")
    real = search_module._bls_spectrum
    monkeypatch.setattr(
        search_module,
        "_bls_spectrum",
        lambda *args: {**real(*args), "power": np.full(len(args[1]), np.nan)},
    )
    status, signals = search_job(tmp_path, {"tic": 5})
    assert status["status"] == "nonfinite_sde" and signals == []
    assert status["n_bins"] >= CFG["min_points"] and math.isnan(status["top_sde"])


def test_too_few_bins_make_a_too_few_points_star(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    lc = make_lc(sectors=(1,), cadence_min=2.0, noise_ppm=300.0, tic=5)
    lc.select(lc.time < lc.time[0] + 3.0).save(tmp_path / "lc" / "5.npz")
    # A control skips the coverage rule, so one short sector reaches the search.
    status, signals = search_job(tmp_path, {"tic": 5}, control=True)
    assert status["status"] == "too_few_points" and signals == []
    assert status["n_points"] >= CFG["min_points"] > status["n_bins"]


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


def third_transit_with(binned_points: int):
    """Three 3-hour transits on one sector; the third keeps only the given number of 30-minute bins."""
    centre = 1346.01
    lc = make_lc(sectors=(1,), noise_ppm=300.0, signals=[(8.5, 1329.01, 0.125, 2000e-6)], seed=1)
    near = np.abs(lc.time - centre) < 0.5
    # Nothing else within half a day, so the box at the third transit holds only the kept cadences;
    # an hour apart, they never share a bin.
    offsets = (0.0,) if binned_points == 1 else (-0.5 / 24, 0.5 / 24)
    kept = [int(np.argmin(np.abs(lc.time - (centre + o)))) for o in offsets]
    near[kept] = False
    lc = lc.select(~near)
    binned = bin_lightcurve(lc, CFG["bin_minutes"])
    assert (np.abs(binned.time - centre) < 0.0625).sum() == binned_points
    return lc


def test_a_transit_on_data_needs_two_binned_points():
    assert CFG["min_points_per_transit"] == 2
    one, two = (search_star(third_transit_with(n), 1.0, 1.0, CFG) for n in (1, 2))
    # The planet is the first peak both times (the grid steps 0.024 d near 8.5 d); with one bin its
    # third transit does not count.
    assert abs(one.top_period - 8.5) < 0.05 and abs(two.top_period - 8.5) < 0.05
    assert one.few_transits >= 1 and not found(one.signals, 8.5, 1329.01, 0.125)
    assert found(two.signals[:1], 8.5, 1329.01, 0.125) and two.signals[0].n_transits == 3


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


def box_bound(period, rho):
    return max(DURATIONS[0], CFG["duration_factor"] * central_duration(period, rho))


def test_dense_star_bounds_every_box():
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], seed=1)
    signals = search_star(lc, 1.0, 1.0, CFG, rho=10.0).signals
    assert signals and all(s.duration <= box_bound(s.period, 10.0) for s in signals)
    # Searched as a Sun, the planet takes a box that a star of ten solar densities cannot transit.
    assert search_star(lc, 1.0, 1.0, CFG).signals[0].duration > box_bound(3.7, 10.0)


def test_repeat_periods_agree_with_ephemeris_match_at_the_boundary():
    emitted = Signal(1, 1, 3.7, 1326.1, 0.12, 1e-3, 10.0, 20.0, 15)
    harmonics, sigma_p = tuple(CFG["repeat_harmonics"]), CFG["repeat_sigma_p"]
    tolerance = math.erfc(sigma_p / math.sqrt(2.0))
    grid, inside, outside = [], [], []
    for h in harmonics:
        centre = emitted.period * h
        grid += list(centre * np.linspace(0.97, 1.03, 301))
        # |P - centre| / P equals the tolerance at centre / (1 -+ tolerance), on either side.
        for side in (-1.0, 1.0):
            inside.append(centre / (1.0 - side * tolerance * (1.0 - 1e-6)))
            outside.append(centre / (1.0 - side * tolerance * (1.0 + 1e-6)))
    periods = np.array(grid + inside + outside)
    flagged = repeat_periods(periods, [emitted], harmonics, sigma_p)
    reference = replace(emitted.ephemeris(), t0=math.nan)
    matched = [
        ephemeris_match(Ephemeris(p, 1326.1, 0.12), reference, harmonics, sigma_p) is not None
        for p in periods
    ]
    assert list(flagged) == matched
    assert repeat_periods(np.array(inside), [emitted], harmonics, sigma_p).all()
    assert not repeat_periods(np.array(outside), [emitted], harmonics, sigma_p).any()


def test_sde_statistics_leave_out_the_excluded_periods(monkeypatch):
    real = search_module._bls_spectrum
    rng = np.random.default_rng(0)
    planted = {}

    def spectrum(lc, periods, durations, counts):
        power = rng.normal(0.0, 1.0, len(periods))
        if not planted:
            planted["first"] = int(np.argmin(np.abs(periods - 3.7)))
            power[planted["first"]] = 100.0
        elif "second" not in planted:
            first = Signal(1, 1, periods[planted["first"]], 0.0, 0.1, 0.0, 0.0, 0.0, 0)
            excluded = repeat_periods(
                periods, [first], CFG["repeat_harmonics"], CFG["repeat_sigma_p"]
            )
            # The first signal's harmonics stay the strongest peaks, as a variable star's do.
            power[excluded] += 30.0
            planted["second"] = int(np.argmin(np.abs(periods - 9.1)))
            power[planted["second"]] = 20.0
            planted.update(power=power, excluded=excluded, period=periods[planted["second"]])
        return {**real(lc, periods, durations, counts), "power": power}

    monkeypatch.setattr(search_module, "_bls_spectrum", spectrum)
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 800e-6)], seed=1)
    second = search_star(lc, 1.0, 1.0, CFG).signals[1]
    power, excluded = planted["power"], planted["excluded"]
    detrended = power - median_filter(power, size=CFG["sde_kernel"], mode="nearest")
    peak, kept = detrended[planted["second"]], detrended[~excluded]
    assert second.period == planted["period"]
    assert second.sde == pytest.approx((peak - kept.mean()) / kept.std(), rel=1e-9)
    # Counted in the mean and spread, the excluded peaks would cut the SDE by more than half.
    assert (peak - detrended.mean()) / detrended.std() < 0.5 * second.sde
