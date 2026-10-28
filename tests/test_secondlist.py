import json
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import test_calls as tc
import test_dossier as td
import test_vetting as tv

from tess_hunt import calls, dossier, secondlist, triage
from tess_hunt.catalogs import KNOWN_COLUMNS
from tess_hunt.checks import failed
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pixels import asked_ephemeris
from tess_hunt.provenance import sha256_file

ROOT = tv.ROOT
MATCH = load_criteria(tv.SEARCH)["match"]
HARMONICS = tuple(load_criteria(tv.VET3)["novelty"]["harmonics"])
NAN = float("nan")
HEAD = subprocess.run(
    ["git", "rev-parse", "HEAD"], cwd=ROOT, check=True, capture_output=True, text=True
).stdout.strip()
NAME = "1-1"
SECOND = [
    {"name": NAME, "tic": 1, **tv.SIGNAL, "kind": "second"},
    {"name": "TOI-9.01", "tic": 2, **tv.SIGNAL, "kind": "control"},
]
DV_ROW = {
    "tce_plnt_num": 1,
    "tce_time0bt": 1400.0,
    "tce_max_mult_ev": 12.0,
    "tce_bin_oedp_stat": 0.5,
    "tce_cap_stat": 1.2,
    "tce_hap_stat": -0.4,
    "tce_dicco_msky": 2.1,
    "tce_dicco_msky_err": 2.5,
    "tce_ditco_msky": 1.7,
    "tce_ditco_msky_err": 2.6,
    "wst_depth": 50.0,
    "tce_model_snr": 30.0,
}
# What triage's evidence holds for a known_to_spoc row that passed the flux tests: LEO-Vetter's metrics, with the
# transit fit's AIC NaN (null in the file), so the pixel check reads the trapezoid fit's ephemeris.
METRICS = {
    **tv.MODSHIFT,
    "tic": 1,
    "planetno": 1,
    "per": 5.0,
    "epo": 1326.1,
    "dur": 0.13,
    "transit_aic": None,
    "transit_per": 5.0002,
    "transit_epo": 1326.12,
    "transit_dur": 0.14,
    "trap_aic": -80.0,
    "trap_per": 5.0001,
    "trap_epo": 1326.11,
    "trap_dur": 0.12,
    "MES": 20.0,
}
NOT_RUN = {
    "check": "pixels",
    "outcome": "inconclusive",
    "reason": "not run: novelty or the flux tests did not pass",
    "evidence": {},
}
FAILED = failed(
    "pixels",
    'centroid offset 21.0" exceeds 15"',
    offset_qual_arcsec=21.0,
    offset_mean_arcsec=18.5,
    sectors=[
        {"sector": 1, "offset_arcsec": 21.0, "quality": 0.9},
        {"sector": 2, "offset_arcsec": 16.0, "quality": 0.6},
    ],
)


def tce_file(snap: Path, run: str, rows: list[dict]) -> None:
    """A dvr-tcestats table as MAST serves it: comment lines, then one row per TCE."""
    first, last = run.split("-")
    path = snap / "raw" / "SPOC-TCE" / f"tess2018206190142-{first}-{last}_dvr-tcestats.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame([{**DV_ROW, "sectors": run, **r} for r in rows])
    path.write_text(
        f"#Select Statistics Per TCE\n#Sectors = {run}\n#\n" + table.to_csv(index=False)
    )


def exominer_v2(snap: Path, name: str, rows: list[dict]) -> None:
    path = snap / "raw" / "ExoMiner-v2" / f"{name}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pd.DataFrame(
        [{"tce_depth": 500.0, "std_score": 0.02, "model_label": "PC", **r} for r in rows]
    )
    path.write_text(
        "# Model: ExoMiner++New\n# mean_score: Average score of 5 models\n"
        + table.to_csv(index=False)
    )


def exominer_v1(snap: Path, rows: list[dict]) -> None:
    path = snap / "raw" / "ExoMiner-v1" / "exominerplusplus_catalog.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    # v1 has no comment lines, and a URL column whose text must not be cut short.
    table = pd.DataFrame(
        [
            {"ExoMiner Unc. Score": 0.01, "DV mini-report URL": "[Download](https://x/a#b)", **r}
            for r in rows
        ]
    )
    table.to_csv(path, index=False)


def v2(uid: str, tic: int, run: str, period: float, score: float) -> dict:
    return {
        "uid": uid,
        "target_id": tic,
        "sector_run": run,
        "tce_period": period,
        "mean_score": score,
    }


def v1(tce: str, tic: int, run: str, period: float, score: float) -> dict:
    return {
        "TCE ID": tce,
        "TIC ID": tic,
        "Sector Run": run,
        "Orbital Period [day]": period,
        "ExoMiner Score": score,
    }


