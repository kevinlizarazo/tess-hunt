import datetime as dt
import json
import math
import re
import shutil
import subprocess
import tomllib
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, with_products

from tess_hunt import dossier, predict, prereg, provenance, vet
from tess_hunt.catalogs import KNOWN_COLUMNS
from tess_hunt.checks.holdout import NO_TRAINING, holdout, season_labels
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file
from tess_hunt.serialize import jsonable

ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v2.toml")
VET3 = load_criteria(ROOT / "criteria" / "vet-v3.toml")
FACTS = ROOT / "results" / "predictions" / "facts.toml"
TESS_SECTORS = pd.read_csv(ROOT / VET3["predict"]["sectors_file"])
SECTORS = (1, 2, 3, 14, 15, 16, 28, 29, 30)  # three seasons about a year apart
# QLP in the last two seasons, so with any season held out the training seasons hold both families.
MIXED_QLP = (15, 16, 28, 29)
EPH = Ephemeris(3.7, 1326.1, 0.12, 1500e-6)
STAR = {"tic": 1, "ra": 30.0, "dec": -40.0, "tmag": 9.0}
LOCK = dt.date(2026, 12, 20)
NAME = "1-1"
VET_RUN = "20261020T000000Z-vetting-run-abc1234-0001"
RECORD_399 = ROOT / "results" / "vetting" / "399023421-1"
# The fields of a held-out season's family row that come from the training cadences.
FAMILY_FIELDS = ("ref", "ref_err", "ref_n", "training_cadences")


def known() -> pd.DataFrame:
    """The catalog: one object, on another star."""
    row = {"source": "TOI", "kind": "candidate", "name": "far", "tic": 999, "period": 2.5}
    base = {"ra": 200.0, "dec": 10.0, "duration": 0.1, "depth_ppm": 1000.0, "t0": 100.0}
    return pd.DataFrame([{**base, **row}])[KNOWN_COLUMNS]


def planet(qlp=(), seed=5, sectors=SECTORS):
    signal = (EPH.period, EPH.t0, EPH.duration, EPH.depth)
    lc = make_lc(sectors=sectors, noise_ppm=300.0, signals=[signal], seed=seed)
    return with_products(lc, {s: "QLP" if s in qlp else "SPOC" for s in sectors})


def windows(sectors=(110, 111, 112, 113), dates=TESS_SECTORS) -> list[dict]:
    """A density-prior fit's windows as a record holds them: the first transit of each sector, at a period a little
    off the refit's."""
    out = []
    for sector in sectors:
        start = predict.btjd(dates.set_index("sector").at[sector, "start_utc"])
        epoch = math.ceil((start - EPH.t0) / 3.7001)
        out.append(
            {
                "sector": sector,
                "epoch": epoch,
                "mid_btjd": EPH.t0 + epoch * 3.7001,
                "sd_minutes": 40.0 + sector,
                "half_width_minutes": {"1": 40.0 + sector, "3": 3 * (40.0 + sector)},
                "duration_days": 0.13,
            }
        )
    return out


def checks_json(name=NAME, **change) -> dict:
    return {
        "tic": STAR["tic"],
        "signal": {"name": name, "kind": "candidate"},
        "star": STAR,
        "ephemeris": asdict(EPH),
        "checks": [{"check": "holdout", "outcome": "inconclusive", "reason": "", "evidence": {}}],
        "dropped_suspect": [],
        "masked": [],
        "pixels": None,
        "catalogued": {"rows": []},
        "windows": windows(),
        "windows_reason": None,
        **change,
    }


def write_record(path: Path, outcome="held", **change) -> Path:
    path.mkdir(parents=True)
    (path / "checks.json").write_text(json.dumps(checks_json(path.name, **change)))
    (path / "call.toml").write_text(
        f'signal = "{path.name}"\noutcome = "{outcome}"\ndate = 2026-10-22\n'
        'reasons = "Held for a season."\nrests_on = ["holdout"]\ncriteria = ["vet-v3"]\n'
        'deciding_evidence = "A third season."\n'
    )
    return path


def predicted(lc, record: Path) -> dict:
    return prereg.predict_signal(
        record, lc, known(), SEARCH.values, VET3.values, TESS_SECTORS, LOCK
    )


def as_json(value) -> str:
    return json.dumps(jsonable(value), sort_keys=True)


def test_prediction_equals_holdout_refit(tmp_path):
    lc = planet(qlp=MIXED_QLP)
    cfg, core = VET3["holdout"], VET3["depth"]["core_fraction"]
    noisy = vet.prepare(lc, STAR, EPH, known(), SEARCH.values, VET3.values).noisy
    seasons = holdout(noisy, EPH, cfg, core, VET3["families"]).evidence["seasons"]
    labels = season_labels(noisy.time, cfg["season_gap_days"])
    record = write_record(tmp_path / NAME)
    assert len(seasons) == 3 and all("predicted_period" in s for s in seasons)
    assert {f["family"] for s in seasons for f in s["family_depths"]} == {"pdcsap", "qlp"}
    for row in seasons:
        # The season holdout leaves out, taken out of the light curve before it is prepared: the new season is
        # not in the M3 light curve either.
        held = np.unique(noisy.sector[labels == row["season"]])
        out = predicted(lc.select(~np.isin(lc.sector, held)), record)
        assert (out["predicted"]["period"], out["predicted"]["t0"]) == (
            row["predicted_period"],
            row["predicted_t0"],
        )
        ref = out["reference"]
        assert as_json([ref[k] for k in ("ref", "ref_err", "ref_n")]) == as_json(
            [row[k] for k in ("ref", "ref_err", "ref_n")]
        )
        for family in row["family_depths"]:
            trained = ref["families"].get(family["family"], NO_TRAINING)
            assert as_json([trained[k] for k in FAMILY_FIELDS]) == as_json(
                [family[k] for k in FAMILY_FIELDS]
            )
        # The two training gates read the same counts.
        assert len(out["training_seasons"]) == row["training_seasons"]
        assert (
            sum(s["holds_transits"] for s in out["training_seasons"])
            == row["training_seasons_with_transits"]
        )
        assert out["min_training_seasons"] == cfg["min_training_seasons"]
        assert out["core_half_width_days"] == 0.5 * core * out["predicted"]["duration"]


