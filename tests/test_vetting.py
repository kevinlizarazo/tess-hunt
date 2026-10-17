import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_transit_lc, with_products, write_catalog_snapshot

from tess_hunt import gaia, neighbours, plots, predict, vet, vetting
from tess_hunt.catalogs import KNOWN_COLUMNS
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.fit import NAMES, FitResult
from tess_hunt.provenance import sha256_file

ROOT = Path(__file__).resolve().parents[1]
SEARCH = ROOT / "criteria" / "search-v2.toml"
VET3 = ROOT / "criteria" / "vet-v3.toml"
TRIAGE = load_criteria(ROOT / "criteria" / "triage-v1.toml")
NAN = float("nan")
CANDIDATE = {"tic": 1, "ra": 30.0, "dec": -40.0, "tmag": 9.0, "rho": 1.0, "e_rho": 0.1, "rad": 1.0}
# The control targets tables have no dr3_source_id column, and this star no TIC density.
CONTROL = {"tic": 2, "ra": 60.0, "dec": -50.0, "tmag": 10.0, "rho": NAN, "e_rho": NAN, "rad": 1.0}
SIGNAL = {"period": 5.0, "t0": 1326.1, "duration": 0.13, "depth": 0.0017}
SIGNALS = [
    {"name": "1-1", "tic": 1, **SIGNAL, "kind": "candidate"},
    {"name": "TOI-9.01", "tic": 2, **SIGNAL, "kind": "control"},
]
PLOTS = {"transits.png", "folds.png", "odd_even.png", "phase.png", "centroids.png"}
MODSHIFT = {
    "sig_pri": 15.2,
    "sig_sec": 3.1,
    "sig_ter": 3.0,
    "sig_pos": 5.2,
    "phs_pri": 0.0001,
    "phs_sec": 0.759,
    "phs_ter": 0.513,
    "phs_pos": 0.533,
    "dep_sec": 0.00016,
    "err_sec": 0.00005,
    "Fred": 1.12,
}
TRIAGE_RUN = "20261015T000000Z-triage-abc-1"
SEARCH_RUN = "20261014T000000Z-search-abc-1"


def fast_criteria(tmp_path: Path) -> Path:
    """vet-v3 with a short chain, so the fits take seconds."""
    text = VET3.read_text()
    for old, new in (("steps = 5000", "steps = 400"), ("burn = 2000", "burn = 200")):
        assert old in text
        text = text.replace(old, new)
    path = tmp_path / "vet-v3-fast.toml"
    path.write_text(text)
    return path


def v2_snapshot(path: Path) -> Path:
    path.mkdir()
    base = {"ra": 200.0, "dec": 10.0, "duration": 0.1, "depth_ppm": 1000.0, "t0": 100.0}
    rows = [
        ("TOI", "candidate", "far", 999, 2.5),
        ("CTOI", "candidate", "far2", 998, 3.5),
        ("archive", "planet", "far3", 997, 4.5),
        ("SPOC-TCE", "tce", "far TCE", 996, 5.5),
        ("TESS-EB", "eb", "far EB", 995, 6.5),
    ]
    known = pd.DataFrame(
        [
            {**base, "source": s, "kind": k, "name": n, "tic": t, "period": p}
            for s, k, n, t, p in rows
        ]
    )[KNOWN_COLUMNS]
    known.to_parquet(path / "known.parquet")
    (path / "manifest.json").write_text("{}\n")
    return path


def cone(ra, dec, radius_arcmin, **kwargs):
    """The target 0.2" from its TIC position and one star 12" away, 5 magnitudes fainter."""
    source = 101 if ra == CANDIDATE["ra"] else 202
    return pd.DataFrame(
        [
            (source, ra, dec, 9.2, 0.8, 0.2, NAN, NAN, 2016.0),
            (7, ra, dec, 14.2, 0.8, 12.0, NAN, NAN, 2016.0),
        ],
        columns=neighbours.COLUMNS,
    )