def write_manifest(snap: Path) -> None:
    """The manifest `catalogs refresh` writes: every raw file with its sha256."""
    files = [
        {"source": p.parent.name, "file": f"{p.parent.name}/{p.name}", "sha256": sha256_file(p)}
        for p in sorted((snap / "raw").rglob("*"))
        if p.is_file()
    ]
    (snap / "manifest.json").write_text(json.dumps({"files": files}))


def test_dv_fields_match_by_period(tmp_path):
    snap = tmp_path / "snap"
    # Two TCEs on one star in a multi-sector run, the first again in two single-sector runs, and one on another star.
    tce_file(
        snap,
        "s0001-s0039",
        [
            {"tceid": "00000000005-01", "ticid": 5, "tce_period": 3.0, "tce_max_mult_ev": 20.0},
            {"tceid": "00000000005-02", "ticid": 5, "tce_period": 7.0, "wst_depth": 120.0},
            {"tceid": "00000000006-01", "ticid": 6, "tce_period": 3.0},
        ],
    )
    # S10 also found it at half the period.
    tce_file(
        snap,
        "s0010-s0010",
        [
            {"tceid": "00000000005-01", "ticid": 5, "tce_period": 3.0002},
            {"tceid": "00000000005-03", "ticid": 5, "tce_period": 1.5},
        ],
    )
    tce_file(snap, "s0039-s0039", [{"tceid": "00000000005-01", "ticid": 5, "tce_period": 2.9998}])
    # Another epoch altogether: the period alone decides, as novelty matches a row whose epoch has gone stale.
    eph = Ephemeris(3.00005, 1400.37, 0.1)
    found = secondlist.dv_fields(snap, 5, eph, MATCH)
    # The latest run is the one with the latest last sector, and of two such, the longer one.
    assert found["run"] == "s0001-s0039" and found["tceid"] == "00000000005-01"
    runs = [("s0001-s0039", "00000000005-01"), ("s0039-s0039", "00000000005-01")]
    runs.append(("s0010-s0010", "00000000005-01"))
    assert found["runs"] == [{"run": r, "tceid": t, "ratio": 1.0} for r, t in runs]
    assert found["tic"] == 5 and found["ratio"] == 1.0 and found["tce_period"] == 3.0
    # Each run's match names its TCE and ratio, so a harmonic reads as one; of one run's, the earlier harmonic first.
    every = secondlist.dv_fields(snap, 5, eph, MATCH, HARMONICS)["runs"]
    assert every[2:] == [
        {"run": "s0010-s0010", "tceid": "00000000005-01", "ratio": 1.0},
        {"run": "s0010-s0010", "tceid": "00000000005-03", "ratio": 2.0},
    ]
    assert found["tce_max_mult_ev"] == 20.0 and found["sectors"] == "s0001-s0039"
    assert {k: found[k] for k in secondlist.DV_FIELDS[2:]} == {
        **{k: DV_ROW[k] for k in secondlist.DV_FIELDS[2:]},
        "tce_max_mult_ev": 20.0,
    }
    other = secondlist.dv_fields(snap, 5, Ephemeris(7.0, 1400.0, 0.1), MATCH)
    assert other["tceid"] == "00000000005-02" and other["wst_depth"] == 120.0
    # At a harmonic only when the harmonics are given: the TCE's period times 2 is the signal's.
    double = Ephemeris(6.0, 1400.0, 0.1)
    assert secondlist.dv_fields(snap, 5, double, MATCH) is None
    assert secondlist.dv_fields(snap, 5, double, MATCH, HARMONICS)["ratio"] == 2.0


def test_no_spoc_row_is_none(tmp_path):
    snap = tmp_path / "snap"
    tce_file(
        snap,
        "s0001-s0039",
        [
            {"tceid": "00000000005-01", "ticid": 5, "tce_period": 3.0},
            # ephemeris_match takes a NaN period for a match at any period; a row without one matches nothing.
            {"tceid": "00000000007-01", "ticid": 7, "tce_period": NAN},
        ],
    )
    exominer_v2(snap, "vetting_catalog_FFI", [v2("8-1-S38", 8, "38", 4.0, 0.9)])
    eph = Ephemeris(4.0, 1400.0, 0.1)
    # Matched only through ExoMiner: SPOC's DV statistics have no row for it.
    assert secondlist.dv_fields(snap, 8, eph, MATCH, HARMONICS) is None
    assert secondlist.exominer(snap, 8, eph, MATCH, HARMONICS)["score"] == 0.9
    # A TCE on the star at another period, a row with no period, and a star with no row at all.
    assert secondlist.dv_fields(snap, 5, eph, MATCH, HARMONICS) is None
    assert secondlist.dv_fields(snap, 7, eph, MATCH, HARMONICS) is None
    assert secondlist.dv_fields(snap, 9, eph, MATCH, HARMONICS) is None