def test_sectors_before_the_lock_are_left_out(tmp_path):
    out = predicted(planet(), write_record(tmp_path / NAME))
    assert [s["sector"] for s in out["left_out"]] == [110, 111]
    for s in out["left_out"]:
        start = TESS_SECTORS.set_index("sector").at[s["sector"], "start_utc"][:10]
        assert s["reason"] == (
            f"starts {start}, before the lock on 2026-12-20: the deposit's files can still be edited until then"
        )
        # S110 and S111 run straight into S112, so they fall in the new season.
        assert s["in_season"] is True
    period, t0 = out["predicted"]["period"], out["predicted"]["t0"]
    dates = TESS_SECTORS.set_index("sector")
    start = predict.btjd(dates.at[112, "start_utc"])
    end = predict.btjd(dates.at[113, "end_utc"])
    every = [n for n in range(-1000, 1000) if start <= t0 + n * period < end]
    assert [t["epoch"] for t in out["transits"]] == every
    for t in out["transits"]:
        assert t["mid_btjd"] == t0 + t["epoch"] * period
        sector_start = predict.btjd(dates.at[t["sector"], "start_utc"])
        sector_end = predict.btjd(dates.at[t["sector"], "end_utc"])
        assert sector_start <= t["mid_btjd"] < sector_end
        assert t["mid_utc"] == predict.seen_utc(t["mid_btjd"], STAR["ra"], STAR["dec"])
    assert {t["sector"] for t in out["transits"]} == {112, 113}


def test_testable_routes(tmp_path):
    record = write_record(tmp_path / NAME)
    pdcsap_only = predicted(planet(), record)
    assert set(pdcsap_only["training_families"]) == {"pdcsap"}
    assert pdcsap_only["testable_with"] == ["SPOC 2-min", "TESS-SPOC"]
    with_qlp = predicted(planet(qlp=MIXED_QLP), record)
    assert with_qlp["training_families"] == {"pdcsap": [1, 2, 3, 14, 30], "qlp": [15, 16, 28, 29]}
    assert with_qlp["testable_with"] == ["SPOC 2-min", "TESS-SPOC", "QLP"]


def test_observer_windows_equal_the_records():
    checks = checks_json()
    kept = prereg.observer_windows(checks, LOCK, TESS_SECTORS)
    assert [w["sector"] for w in kept] == [112, 113]
    # Every field, unchanged.
    assert kept == [w for w in windows() if w["sector"] in (112, 113)]
    assert [as_json(w) for w in kept] == [as_json(w) for w in checks["windows"][2:]]


def facts() -> dict:
    """The committed facts, with the fixture's star among those on no 2-min list."""
    found = tomllib.loads(FACTS.read_text())
    found["off_two_minute_lists"]["value"].append(STAR["tic"])
    return found


def test_refuses_a_new_season_that_would_merge_with_the_vetted_ones(tmp_path):
    # Synthetic S109 ends about 33 days before the record's first window sector, S110, starts: holdout would label
    # them one season.
    with pytest.raises(ValueError, match=r"starts 33\.\d days after its last vetted cadence"):
        predicted(planet(sectors=(*SECTORS, 109)), write_record(tmp_path / NAME))
    # Far enough from the window sectors, the same record is predicted.
    assert predicted(planet(), tmp_path / NAME)["transits"]


def made(signals: dict) -> dict:
    """What the run's provenance gives the README."""
    return {
        "run_id": "20261101T000000Z-predictions-abc1234-0002",
        "started_at": "2026-11-01T00:00:00+00:00",
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
        "criteria": [
            {"file": "criteria/search-v2.toml", "sha256": SEARCH.sha256},
            {"file": "criteria/vet-v3.toml", "sha256": VET3.sha256},
        ],
        "vetting_run": VET_RUN,
        "catalogs": "2026-10-17T000000Z",
        "lock_start": LOCK.isoformat(),
        "inputs": {
            **{f"checks_{n}": {"file": "checks.json", "sha256": "1" * 64} for n in signals},
            "light_curve_1": {"file": "1.npz", "sha256": "2" * 64},
            "known": {"file": "known.parquet", "sha256": "3" * 64},
            "catalog_manifest": {"file": "manifest.json", "sha256": "4" * 64},
            "tess_sectors": {"file": "tess_sectors.csv", "sha256": "5" * 64},
            "facts": {"file": "facts.toml", "sha256": "6" * 64},
        },
    }


