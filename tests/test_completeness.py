import json
import shutil
import subprocess
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, write_catalog_snapshot

from tess_hunt import triage
from tess_hunt.benchmark import ENGINES, injection_job
from tess_hunt.catalogs import KNOWN_COLUMNS, snapshot_inputs
from tess_hunt.checks import inconclusive, passed
from tess_hunt.cli import main
from tess_hunt.completeness import replay_job, summarise
from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.inject import Injection, inject
from tess_hunt.leo import LeoOutcome
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file
from tess_hunt.search import search_code_sha256, search_star, stellar_density

ROOT = Path(__file__).resolve().parents[1]
CRITERIA = load_criteria(ROOT / "criteria" / "search-v2.toml")
TRIAGE = load_criteria(ROOT / "criteria" / "triage-v1.toml")
LEVEL = CRITERIA["benchmark"]["provisional_sde"]
# The inject run's sample rule wants four sectors, one of them recent; three early ones count here.
COVERED = {
    **CRITERIA.values,
    "sample": {
        **CRITERIA["sample"],
        "min_sectors": 3,
        "recent_sector_min": 1,
        "recent_sector_max": 3,
    },
}
STAR = {"tic": 1, "ra": 30.0, "dec": -40.0, "rad": 1.0, "mass": 1.0, "teff": 5800.0, "logg": 4.4}
# A planet the search recovers at LEVEL (test_benchmark's replay planet) and one far too small to find.
FOUND = {
    "tic": 1,
    "injection": 0,
    "inj_period": 4.3008701448475755,
    "inj_t0": 1325.9997328314087,
    "inj_rp_rearth": 9.0,
    "inj_b": 0.2,
    "inj_rp_rs": 0.0824,
    "inj_a_rs": 12.6,
    "inj_duration": 0.12,
}
MISSED = {**FOUND, "injection": 1, "inj_rp_rearth": 0.5, "inj_rp_rs": 0.0046}
THRESHOLD_RUN = "20261020T000000Z-threshold-abc-1"
INJECT_RUN = "20261021T000000Z-benchmark-inject-abc-2"
TRIAGE_RUN = "20261021T010000Z-triage-abc-3"
HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
).stdout.strip()


def injection(row: dict) -> Injection:
    return Injection(
        *(row[f"inj_{k}"] for k in ("period", "t0", "rp_rearth", "b", "rp_rs", "a_rs", "duration"))
    )


def job(row: dict, known=()) -> dict:
    return {
        "row": row,
        "star": STAR,
        "known": list(known),
        "criteria": {**CRITERIA.values, "search": {**CRITERIA["search"], "continue_sde": LEVEL}},
        "triage": TRIAGE.values,
        "level": LEVEL,
    }