def test_exominer_prefers_v2(tmp_path):
    snap = tmp_path / "snap"
    exominer_v1(
        snap,
        [v1("5-1-S1-39", 5, "1-39", 3.0, 0.91), v1("6-1-S12", 6, "12", 3.0, 0.4)],
    )
    exominer_v2(
        snap,
        "vetting_catalog_2-min",
        [v2("5-1-S1-13", 5, "1-13", 3.0, 0.62), v2("5-1-S1-39", 5, "1-39", 3.0001, 0.7)],
    )
    exominer_v2(
        snap,
        "vetting_catalog_FFI",
        [v2("5-1-S38", 5, "38", 2.9999, 0.55), v2("7-1-S56-69", 7, "56-69", 6.0, 0.3)],
    )
    eph = Ephemeris(3.0, 1400.0, 0.1)
    found = secondlist.exominer(snap, 5, eph, MATCH)
    # v2 over v1, and of v2's rows in both catalogs the latest run.
    assert found["catalog"] == "ExoMiner-v2 vetting_catalog_2-min" and found["id"] == "5-1-S1-39"
    assert found["score"] == 0.7 and found["score_sd"] == 0.02 and found["label"] == "PC"
    assert found["run"] == "1-39" and found["rows"] == 3 and found["ratio"] == 1.0
    only_v1 = secondlist.exominer(snap, 6, eph, MATCH)
    assert only_v1["catalog"] == "ExoMiner-v1 exominerplusplus_catalog"
    assert only_v1["score"] == 0.4 and only_v1["score_sd"] == 0.01 and only_v1["label"] is None
    ffi = secondlist.exominer(snap, 7, Ephemeris(6.0, 1400.0, 0.1), MATCH)
    assert ffi["catalog"] == "ExoMiner-v2 vetting_catalog_FFI" and ffi["run"] == "56-69"
    assert secondlist.exominer(snap, 9, eph, MATCH) is None


def test_a_missing_value_renders_as_missing(tmp_path):
    """The tables are written after the TESScut work; a catalog row without a score must not stop the run there."""
    snap = tmp_path / "snap"
    exominer_v2(snap, "vetting_catalog_FFI", [v2("8-1-S38", 8, "38", 4.0, NAN)])
    found = secondlist.exominer(snap, 8, Ephemeris(4.0, 1400.0, 0.1), MATCH)
    assert found["score"] is None
    checks = {
        "star": {"tic": 8},
        "ephemeris": {"period": 4.0, "t0": 1400.0, "duration": 0.1, "depth": None},
        "checks": [{"check": "novelty", "outcome": "inconclusive"}],
        "neighbours": {"outcome": "pass"},
        "upcoming_sectors": None,
    }
    about = {
        "run_id": "r",
        "vetting_run": "v",
        "triage_run": "t",
        "triage_criteria": "criteria/triage-v1.toml",
        "criteria": ["search-v2", "vet-v3"],
        "limit": 15.0,
    }
    for score in (None, NAN):
        item = {
            "name": "8-1",
            "checks": checks,
            "pixels": NOT_RUN,
            "dv": None,
            "exominer": {**found, "score": score},
        }
        text = secondlist.markdown([item], about)
        assert "| 8-1 | 8 | 4.000000 | missing |" in text
        assert "missing (PC; ExoMiner-v2 vetting_catalog_FFI, run 38)" in text
        assert len(secondlist.table([item])) == 1


def writable_json(path: Path, change) -> None:
    td.edit_json(path, change)