def test_package_fails_on_a_missing_value(tmp_path):
    good = write_record(tmp_path / "good" / NAME)
    signals = {NAME: predicted(planet(), good)}
    text = prereg.readme(made(signals), signals, {NAME: good}, VET3.values, facts(), TESS_SECTORS)
    assert "$" not in text and "None" not in text
    assert not re.search(r"\b(nan|null|missing)\b", text, re.IGNORECASE)
    # The 2-min lists as facts.toml read them, and no DDT proposal beside the record.
    words = " ".join(text.split())
    assert f"none of the 1 stars is on {facts()['two_minute_lists']['value']}," in words
    assert "No DDT proposal asks for 2-min data on any of them" in words

    # A star facts.toml does not give as on no 2-min list raises rather than being said to be on none.
    with pytest.raises(ValueError, match="TIC 1 as on none of the 2-min lists"):
        prereg.readme(
            made(signals),
            signals,
            {NAME: good},
            VET3.values,
            tomllib.loads(FACTS.read_text()),
            TESS_SECTORS,
        )

    # A sector with no read date in the sectors file would render "nan".
    undated = TESS_SECTORS.copy()
    undated.loc[undated["sector"] == 112, "read_on"] = float("nan")
    with pytest.raises(KeyError, match="sectors_read"):
        prereg.readme(made(signals), signals, {NAME: good}, VET3.values, facts(), undated)

    # A null in the record, or a NaN, is no value: the README never shows "missing", "nan" or "None".
    for key, value in (("period", None), ("t0", float("nan"))):
        record = write_record(tmp_path / key / NAME, ephemeris={**asdict(EPH), key: value})
        with pytest.raises(KeyError, match=f"search_{key}"):
            prereg.readme(
                made(signals), signals, {NAME: record}, VET3.values, facts(), TESS_SECTORS
            )

    # Nor is a fact facts.toml lacks.
    partial = {k: v for k, v in facts().items() if k != "tess_spoc_last_sector"}
    with pytest.raises(KeyError, match="fact_tess_spoc_last_sector"):
        prereg.readme(made(signals), signals, {NAME: good}, VET3.values, partial, TESS_SECTORS)

    # 399023421-1's section quotes its review's F9 and F4 and gives RAVEN's period from the record: a review
    # without F9, or a record without the RAVEN row, raises.
    values = prereg.record_values(RECORD_399) | prereg.fact_values(facts())
    assert prereg.note("399023421-1", values)
    no_f9 = tmp_path / "no-f9"
    shutil.copytree(RECORD_399, no_f9)
    review = json.loads((no_f9 / "review.json").read_text())
    review["findings"] = [f for f in review["findings"] if f["id"] != "F9"]
    (no_f9 / "review.json").write_text(json.dumps(review))
    with pytest.raises(KeyError, match="review_F9"):
        prereg.note("399023421-1", prereg.record_values(no_f9) | prereg.fact_values(facts()))
    no_raven = tmp_path / "no-raven"
    shutil.copytree(RECORD_399, no_raven)
    checks = json.loads((no_raven / "checks.json").read_text())
    checks["catalogued"]["rows"] = []
    (no_raven / "checks.json").write_text(json.dumps(checks))
    with pytest.raises(KeyError, match="raven_period"):
        prereg.note("399023421-1", prereg.record_values(no_raven) | prereg.fact_values(facts()))


def test_a_family_without_cadences_in_the_cores_shows_none(tmp_path):
    prediction = predicted(planet(qlp=MIXED_QLP), write_record(tmp_path / NAME))
    prediction["reference"]["families"]["qlp"].update(
        ref=float("nan"), ref_err=float("nan"), ref_n=0
    )
    table = prereg._references_table(prediction)
    qlp = prediction["reference"]["families"]["qlp"]["training_cadences"]
    assert f"| QLP | 15, 16, 28 and 29 | none | none | 0 | {qlp} |" in table
    # The README says what a family showing none means.
    assert "shows none for its depth and error" in prereg.README.template


@pytest.mark.parametrize(
    ("state", "read"),
    [
        tuple(tomllib.loads(FACTS.read_text())["ddt_241522065"][k] for k in ("value", "read")),
        # Recorded on a later day than every other fact: each sentence names its own facts' read dates.
        ("sent to the TESS DDT program on 2026-11-08", "2026-11-08"),
        ("not sent", "2026-11-09"),
    ],
)
def test_the_ddt_proposal_s_state_comes_from_facts(tmp_path, state, read):
    record = write_record(tmp_path / NAME)
    signals = {NAME: predicted(planet(), record)}
    stated = facts() | {
        "ddt_1": {"value": state, "source": "results/ddt/1-1/proposal.md", "read": read}
    }
    text = " ".join(
        prereg.readme(
            made(signals), signals, {NAME: record}, VET3.values, stated, TESS_SECTORS
        ).split()
    )
    assert (
        f"For {NAME}, tess-hunt has a DDT proposal asking for 2-min data (`results/ddt/{NAME}/` in its repository); "
        f"its state, as `facts.toml` records it on {read}: {state}. A sent proposal is a request, which the TESS "
        "office may or may not take." in text
    )
    assert "no 2-min data are in sight" not in text
    # The other facts keep their own dates.
    archives = facts()["tess_spoc_last_sector"]["read"]
    assert f"partial Sector 105 (as read on {archives})" in text
    assert f"results/ddt/1-1/proposal.md (read {read})" in text


