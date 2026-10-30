import datetime as dt
import json
import tomllib
from pathlib import Path

import pandas as pd
import pytest
import test_vetting as tv

from tess_hunt import claims
from tess_hunt.catalogs import KNOWN_COLUMNS
from tess_hunt.claims import Claim
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.provenance import sha256_file
from tess_hunt.threshold import load_v2_catalog

ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v2.toml")
VET = load_criteria(ROOT / "criteria" / "vet-v3.toml")
NAN = float("nan")
NAME = "1-1"
# test_vetting's candidate: its star and the signal its runs vet.
STAR = {"tic": 1, "ra": 30.0, "dec": -40.0}
EPH = {"period": 5.0, "t0": 1326.1, "duration": 0.13, "depth": 0.0017}
CHECKS = {"signal": {"name": NAME, "kind": "candidate"}, "star": STAR, "ephemeris": EPH}
DOI = "https://doi.org/10.5281/zenodo.23745923"
CLAIM = Claim(NAME, dt.date(2026, 10, 28), DOI)
LATER = "2027-03-01"
SNAPSHOT = "2026-10-17T000000Z"
VETTING_RUN = "20261101T000000Z-vetting-run-abc1234-0001"
LITERATURE_RUN = "20261101T010000Z-vetting-literature-abc1234-0001"


def row(source: str, name: str, tic: int = 1, kind: str = "candidate", **change) -> dict:
    """A snapshot row at the signal's ephemeris, on its star unless `change` moves it."""
    return {
        "source": source,
        "kind": kind,
        "name": name,
        "tic": tic,
        "ra": STAR["ra"],
        "dec": STAR["dec"],
        "period": EPH["period"],
        "t0": EPH["t0"],
        "duration": EPH["duration"],
        "depth_ppm": 1700.0,
        **change,
    }


FAR = {"ra": 200.0, "dec": 10.0}
# Novelty needs TOI, CTOI and archive rows, and a v2 snapshot TCE and EB rows.
FAR_ROWS = [
    row("TOI", "TOI-9001.01", tic=999, **FAR),
    row("CTOI", "CTOI-998.01", tic=998, **FAR),
    row("archive", "Far b", tic=997, kind="planet", **FAR),
    row("SPOC-TCE", "far TCE", tic=996, kind="tce", **FAR),
    row("TESS-EB", "far EB", tic=995, kind="eb", **FAR),
]


def known(*rows: dict) -> pd.DataFrame:
    return pd.DataFrame([*FAR_ROWS, *rows])[KNOWN_COLUMNS]


def toi(name: str, first: str | None = LATER, tess: str = "PC", tfop: str | None = "") -> dict:
    """ExoFOP's TOI row as a literature record keeps it; a field given as None is left out."""
    out = {
        "toi": name,
        # Every TOI row names its star's listing this way too; it is not a CTOI (pin P2).
        "ctoi": "TIC 1.01",
        "toidate1": first,
        "toidate2": LATER,
        "date": f"{LATER} 12:00:00",
        "disp_tess": tess,
        "disp_tfop": tfop,
    }
    return {k: v for k, v in out.items() if v is not None}


def ctoi(name: str, first: str = LATER, user: str = "PC", tfop: str = "") -> dict:
    return {"ctoi": name, "ctoi_created": first, "cdate": first, "cdisp": user, "tdisp": tfop}


def exofop(tois=(), ctois=(), status: str = "ok") -> dict:
    return {
        "status": status,
        "tois": list(tois),
        "ctois": list(ctois),
        "planets": [],
        "error": None if status == "ok" else "ExoFOP: ReadTimeout",
    }


def sort(snapshot: pd.DataFrame, record: dict, claim: Claim | None = CLAIM) -> dict:
    return claims.sort_signal(CHECKS, snapshot, record, claim, SEARCH, VET)


def novelty(snapshot: pd.DataFrame) -> dict:
    return claims.rerun(CHECKS, snapshot, SEARCH, VET)