def join(found: dict, asked: list | None = None):
    """gaia.dr3_join without the archive: `found` maps a TIC to its Gaia DR3 source id and RUWE; `asked` collects
    the rows each call was given."""

    def dr3_join(stars):
        if asked is not None:
            asked.append(stars[["tic", "gaia"]].to_dict("records"))
        rows = [
            {"tic": t, "dr3_source_id": found[t][0], "ruwe": found[t][1]}
            for t in stars["tic"]
            if t in found
        ]
        return pd.DataFrame(rows, columns=gaia.COLUMNS)

    return dr3_join


def fake_fit(lc, eph, cfg, rho_prior=None, seed=None):
    rng = np.random.default_rng(0)
    n = 4000
    values = {
        "t0": eph.t0 + rng.normal(0.0, 1e-3, n),
        "period": eph.period + rng.normal(0.0, 1e-5, n),
        "rp_rs": np.full(n, 0.04),
        "b": np.full(n, 0.3),
        "log_rho": np.full(n, 0.15),
        "q1": np.full(n, 0.36),
        "q2": np.full(n, 0.36),
    }
    return FitResult(np.column_stack([values[name] for name in NAMES]), 0.3, rho_prior)


def setup(tmp_path, monkeypatch, signals=SIGNALS, suspect=(), fit=None):
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    for star in (CANDIDATE, CONTROL):
        lc = make_transit_lc(
            rp_rs=0.04,
            cadences={1: 30.0, 2: 30.0, 64: 30.0},
            noise_ppm=dict.fromkeys((1, 2, 64), 200.0),
        )
        lc.tic = star["tic"]
        with_products(lc, dict.fromkeys((1, 2, 64), "SPOC"), suspect=suspect)
        lc.save(data / "lc" / f"{star['tic']}.npz")
    targets = tmp_path / "targets.parquet"
    pd.DataFrame([CANDIDATE]).astype({"tic": "int64"}).assign(
        dr3_source_id=pd.array([101], dtype="Int64")
    ).to_parquet(targets)
    controls = tmp_path / "controls.parquet"
    pd.DataFrame([CONTROL]).to_parquet(controls)
    signals_csv = tmp_path / "signals.csv"
    pd.DataFrame(signals).to_csv(signals_csv, index=False)
    depths = []
    original = neighbours.required_depths

    def watched(table, depth, t_target, target_source_id, cfg):
        depths.append((depth, t_target, target_source_id))
        return original(table, depth, t_target, target_source_id, cfg)

    monkeypatch.setattr(neighbours, "gaia_cone", cone)
    monkeypatch.setattr(neighbours, "required_depths", watched)
    # Never the archive: a star the fixtures leave without a DR3 id or RUWE matches nothing.
    monkeypatch.setattr(gaia, "dr3_join", join({}))
    # tess-point's layout: index 3 holds the sectors, one row per camera.
    monkeypatch.setattr(
        predict,
        "tess_stars2px_function_entry",
        lambda tic, ra, dec: (None, None, None, np.array([35, 110, 111, 115])),
    )
    if fit is not None:
        monkeypatch.setattr(vet, "fit_transit", fit)
    monkeypatch.chdir(ROOT)
    argv = [
        "vetting",
        "run",
        *("--signals", str(signals_csv)),
        *("--targets", str(targets), "--targets", str(controls)),
        *("--catalogs", str(v2_snapshot(tmp_path / "snap"))),
        *("--criteria-search", str(SEARCH)),
        *("--criteria-vet", str(VET3)),
        *("--workers", "1"),
    ]
    return argv, depths


def only_run(tmp_path) -> Path:
    [run] = (tmp_path / "data" / "runs").glob("*-vetting-run-*")
    return run


def read(run: Path, name: str) -> dict:
    return json.loads((run / "signals" / name / "checks.json").read_text())


def no_run(tmp_path) -> bool:
    runs = tmp_path / "data" / "runs"
    return not runs.exists() or not any(runs.iterdir())


