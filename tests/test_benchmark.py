import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, relaxed_criteria, write_catalog_snapshot

from tess_hunt.benchmark import (
    SNR_EDGES,
    completeness,
    completeness_map,
    injection_job,
    known_job,
    md_table,
)
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.provenance import sha256_file
from tess_hunt.recovery import classify
from tess_hunt.search import Signal, search_code_sha256

ROOT = Path(__file__).resolve().parents[1]
CRIT = load_criteria(ROOT / "criteria" / "search-v2.toml").values
LEVEL = CRIT["benchmark"]["provisional_sde"]
MATCH = CRIT["match"]
SUN = {"tic": 1, "rad": 1.0, "mass": 1.0}
BAD_STAR = {"tic": 1, "rad": "not a number", "mass": 1.0}
PLANET = {
    "toi": "100.01",
    "tic": 1,
    "period": 4.3,
    "t0": 1326.0,
    "duration": 0.12,
    "depth_ppm": 3000.0,
    "planet_snr": 40.0,
    "required": True,
}
# Grouping completeness_map's two interval columns, pandas fails to hash the intervals and falls
# back through a cast that warns.
INTERVAL_CAST = pytest.mark.filterwarnings(
    "ignore:invalid value encountered in cast:RuntimeWarning"
)


def sig(period, t0=100.0, sde=20.0, rank=1):
    return Signal(1, rank, period, t0, 0.1, 1e-3, 10.0, sde, 5)


def test_injection_job_records_a_light_curve_that_fails_to_load(tmp_path):
    path = tmp_path / "1.npz"
    path.write_bytes(b"not a light curve")
    rows = injection_job((SUN, path, [], CRIT, ["bls30"], 1, 11, None, LEVEL))
    assert len(rows) == 1 and rows[0]["status"] == "error" and rows[0]["error"]
    assert rows[0]["lc_sha256"] == sha256_file(path)


def test_injection_job_records_a_missing_light_curve(tmp_path):
    rows = injection_job((SUN, tmp_path / "1.npz", [], CRIT, ["bls30"], 2, 11, None, LEVEL))
    assert [r["status"] for r in rows] == ["error", "error"]
    assert all("FileNotFoundError" in r["error"] and "lc_sha256" not in r for r in rows)


def test_injection_job_gates_a_light_curve_too_short_to_search(tmp_path):
    path = tmp_path / "1.npz"
    lc = make_lc(sectors=(1,), seed=3)
    # Every 13th cadence leaves 96 points: enough for transits to land on data, too few for detrend.
    lc.select(np.arange(len(lc.time)) % 13 == 0).save(path)
    # One sector counts as covered here; the coverage gate has its own test.
    sample = {**CRIT["sample"], "min_sectors": 1, "recent_sector_min": 1, "recent_sector_max": 1}
    rows = injection_job((SUN, path, [], {**CRIT, "sample": sample}, ["bls30"], 1, 11, None, LEVEL))
    assert [r["status"] for r in rows] == ["too_few_points"] and rows[0]["n_points"] == 0
    assert rows[0]["lc_sha256"] == sha256_file(path)


def test_injection_job_gates_too_few_bins_as_the_search_does(tmp_path):
    path = tmp_path / "1.npz"
    # Three days of 2-min cadence: enough points to detrend, under min_points once binned to 30 min,
    # as in test_search's test_too_few_bins_make_a_too_few_points_star.
    lc = make_lc(sectors=(1,), cadence_min=2.0, noise_ppm=300.0)
    lc.select(lc.time < lc.time[0] + 3.0).save(path)
    sample = {**CRIT["sample"], "min_sectors": 1, "recent_sector_min": 1, "recent_sector_max": 1}
    # Short periods, so three transits land in three days and the draw succeeds.
    search = {**CRIT["search"], "period_max_days": 1.4}
    crit = {**CRIT, "sample": sample, "search": search}
    rows = injection_job((SUN, path, [], crit, ["bls30"], 1, 11, None, LEVEL))
    assert [r["status"] for r in rows] == ["too_few_points"]
    assert rows[0]["n_bins"] < CRIT["search"]["min_points"]