def test_a_same_star_pc_toi_listed_after_the_claim_is_excepted():
    snapshot = known(row("TOI", "TOI-7001.01"))
    assert novelty(snapshot)["outcome"] == "fail"
    found = sort(snapshot, exofop([toi("TOI 7001.01")]))
    assert found["claim"] == {"date": "2026-10-28", "record": DOI}
    assert found["exofop_status"] == "ok"
    assert found["excepted"] == [
        {
            "source": "TOI",
            "name": "TOI-7001.01",
            "tic": 1,
            "period": 5.0,
            "first_listed": LATER,
            "dispositions": ["PC"],
        }
    ]
    assert found["kept"] == []
    assert found["novelty"]["outcome"] == "pass"


def test_a_toi_listed_on_the_claim_day_is_kept():
    found = sort(known(row("TOI", "TOI-7001.01")), exofop([toi("TOI 7001.01", first="2026-10-28")]))
    assert found["excepted"] == [] and found["novelty"] is None
    [kept] = found["kept"]
    assert kept["name"] == "TOI-7001.01"
    assert kept["reason"] == "first listed 2026-10-28, not after the claim date 2026-10-28"


@pytest.mark.parametrize("first", ["", None, "2027-03-01T00:00:00", "03/01/2027", "2027-02-30"])
def test_a_row_without_a_first_listed_date_is_kept(first):
    found = sort(known(row("TOI", "TOI-7001.01")), exofop([toi("TOI 7001.01", first=first)]))
    assert found["excepted"] == [] and found["novelty"] is None
    assert found["kept"] == [
        {
            "source": "TOI",
            "name": "TOI-7001.01",
            "reason": "ExoFOP gives no first-listed date (toidate1)",
        }
    ]


def test_a_neighbours_toi_is_kept():
    # One arcminute from the star at the signal's period: the dip may be the neighbour's. Even in the star's ExoFOP
    # record, a row on another TIC is never a candidate for the exception.
    neighbour = row("TOI", "TOI-7002.01", tic=2, dec=STAR["dec"] + 1 / 60)
    found = sort(
        known(row("TOI", "TOI-7001.01"), neighbour),
        exofop([toi("TOI 7001.01"), toi("TOI 7002.01")]),
    )
    assert [r["name"] for r in found["excepted"]] == ["TOI-7001.01"]
    assert found["kept"] == []
    assert found["novelty"]["outcome"] == "fail"
    assert [m["name"] for m in found["novelty"]["evidence"]["matches"]] == ["TOI-7002.01"]


@pytest.mark.parametrize(
    ("tfop", "reason"),
    [
        ("FP", "disposition FP, not PC"),
        ("APC", "disposition APC, not PC"),
        (None, "ExoFOP's row gives no disp_tfop"),
    ],
)
def test_a_disposition_other_than_pc_is_kept(tfop, reason):
    found = sort(known(row("TOI", "TOI-7001.01")), exofop([toi("TOI 7001.01", tfop=tfop)]))
    assert found["excepted"] == [] and found["novelty"] is None
    assert found["kept"] == [{"source": "TOI", "name": "TOI-7001.01", "reason": reason}]


@pytest.mark.parametrize(
    ("change", "category"),
    [
        ({"t0": EPH["t0"] + EPH["period"] / 2}, "stale_catalog_epoch"),
        ({"period": NAN}, "no_period_object"),
    ],
)
def test_a_later_toi_with_a_missed_epoch_or_no_period_is_excepted(change, category):
    snapshot = known(row("TOI", "TOI-7001.01", **change))
    assert novelty(snapshot)["evidence"]["category"] == category
    found = sort(snapshot, exofop([toi("TOI 7001.01")]))
    assert [r["name"] for r in found["excepted"]] == ["TOI-7001.01"]
    assert found["novelty"]["outcome"] == "pass"
    assert "category" not in found["novelty"]["evidence"]