def test_replay_job_runs_leo_on_the_found_signal_not_the_truth(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    # The star has a signal of its own, which the search finds beside the injection.
    lc = make_lc(sectors=(1, 2, 3), noise_ppm=300.0, signals=[(6.7, 1327.3, 0.15, 0.003)], seed=3)
    path = tmp_path / "lc" / "1.npz"
    lc.save(path)
    known = [Ephemeris(9.9, 1326.4, 0.1)]
    [row] = injection_job((STAR, path, known, COVERED, ["bls30"], 1, 11, [FOUND], LEVEL))
    assert row["recovered"]
    seen = []

    def fake_leo(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        seen.append((lc, eph, others, lc.time[exclude]))
        return passed("leo_flux", "planet candidate", disposition="PC"), LeoOutcome("PC"), None

    monkeypatch.setattr(triage, "leo_flux", fake_leo)
    out = replay_job(job(row, known))
    # The oracle: the search of the planted light curve, and the signal it matched to the injection.
    bench = CRITERIA["benchmark"]
    loaded = LightCurve.load(path)
    planted = inject(loaded, injection(FOUND), (bench["inject_u1"], bench["inject_u2"]))
    flat = detrend(planted, CRITERIA["detrend"], known)
    search = {**CRITERIA["search"], "continue_sde": LEVEL, **ENGINES["bls30"]}
    signals = search_star(flat, 1.0, 1.0, search, stellar_density(STAR, 1.0, 1.0)).signals
    matched = signals[row["rank"] - 1]
    [(given, eph, others, excluded)] = seen
    assert eph == matched.ephemeris() and eph.period != FOUND["inj_period"]
    # The star's own signal is dropped as triage drops a star's other signals.
    assert [o.period for o in others] == [
        s.period for s in signals if s.rank != matched.rank and s.sde >= LEVEL
    ]
    assert len(others) == 1 and others[0].period == pytest.approx(6.7, rel=0.01)
    # LEO-Vetter re-detrends for itself, so it gets the planted light curve before detrending, with the
    # known object's transits excluded as triage excludes them.
    assert np.array_equal(given.time, loaded.time) and np.array_equal(given.flux, planted.flux)
    window = in_transit(loaded.time, known[0], CRITERIA["detrend"]["known_mask_width"])
    assert window.any() and np.array_equal(excluded, loaded.time[window])
    assert (out["tic"], out["injection"], out["engine"], out["replay"]) == (1, 0, "bls30", "ok")
    assert (out["period"], out["t0"], out["duration"], out["depth"]) == (
        eph.period,
        eph.t0,
        eph.duration,
        eph.depth,
    )
    assert (out["leo_flux"], out["leo_disposition"], out["fa_failed"]) == ("pass", "PC", "")


def test_replay_job_does_not_judge_a_search_that_differs_from_the_inject_run(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path))
    path = tmp_path / "lc" / "1.npz"
    make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=3).save(path)
    [row] = injection_job((STAR, path, [], COVERED, ["bls30"], 1, 11, [FOUND], LEVEL))
    monkeypatch.setattr(triage, "leo_flux", lambda *a, **k: pytest.fail("judged"))
    out = replay_job(job({**row, "sde": row["sde"] + 0.5}))
    assert out["replay"] == "not_reproduced" and "SDE" in out["replay_reason"]


def write_run(path: Path, provenance: dict) -> Path:
    path.mkdir(parents=True)
    (path / "provenance.json").write_text(
        json.dumps({"ended_at": "2026-10-21T02:00:00+00:00", **provenance})
    )
    return path


def edit_json(path: Path, change) -> None:
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


@pytest.fixture(scope="module")
def m2(tmp_path_factory):
    """A light curve and the inject run's rows for it: one planet recovered, one missed."""
    path = tmp_path_factory.mktemp("m2") / "1.npz"
    make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=3).save(path)
    rows = injection_job((STAR, path, [], COVERED, ["bls30"], 1, 11, [FOUND, MISSED], LEVEL))
    assert [r["recovered"] for r in rows] == [True, False]
    return path, rows