def test_injection_job_records_a_bad_star_row(tmp_path):
    path = tmp_path / "1.npz"
    make_lc(sectors=(1,), seed=3).save(path)
    rows = injection_job((BAD_STAR, path, [], CRIT, ["bls30"], 2, 11, None, LEVEL))
    assert [r["status"] for r in rows] == ["error", "error"]
    assert all(r["error"].startswith("ValueError: ") for r in rows)


def test_injection_job_marks_a_star_not_covered_after_fetch(tmp_path):
    path = tmp_path / "1.npz"
    # Three early sectors: search-v2 wants four, one of them from 97 to 107.
    make_lc(sectors=(1, 2, 3), seed=3).save(path)
    rows = injection_job((SUN, path, [], CRIT, ["bls30"], 2, 11, None, LEVEL))
    assert [r["status"] for r in rows] == ["not_covered_after_fetch"] * 2
    assert all(r["lc_sha256"] == sha256_file(path) and "engine" not in r for r in rows)


def test_known_job_flags_a_host_missing_from_targets(tmp_path):
    path = tmp_path / "1.npz"
    make_lc(noise_ppm=300.0, signals=[(4.3, 1326.0, 0.12, 0.003)], seed=3).save(path)
    row = known_job((PLANET, {"tic": 1}, path, CRIT))
    assert row["status"] == "ok" and row["assumed_solar"] and row["recovered"]
    assert row["lc_sha256"] == sha256_file(path)


def test_known_job_records_an_error_as_a_miss(tmp_path):
    path = tmp_path / "1.npz"
    path.write_bytes(b"not a light curve")
    row = known_job((PLANET, SUN, path, CRIT))
    assert row["status"] == "error" and not row["recovered"] and not row["alias"]
    assert row["lc_sha256"] == sha256_file(path)