@pytest.mark.slow
def test_vetting_run_writes_one_directory_per_signal(tmp_path, monkeypatch):
    argv, depths = setup(tmp_path, monkeypatch)
    fast = fast_criteria(tmp_path)
    argv[argv.index(str(VET3))] = str(fast)
    run_jobs = vetting.run_jobs

    def through_pickle(fn, jobs, workers):
        # What a spawned worker gets and gives back; the fakes above need this process.
        jobs = [pickle.loads(pickle.dumps(job)) for job in jobs]
        return [pickle.loads(pickle.dumps(r)) for r in run_jobs(fn, jobs, workers)]

    monkeypatch.setattr(vetting, "run_jobs", through_pickle)
    assert main(argv) == 0
    run = only_run(tmp_path)
    assert sorted(p.name for p in (run / "signals").iterdir()) == ["1-1", "TOI-9.01"]

    checks = read(run, "1-1")
    assert checks["criteria_version"] == "vet-v3" and checks["evidence_only"] is False
    assert checks["signal"] == {"name": "1-1", "kind": "candidate"}
    assert checks["star"]["dr3_source_id"] == 101 and checks["sources"]["1"]["provenance"] == "SPOC"
    assert {c["check"] for c in checks["checks"]} >= {"odd_even", "shape", "density", "radius"}
    # The neighbour table sits beside the checks, never among them.
    assert "neighbours" not in {c["check"] for c in checks["checks"]}
    nb = checks["neighbours"]
    assert nb["outcome"] == "pass", nb
    assert [h["source_id"] for h in nb["evidence"]["possible_hosts"]] == [7]
    assert nb["evidence"]["depth"] == SIGNAL["depth"]
    assert nb["evidence"]["depth_from"] == "the signals file"
    # The candidate's targets row gives its DR3 id; the control's table has none.
    assert depths == [(SIGNAL["depth"], 9.0, 101), (SIGNAL["depth"], 10.0, None)]
    assert type(depths[0][2]) is int
    table = pd.read_csv(run / "signals" / "1-1" / "neighbours.csv")
    assert table["source_id"].tolist() == [7]

    assert checks["upcoming_sectors"] == [110, 111, 115]
    dated = [w for w in checks["windows"] if "epoch" in w]
    assert {w["sector"] for w in dated} == {110, 111}
    assert {"sector": 115, "dates": "unknown"} in checks["windows"]
    assert checks["window_duration"]["from"] == "fit_prior"
    assert checks["window_duration"]["days"] == pytest.approx(SIGNAL["duration"], rel=0.25)
    assert all(w["duration_days"] == checks["window_duration"]["days"] for w in dated)
    assert checks["windows_reason"] is None

    for name in ("fit_samples.npz", "fit_prior_samples.npz"):
        with np.load(run / "signals" / "1-1" / name) as z:
            assert z["samples"].shape[1] == len(NAMES), name
    for name in ("modshift", "pixels", "other_signals"):
        assert checks[name] is None
    assert checks["triage_reason"] == "no --triage-run given"
    assert {p.name for p in (run / "signals" / "1-1" / "plots").iterdir()} == PLOTS

    control = read(run, "TOI-9.01")
    assert control["signal"] == {"name": "TOI-9.01", "kind": "control"}
    assert control["fit_prior"] is None
    assert not (run / "signals" / "TOI-9.01" / "fit_prior_samples.npz").exists()
    assert control["windows"] is None and control["upcoming_sectors"] == [110, 111, 115]
    assert control["windows_reason"] == "no density-prior fit: the TIC gives no stellar density"
    assert {p.name for p in (run / "signals" / "TOI-9.01" / "plots").iterdir()} == PLOTS

    provenance = json.loads((run / "provenance.json").read_text())
    criteria = load_criteria(fast)
    assert provenance["criteria"][1]["sha256"] == criteria.sha256, "Ruling C reads it here"
    assert provenance["evidence_only"] is False and provenance["triage_run"] is None
    inputs = provenance["inputs"]
    assert {"signals", "targets_1", "targets_2", "known", "catalog_manifest"} <= set(inputs)
    for tic in (1, 2):
        lc = tmp_path / "data" / "lc" / f"{tic}.npz"
        assert inputs[f"light_curve_{tic}"]["sha256"] == sha256_file(lc)
    sectors = ROOT / "benchmarks" / "tess_sectors.csv"
    assert inputs["tess_sectors"]["sha256"] == sha256_file(sectors)
    summary = provenance["summary"]
    assert summary["evidence_only"] is False and summary["errors"] == {}
    assert summary["signals"]["1-1"]["outcomes"] == {
        c["check"]: c["outcome"] for c in checks["checks"]
    }
    assert summary["signals"]["1-1"]["neighbours"] == "pass"