def setup(tmp_path, monkeypatch, m2, production=False):
    path, rows = m2
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    (data / "lc").mkdir(parents=True)
    # Copied, not saved again: a new save writes other bytes, and so another sha256.
    shutil.copy(path, data / "lc" / "1.npz")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([STAR]).to_parquet(targets)
    masks = write_catalog_snapshot(tmp_path / "masks")
    snap = tmp_path / "snap"
    snap.mkdir()
    base = {"ra": 1.0, "dec": 80.0, "duration": 0.1, "depth_ppm": 1000.0}
    known = pd.DataFrame(
        [
            {**base, "source": s, "kind": k, "name": n, "tic": t, "period": p, "t0": t0}
            for s, k, n, t, p, t0 in [
                ("TOI", "candidate", "far", 999, 2.5, 100.0),
                ("CTOI", "candidate", "far2", 998, 3.5, 100.0),
                ("archive", "planet", "far3", 997, 4.5, 100.0),
                ("TESS-EB", "eb", "far EB", 996, 5.5, 100.0),
                # SPOC saw the injected planet's period on the star: novelty says so.
                ("SPOC-TCE", "tce", "TCE s0001 1", 1, FOUND["inj_period"], FOUND["inj_t0"]),
            ]
        ]
    )[KNOWN_COLUMNS]
    known.loc[known["tic"] == 1, ["ra", "dec"]] = (STAR["ra"], STAR["dec"])
    known.to_parquet(snap / "known.parquet")
    (snap / "manifest.json").write_text("{}")
    runs = data / "runs"
    thr = write_run(runs / THRESHOLD_RUN, {"run_id": THRESHOLD_RUN, "stage": "threshold"})
    (thr / "threshold.json").write_text(
        json.dumps(
            {
                "threshold": LEVEL,
                "search_criteria_sha256": CRITERIA.sha256,
                "search_code_sha256": search_code_sha256(ROOT),
            }
        )
    )

    def inputs(snapshot: Path, prefix: str = "") -> dict:
        return {
            prefix + name: {"file": p.name, "sha256": sha256_file(p)}
            for name, p in snapshot_inputs(snapshot).items()
        }

    shared = {
        "production": production,
        "threshold": {"value": LEVEL, "file": "threshold.json", "run_id": THRESHOLD_RUN},
        # Made at this checkout, so LEO-Vetter judges here as it did there.
        "git": {"commit": HEAD, "dirty_paths": []},
        "uv_lock_sha256": sha256_file(ROOT / "uv.lock"),
    }
    read = {
        "targets": {"file": targets.name, "sha256": sha256_file(targets)},
        "threshold": {"file": "threshold.json", "sha256": sha256_file(thr / "threshold.json")},
    }
    search_entry = {"file": "criteria/search-v2.toml", "sha256": CRITERIA.sha256}
    injected = write_run(
        runs / INJECT_RUN,
        {
            "run_id": INJECT_RUN,
            "stage": "benchmark-inject",
            "criteria": [search_entry],
            "inputs": {**inputs(masks), **read},
            **shared,
        },
    )
    pd.DataFrame(rows).to_csv(injected / "injections.csv", index=False)
    triaged = write_run(
        runs / TRIAGE_RUN,
        {
            "run_id": TRIAGE_RUN,
            "stage": "triage",
            "criteria": [
                search_entry,
                {"file": "criteria/triage-v1.toml", "sha256": TRIAGE.sha256},
            ],
            "inputs": {**inputs(snap), **inputs(masks, "mask_"), **read},
            **shared,
        },
    )
    calls = []

    def fake_leo(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        calls.append(eph)
        return (
            passed("leo_flux", "planet candidate", disposition="PC"),
            LeoOutcome("PC", unknown=["asymmetric"]),
            None,
        )

    monkeypatch.setattr(triage, "leo_flux", fake_leo)
    monkeypatch.chdir(ROOT)
    argv = [
        "benchmark",
        "triage-completeness",
        "--inject-run",
        str(injected),
        "--triage-run",
        str(triaged),
        "--catalogs",
        str(snap),
        "--mask-catalogs",
        str(masks),
        "--targets",
        str(targets),
        "--workers",
        "1",
    ]
    return argv, calls


def completeness_runs(tmp_path) -> list[Path]:
    return sorted((tmp_path / "data" / "runs").glob("*-benchmark-triage-completeness-*"))


def test_triage_completeness_judges_only_the_recovered_injections(tmp_path, monkeypatch, m2):
    argv, calls = setup(tmp_path, monkeypatch, m2)
    assert main(argv) == 0
    [run] = completeness_runs(tmp_path)
    rows = pd.read_csv(run / "rows.csv", float_precision="round_trip").set_index("injection")
    assert len(calls) == 1 and calls[0].period == rows.loc[0, "period"]
    assert rows.loc[0, "replay"] == "ok" and pd.isna(rows.loc[1, "replay"])
    assert (rows.loc[0, "leo_flux"], rows.loc[0, "unknown"]) == ("pass", "asymmetric")
    # Novelty judged the found signal against the v2 catalog, as triage judges one.
    assert rows.loc[0, "novelty_category"] == "known_to_spoc"
    by_snr = pd.read_csv(run / "by_snr.csv")
    assert by_snr["searched"].sum() == 2 and by_snr["judged"].sum() == 1
    for name in ("by_period", "by_radius", "failed_tests", "outcomes"):
        assert (run / f"{name}.csv").exists()
    assert "## By expected SNR" in (run / "summary.md").read_text()
    provenance = json.loads((run / "provenance.json").read_text())
    assert (provenance["inject_run"], provenance["triage_run"]) == (INJECT_RUN, TRIAGE_RUN)
    assert provenance["threshold"]["run_id"] == THRESHOLD_RUN
    assert provenance["summary"]["judged"] == 1 and provenance["summary"]["recovered"] == 1


def test_triage_completeness_with_nothing_recovered_writes_empty_shares(tmp_path, monkeypatch, m2):
    argv, calls = setup(tmp_path, monkeypatch, m2)
    path = tmp_path / "data/runs" / INJECT_RUN / "injections.csv"
    pd.read_csv(path).assign(recovered=False).to_csv(path, index=False)
    # Empty tables are where pandas warns about casts and downcasts; none may reach the output.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert main(argv) == 0
    [run] = completeness_runs(tmp_path)
    by_snr = pd.read_csv(run / "by_snr.csv")
    assert calls == [] and by_snr["judged"].sum() == 0 and by_snr["triage_pass"].isna().all()
    assert pd.read_csv(run / "failed_tests.csv").empty
    assert "Judged: 0." in (run / "summary.md").read_text()


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p: p.update(uv_lock_sha256="0" * 64), "uv.lock differs"),
        (
            lambda p: p["git"].update(dirty_paths=["src/tess_hunt/leo.py"]),
            "leo.py had uncommitted changes",
        ),
    ],
)
def test_triage_completeness_refuses_another_lock_or_wrapper(
    tmp_path, monkeypatch, m2, change, message
):
    argv, _ = setup(tmp_path, monkeypatch, m2)
    edit_json(tmp_path / "data/runs" / TRIAGE_RUN / "provenance.json", change)
    with pytest.raises(
        SystemExit, match=f"LEO-Vetter would not judge as in {TRIAGE_RUN}: .*{message}"
    ):
        main(argv)
    assert not completeness_runs(tmp_path)