def second_list_runs(tmp_path, monkeypatch, signals=SECOND) -> dict[str, Path]:
    """A vetting run of a second-list row beside triage's evidence for it, from a snapshot with raw SPOC and ExoMiner
    files: SPOC found the signal as a TCE on a star 30" away, and ExoMiner scored it on the target."""
    # The targets row and the light curve's sources as the dossier reads them (test_dossier.vetting_runs).
    monkeypatch.setattr(tv, "CANDIDATE", {**tv.CANDIDATE, "teff": 5800.0, "ruwe": 0.85})
    argv, _ = tv.setup(tmp_path, monkeypatch, signals=signals, fit=tv.fake_fit)
    path = tmp_path / "data" / "lc" / "1.npz"
    lc = LightCurve.load(path)
    for source in lc.sources.values():
        source["crowdsap"] = 0.95
    lc.save(path)
    snap = Path(argv[argv.index("--catalogs") + 1])
    known = pd.read_parquet(snap / "known.parquet")
    near = {
        "source": "SPOC-TCE",
        "kind": "tce",
        "name": "TCE s0001-s0039 00000000003-01",
        "tic": 3,
        "ra": tv.CANDIDATE["ra"],
        "dec": tv.CANDIDATE["dec"] + 30.0 / 3600.0,
        **{k: tv.SIGNAL[k] for k in ("period", "t0", "duration")},
        "depth_ppm": 1700.0,
    }
    pd.concat([known, pd.DataFrame([near])[KNOWN_COLUMNS]], ignore_index=True).to_parquet(
        snap / "known.parquet"
    )
    tce_file(
        snap,
        "s0001-s0039",
        [{"tceid": "00000000003-01", "ticid": 3, "tce_period": 5.0, "tce_max_mult_ev": 15.5}],
    )
    exominer_v1(snap, [v1("1-1-S1", 1, "1", 5.0, 0.8)])
    exominer_v2(snap, "vetting_catalog_2-min", [v2("1-1-S1-2", 1, "1-2", 5.0, 0.64)])
    exominer_v2(snap, "vetting_catalog_FFI", [v2("2-1-S64", 2, "64", 9.0, 0.1)])
    write_manifest(snap)

    triage_run = tv.triage_run(tmp_path)
    evidence = triage_run / "evidence" / f"{NAME}.json"
    item = json.loads(evidence.read_text())
    item["leo_flux"]["evidence"]["metrics"] = METRICS
    item["pixels"] = NOT_RUN
    evidence.write_text(json.dumps(item))
    search = triage_run.parent / tv.SEARCH_RUN
    lcs = tmp_path / "data" / "lc"
    pd.DataFrame(
        [
            {"tic": tic, "control": False, "lc_sha256": sha256_file(lcs / f"{tic}.npz")}
            for tic in (1, 2)
        ]
    ).to_parquet(search / "stars.parquet")
    provenance = json.loads((triage_run / "provenance.json").read_text())
    provenance |= {
        "production": False,
        "git": {"commit": HEAD, "dirty_paths": []},
        "uv_lock_sha256": sha256_file(ROOT / "uv.lock"),
    }
    provenance["inputs"] |= {
        "search_stars": {"file": "stars.parquet", "sha256": sha256_file(search / "stars.parquet")},
        "targets": {
            "file": "targets.parquet",
            "sha256": sha256_file(tmp_path / "targets.parquet"),
        },
    }
    (triage_run / "provenance.json").write_text(json.dumps(provenance))
    assert main([*argv, "--triage-run", str(triage_run)]) == 0
    assert main([*argv, "--triage-run", str(triage_run), "--include-suspect"]) == 0
    runs = {
        json.loads((p / "provenance.json").read_text())["evidence_only"]: p
        for p in (tmp_path / "data" / "runs").glob("*-vetting-run-*")
    }
    return {"run": runs[False], "suspect": runs[True], "triage": triage_run, "snapshot": snap}


def second_list_argv(runs: dict[str, Path], run: Path | None = None) -> list[str]:
    return [
        "vetting",
        "second-list",
        *("--run", str(run or runs["run"])),
        *("--catalogs", str(runs["snapshot"])),
        *("--triage-run", str(runs["triage"])),
        *("--criteria-search", str(tv.SEARCH), "--criteria-vet", str(tv.VET3)),
        *("--workers", "1"),
    ]


def second_list_run(tmp_path) -> Path:
    [run] = (tmp_path / "data" / "runs").glob("*-vetting-second-list-*")
    return run


def stub_pixels(monkeypatch, result=FAILED) -> list[tuple]:
    seen = []

    def check(tlc, star, sectors, cfg, tdi):
        seen.append((dict(tlc.metrics), dict(star), list(sectors), dict(cfg), Path(tdi)))
        return result

    monkeypatch.setattr(triage, "pixel_check", check)
    return seen