def test_every_window_sector_is_checked_against_the_last_vetted_cadence(tmp_path):
    # A left-out window sector outside the new season, 17 days after the synthetic S30: at a re-vet it would merge with
    # the last vetted season, though the new season (S112, S113) is far away.
    dates = pd.concat(
        [
            TESS_SECTORS,
            pd.DataFrame(
                [
                    {
                        "sector": 31,
                        "start_utc": "2020-11-10T00:00:00",
                        "end_utc": "2020-12-07T00:00:00",
                    }
                ]
            ),
        ],
        ignore_index=True,
    )
    record = write_record(tmp_path / NAME, windows=windows((31, 112, 113), dates))
    with pytest.raises(
        ValueError, match=r"window sector 31 starts 17\.\d days after its last vetted cadence"
    ):
        prereg.predict_signal(record, planet(), known(), SEARCH.values, VET3.values, dates, LOCK)


def test_399023421_section_quotes_the_review_and_cites_raven():
    review = json.loads((RECORD_399 / "review.json").read_text())
    claims = {f["id"]: f["claim"] for f in review["findings"]}
    text = prereg.note(
        "399023421-1", prereg.record_values(RECORD_399) | prereg.fact_values(facts())
    )
    # Word for word, as the dossier quotes them (decision 0037).
    for finding in ("F9", "F4"):
        assert (
            f'finding {finding}, quoted word for word: "{dossier._scrub(claims[finding])}"' in text
        )
    # The model that wrote the review, and its date, from review.json.
    assert (
        f"tess-hunt's adversarial review of this signal was written by an AI model, {review['model']}, on "
        f"{review['date']}." in " ".join(text.split())
    )
    # The citation as facts.toml read it from the Zenodo record, and the period from the record's RAVEN row.
    assert facts()["raven"]["value"] in text and "Lafarga et al. 2026" in text
    assert "9.825 d" in text


def test_deposit_by_is_the_lock_less_zenodo_s_publish_limit(tmp_path):
    found = facts()
    days = found["zenodo_edit_publish_days"]["value"]
    assert prereg._deposit_by(LOCK, found) == (LOCK - dt.timedelta(days=days)).isoformat()
    # The maintainer's decision of 2026-10-28: an edit opened within 30 days can be published until day 45.
    assert prereg._deposit_by(LOCK, found) == "2026-11-05"
    later = found | {"zenodo_edit_publish_days": {**found["zenodo_edit_publish_days"], "value": 60}}
    assert prereg._deposit_by(LOCK, later) == "2026-10-21"

    record = write_record(tmp_path / NAME)
    signals = {NAME: predicted(planet(), record)}

    def readme(stated: dict) -> str:
        text = prereg.readme(
            made(signals), signals, {NAME: record}, VET3.values, stated, TESS_SECTORS
        )
        return " ".join(text.split())

    # The lock's sentence names both facts' read dates, one when they share it.
    assert "must be published within 45 days of publishing (as read on 2026-10-28)" in readme(found)
    earlier = found | {"zenodo_edit_days": {**found["zenodo_edit_days"], "read": "2026-10-27"}}
    assert (
        "(as read on 2026-10-27 and 2026-10-28), so a record's files are fixed 45 days"
        in readme(earlier)
    )
    # A facts file without the limit raises, naming it, in the README and the Zenodo text alike.
    partial = {k: v for k, v in found.items() if k != "zenodo_edit_publish_days"}
    with pytest.raises(KeyError, match="zenodo_edit_publish_days"):
        readme(partial)
    with pytest.raises(KeyError, match="zenodo_edit_publish_days"):
        prereg.zenodo(made(signals), signals, partial)


def test_zenodo_says_an_ai_model_wrote_the_review_the_readme_quotes(tmp_path):
    prediction = predicted(planet(), write_record(tmp_path / NAME))
    both = {NAME: prediction, "399023421-1": {**prediction, "tic": 399023421}}
    text = " ".join(prereg.zenodo(made(both), both, facts()).split())
    assert (
        "tess-hunt's code and the package's text were written with LLM assistance, and the adversarial review of "
        "399023421-1 that the README quotes was written by an AI model." in text
    )


def test_windows_wider_than_half_the_period_say_so(tmp_path):
    """A signal's section says its observers' windows can't place a transit only when the widest, at 3 sigma, reaches
    half the refit period either side."""
    narrow = write_record(tmp_path / "narrow" / NAME)
    prediction = predicted(planet(), narrow)
    half = 0.5 * prediction["predicted"]["period"] * prereg.MINUTES_PER_DAY

    def section(record: Path) -> str:
        text = prereg._section(prediction, record, VET3.values, TESS_SECTORS, LOCK, facts())
        return " ".join(text.split())

    def wide(name: str, width: float) -> Path:
        found = [{**w, "half_width_minutes": {"1": width / 3, "3": width}} for w in windows()]
        return write_record(tmp_path / name / NAME, windows=found)

    # The fixture's 3-sigma half-widths are a few hundred minutes, on a 3.7 d period.
    assert "cannot place a transit by eye" not in section(narrow)
    assert "cannot place a transit by eye" not in section(wide("under", half - 1))
    assert (
        f"At 3 sigma its observers' windows reach up to {half:.0f} min either side of their mid-times, against a refit "
        f"period of {2 * half:.0f} min: at least half the period either side, so the widest spans a whole orbit and "
        "the windows cannot place a transit by eye. The refit's predicted mid-times in `predictions.csv` are what the "
        "test judges." in section(wide("half", half))
    )