def test_vetting_run_refuses_v2_criteria(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    argv[argv.index(str(VET3))] = str(ROOT / "criteria" / "vet-v2.toml")
    with pytest.raises(SystemExit, match=r"\[families\]"):
        main(argv)
    assert no_run(tmp_path)


def test_vetting_run_refuses_a_v1_snapshot(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch)
    argv[argv.index("--catalogs") + 1] = str(write_catalog_snapshot(tmp_path / "v1"))
    with pytest.raises(SystemExit, match="not a v2 snapshot"):
        main(argv)
    assert no_run(tmp_path)


@pytest.mark.parametrize(
    "change, message",
    [
        (lambda rows: rows[:1] + [{**rows[1], "tic": 3}], "no targets file lists TIC 3"),
        (lambda rows: rows[:1] + [{**rows[1], "kind": "planet"}], "unknown kind"),
        (lambda rows: rows[:1] + [{**rows[1], "name": "1-1"}], "more than once: 1-1"),
        (lambda rows: rows[:1] + [{**rows[1], "t0": 2459326.1}], "BTJD"),
    ],
)
def test_vetting_run_refuses_a_signal_list_it_cannot_vet(tmp_path, monkeypatch, change, message):
    argv, _ = setup(tmp_path, monkeypatch, signals=change(SIGNALS))
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert no_run(tmp_path)


# A DR2 id past 2**53, as the TIC's are: a float would round it.
DR2 = "5431607545961330561"


def test_a_star_without_dr3_values_gets_them_from_the_join(tmp_path, monkeypatch):
    """Ruling N: the control targets tables (`targets tics`) carry the TIC's Gaia DR2 id and no DR3 columns, so
    TRICERATOPS would have no RUWE and the neighbour table no DR3 id for them."""
    # The sample's targets row carries both values; the control's carries only the DR2 id.
    monkeypatch.setitem(globals(), "CANDIDATE", {**CANDIDATE, "ruwe": 0.9})
    monkeypatch.setitem(globals(), "CONTROL", {**CONTROL, "gaia": DR2})
    argv, depths = setup(tmp_path, monkeypatch, fit=fake_fit)
    asked = []
    monkeypatch.setattr(gaia, "dr3_join", join({2: (202, 1.1)}, asked))
    assert main(argv) == 0
    run = only_run(tmp_path)
    # One join for the run, and a row that has both values is never joined again.
    assert asked == [[{"tic": 2, "gaia": DR2}]]
    candidate, control = read(run, "1-1")["star"], read(run, "TOI-9.01")["star"]
    assert candidate["dr3_source_id"] == 101 and candidate["ruwe"] == 0.9
    assert candidate["dr3_from"] == "targets" and candidate["dr3_reason"] is None
    assert control["dr3_source_id"] == 202 and control["ruwe"] == 1.1
    assert control["dr3_from"] == "dr3_join" and control["dr3_reason"] is None
    # The neighbour table now finds the control's target by its DR3 id.
    assert depths == [(SIGNAL["depth"], 9.0, 101), (SIGNAL["depth"], 10.0, 202)]
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["dr3_join"] == {"tics": [2], "worked": True, "error": None}


def down(stars):
    raise gaia.GaiaError("Gaia archive failed 3 times: OSError: archive unavailable")


@pytest.mark.parametrize(
    "dr3_join, reason, worked",
    [
        (
            down,
            "the Gaia DR3 join failed: Gaia archive failed 3 times: OSError: archive unavailable",
            False,
        ),
        (join({}), f"the Gaia DR3 join found no source for Gaia DR2 {DR2}", True),
    ],
    ids=["failed", "no match"],
)
def test_a_star_the_join_gives_nothing_keeps_nulls_and_the_reason(
    tmp_path, monkeypatch, dr3_join, reason, worked
):
    monkeypatch.setitem(globals(), "CONTROL", {**CONTROL, "gaia": DR2})
    argv, depths = setup(tmp_path, monkeypatch, fit=fake_fit)
    monkeypatch.setattr(gaia, "dr3_join", dr3_join)
    assert main(argv) == 0
    run = only_run(tmp_path)
    # Every star row carries both keys, which the dossier reads.
    control = read(run, "TOI-9.01")["star"]
    assert control["dr3_source_id"] is None and control["ruwe"] is None
    assert control["dr3_from"] == "missing" and control["dr3_reason"] == reason
    # The candidate lacks only RUWE, and keeps its targets row's DR3 id.
    candidate = read(run, "1-1")["star"]
    assert candidate["dr3_source_id"] == 101 and candidate["ruwe"] is None
    assert candidate["dr3_from"] == "missing"
    assert candidate["dr3_reason"] == "the TIC gives no Gaia DR2 id to join on"
    # Without an id the neighbour table takes the one star within 1" of the TIC position, as before.
    assert depths == [(SIGNAL["depth"], 9.0, 101), (SIGNAL["depth"], 10.0, None)]
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["ended_at"] is not None
    error = None if worked else reason.removeprefix("the Gaia DR3 join failed: ")
    assert provenance["dr3_join"] == {"tics": [1, 2], "worked": worked, "error": error}


def test_evidence_only_run_is_marked(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch, signals=SIGNALS[:1], suspect={64}, fit=fake_fit)

    def down(*args, **kwargs):
        raise neighbours.NeighbourError("Gaia archive failed after 3 attempts")

    monkeypatch.setattr(neighbours, "gaia_cone", down)
    assert main(argv) == 0
    main_run = only_run(tmp_path)
    good = read(main_run, "1-1")
    assert good["dropped_suspect"] == [64] and good["windows"]
    assert good["neighbours"]["outcome"] == "inconclusive"
    assert "Gaia archive failed" in good["neighbours"]["reason"]
    assert not (main_run / "signals" / "1-1" / "neighbours.csv").exists()

    assert main([*argv, "--include-suspect"]) == 0
    [evidence_run] = [r for r in (tmp_path / "data" / "runs").iterdir() if r != main_run]
    checks = read(evidence_run, "1-1")
    assert checks["evidence_only"] is True and checks["dropped_suspect"] == []
    assert checks["windows"] is None and checks["upcoming_sectors"] is None
    assert "evidence-only" in checks["windows_reason"]
    assert (evidence_run / "signals" / "1-1" / "fit_prior_samples.npz").exists()
    provenance = json.loads((evidence_run / "provenance.json").read_text())
    assert provenance["evidence_only"] is True and provenance["summary"]["evidence_only"] is True
    assert "advances" not in provenance["summary"]["signals"]["1-1"]


def triage_run(tmp_path: Path) -> Path:
    runs = tmp_path / "data" / "runs"
    search = runs / SEARCH_RUN
    search.mkdir(parents=True)
    pd.DataFrame(
        [
            {"tic": 1, "rank": 1, "period": 5.0, "t0": 1326.1, "duration": 0.13, "depth": 0.0017},
            {"tic": 1, "rank": 2, "period": 7.5, "t0": 1327.0, "duration": 0.1, "depth": 0.0005},
            {"tic": 4, "rank": 1, "period": 3.0, "t0": 1326.0, "duration": 0.1, "depth": 0.001},
        ]
    ).assign(sde=[40.0, 12.0, 30.0]).to_parquet(search / "signals.parquet")
    run = runs / TRIAGE_RUN
    (run / "evidence").mkdir(parents=True)
    pixels = {
        "check": "pixels",
        "outcome": "pass",
        "reason": 'centroid offset 10.9" within 15"',
        "evidence": {
            "sectors": [
                {"sector": 1, "offset_arcsec": 10.9, "quality": 0.92},
                {"sector": 2, "offset_arcsec": 12.8, "quality": 0.84},
            ],
            "offset_qual_arcsec": 10.9,
        },
    }
    evidence = {
        "signal": {"tic": 1, "rank": 1, **SIGNAL},
        "leo_flux": {"outcome": "pass", "evidence": {"metrics": {**MODSHIFT, "MES": 20.0}}},
        "pixels": pixels,
    }
    (run / "evidence" / "1-1.json").write_text(json.dumps(evidence))
    provenance = {
        "run_id": TRIAGE_RUN,
        "stage": "triage",
        "ended_at": "2026-10-16T00:00:00+00:00",
        "search_run": SEARCH_RUN,
        "criteria": [
            {"file": "criteria/search-v2.toml", "sha256": load_criteria(SEARCH).sha256},
            {"file": "criteria/triage-v1.toml", "sha256": TRIAGE.sha256},
        ],
        "inputs": {
            "search_signals": {
                "file": "signals.parquet",
                "sha256": sha256_file(search / "signals.parquet"),
            }
        },
    }
    (run / "provenance.json").write_text(json.dumps(provenance))
    return run


def test_modshift_and_pixels_come_from_the_triage_run(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch, fit=fake_fit)
    triage = triage_run(tmp_path)

    def doubled(ra, dec, radius_arcmin, **kwargs):
        if ra == CANDIDATE["ra"]:
            return cone(ra, dec, radius_arcmin)
        # The control has no DR3 id and two stars within 1", so its target can't be told apart.
        return pd.DataFrame(
            [
                (5, ra, dec, 10.0, 0.8, 0.2, NAN, NAN, 2016.0),
                (6, ra, dec, 10.5, 0.8, 0.6, NAN, NAN, 2016.0),
            ],
            columns=neighbours.COLUMNS,
        )

    monkeypatch.setattr(neighbours, "gaia_cone", doubled)
    assert main([*argv, "--triage-run", str(triage)]) == 0
    run = only_run(tmp_path)
    checks = read(run, "1-1")
    assert checks["modshift"] == MODSHIFT
    evidence = json.loads((triage / "evidence" / "1-1.json").read_text())
    assert checks["pixels"]["evidence"] == evidence["pixels"]["evidence"]
    assert checks["pixels"]["outcome"] == "pass"
    assert checks["pixels"]["max_offset_arcsec"] == TRIAGE["pixels"]["max_offset_arcsec"]
    assert checks["other_signals"] == [
        {
            "rank": 2,
            "period": 7.5,
            "t0": 1327.0,
            "duration": 0.1,
            "depth": 0.0005,
            "sde": 12.0,
            "period_ratio": pytest.approx(1.5),
        }
    ]
    assert checks["triage_reason"] is None

    control = read(run, "TOI-9.01")
    assert control["modshift"] is control["pixels"] is control["other_signals"] is None
    assert control["triage_reason"] == f"TOI-9.01 is not in triage run {TRIAGE_RUN}"
    assert control["neighbours"]["outcome"] == "inconclusive"
    assert "2 Gaia DR3 stars" in control["neighbours"]["reason"]

    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["triage_run"] == TRIAGE_RUN and provenance["search_run"] == SEARCH_RUN
    inputs = provenance["inputs"]
    assert inputs["triage_provenance"]["sha256"] == sha256_file(triage / "provenance.json")
    assert inputs["triage_evidence_1-1"]["sha256"] == sha256_file(triage / "evidence" / "1-1.json")
    assert inputs["search_signals"]["sha256"] == sha256_file(
        tmp_path / "data" / "runs" / SEARCH_RUN / "signals.parquet"
    )


def test_triage_evidence_for_another_star_is_refused(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch, fit=fake_fit)
    triage = triage_run(tmp_path)
    path = triage / "evidence" / "1-1.json"
    evidence = json.loads(path.read_text())
    evidence["signal"]["tic"] = 4
    path.write_text(json.dumps(evidence))
    with pytest.raises(SystemExit, match="TIC 4"):
        main([*argv, "--triage-run", str(triage)])
    assert not list((tmp_path / "data" / "runs").glob("*-vetting-run-*"))


def other_search_criteria(tmp_path: Path) -> list[str]:
    path = tmp_path / "search-other.toml"
    path.write_text(SEARCH.read_text() + "# not the file triage ran with\n")
    return ["--criteria-search", str(path)]


@pytest.mark.parametrize(
    "extra, message",
    [
        # The triage run fixture is not a production run.
        (lambda tmp_path: ["--production"], "not a production triage run"),
        (other_search_criteria, "is not the criteria/search-v2.toml that"),
    ],
)
def test_vetting_run_refuses_triage_evidence_its_checks_cannot_stand_beside(
    tmp_path, monkeypatch, extra, message
):
    argv, _ = setup(tmp_path, monkeypatch, fit=fake_fit)
    triage = triage_run(tmp_path)
    with pytest.raises(SystemExit, match=message):
        main([*argv, "--triage-run", str(triage), *extra(tmp_path)])
    assert not list((tmp_path / "data" / "runs").glob("*-vetting-run-*"))


def test_every_catalogued_row_on_the_star_is_listed_with_the_transits_it_overlaps(
    tmp_path, monkeypatch
):
    argv, _ = setup(tmp_path, monkeypatch, signals=SIGNALS[:1], fit=fake_fit)
    known_file = Path(argv[argv.index("--catalogs") + 1]) / "known.parquet"
    known = pd.read_parquet(known_file)
    on_star = {"tic": 1, "ra": CANDIDATE["ra"], "dec": CANDIDATE["dec"], "depth_ppm": 900.0}
    rows = [
        # The signal itself, a mask the search would leave alone.
        {**on_star, "source": "TOI", "kind": "candidate", "name": "TOI-9.01", **SIGNAL},
        {
            **on_star,
            "source": "CTOI",
            "kind": "candidate",
            "name": "CTOI-1.01",
            "period": 7.3,
            "t0": 1330.0,
            "duration": 0.1,
        },
        # Every third transit of ours; vet-v3 leaves a TCE unmasked, as the search does (0021).
        {
            **on_star,
            "source": "SPOC-TCE",
            "kind": "tce",
            "name": "TCE 1-01",
            "period": 15.0,
            "t0": SIGNAL["t0"],
            "duration": NAN,
        },
        {
            **on_star,
            "source": "RAVEN",
            "kind": "candidate",
            "name": "RAVEN 1",
            "period": 9.8,
            "t0": NAN,
        },
    ]
    pd.concat([known, pd.DataFrame(rows)[KNOWN_COLUMNS]], ignore_index=True).to_parquet(known_file)
    assert main(argv) == 0
    checks = read(only_run(tmp_path), "1-1")
    found = checks["catalogued"]
    ours = found["transits"]
    assert ours == sorted(ours) and len(ours) > 6
    assert found["mask_width_durations"] == 2.0 and found["fallback_duration_days"] == 0.25
    by_name = {r["name"]: r for r in found["rows"]}
    assert list(by_name) == ["TOI-9.01", "CTOI-1.01", "TCE 1-01", "RAVEN 1"]
    toi, ctoi, tce, raven = by_name.values()
    assert toi["matches_signal"] and not toi["masked"] and toi["overlaps"] == ours
    assert ctoi["masked"] and not ctoi["matches_signal"] and set(ctoi["overlaps"]) <= set(ours)
    assert [m["period"] for m in checks["masked"]] == [7.3], "the same rows vet masked"
    assert not tce["masked"] and tce["overlaps"] == [n for n in ours if n % 3 == 0]
    assert tce["duration"] is None, "the catalog's own value; the fallback stands in for it"
    assert raven["overlaps"] is None and not raven["masked"] and raven["t0"] is None
    assert raven["source"] == "RAVEN" and raven["kind"] == "candidate" and raven["period"] == 9.8


def test_a_signal_that_raises_is_recorded_and_the_others_are_vetted(tmp_path, monkeypatch):
    argv, _ = setup(tmp_path, monkeypatch, fit=fake_fit)
    phase = plots.phase

    def breaks_on_the_control(lc, *args):
        if lc.tic == CONTROL["tic"]:
            raise RuntimeError("plotting failed")
        return phase(lc, *args)

    # The control's directory already holds its samples and neighbours.csv when this raises.
    monkeypatch.setattr(plots, "phase", breaks_on_the_control)
    assert main(argv) == 1
    run = only_run(tmp_path)
    assert [p.name for p in (run / "signals").iterdir()] == ["1-1"]
    assert (run / "signals" / "1-1" / "checks.json").is_file()
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["ended_at"] is not None
    assert provenance["summary"]["errors"] == {"TOI-9.01": "raised RuntimeError: plotting failed"}
    assert list(provenance["summary"]["signals"]) == ["1-1"]