def test_second_list_runs_pixels_as_triage_did(tmp_path, monkeypatch):
    runs = second_list_runs(tmp_path, monkeypatch)
    seen = stub_pixels(monkeypatch)
    assert main(second_list_argv(runs)) == 0
    run = second_list_run(tmp_path)

    # Only the second-list row, with what triage hands the pixel check: its [pixels] criteria, the signal's
    # LEO-Vetter metrics (the NaN restored, so the trapezoid fit's ephemeris is asked for), the star's row, every
    # sector of its light curve, and a difference-image directory of its own under this run.
    [(metrics, star, sectors, cfg, tdi)] = seen
    assert cfg == tv.TRIAGE["pixels"]
    assert np.isnan(metrics.pop("transit_aic"))
    assert metrics == {k: v for k, v in METRICS.items() if k != "transit_aic"}
    assert asked_ephemeris({**metrics, "transit_aic": NAN}) == (5.0001, 1326.11, 0.12 * 24)
    assert (star["tic"], star["ra"], star["dec"]) == (1, tv.CANDIDATE["ra"], tv.CANDIDATE["dec"])
    assert sectors == [1, 2, 64]
    assert tdi == run / "tdi" / NAME

    record = json.loads((run / "signals" / NAME / "pixels.json").read_text())
    assert record["outcome"] == "fail" and record["reason"] == FAILED.reason
    assert record["evidence"] == FAILED.to_dict()["evidence"]
    assert record["max_offset_arcsec"] == tv.TRIAGE["pixels"]["max_offset_arcsec"]
    assert record["signal"] == {"name": NAME, "tic": 1}
    assert record["vetting_run"] == runs["run"].name
    assert record["triage_run"] == runs["triage"].name
    # Its centroid plot, drawn from this record, beside it.
    assert (run / "signals" / NAME / "pixels.png").read_bytes().startswith(b"\x89PNG")
    assert not (run / "signals" / "TOI-9.01").exists()

    checks = tv.read(runs["run"], NAME)
    [row] = pd.read_csv(run / "second-list.csv").to_dict("records")
    assert row["name"] == NAME and row["tic"] == 1 and row["period"] == tv.SIGNAL["period"]
    for c in checks["checks"]:
        assert row[c["check"]] == c["outcome"], c["check"]
    assert row["neighbours"] == checks["neighbours"]["outcome"]
    assert row["pixels"] == "fail" and row["offset_qual_arcsec"] == 21.0
    # SPOC found it on the star 30" away; ExoMiner scored it on the target, v2 before v1.
    assert (
        row["dv_tic"] == 3 and row["tceid"] == "00000000003-01" and row["dv_run"] == "s0001-s0039"
    )
    assert row["tce_max_mult_ev"] == 15.5 and row["tce_ditco_msky"] == DV_ROW["tce_ditco_msky"]
    assert row["dv_runs"] == "s0001-s0039 00000000003-01 ratio 1"
    assert row["exominer_tic"] == 1 and row["exominer_score"] == 0.64
    assert row["exominer_catalog"] == "ExoMiner-v2 vetting_catalog_2-min"
    assert row["upcoming_sectors"] == " ".join(str(s) for s in checks["upcoming_sectors"])

    text = (run / "second-list.md").read_text()
    assert f"| {NAME} | 1 |" in text and "00000000003-01" in text and "TIC 3" in text
    assert "0.64" in text and "21.0" in text and runs["run"].name in text
    assert "/home/" not in text and str(tmp_path) not in text

    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["stage"] == "vetting-second-list"
    assert provenance["vetting_run"] == runs["run"].name
    assert provenance["triage_run"] == runs["triage"].name
    assert (
        provenance["criteria"]
        == json.loads((runs["run"] / "provenance.json").read_text())["criteria"]
    )
    inputs = provenance["inputs"]
    assert inputs[f"checks_{NAME}"]["sha256"] == sha256_file(
        runs["run"] / "signals" / NAME / "checks.json"
    )
    assert inputs["triage_criteria"]["sha256"] == tv.TRIAGE.sha256
    assert inputs[f"triage_evidence_{NAME}"]["sha256"] == sha256_file(
        runs["triage"] / "evidence" / f"{NAME}.json"
    )
    assert {"light_curve_1", "known", "catalog_manifest", "search_stars"} <= set(inputs)
    assert provenance["summary"]["signals"][NAME] == {
        "tic": 1,
        "pixels": "fail",
        "sha256": sha256_file(run / "signals" / NAME / "pixels.json"),
    }


def test_a_row_without_leo_vetter_metrics_is_inconclusive(tmp_path, monkeypatch):
    runs = second_list_runs(tmp_path, monkeypatch)
    seen = stub_pixels(monkeypatch)
    td.writable(runs["run"])
    evidence = runs["triage"] / "evidence" / f"{NAME}.json"
    item = json.loads(evidence.read_text())
    del item["leo_flux"]["evidence"]["metrics"]
    evidence.write_text(json.dumps(item))
    # The vetting run read the file as it is now.
    td.edit_json(
        runs["run"] / "provenance.json",
        lambda p: p["inputs"][f"triage_evidence_{NAME}"].update(sha256=sha256_file(evidence)),
    )
    assert main(second_list_argv(runs)) == 0
    assert seen == []
    record = json.loads((second_list_run(tmp_path) / "signals" / NAME / "pixels.json").read_text())
    assert record["outcome"] == "inconclusive" and "no metrics" in record["reason"]