def test_a_toi_excepted_beside_a_spoc_tce_leaves_known_to_spoc():
    tce = row("SPOC-TCE", "TCE s0001-s0001 00000000001-01", kind="tce")
    found = sort(known(row("TOI", "TOI-7001.01"), tce), exofop([toi("TOI 7001.01")]))
    assert [r["name"] for r in found["excepted"]] == ["TOI-7001.01"]
    assert found["novelty"]["outcome"] == "inconclusive"
    assert found["novelty"]["evidence"]["category"] == "known_to_spoc"


def test_a_signal_without_a_claim_excepts_nothing():
    found = sort(known(row("TOI", "TOI-7001.01")), exofop([toi("TOI 7001.01")]), claim=None)
    assert found["claim"] is None
    assert found["excepted"] == [] and found["novelty"] is None
    assert found["kept"] == [
        {
            "source": "TOI",
            "name": "TOI-7001.01",
            "reason": "the claims file gives the signal no claim",
        }
    ]


def test_snapshot_and_exofop_names_match_across_forms():
    for name, number in (
        ("TOI-1234.01", "1234.01"),
        ("TOI 1234.01", "1234.01"),
        ("TIC 241522065.01", "241522065.01"),
        ("CTOI-17361.01", "17361.01"),
        ("TIC 17361.01 (now TOI 3127.01)", "17361.01"),
    ):
        assert claims.listing_id(name) == number, name
    for name in ("TOI-1234", "TIC 241522065", "CTOI 17361.01", "RAVEN 17361", "Far b", ""):
        assert claims.listing_id(name) is None, name
    snapshot = known(
        row("TOI", "TOI-7001.01"),
        # A CTOI the TOI team promoted stays a row of its own (pin P2).
        row("CTOI", "CTOI-1.01"),
        row("CTOI", "CTOI-1.02"),
    )
    found = sort(snapshot, exofop([toi("TOI 7001.01")], [ctoi("TIC 1.01 (now TOI 7001.01)")]))
    assert [r["name"] for r in found["excepted"]] == ["TOI-7001.01", "CTOI-1.01"]
    assert found["kept"] == [
        {"source": "CTOI", "name": "CTOI-1.02", "reason": "ExoFOP's record for the star lacks it"}
    ]
    # The TOI row's "TIC 1.01" names the star's listing but is not a CTOI row: a CTOI matches ExoFOP's CTOIs only.
    found = sort(known(row("CTOI", "CTOI-1.01")), exofop([toi("TOI 7001.01")]))
    assert found["excepted"] == []
    assert found["kept"] == [
        {"source": "CTOI", "name": "CTOI-1.01", "reason": "ExoFOP's record for the star lacks it"}
    ]


def test_an_exofop_read_that_failed_excepts_nothing():
    record = {**exofop([toi("TOI 7001.01")]), "status": "error"}
    found = sort(known(row("TOI", "TOI-7001.01")), record)
    assert found["exofop_status"] == "error"
    assert found["excepted"] == [] and found["novelty"] is None
    assert found["kept"] == [
        {
            "source": "TOI",
            "name": "TOI-7001.01",
            "reason": "ExoFOP's record was not read (status error)",
        }
    ]


def write_snapshot(path: Path, *rows: dict) -> Path:
    path.mkdir(parents=True)
    known(*rows).to_parquet(path / "known.parquet")
    (path / "manifest.json").write_text("{}\n")
    return path


def test_the_rerun_without_exceptions_reproduces_the_vetting_runs_novelty(tmp_path, monkeypatch):
    argv, _ = tv.setup(tmp_path, monkeypatch, signals=tv.SIGNALS[:1], fit=tv.fake_fit)
    snapshot = write_snapshot(
        tmp_path / "data" / "catalogs" / SNAPSHOT,
        row("TOI", "TOI-7001.01"),
        row("SPOC-TCE", "TCE s0001-s0001 00000000001-01", kind="tce"),
        # At twice the period and a quarter of the signal's cycle off: a period match whose epoch misses.
        row("ExoMiner-v2", "ExoMiner 1-1-S1", kind="tce", period=10.0, t0=EPH["t0"] + 1.25),
        row("CTOI", "CTOI-3.01", tic=3, dec=STAR["dec"] + 1 / 60, period=3.3),
    )
    argv[argv.index("--catalogs") + 1] = str(snapshot)
    assert main(argv) == 0
    run = tv.only_run(tmp_path)
    made = json.loads((run / "provenance.json").read_text())
    # The vetting run's record of its snapshot, which the claims stage reads.
    assert made["catalogs"] == SNAPSHOT
    assert made["inputs"]["known"]["sha256"] == sha256_file(snapshot / "known.parquet")
    checks = tv.read(run, NAME)
    [entry] = [c for c in checks["checks"] if c["check"] == "novelty"]
    assert entry["evidence"]["tce_matches"] and entry["evidence"]["tce_period_matches"]
    rerun = claims.rerun(checks, load_v2_catalog(snapshot), SEARCH, VET)
    assert json.loads(json.dumps(rerun)) == entry