def test_known_job_records_a_bad_star_row_as_a_required_miss(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    path = data / "lc" / "1.npz"
    make_lc(noise_ppm=300.0, signals=[(4.3, 1326.0, 0.12, 0.003)], seed=3).save(path)
    row = known_job((PLANET, BAD_STAR, path, CRIT))
    assert row["status"] == "error" and row["error"].startswith("ValueError: ")
    assert not row["recovered"] and not row["alias"]
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([{**BAD_STAR, "ra": 30.0, "dec": -40.0}]).to_parquet(targets)
    known = tmp_path / "known.csv"
    pd.DataFrame([PLANET]).to_csv(known, index=False)
    monkeypatch.chdir(ROOT)
    argv = ["benchmark", "known", "--known", str(known), "--targets", str(targets)]
    assert main([*argv, "--workers", "1"]) == 1


@pytest.mark.parametrize(
    "mode",
    [
        "known",
        pytest.param("inject", marks=INTERVAL_CAST),
    ],
)
def test_benchmark_records_the_fetch_manifest(mode, tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    make_lc(noise_ppm=300.0, signals=[(4.3, 1326.0, 0.12, 0.003)], seed=3).save(
        data / "lc" / "1.npz"
    )
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([{**SUN, "ra": 30.0, "dec": -40.0}]).to_parquet(targets)
    manifest = tmp_path / "fetch_manifest.jsonl"
    manifest.write_text('{"tic": 1, "status": "ok"}\n')
    known = tmp_path / "known.csv"
    pd.DataFrame([PLANET]).to_csv(known, index=False)
    snap = write_catalog_snapshot(tmp_path / "snap")
    extra = {
        "known": ["--known", str(known)],
        "inject": [
            "--catalogs",
            str(snap),
            "--engines",
            "bls30",
            "--per-star",
            "1",
            "--criteria",
            str(relaxed_criteria(tmp_path)),
        ],
    }[mode]
    monkeypatch.chdir(ROOT)
    argv = ["benchmark", mode, "--targets", str(targets), "--manifest", str(manifest), *extra]
    assert main([*argv, "--workers", "1"]) == 0
    run = sorted((data / "runs").iterdir())[-1]
    inputs = json.loads((run / "provenance.json").read_text())["inputs"]
    assert inputs["fetch_manifest"] == {
        "file": "fetch_manifest.jsonl",
        "sha256": sha256_file(manifest),
    }


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


def test_classify_recovers_when_catalog_period_drifts():
    # TOI-396.01: its sector-97 epoch, carried 426 cycles back with the catalog period, misses the
    # sector-3 signal; carried with the signal's period, it lands on it.
    truth = Ephemeris(5.973912448814195, 3936.895179999992, 0.1301477674611527)
    found = Signal(178155732, 2, 5.97471, 1391.7001, 0.1875, 1e-3, 10.0, 37.1, 5)
    out = classify(truth, [found], MATCH, 9.0)
    assert out["recovered"] and not out["alias"] and out["rank"] == 2


def test_classify_recovers_when_search_period_drifts():
    truth = Ephemeris(5.973912448814195, 3936.895179999992, 0.1301477674611527)
    found = sig(5.97471, t0=truth.t0 - 426 * truth.period, sde=37.1)
    out = classify(truth, [found], MATCH, 9.0)
    assert out["recovered"] and not out["alias"]


def test_classify_still_rejects_wrong_phase():
    truth = Ephemeris(5.973912448814195, 3936.895179999992, 0.1301477674611527)
    off_phase = sig(truth.period, t0=truth.t0 + 0.5 * truth.period, sde=37.1)
    out = classify(truth, [off_phase], MATCH, 9.0)
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


@INTERVAL_CAST
def test_completeness_of_a_run_with_no_searched_rows_is_empty():
    # Only searched rows carry an engine column, so these rows have none.
    rows = pd.DataFrame({"tic": [1, 2], "status": ["error", "not_covered_after_fetch"]})
    assert completeness(rows, "expected_snr", SNR_EDGES).empty
    table = completeness_map(rows, "bls30")
    assert len(table) == 25 and (table["count"] == 0).all() and table["fraction"].isna().all()


def test_md_table():
    assert (
        md_table(pd.DataFrame({"a": [1.23456], "b": ["x"]})) == "| a | b |\n|---|---|\n| 1.23 | x |"
    )


@pytest.mark.slow
def test_injection_job_recovers_a_large_planet(tmp_path):
    path = tmp_path / "1.npz"
    make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=3).save(path)
    covered = load_criteria(relaxed_criteria(tmp_path)).values
    crit = {
        **covered,
        "benchmark": {
            **covered["benchmark"],
            "inject_rp_min_rearth": 8.0,
            "inject_rp_max_rearth": 10.0,
        },
    }
    star = {"tic": 1, "rad": 1.0, "mass": 1.0}
    rows = injection_job((star, path, [], crit, ["bls30"], 1, 11, None, LEVEL))
    assert len(rows) == 1 and rows[0]["recovered"] and rows[0]["expected_snr"] > 20
    assert np.isfinite(rows[0]["runtime_s"]) and rows[0]["lc_sha256"] == sha256_file(path)


def publish(run_id, tmp_path, monkeypatch):
    monkeypatch.setattr("tess_hunt.benchmark.repo_root", lambda: tmp_path / "repo")
    return main(["benchmark", "publish", "--run", run_id])


def test_publish_refuses_a_missing_or_unfinished_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    with pytest.raises(SystemExit, match="no run"):
        publish("nope", tmp_path, monkeypatch)
    run = tmp_path / "data" / "runs" / "r1"
    run.mkdir(parents=True)
    (run / "provenance.json").write_text(json.dumps({"ended_at": None}))
    with pytest.raises(SystemExit, match="not finished"):
        publish("r1", tmp_path, monkeypatch)


def test_publish_never_overwrites(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    run = tmp_path / "data" / "runs" / "r2"
    run.mkdir(parents=True)
    (run / "provenance.json").write_text(json.dumps({"ended_at": "2026-10-13T00:00:00+00:00"}))
    (run / "summary.md").write_text("# s\n")
    assert publish("r2", tmp_path, monkeypatch) == 0
    assert (tmp_path / "repo" / "results" / "benchmarks" / "r2" / "summary.md").exists()
    with pytest.raises(SystemExit, match="exists"):
        publish("r2", tmp_path, monkeypatch)


@INTERVAL_CAST
def test_replay_injects_the_listed_planets(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=3).save(data / "lc" / "1.npz")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([{**SUN, "ra": 30.0, "dec": -40.0}]).to_parquet(targets)
    published = tmp_path / "injections.csv"
    # pandas' default float parser reads these 17-digit values one ULP off; a replay must not.
    period, t0 = 4.3008701448475755, 1325.9997328314087
    row = {
        "tic": 1,
        "injection": 4,
        "engine": "bls30",
        "status": "ok",
        "inj_period": period,
        "inj_t0": t0,
        "inj_rp_rearth": 9.0,
        "inj_b": 0.2,
        "inj_rp_rs": 0.0824,
        "inj_a_rs": 12.6,
        "inj_duration": 0.12,
    }
    pd.DataFrame([row, {**row, "engine": "bls10"}]).to_csv(published, index=False)
    snap = write_catalog_snapshot(tmp_path / "snap")
    monkeypatch.chdir(ROOT)
    argv = [
        "benchmark",
        "inject",
        "--targets",
        str(targets),
        "--catalogs",
        str(snap),
        "--engines",
        "bls30",
        "--replay",
        str(published),
        "--criteria",
        str(relaxed_criteria(tmp_path)),
        "--workers",
        "1",
    ]
    assert main(argv) == 0
    run = sorted((data / "runs").iterdir())[-1]
    out = pd.read_csv(run / "injections.csv", float_precision="round_trip")
    assert list(out["injection"]) == [4]
    assert out.iloc[0]["inj_period"] == period and out.iloc[0]["inj_t0"] == t0
    assert out.iloc[0]["recovered"] and "few_transits" in out.columns
    inputs = json.loads((run / "provenance.json").read_text())["inputs"]
    assert inputs["replay"]["sha256"] == sha256_file(published)


def inject_cli(tmp_path, monkeypatch, *extra, tics=(1, 2)):
    tmp_path.mkdir(parents=True, exist_ok=True)
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    for tic in tics:
        make_lc(noise_ppm=300.0, seed=tic, tic=tic).save(data / "lc" / f"{tic}.npz")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([{**SUN, "tic": t, "ra": 30.0, "dec": -40.0} for t in tics]).to_parquet(targets)
    snap = write_catalog_snapshot(tmp_path / "snap")
    criteria = relaxed_criteria(tmp_path)
    monkeypatch.chdir(ROOT)
    argv = [
        "benchmark",
        "inject",
        "--targets",
        str(targets),
        "--catalogs",
        str(snap),
        "--engines",
        "bls30",
        "--per-star",
        "1",
        "--workers",
        "1",
        "--criteria",
        str(criteria),
    ]
    assert main([*argv, *extra]) == 0
    run = sorted((data / "runs").iterdir())[-1]
    return (
        pd.read_csv(run / "injections.csv"),
        json.loads((run / "provenance.json").read_text()),
        criteria,
    )


@INTERVAL_CAST
def test_inject_threshold_sets_the_classification_level(tmp_path, monkeypatch):
    # Planets of 8 to 10 Earth radii, which the provisional level recovers, as in
    # test_injection_job_recovers_a_large_planet.
    text = relaxed_criteria(tmp_path).read_text()
    for old, new in (
        ("inject_rp_min_rearth = 0.5", "inject_rp_min_rearth = 8.0"),
        ("inject_rp_max_rearth = 16.0", "inject_rp_max_rearth = 10.0"),
    ):
        assert old in text
        text = text.replace(old, new)
    criteria = tmp_path / "large.toml"
    criteria.write_text(text)
    threshold = tmp_path / "threshold.json"
    threshold.write_text(
        json.dumps(
            {
                "threshold": 1000.0,
                "search_criteria_sha256": load_criteria(criteria).sha256,
                "search_code_sha256": search_code_sha256(ROOT),
            }
        )
    )
    # Each --criteria is given after inject_cli's own, so it wins. The default seed draws a 31-day
    # planet that the search finds at half its period; seed 3 draws two it recovers.
    args = ("--criteria", str(criteria), "--seed", "3")
    provisional, _, _ = inject_cli(tmp_path / "a", monkeypatch, *args)
    assert provisional["recovered"].all() and (provisional["masked_fraction"] > 0).all()
    rows, provenance, _ = inject_cli(
        tmp_path / "b", monkeypatch, *args, "--threshold", str(threshold)
    )
    assert not rows["recovered"].any()
    # Below continue_sde the search stops before masking its first signal.
    assert (rows["masked_fraction"] == 0).all()
    assert provenance["threshold"]["value"] == 1000.0


def test_production_inject_needs_a_threshold(tmp_path, monkeypatch):
    with pytest.raises(SystemExit, match="production injection run needs --threshold"):
        inject_cli(tmp_path, monkeypatch, "--production")
    # Refused before start_run: no run directory is left behind.
    assert not (tmp_path / "data" / "runs").exists()


@pytest.mark.parametrize("other", ["criteria", "code"])
def test_inject_refuses_a_threshold_from_other_criteria_or_code(other, tmp_path, monkeypatch):
    criteria = (
        ROOT / "criteria" / "search-v2.toml" if other == "criteria" else relaxed_criteria(tmp_path)
    )
    code = "0" * 64 if other == "code" else search_code_sha256(ROOT)
    threshold = tmp_path / "threshold.json"
    threshold.write_text(
        json.dumps(
            {
                "threshold": 12.0,
                "search_criteria_sha256": load_criteria(criteria).sha256,
                "search_code_sha256": code,
            }
        )
    )
    with pytest.raises(SystemExit, match="other search criteria or code"):
        inject_cli(tmp_path, monkeypatch, "--threshold", str(threshold))
    # Refused before start_run: no run directory is left behind.
    assert not (tmp_path / "data" / "runs").exists()


@INTERVAL_CAST
def test_inject_sample_draws_stars_by_seed(tmp_path, monkeypatch):
    def drawn(name, seed):
        rows, _, _ = inject_cli(
            tmp_path / name, monkeypatch, "--sample", "1", "--seed", str(seed), tics=(1, 2, 3)
        )
        return set(rows["tic"])

    first = drawn("a", 3)
    assert len(first) == 1
    assert drawn("b", 3) == first
    assert drawn("c", 1) != first


@INTERVAL_CAST
def test_injections_pair_by_star_whatever_the_order(tmp_path, monkeypatch):
    first, _, _ = inject_cli(tmp_path / "a", monkeypatch, tics=(1, 2))
    second, _, _ = inject_cli(tmp_path / "b", monkeypatch, tics=(2, 1))
    a, b = first.set_index("tic"), second.set_index("tic")
    assert (
        a.loc[1, "inj_period"] == b.loc[1, "inj_period"]
        and a.loc[2, "inj_t0"] == b.loc[2, "inj_t0"]
    )


@INTERVAL_CAST
def test_inject_with_no_star_covered_reports_empty_maps(tmp_path, monkeypatch):
    # search-v2's own coverage rule, given after inject_cli's relaxed file so it wins, covers no
    # synthetic star.
    rows, provenance, _ = inject_cli(tmp_path, monkeypatch, "--criteria", "criteria/search-v2.toml")
    assert set(rows["status"]) == {"not_covered_after_fetch"}
    summary = provenance["summary"]
    assert summary["not_covered_after_fetch"] == 2 and summary["injections"] == 0
    run = sorted((tmp_path / "data" / "runs").iterdir())[-1]
    assert "No injection reached the search" in (run / "summary.md").read_text()
    assert pd.read_csv(run / "completeness_snr.csv").empty
    assert (pd.read_csv(run / "completeness_bls30.csv")["count"] == 0).all()


@INTERVAL_CAST
@pytest.mark.parametrize(
    ("source", "kind", "status"),
    [("TOI", "candidate", "too_few_points"), ("SPOC-TCE", "tce", "ok")],
)
def test_inject_masks_only_the_mask_sources(source, kind, status, tmp_path, monkeypatch):
    snap = tmp_path / "known-snap"
    snap.mkdir(parents=True)
    # A one-day period with a half-day duration masks every cadence of the star.
    known = {"source": source, "kind": kind, "name": "x", "tic": 1, "ra": 30.0, "dec": -40.0}
    known |= {"period": 1.0, "t0": 1325.0, "duration": 0.5, "depth_ppm": 500.0}
    pd.DataFrame([known]).to_parquet(snap / "known.parquet")
    (snap / "manifest.json").write_text("{}\n")
    # Given after inject_cli's own snapshot, so it wins.
    rows, _, _ = inject_cli(tmp_path, monkeypatch, "--catalogs", str(snap), tics=(1,))
    assert list(rows["status"]) == [status]