def evidence_only(tmp_path, runs) -> list[str]:
    return second_list_argv(runs, runs["suspect"])


def other_vet_criteria(tmp_path, runs) -> list[str]:
    path = tmp_path / "vet-v3-other.toml"
    path.write_text(tv.VET3.read_text() + "# not the file the vetting run ran with\n")
    argv = second_list_argv(runs)
    argv[argv.index(str(tv.VET3))] = str(path)
    return argv


def other_triage_run(tmp_path, runs) -> list[str]:
    other = runs["triage"].parent / "20261015T000000Z-triage-abc-2"
    other.mkdir()
    (other / "provenance.json").write_text((runs["triage"] / "provenance.json").read_text())
    argv = second_list_argv(runs)
    argv[argv.index("--triage-run") + 1] = str(other)
    return argv


def changed_evidence(tmp_path, runs) -> list[str]:
    td.edit_json(runs["triage"] / "evidence" / f"{NAME}.json", lambda e: e.update(note="edited"))
    return second_list_argv(runs)


def other_snapshot(tmp_path, runs) -> list[str]:
    writable_json(runs["snapshot"] / "manifest.json", lambda m: m.update(created="another"))
    return second_list_argv(runs)


def unlisted_raw_file(tmp_path, runs) -> list[str]:
    tce_file(runs["snapshot"], "s0040-s0040", [{"tceid": "1-01", "ticid": 1, "tce_period": 5.0}])
    return second_list_argv(runs)


def changed_raw_file(tmp_path, runs) -> list[str]:
    [path] = (runs["snapshot"] / "raw" / "SPOC-TCE").glob("*.csv")
    path.write_text(path.read_text().replace("15.5", "25.5"))
    return second_list_argv(runs)


def triage_code(change):
    """The triage run recorded other pixel code or another lock than this checkout's, and the vetting run read that
    provenance."""

    def argv(tmp_path, runs) -> list[str]:
        path = runs["triage"] / "provenance.json"
        td.edit_json(path, change)
        td.edit_json(
            runs["run"] / "provenance.json",
            lambda p: p["inputs"]["triage_provenance"].update(sha256=sha256_file(path)),
        )
        return second_list_argv(runs)

    return argv


def no_second_list_row(tmp_path, runs) -> list[str]:
    td.writable(runs["run"])
    checks = runs["run"] / "signals" / NAME / "checks.json"
    td.edit_json(checks, lambda c: c["signal"].update(kind="candidate"))
    return second_list_argv(runs)


@pytest.mark.parametrize(
    "argv, message",
    [
        (evidence_only, "evidence-only"),
        (other_vet_criteria, "is not the criteria/vet-v3.toml that"),
        (other_triage_run, "read triage run"),
        (changed_evidence, "is not the file"),
        (other_snapshot, "is not the snapshot"),
        (unlisted_raw_file, "not in the manifest"),
        (changed_raw_file, "not the file the manifest lists"),
        (no_second_list_row, "no second-list signal"),
        (
            triage_code(lambda p: p.update(uv_lock_sha256="0" * 64)),
            "would not run as in .*uv.lock differs",
        ),
        (
            triage_code(lambda p: p["git"].update(dirty_paths=["src/tess_hunt/pixels.py"])),
            "would not run as in .*pixels.py had uncommitted changes",
        ),
    ],
)
def test_second_list_refuses_inputs_it_cannot_stand_on(tmp_path, monkeypatch, argv, message):
    runs = second_list_runs(tmp_path, monkeypatch)
    stub_pixels(monkeypatch)
    with pytest.raises(SystemExit, match=message):
        main(argv(tmp_path, runs))
    assert not list((tmp_path / "data" / "runs").glob("*-vetting-second-list-*"))