def vetting_run(tmp_path, monkeypatch, production=True) -> tuple[list[str], Path]:
    """A finished vetting run that read star 1's light curve, its record of 1-1 published in a repo, and the
    predictions run's arguments."""
    data = tmp_path / "data"
    monkeypatch.setenv("TESS_HUNT_DATA", str(data))
    repo = tmp_path / "repo"
    (repo / "benchmarks").mkdir(parents=True)
    shutil.copy(ROOT / VET3["predict"]["sectors_file"], repo / "benchmarks")
    (repo / "results" / "predictions").mkdir(parents=True)
    # The committed facts, with star 1 among the stars on no 2-min list.
    listed = FACTS.read_text().replace("value = [103312990", "value = [1, 103312990")
    assert listed != FACTS.read_text()
    (repo / prereg.FACTS).write_text(listed)
    monkeypatch.setattr(prereg, "repo_root", lambda: repo)
    monkeypatch.setattr(predict, "repo_root", lambda: repo)
    # A production run needs a clean tree and committed facts; this test's repo is no git checkout.
    monkeypatch.setattr(
        provenance, "git_state", lambda root: {"commit": "abc1234" + "0" * 33, "dirty_paths": []}
    )
    monkeypatch.setattr(prereg, "_uncommitted", lambda path: False)
    lc_file = data / "lc" / "1.npz"
    planet().save(lc_file)
    snap = tmp_path / "snap"
    snap.mkdir()
    known().to_parquet(snap / "known.parquet")
    (snap / "manifest.json").write_text("{}\n")
    run = data / "runs" / VET_RUN
    record = write_record(run / "signals" / NAME)
    (record / "call.toml").unlink()
    published = repo / "results" / "vetting" / NAME
    write_record(published)
    shutil.copy(record / "checks.json", published / "checks.json")
    inputs = {
        "light_curve_1": lc_file,
        "known": snap / "known.parquet",
        "catalog_manifest": snap / "manifest.json",
        "tess_sectors": repo / VET3["predict"]["sectors_file"],
    }
    (run / "provenance.json").write_text(
        json.dumps(
            {
                "stage": "vetting-run",
                "ended_at": "2026-10-20T01:00:00+00:00",
                "production": production,
                "evidence_only": False,
                "criteria": [
                    {"file": "criteria/search-v2.toml", "sha256": SEARCH.sha256},
                    {"file": "criteria/vet-v3.toml", "sha256": VET3.sha256},
                ],
                "inputs": {
                    name: {"file": path.name, "sha256": sha256_file(path)}
                    for name, path in inputs.items()
                },
            }
        )
    )
    argv = [
        "predictions",
        "run",
        *("--vetting-run", str(run)),
        *("--records", NAME),
        *("--catalogs", str(snap)),
        *("--lock-start", "2026-12-20"),
        *("--criteria-search", str(SEARCH.path)),
        *("--criteria-vet", str(VET3.path)),
    ]
    return argv, repo


def runs(tmp_path) -> list[Path]:
    return sorted((tmp_path / "data" / "runs").glob("*-predictions-*"))


