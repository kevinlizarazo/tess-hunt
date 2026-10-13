import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, write_catalog_snapshot

from tess_hunt.benchmark import classify, completeness, injection_job, known_job, md_table
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.provenance import sha256_file
from tess_hunt.search import Signal

ROOT = Path(__file__).resolve().parents[1]
CRIT = load_criteria(ROOT / "criteria" / "search-v1.toml").values
MATCH = CRIT["match"]
SUN = {"tic": 1, "rad": 1.0, "mass": 1.0}
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


def sig(period, t0=100.0, sde=20.0, rank=1):
    return Signal(1, rank, period, t0, 0.1, 1e-3, 10.0, sde, 5)


def test_injection_job_records_a_light_curve_that_fails_to_load(tmp_path):
    path = tmp_path / "1.npz"
    path.write_bytes(b"not a light curve")
    rows = injection_job((SUN, path, [], CRIT, ["bls30"], 1, 11))
    assert len(rows) == 1 and rows[0]["status"] == "error" and rows[0]["error"]
    assert rows[0]["lc_sha256"] == sha256_file(path)


def test_injection_job_records_a_missing_light_curve(tmp_path):
    rows = injection_job((SUN, tmp_path / "1.npz", [], CRIT, ["bls30"], 2, 11))
    assert [r["status"] for r in rows] == ["error", "error"]
    assert all("FileNotFoundError" in r["error"] and "lc_sha256" not in r for r in rows)


def test_injection_job_gates_a_light_curve_too_short_to_search(tmp_path):
    path = tmp_path / "1.npz"
    lc = make_lc(sectors=(1,), seed=3)
    # Every 13th cadence leaves 96 points: enough for transits to land on data, too few for detrend.
    lc.select(np.arange(len(lc.time)) % 13 == 0).save(path)
    rows = injection_job((SUN, path, [], CRIT, ["bls30"], 1, 11))
    assert [r["status"] for r in rows] == ["too_few_points"] and rows[0]["n_points"] == 0
    assert rows[0]["lc_sha256"] == sha256_file(path)


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


@pytest.mark.parametrize(
    "mode",
    [
        "known",
        # Grouping completeness_map's two interval columns, pandas fails to hash the intervals and
        # falls back through a cast that warns.
        pytest.param(
            "inject",
            marks=pytest.mark.filterwarnings(
                "ignore:invalid value encountered in cast:RuntimeWarning"
            ),
        ),
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
        "inject": ["--catalogs", str(snap), "--engines", "bls30", "--per-star", "1"],
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