@pytest.mark.parametrize(
    ("old", "new", "refused"),
    [
        ("\nMES = 6.2\n", "\nMES = 7.1\n", True),
        ("neighbour_arcmin = 2.5", "neighbour_arcmin = 3.0", True),
        ("max_offset_arcsec = 15.0", "max_offset_arcsec = 20.0", False),
    ],
)
def test_triage_completeness_refuses_other_triage_criteria(
    tmp_path, monkeypatch, m2, old, new, refused
):
    argv, _ = setup(tmp_path, monkeypatch, m2)
    text = (ROOT / "criteria" / "triage-v1.toml").read_text()
    assert old in text
    criteria = tmp_path / "triage.toml"
    criteria.write_text(text.replace(old, new))
    argv += ["--criteria-triage", str(criteria)]
    if refused:
        with pytest.raises(SystemExit, match=r"\[leo\], \[leo_metrics\] and \[novelty\]"):
            main(argv)
        assert not completeness_runs(tmp_path)
    else:
        assert main(argv) == 0


def rewrite_threshold(tmp: Path) -> None:
    """The threshold file names other search code, and both runs read it."""
    path = tmp / "data/runs" / THRESHOLD_RUN / "threshold.json"
    edit_json(path, lambda t: t.update(search_code_sha256="0" * 64))
    for run in (INJECT_RUN, TRIAGE_RUN):
        edit_json(
            tmp / "data/runs" / run / "provenance.json",
            lambda p: p["inputs"]["threshold"].update(sha256=sha256_file(path)),
        )


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / INJECT_RUN / "provenance.json",
                lambda p: p.update(ended_at=None),
            ),
            f"{INJECT_RUN} has not finished",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / TRIAGE_RUN / "provenance.json",
                lambda p: p.update(ended_at=None),
            ),
            f"{TRIAGE_RUN} has not finished",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / TRIAGE_RUN / "provenance.json",
                lambda p: p.update(stage="search"),
            ),
            f"{TRIAGE_RUN} is not a triage run",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / INJECT_RUN / "provenance.json",
                lambda p: p.update(uv_lock_sha256="0" * 64),
            ),
            f"uv.lock differs from the one {INJECT_RUN} ran",
        ),
        (
            lambda tmp: edit_json(
                tmp / "data/runs" / TRIAGE_RUN / "provenance.json",
                lambda p: p["inputs"]["threshold"].update(sha256="0" * 64),
            ),
            f"{INJECT_RUN} and {TRIAGE_RUN} read different threshold files",
        ),
        (rewrite_threshold, "search code changed since the inject run ran"),
        (
            lambda tmp: make_lc(sectors=(1, 2, 3), noise_ppm=300.0, seed=4).save(
                tmp / "data/lc/1.npz"
            ),
            r"light curves of 1 inject run star differ .*\[1\]",
        ),
        (
            lambda tmp: (tmp / "masks" / "toi.csv").write_text("TIC ID\n1\n"),
            "--mask-catalogs differs from the snapshot the inject run masked with",
        ),
        (
            lambda tmp: (tmp / "snap" / "manifest.json").write_text('{"other": 1}'),
            f"--catalogs differs from the snapshot {TRIAGE_RUN} judged novelty with",
        ),
        (
            lambda tmp: pd.DataFrame([{**STAR, "rad": 1.1}]).to_parquet(tmp / "targets.parquet"),
            "--targets differs from the targets the inject run searched",
        ),
    ],
)
def test_triage_completeness_refuses_runs_it_cannot_replay(
    tmp_path, monkeypatch, m2, change, message
):
    argv, _ = setup(tmp_path, monkeypatch, m2)
    change(tmp_path)
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert not completeness_runs(tmp_path)