def test_predictions_run_and_publish(tmp_path, monkeypatch):
    argv, repo = vetting_run(tmp_path, monkeypatch)
    assert main([*argv, "--production"]) == 0
    [run] = runs(tmp_path)
    made = json.loads((run / "provenance.json").read_text())
    assert made["production"] and made["vetting_run"] == VET_RUN and made["ended_at"]
    assert made["lock_start"] == "2026-12-20"
    record = repo / "results" / "vetting" / NAME
    assert made["inputs"][f"checks_{NAME}"]["sha256"] == sha256_file(record / "checks.json")
    lc = tmp_path / "data" / "lc" / "1.npz"
    assert made["inputs"]["light_curve_1"]["sha256"] == sha256_file(lc)

    expected = predicted(planet(), record)
    references = json.loads((run / "references.json").read_text())
    assert as_json(references["signals"][NAME]) == as_json(
        {k: v for k, v in expected.items() if k != "transits"}
    )
    assert references["test"]["holdout"] == VET3["holdout"]
    rows = pd.read_csv(run / "predictions.csv", float_precision="round_trip").to_dict("records")
    assert [(r["signal"], r["sector"], r["epoch"], r["mid_btjd"], r["mid_utc"]) for r in rows] == [
        (NAME, t["sector"], t["epoch"], t["mid_btjd"], t["mid_utc"]) for t in expected["transits"]
    ]
    assert {r["period"] for r in rows} == {expected["predicted"]["period"]}
    observed = pd.read_csv(run / "windows.csv", float_precision="round_trip").to_dict("records")
    kept = prereg.observer_windows(checks_json(), LOCK, TESS_SECTORS)
    assert [(r["sector"], r["epoch"], r["mid_btjd"], r["sd_minutes"]) for r in observed] == [
        (w["sector"], w["epoch"], w["mid_btjd"], w["sd_minutes"]) for w in kept
    ]
    assert [r["half_width_3sigma_minutes"] for r in observed] == [
        w["half_width_minutes"]["3"] for w in kept
    ]
    readme = (run / "README.md").read_text()
    assert made["run_id"] in readme and VET_RUN in readme and VET3.sha256 in readme
    assert sha256_file(lc) in readme and sha256_file(record / "checks.json") in readme
    assert (run / "facts.toml").read_bytes() == (repo / prereg.FACTS).read_bytes()
    assert made["inputs"]["facts"]["sha256"] == sha256_file(repo / prereg.FACTS)
    zenodo = (run / "zenodo.md").read_text()
    assert "CC BY 4.0" in zenodo and made["run_id"] in zenodo
    flat, zflat = " ".join(readme.split()), " ".join(zenodo.split())
    # The lock date holds only for a deposit made in time, and the README and the Zenodo text say so.
    assert "Deposited by 2026-11-05, this package's files are fixed by 2026-12-20" in flat
    assert "deposited by 2026-11-05, this package's files are fixed by 2026-12-20" in zflat
    # The code and text were written with LLM assistance; this package quotes no review.
    assert "tess-hunt's code and this text were written with LLM assistance." in flat
    assert "tess-hunt's code and the package's text were written with LLM assistance." in zflat
    assert "AI model" not in zflat
    # 1-1's windows are far narrower than its period.
    assert "cannot place a transit by eye" not in flat
    # The judging date cuts on when a light curve was fetched, as judge_signal applies it (decision 0041), not on when
    # a re-vet runs; the deposited text states that rule.
    assert (
        "The judging date, 2027-12-31, applies to when a re-vet's light curve was fetched" in flat
    )
    assert (
        "A re-vet judged as of a day before 2027-12-31, on a light curve that lacks a predicted sector, may run but"
        " reports the result as pending." in flat
    )
    assert "one fetched on or after it completes no season" in flat
    assert (
        "still lacks a predicted sector in a re-vet judged as of that date or later stays untested"
        in flat
    )
    assert "on its complete new season in a light curve fetched before 2027-12-31" in zflat
    assert "failing that" not in flat and "not judged by" not in zflat
    for text in (readme, zenodo):
        assert "$" not in text and provenance.scrub(text) == text
        assert not any(n.lower() in text.lower() for n in provenance.maintainer() or ())

    assert main(["predictions", "publish", "--run", made["run_id"]]) == 0
    package = repo / "results" / "predictions" / made["run_id"]
    assert sorted(p.name for p in package.iterdir()) == sorted(prereg.PACKAGE)
    for name in prereg.PACKAGE:
        assert sha256_file(package / name) == sha256_file(run / name)
    index = (repo / "results" / "predictions" / "README.md").read_text()
    [line] = [x for x in index.splitlines() if made["run_id"] in x]
    assert f"| {NAME} | DOI pending |" in line and "| 2026-" in line

    # Recording the DOI and rendering the index again shows it (Task 4).
    (repo / "results" / "predictions" / "dois.toml").write_text(
        f'["{made["run_id"]}"]\ndoi = "10.5281/zenodo.1"\npublished = 2026-11-20\n'
    )
    assert main(["predictions", "index"]) == 0
    index = (repo / "results" / "predictions" / "README.md").read_text()
    assert "[10.5281/zenodo.1](https://doi.org/10.5281/zenodo.1), published 2026-11-20" in index
    with pytest.raises(SystemExit, match="exists"):
        main(["predictions", "publish", "--run", made["run_id"]])


def test_a_production_run_states_only_the_committed_facts(tmp_path, monkeypatch):
    argv, repo = vetting_run(tmp_path, monkeypatch)
    elsewhere = tmp_path / "facts.toml"
    shutil.copy(repo / prereg.FACTS, elsewhere)
    with pytest.raises(
        SystemExit, match=f"states {prereg.FACTS} from this checkout, not {elsewhere}"
    ):
        main([*argv, "--facts", str(elsewhere), "--production"])
    monkeypatch.setattr(prereg, "_uncommitted", lambda path: path == repo / prereg.FACTS)
    with pytest.raises(SystemExit, match="has changes that are not committed"):
        main([*argv, "--production"])
    assert not runs(tmp_path)
    # Outside production another facts file may be tried.
    assert main([*argv, "--facts", str(elsewhere)]) == 0