def test_the_dossier_shows_the_second_lists_pixel_check(tmp_path, monkeypatch):
    runs = second_list_runs(tmp_path, monkeypatch)
    stub_pixels(monkeypatch)
    assert main(second_list_argv(runs)) == 0
    second = second_list_run(tmp_path)
    out = tmp_path / "drafts"
    argv = ["vetting", "dossier", "--run", str(runs["run"]), "--signals", NAME, "--out", str(out)]

    # Triage never ran its pixel check on a second-list row, so without the second list the record has none, and the
    # dossier neither claims one nor shows the vetting run's empty centroid plot under triage's name.
    assert main(argv) == 0
    text = (out / NAME / "dossier.md").read_text()
    assert "| pixels | not run | No second-list run was given. |" in text
    assert "Centroids: no pixel evidence (No second-list run was given.)" in text
    assert "second list ran it" not in text and "which triage did not run on this row" in text
    plots = td.section(text, "Plots")
    assert "centroids.png" not in plots and "Triage's centroid" not in plots

    assert main([*argv, "--second-list", str(second)]) == 0
    signal = out / NAME
    for name in ("pixels.json", "pixels.png"):
        assert sha256_file(signal / name) == sha256_file(second / "signals" / NAME / name)
    # The vetting run's plot keeps its place and its provenance; the second list's has its own path.
    assert sha256_file(signal / "plots" / "centroids.png") == sha256_file(
        runs["run"] / "signals" / NAME / "plots" / "centroids.png"
    )
    text = (signal / "dossier.md").read_text()
    assert text == dossier.render(signal)
    assert f"| pixels | fail | {FAILED.reason} |" in text
    assert "triage's pixel check as the second list ran it on this row" in text
    on_star = td.section(text, "On the star?")
    assert "from the second list's pixel check (fail" in on_star
    assert "| 1 | 21.0 | 0.90 | the offset the second list's check judged |" in on_star
    assert "| 2 | 16.0 | 0.60 |  |" in on_star
    assert second.name in td.section(text, "Signal and star")
    plots = td.section(text, "Plots")
    assert "](pixels.png)" in plots and "The second list's pixel check" in plots
    assert "centroids.png" not in plots and "Triage's centroid" not in plots


KILLED = tc.edit(
    tc.edit(tc.KILLED, 'signal = "44926986-1"', f'signal = "{NAME}"'), '["odd_even"]', '["pixels"]'
)


def test_publish_carries_the_second_lists_pixel_record(tmp_path, monkeypatch):
    runs = second_list_runs(tmp_path, monkeypatch)
    stub_pixels(monkeypatch)
    assert main(second_list_argv(runs)) == 0
    second = second_list_run(tmp_path)
    tric = td.made_run(tmp_path, "vetting-triceratops", runs["run"], {})
    lit = td.made_run(tmp_path, "vetting-literature", runs["run"], {})
    td.production(runs["run"], second, tric, lit)
    repo = tmp_path / "repo"
    monkeypatch.setattr(td.vetting, "repo_root", lambda: repo)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    # A kill that rests on the pixel check stands only with the second list's record beside it.
    (signal / "call.toml").write_text(KILLED)
    argv = [
        "vetting",
        "publish",
        "--name",
        NAME,
        *("--run", str(runs["run"]), "--triceratops", str(tric), "--literature", str(lit)),
    ]
    with pytest.raises(SystemExit, match="pixels"):
        main(argv)
    assert main([*argv, "--second-list", str(second)]) == 0
    files = td.published(repo)
    for name in ("pixels.json", "pixels.png"):
        assert files[f"{NAME}/{name}"] == sha256_file(second / "signals" / NAME / name)
    assert files[f"{NAME}/provenance-second-list.json"] == sha256_file(second / "provenance.json")
    # Every file under plots/ is the vetting run's, as provenance-checks.json says.
    vetted = runs["run"] / "signals" / NAME / "plots"
    assert {k: v for k, v in files.items() if k.startswith(f"{NAME}/plots/")} == {
        f"{NAME}/plots/{p.name}": sha256_file(p) for p in vetted.glob("*.png")
    }
    readme = (repo / "results" / "vetting" / "README.md").read_text()
    assert f"[{NAME}]({NAME}/dossier.md) | killed |" in readme

    # A second-list run made from another vetting run is refused before anything is copied.
    other = td.made_run(
        tmp_path,
        "vetting-second-list",
        runs["suspect"],
        {
            NAME: {
                "pixels.json": json.loads((second / "signals" / NAME / "pixels.json").read_text())
            }
        },
        tag="b",
    )
    td.production(other)
    before = td.published(repo)
    with pytest.raises(SystemExit, match="was made from"):
        main([*argv, "--second-list", str(other)])
    assert td.published(repo) == before