def made_run(path: Path, stage: str, files: dict, **provenance) -> Path:
    """A finished `stage` run at `path` holding `files` ({signal: {file name: record}})."""
    for name, contents in files.items():
        (path / "signals" / name).mkdir(parents=True)
        for file, content in contents.items():
            (path / "signals" / name / file).write_text(json.dumps(content, indent=2))
    path.mkdir(parents=True, exist_ok=True)
    made = {
        "run_id": path.name,
        "stage": stage,
        "production": False,
        "started_at": "2026-11-01T00:00:00+00:00",
        "ended_at": "2026-11-01T00:30:00+00:00",
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
        "criteria": [
            {"file": "criteria/search-v2.toml", "sha256": SEARCH.sha256},
            {"file": "criteria/vet-v3.toml", "sha256": VET.sha256},
        ],
        "inputs": {},
        "summary": {},
        **provenance,
    }
    (path / "provenance.json").write_text(json.dumps(made, indent=2))
    return path


OTHER = {
    "signal": {"name": "2-1", "kind": "candidate"},
    "star": {"tic": 2, "ra": 60.0, "dec": -50.0},
}
SIGNALS = {
    NAME: (
        CHECKS,
        exofop([toi("TOI 7001.01")], [ctoi("TIC 1.01", first="2026-01-05")]),
    ),
    "2-1": ({**OTHER, "ephemeris": EPH}, exofop([toi("TOI 7003.01")])),
}
ROWS = [
    row("TOI", "TOI-7001.01"),
    # Listed before the claim, at the signal's ephemeris: novelty run again still fails on it.
    row("CTOI", "CTOI-1.01"),
    row("TOI", "TOI-7003.01", tic=2, ra=60.0, dec=-50.0),
]


def runs(tmp_path, monkeypatch) -> tuple[list[str], Path, Path, Path]:
    """`vetting claims`'s arguments for a vetting run of SIGNALS on a snapshot of ROWS, the literature run made from
    it, and a claims file holding 1-1's claim; and the vetting run, the literature run and the snapshot."""
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    monkeypatch.chdir(ROOT)
    snapshot = write_snapshot(data / "catalogs" / SNAPSHOT, *ROWS)
    inputs = {
        "known": {"file": "known.parquet", "sha256": sha256_file(snapshot / "known.parquet")},
        "catalog_manifest": {
            "file": "manifest.json",
            "sha256": sha256_file(snapshot / "manifest.json"),
        },
    }
    vetting_run = made_run(
        data / "runs" / VETTING_RUN,
        "vetting-run",
        {name: {"checks.json": checks} for name, (checks, _) in SIGNALS.items()},
        evidence_only=False,
        catalogs=SNAPSHOT,
        inputs=inputs,
    )
    records = {
        name: {
            "signal": {"name": name, "tic": checks["star"]["tic"]},
            "vetting_run": VETTING_RUN,
            "search": {"tic": checks["star"]["tic"], "exofop": record},
        }
        for name, (checks, record) in SIGNALS.items()
    }
    literature_run = made_run(
        data / "runs" / LITERATURE_RUN,
        "vetting-literature",
        {name: {"literature.json": record} for name, record in records.items()},
        vetting_run=VETTING_RUN,
    )
    summary = {
        name: {
            "tic": record["signal"]["tic"],
            "sha256": sha256_file(literature_run / "signals" / name / "literature.json"),
        }
        for name, record in records.items()
    }
    edit(literature_run, lambda p: p.update(summary={"signals": summary}))
    claims_file = tmp_path / "claims.toml"
    claims_file.write_text(f'["{NAME}"]\ndate = 2026-10-28\nrecord = "{DOI}"\n')
    argv = [
        *("vetting", "claims"),
        *("--run", str(vetting_run)),
        *("--literature", str(literature_run)),
        *("--claims", str(claims_file)),
        *("--criteria-search", str(SEARCH.path)),
        *("--criteria-vet", str(VET.path)),
    ]
    return argv, vetting_run, literature_run, snapshot