def test_production_triage_completeness_needs_production_runs(tmp_path, monkeypatch, m2):
    argv, _ = setup(tmp_path, monkeypatch, m2)
    with pytest.raises(SystemExit, match="needs a production inject run and triage run"):
        main([*argv, "--production"])
    assert not completeness_runs(tmp_path)


def test_summarise_bins_and_counts():
    def row(snr, period, radius, recovered, replay=None, **judged):
        return {
            "status": "ok",
            "engine": "bls30",
            "expected_snr": snr,
            "inj_period": period,
            "inj_rp_rearth": radius,
            "recovered": recovered,
            "replay": replay,
            **judged,
        }

    rows = pd.DataFrame(
        [
            row(6.0, 1.5, 0.7, False),
            row(6.0, 1.5, 0.7, True, "ok", novelty="pass", leo_flux="pass", fa_failed=""),
            row(
                12.0,
                3.0,
                3.0,
                True,
                "ok",
                novelty="pass",
                leo_flux="fail",
                fa_failed="non_unique, sinusoidal",
            ),
            row(
                12.0,
                3.0,
                3.0,
                True,
                "ok",
                novelty="inconclusive",
                leo_flux="fail",
                fp_failed="odd_even",
                unknown="asymmetric, chi: KeyError",
            ),
            # Not reproduced: searched and recovered, never judged.
            row(12.0, 3.0, 3.0, True, "not_reproduced"),
        ]
    )
    tables = summarise(rows)
    snr = tables["by_snr"].set_index("bin")
    low, mid = snr.loc["[5.0, 7.0)"], snr.loc["[10.0, 15.0)"]
    assert (low["searched"], low["search"], low["judged"]) == (2, 0.5, 1)
    assert (low["leo_pc"], low["novelty_pass"], low["triage_pass"], low["product"]) == (
        1,
        1,
        1,
        0.5,
    )
    assert (mid["searched"], mid["search"], mid["judged"]) == (3, 1.0, 2)
    assert (mid["leo_pc"], mid["novelty_pass"], mid["triage_pass"], mid["product"]) == (
        0,
        0.5,
        0,
        0,
    )
    assert snr.loc["[0.0, 5.0)", "judged"] == 0 and np.isnan(snr.loc["[0.0, 5.0)", "leo_pc"])
    period = tables["by_period"].set_index("bin")
    assert (period.loc["[1, 2)", "judged"], period.loc["[2, 4)", "novelty_pass"]) == (1, 0.5)
    radius = tables["by_radius"].set_index("bin")
    assert radius.loc["[2.0, 4.0)", "search"] == 1.0
    failed = {
        (r["kind"], r["test"]): r["injections"] for r in tables["failed_tests"].to_dict("records")
    }
    assert failed == {
        ("fa_failed", "non_unique"): 1,
        ("fa_failed", "sinusoidal"): 1,
        ("fp_failed", "odd_even"): 1,
        ("unknown", "asymmetric"): 1,
        ("unknown", "chi"): 1,
    }
    outcomes = tables["outcomes"].set_index("step")
    assert outcomes.loc["novelty"].to_dict() == {"pass": 2, "fail": 0, "inconclusive": 1}
    assert outcomes.loc["leo_flux"].to_dict() == {"pass": 1, "fail": 2, "inconclusive": 0}