def test_uncommitted_sees_an_edit_to_a_tracked_file(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    path = tmp_path / "facts.toml"
    path.write_text("[a]\nvalue = 1\n")
    assert prereg._uncommitted(path)
    git("add", "facts.toml")
    git("commit", "-m", "facts")
    assert not prereg._uncommitted(path)
    path.write_text("[a]\nvalue = 2\n")
    assert prereg._uncommitted(path)


def test_publish_refuses_a_run_that_was_not_production(tmp_path, monkeypatch):
    argv, repo = vetting_run(tmp_path, monkeypatch, production=False)
    assert main(argv) == 0
    [run] = runs(tmp_path)
    with pytest.raises(SystemExit, match="not a production run"):
        main(["predictions", "publish", "--run", run.name])
    assert not (repo / "results" / "predictions" / run.name).exists()


def test_refuses_a_light_curve_the_vetting_run_did_not_read(tmp_path, monkeypatch):
    argv, _ = vetting_run(tmp_path, monkeypatch)
    # The shared cache rewritten by a later fetch.
    planet(seed=6).save(tmp_path / "data" / "lc" / "1.npz")
    with pytest.raises(SystemExit, match=f"TIC 1 is not the one {VET_RUN} read"):
        main(argv)
    assert not runs(tmp_path)


def test_refuses_a_record_not_held(tmp_path, monkeypatch):
    argv, repo = vetting_run(tmp_path, monkeypatch)
    call = repo / "results" / "vetting" / NAME / "call.toml"
    call.write_text(call.read_text().replace('"held"', '"killed"'))
    with pytest.raises(SystemExit, match=f"{NAME} is killed, not held"):
        main(argv)
    assert not runs(tmp_path)


def other_snapshot(tmp_path) -> list[str]:
    snap = tmp_path / "snap2"
    shutil.copytree(tmp_path / "snap", snap)
    (snap / "manifest.json").write_text('{"created": "later"}\n')
    return ["--catalogs", str(snap)]


def other_criteria(tmp_path) -> list[str]:
    path = tmp_path / "vet-v3-other.toml"
    path.write_text(VET3.path.read_text().replace("min_points = 5", "min_points = 6", 1))
    return ["--criteria-vet", str(path)]


def edited_record(tmp_path) -> list[str]:
    path = tmp_path / "repo" / "results" / "vetting" / NAME / "checks.json"
    path.write_text(path.read_text() + "\n")
    return []


def other_sectors_file(tmp_path) -> list[str]:
    path = tmp_path / "repo" / VET3["predict"]["sectors_file"]
    path.write_text(path.read_text() + "115,2027-03-14T00:00:00,2027-04-10T00:00:00,x,2026-10-28\n")
    return []


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (edited_record, f"results/vetting/{NAME}/checks.json is not {VET_RUN}'s checks.json"),
        (other_snapshot, f"snap2 is not the catalog snapshot {VET_RUN} read"),
        (other_criteria, f"is not the criteria/vet-v3.toml that {VET_RUN} ran with"),
        (other_sectors_file, f"tess_sectors.csv is not the file {VET_RUN} read"),
    ],
)
def test_refuses_inputs_other_than_the_vetting_runs(tmp_path, monkeypatch, change, message):
    argv, _ = vetting_run(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match=message):
        main([*argv, *change(tmp_path)])
    assert not runs(tmp_path)


def test_the_committed_index_is_its_render():
    assert (ROOT / "results" / "predictions" / "README.md").read_text() == prereg.index(ROOT)


def package(path: Path, prediction: dict, sectors, name: str = NAME) -> Path:
    """A predictions package's two files the test reads, as `predictions run` writes them, for one signal predicted
    in `sectors`."""
    path.mkdir(parents=True)
    references = {
        "test": {
            "holdout": VET3["holdout"],
            "core_fraction": VET3["depth"]["core_fraction"],
            "families": VET3["families"],
        },
        "signals": {name: {k: v for k, v in prediction.items() if k != "transits"}},
    }
    (path / "references.json").write_text(json.dumps(jsonable(references), sort_keys=True))
    rows = [{"signal": name, "sector": s} for s in sectors]
    pd.DataFrame(rows).to_csv(path / "predictions.csv", index=False)
    return path


def judged(lc, path: Path, as_of: dt.date, crit_vet: dict = VET3.values, fetched=None) -> dict:
    prepared = vet.prepare(lc, STAR, EPH, known(), SEARCH.values, VET3.values)
    return prereg.judge_signal(path, NAME, prepared, crit_vet, as_of, fetched=fetched)


def replaced(lc: LightCurve, other: LightCurve, sectors) -> LightCurve:
    """`lc` with `other`'s cadences in `sectors` in place of its own."""
    parts = [lc.select(~np.isin(lc.sector, sectors)), other.select(np.isin(other.sector, sectors))]
    time, flux, err, sector = (
        np.concatenate([getattr(p, k) for p in parts])
        for k in ("time", "flux", "flux_err", "sector")
    )
    order = np.argsort(time)
    return LightCurve(lc.tic, time[order], flux[order], err[order], sector[order], lc.sources)


EARLY, LATE = dt.date(2027, 6, 1), dt.date(2028, 1, 1)
TRAINING, NEW = (1, 2, 3, 14, 15, 16), (28, 29, 30)