def test_second_list_row_carries_the_m3_pixel_record(tmp_path, monkeypatch):
    """A re-vet of a second-list row keeps the M3 record's second-list pixel check (decision 0041): the one run a
    version may name that was made from another vetting run."""
    runs = second_list_runs(tmp_path, monkeypatch)
    stub_pixels(monkeypatch)
    assert main(second_list_argv(runs)) == 0
    second = second_list_run(tmp_path)
    tric = td.made_run(tmp_path, "vetting-triceratops", runs["run"], {})
    lit = td.made_run(tmp_path, "vetting-literature", runs["run"], {})
    td.production(runs["run"], second, tric, lit)

    # The re-vet: both stars' light curves with a new sector, a vetting run on them, and the runs made from it.
    lc_run = td.revet_run(tmp_path, tics=(1, 2))
    vetted = set((tmp_path / "data" / "runs").glob("*-vetting-run-*"))
    argv = [
        *tv.run_argv(tmp_path),
        "--triage-run",
        str(runs["triage"]),
        "--lc-dir",
        str(lc_run / "lc"),
    ]
    assert main(argv) == 0
    [run] = set((tmp_path / "data" / "runs").glob("*-vetting-run-*")) - vetted
    # The second list runs the pixel check on the light curve the search searched, as triage would have; a re-vet's
    # light curve is not that one.
    with pytest.raises(SystemExit, match="decision 0041"):
        main(second_list_argv(runs, run))
    assert len(list((tmp_path / "data" / "runs").glob("*-vetting-second-list-*"))) == 1
    revet_tric = td.made_run(tmp_path, "vetting-triceratops", run, {}, tag="v")
    revet_lit = td.made_run(tmp_path, "vetting-literature", run, {}, tag="v")
    td.production(run, revet_tric, revet_lit)

    repo = td.results_repo(tmp_path, monkeypatch)
    m3 = repo / "results" / "vetting" / NAME
    m3.mkdir(parents=True)
    (m3 / "call.toml").write_text(KILLED)
    publish = ["vetting", "publish", "--name", NAME]
    record = ("--run", str(runs["run"]), "--triceratops", str(tric), "--literature", str(lit))
    assert main([*publish, *record, "--second-list", str(second)]) == 0
    version = m3 / "r2"
    version.mkdir()
    (version / "call.toml").write_text(KILLED)
    argv = [
        *(*publish, "--version", "2", "--run", str(run), "--lc-run", str(lc_run)),
        *("--triceratops", str(revet_tric), "--literature", str(revet_lit)),
    ]
    before = td.published(repo)
    # Without it the version would drop the row's pixel check.
    with pytest.raises(SystemExit, match="carries the second list's pixel check"):
        main(argv)
    # A second-list run made from another vetting run than the previous record's is refused, as for an M3 record.
    pixels = json.loads((second / "signals" / NAME / "pixels.json").read_text())
    other = td.made_run(
        tmp_path, "vetting-second-list", runs["suspect"], {NAME: {"pixels.json": pixels}}, tag="b"
    )
    td.production(other)
    with pytest.raises(SystemExit, match="was made from"):
        main([*argv, "--second-list", str(other)])
    assert td.published(repo) == before

    # The previous record's own second-list run is the one exception.
    assert main([*argv, "--second-list", str(second)]) == 0
    for name in ("pixels.json", "pixels.png", "provenance-second-list.json"):
        assert sha256_file(version / name) == sha256_file(m3 / name), name
    # Its provenance, unchanged, names the M3 record's vetting run, not this version's: it was carried.
    carried = json.loads((version / "provenance-second-list.json").read_text())
    assert carried["vetting_run"] == runs["run"].name != run.name
    text = " ".join((version / "dossier.md").read_text().split())
    assert (
        f"The second list's pixel check is carried from the M3 record: second-list run {second.name}, made from "
        f"vetting run {runs['run'].name}, is not run again on a re-vet" in text
    )
    assert f"| pixels | fail | {FAILED.reason} |" in text
    # The kill rests on the carried pixel check, and stands.
    assert calls.problems(version) == []

    # r3, re-vetted on r2's light curve with one more sector, carries the same record: the second-list run read the
    # M3 record's checks.json, not r2's.
    lc_run3 = td.revet_run(tmp_path, tics=(1, 2), tag="r3", base=lc_run / "lc", sector=66)
    vetted = set((tmp_path / "data" / "runs").glob("*-vetting-run-*"))
    argv3 = [
        *tv.run_argv(tmp_path),
        "--triage-run",
        str(runs["triage"]),
        "--lc-dir",
        str(lc_run3 / "lc"),
    ]
    assert main(argv3) == 0
    [run3] = set((tmp_path / "data" / "runs").glob("*-vetting-run-*")) - vetted
    tric3 = td.made_run(tmp_path, "vetting-triceratops", run3, {}, tag="w")
    lit3 = td.made_run(tmp_path, "vetting-literature", run3, {}, tag="w")
    td.production(run3, tric3, lit3)
    r3 = m3 / "r3"
    r3.mkdir()
    (r3 / "call.toml").write_text(KILLED)
    argv = [
        *(*publish, "--version", "3", "--run", str(run3), "--lc-run", str(lc_run3)),
        *("--triceratops", str(tric3), "--literature", str(lit3), "--second-list", str(second)),
    ]
    assert main(argv) == 0
    for name in ("pixels.json", "pixels.png", "provenance-second-list.json"):
        assert sha256_file(r3 / name) == sha256_file(m3 / name), name
    assert "carried from r2" in " ".join((r3 / "dossier.md").read_text().split())
    assert calls.problems(r3) == []