def test_pixel_completeness_uses_the_catalog_ephemeris(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    make_lc(sectors=(1, 2, 98), tic=5).save(data / "lc" / "5.npz")
    planets = [
        {"toi": "50.01", "tic": 5, "period": 3.1, "t0": 1326.2, "duration": 0.11},
        {"toi": "50.02", "tic": 5, "period": 7.7, "t0": 1327.9, "duration": 0.16},
        # Its host's light curve was never fetched.
        {"toi": "60.01", "tic": 6, "period": 2.2, "t0": 1325.4, "duration": 0.09},
    ]
    known = tmp_path / "known.csv"
    pd.DataFrame(planets).to_csv(known, index=False)
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([{"tic": t, "ra": 30.0 + t, "dec": -40.0} for t in (5, 6)]).to_parquet(targets)
    seen = {}

    def check(tlc, star, sectors, cfg, tdi):
        seen[Path(tdi).name] = (dict(tlc.metrics), int(star["tic"]), sorted(sectors))
        if not sectors:
            return inconclusive("pixels", "no sector with data")
        return passed("pixels", "ok", offset_qual_arcsec=2.5)

    monkeypatch.setattr(triage, "pixel_check", check)
    monkeypatch.chdir(ROOT)
    argv = ["benchmark", "pixel-completeness", "--known", str(known), "--targets", str(targets)]
    assert main([*argv, "--workers", "1"]) == 0
    for p in planets:
        metrics, tic, sectors = seen[f"{p['tic']}-{p['toi']}"]
        assert (metrics["per"], metrics["epo"], metrics["dur"]) == (
            p["period"],
            p["t0"],
            p["duration"],
        )
        assert metrics["tic"] == tic == p["tic"]
    assert seen["5-50.01"][2] == [1, 2, 98] and seen["6-60.01"][2] == []
    [run] = sorted((data / "runs").glob("*-benchmark-pixel-completeness-*"))
    table = pd.read_csv(run / "pixels.csv", dtype={"toi": str}).set_index("toi")
    assert list(table["pixels"]) == ["pass", "pass", "inconclusive"]
    assert table.loc["50.02", "offset_qual_arcsec"] == 2.5
    assert np.isnan(table.loc["60.01", "offset_qual_arcsec"])
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert summary == {"planets": 3, "pass": 2, "fail": 0, "inconclusive": 1}