def test_prereg_results(tmp_path):
    """The preregistered test of a synthetic new season (decision 0040): replicated, missed, untested and pending."""
    record = write_record(tmp_path / NAME)
    prediction = predicted(planet(sectors=TRAINING), record)
    assert prediction["testable_with"] == ["SPOC 2-min", "TESS-SPOC"]
    whole = package(tmp_path / "package", prediction, NEW)

    # The dip where the package put it: replicated, on the complete season, before the judging date or after.
    for as_of in (EARLY, LATE):
        found = judged(planet(), whole, as_of)
        assert (found["result"], found["status"]) == ("replicated", "predicted")
    assert found["season"]["sectors"] == list(NEW) and found["predicted_sectors"] == list(NEW)
    assert found["sigma"] >= VET3["holdout"]["min_sigma"]
    assert found["as_of"] == LATE.isoformat() and found["judged_by"] == "2027-12-31"

    # No dip in the new season: missed.
    flat = with_products(
        make_lc(sectors=SECTORS, noise_ppm=300.0, seed=6), dict.fromkeys(SECTORS, "SPOC")
    )
    found = judged(replaced(planet(), flat, NEW), whole, LATE)
    assert (found["result"], found["status"]) == ("missed", "missed")
    assert found["expected_snr"] >= VET3["holdout"]["min_expected_snr"]

    # The new season holds a sector of a family with no training data (S28, QLP, not itself predicted): untested
    # with the reason, never replicated or missed.
    found = judged(planet(qlp=(28,)), package(tmp_path / "late", prediction, NEW[1:]), LATE)
    assert (found["result"], found["status"]) == ("untested", "untestable")
    assert found["reason"] == "no training cadences in the held-out season's qlp family"
    assert found["season"]["sectors"] == list(NEW)

    # A predicted sector with no light curve the test can use (S29 is QLP, which has no training data; S30 is not
    # there): pending before the judging date, untested from it on.
    partial = planet(qlp=(29,), sectors=(*TRAINING, 28, 29))
    found = judged(partial, whole, EARLY)
    assert (found["result"], found["status"]) == ("pending", "pending")
    assert "S29 (QLP, which can't test it) and S30 (no data)" in found["reason"]
    assert "2027-12-31" in found["reason"]
    found = judged(partial, whole, prereg.JUDGED_BY)
    assert (found["result"], found["status"]) == ("untested", "no_light_curve")
    assert "S29 (QLP, which can't test it) and S30 (no data)" in found["reason"]
    # A timing-suspect sector reaches no check, so it can't test the prediction either.
    suspect = with_products(planet(), dict.fromkeys(SECTORS, "SPOC"), suspect={30})
    found = judged(suspect, whole, EARLY)
    assert found["result"] == "pending" and "S30 (timing-suspect)" in found["reason"]

    # The season pending above, completed by a light curve fetched on or after the judging date: untested, whatever
    # it holds (decision 0041). Fetched the day before, it is judged.
    assert found["fetched"] is None
    found = judged(planet(), whole, LATE, fetched=dt.date(2028, 1, 2))
    assert (found["result"], found["status"]) == ("untested", "fetched_after_judged_by")
    assert found["reason"] == (
        "the light curve was fetched on 2028-01-02, on or after the judging date 2027-12-31: data fetched then "
        "complete no season"
    )
    assert found["fetched"] == "2028-01-02"
    found = judged(planet(), whole, LATE, fetched=dt.date(2027, 12, 30))
    assert found["result"] == "replicated"

    # The two training gates read the package's counts.
    one = {**prediction, "training_seasons": prediction["training_seasons"][:1]}
    found = judged(planet(), package(tmp_path / "one", one, NEW), EARLY)
    assert (found["result"], found["status"]) == ("untested", "untestable")
    assert found["reason"].startswith("1 training season(s), need 2")
    none = {
        **prediction,
        "training_seasons": [
            {**s, "holds_transits": False} for s in prediction["training_seasons"]
        ],
    }
    found = judged(planet(), package(tmp_path / "none", none, NEW), EARLY)
    assert found["result"] == "untested" and found["reason"].startswith("0 of 2 training seasons")

    # The test is the package's: other [holdout] values are not it.
    other = {**VET3.values, "holdout": {**VET3["holdout"], "min_sigma": 3.0}}
    with pytest.raises(ValueError, match=r"not the test the package froze"):
        judged(planet(), whole, LATE, crit_vet=other)
    with pytest.raises(ValueError, match="predicts no 9-9"):
        prereg.judge_signal(
            whole,
            "9-9",
            vet.prepare(planet(), STAR, EPH, known(), SEARCH.values, VET3.values),
            VET3.values,
            LATE,
        )


def test_prereg_equals_holdout_on_an_unchanged_light_curve(tmp_path):
    """With each season of an M3 light curve as the new season, the preregistered test gives the row
    `checks.holdout` gives that season."""
    lc = planet(qlp=MIXED_QLP)
    cfg, core = VET3["holdout"], VET3["depth"]["core_fraction"]
    prepared = vet.prepare(lc, STAR, EPH, known(), SEARCH.values, VET3.values)
    seasons = holdout(prepared.noisy, EPH, cfg, core, VET3["families"]).evidence["seasons"]
    labels = season_labels(prepared.noisy.time, cfg["season_gap_days"])
    record = write_record(tmp_path / NAME)
    # What holdout adds to a season row besides the judgement.
    gates = {"season", "start", "end", "training_seasons", "training_seasons_with_transits"}
    refit = {"predicted_period", "predicted_t0"}
    results = []
    for row in seasons:
        held = sorted(int(s) for s in np.unique(prepared.noisy.sector[labels == row["season"]]))
        prediction = predicted(lc.select(~np.isin(lc.sector, held)), record)
        path = package(tmp_path / f"package-{row['season']}", prediction, held)
        found = prereg.judge_signal(path, NAME, prepared, VET3.values, EARLY)
        judgement = set(row) - gates - refit
        assert as_json({k: found[k] for k in judgement}) == as_json({k: row[k] for k in judgement})
        assert (found["season"]["start"], found["season"]["end"]) == (row["start"], row["end"])
        assert found["result"] == prereg.RESULTS.get(row["status"], "untested")
        results.append(found["result"])
    assert "replicated" in results


def test_every_fact_names_its_source_and_read_date():
    for key, fact in facts().items():
        assert set(fact) - {"note"} == {"value", "source", "read"}, key
        # A page read on the web, or a file in this repository.
        assert fact["source"].startswith("https://") or (ROOT / fact["source"]).is_file(), key
        assert dt.date.fromisoformat(fact["read"])