def edit(run: Path, change) -> None:
    path = run / "provenance.json"
    provenance = json.loads(path.read_text())
    change(provenance)
    path.write_text(json.dumps(provenance, indent=2))


def claims_runs(tmp_path) -> list[Path]:
    return sorted((tmp_path / "data" / "runs").glob("*-vetting-claims-*"))


def unfinished(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(vetting_run, lambda p: p.update(ended_at=None))


def evidence_only(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(vetting_run, lambda p: p.update(evidence_only=True))


def literature_unfinished(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(literature_run, lambda p: p.update(ended_at=None))


def literature_of_another_run(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(
        literature_run, lambda p: p.update(vetting_run="20261101T000000Z-vetting-run-abc1234-0002")
    )


def other_criteria(tmp_path, argv, vetting_run, literature_run, snapshot):
    other = tmp_path / "vet-v3.toml"
    other.write_text(VET.path.read_text() + "\n# edited\n")
    argv[argv.index("--criteria-vet") + 1] = str(other)


def other_snapshot_file(tmp_path, argv, vetting_run, literature_run, snapshot):
    (snapshot / "manifest.json").write_text('{"edited": true}\n')


def no_snapshot_recorded(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(vetting_run, lambda p: p.pop("catalogs"))


def vetting_run_not_production(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(literature_run, lambda p: p.update(production=True))
    argv.append("--production")


def literature_not_production(tmp_path, argv, vetting_run, literature_run, snapshot):
    edit(vetting_run, lambda p: p.update(production=True))
    argv.append("--production")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (unfinished, "is not a finished vetting run"),
        (evidence_only, "is an evidence-only vetting run"),
        (literature_unfinished, "is not a finished literature run"),
        (literature_of_another_run, "was made from 20261101T000000Z-vetting-run-abc1234-0002"),
        (other_criteria, "--criteria-vet vet-v3.toml is not the criteria/vet-v3.toml"),
        (
            other_snapshot_file,
            f"snapshot {SNAPSHOT} is not the one .* vetted with \\(manifest.json\\)",
        ),
        (no_snapshot_recorded, "recorded no catalog snapshot"),
        (vetting_run_not_production, "is not a production vetting run"),
        (literature_not_production, "is not a production literature run"),
    ],
)
def test_claims_refuses_what_it_cannot_stand_on(tmp_path, monkeypatch, change, message):
    argv, *made = runs(tmp_path, monkeypatch)
    change(tmp_path, argv, *made)
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert claims_runs(tmp_path) == []


def test_claims_writes_one_record_per_signal_with_provenance(tmp_path, monkeypatch):
    argv, vetting_run, literature_run, snapshot = runs(tmp_path, monkeypatch)
    assert main(argv) == 0
    [run] = claims_runs(tmp_path)
    snapshot_rows = load_v2_catalog(snapshot)
    without = snapshot_rows[snapshot_rows["name"] != "TOI-7001.01"]
    first = json.loads((run / "signals" / NAME / "claims.json").read_text())
    assert first == {
        "signal": {"name": NAME, "tic": 1},
        "vetting_run": VETTING_RUN,
        "literature_run": LITERATURE_RUN,
        "claim": {"date": "2026-10-28", "record": DOI},
        "exofop_status": "ok",
        "excepted": [
            {
                "source": "TOI",
                "name": "TOI-7001.01",
                "tic": 1,
                "period": 5.0,
                "first_listed": LATER,
                "dispositions": ["PC"],
            }
        ],
        "kept": [
            {
                "source": "CTOI",
                "name": "CTOI-1.01",
                "reason": "first listed 2026-01-05, not after the claim date 2026-10-28",
            }
        ],
        "novelty": json.loads(json.dumps(claims.rerun(CHECKS, without, SEARCH, VET))),
    }
    assert first["novelty"]["outcome"] == "fail"
    second = json.loads((run / "signals" / "2-1" / "claims.json").read_text())
    assert second["claim"] is None and second["excepted"] == [] and second["novelty"] is None
    assert second["kept"] == [
        {
            "source": "TOI",
            "name": "TOI-7003.01",
            "reason": "the claims file gives the signal no claim",
        }
    ]

    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["stage"] == "vetting-claims" and provenance["ended_at"] is not None
    assert provenance["vetting_run"] == VETTING_RUN
    assert provenance["literature_run"] == LITERATURE_RUN
    assert provenance["catalogs"] == SNAPSHOT
    assert [c["sha256"] for c in provenance["criteria"]] == [SEARCH.sha256, VET.sha256]
    read = {
        "claims": tmp_path / "claims.toml",
        "vetting_provenance": vetting_run / "provenance.json",
        "literature_provenance": literature_run / "provenance.json",
        "known": snapshot / "known.parquet",
        "catalog_manifest": snapshot / "manifest.json",
        **{f"checks_{n}": vetting_run / "signals" / n / "checks.json" for n in SIGNALS},
        **{f"literature_{n}": literature_run / "signals" / n / "literature.json" for n in SIGNALS},
    }
    assert {k: v["sha256"] for k, v in provenance["inputs"].items()} == {
        k: sha256_file(p) for k, p in read.items()
    }
    assert provenance["summary"]["signals"] == {
        NAME: {
            "tic": 1,
            "excepted": 1,
            "novelty": "fail",
            "sha256": sha256_file(run / "signals" / NAME / "claims.json"),
        },
        "2-1": {
            "tic": 2,
            "excepted": 0,
            "novelty": None,
            "sha256": sha256_file(run / "signals" / "2-1" / "claims.json"),
        },
    }

    assert main([*argv, "--signals", "2-1"]) == 0
    later = next(r for r in claims_runs(tmp_path) if r != run)
    assert [p.name for p in (later / "signals").iterdir()] == ["2-1"]


def test_claims_refuses_a_signal_the_literature_run_has_no_record_of(tmp_path, monkeypatch):
    argv, *_ = runs(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match="has no record of 3-1"):
        main([*argv, "--signals", "3-1"])
    assert claims_runs(tmp_path) == []


def test_the_claims_file_dates_each_predicted_signal_by_its_deposit():
    found = claims.load_claims(ROOT / "results" / "claims.toml")
    root = ROOT / "results" / "predictions"
    dois = tomllib.loads((root / "dois.toml").read_text())
    for run_id, entry in dois.items():
        predicted = set(pd.read_csv(root / run_id / "predictions.csv")["signal"])
        for name in predicted:
            assert found[name] == Claim(name, entry["published"], f"https://doi.org/{entry['doi']}")


@pytest.mark.parametrize(
    "entry",
    [
        f'date = 2026-10-28T21:17:19Z\nrecord = "{DOI}"',
        'date = "2026-10-28"\nrecord = "' + DOI + '"',
        "date = 2026-10-28",
        'date = 2026-10-28\nrecord = "10.5281/zenodo.23745923"',
        f'date = 2026-10-28\nrecord = "{DOI}"\nnote = "the deposit"',
    ],
)
def test_load_claims_refuses_an_entry_it_cannot_read(tmp_path, entry):
    path = tmp_path / "claims.toml"
    path.write_text(f'["{NAME}"]\n{entry}\n')
    with pytest.raises(SystemExit, match=f"claims.toml: {NAME} needs"):
        claims.load_claims(path)
