import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, write_catalog_snapshot

from tess_hunt import threshold as threshold_module
from tess_hunt.catalogs import KNOWN_COLUMNS, load_known
from tess_hunt.checks import inconclusive
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.leo import LeoOutcome
from tess_hunt.provenance import sha256_file
from tess_hunt.search import search_code_sha256, search_input, search_star
from tess_hunt.threshold import (
    _leo_job,
    _own_transits_job,
    all_thresholds,
    check_search,
    compute_threshold,
    exclude_known,
    own_transits,
)

HARMONICS = (1.0, 0.5, 2.0, 1 / 3, 3.0)
ROOT = Path(__file__).resolve().parents[1]
SEARCH = load_criteria(ROOT / "criteria" / "search-v2.toml")
TRIAGE = load_criteria(ROOT / "criteria" / "triage-v1.toml")
SUN = {
    "tic": 1,
    "ra": 10.0,
    "dec": -60.0,
    "rad": 1.0,
    "mass": 1.0,
    "rho": 1.0,
    "teff": 5770.0,
    "logg": 4.44,
}
# The decoherence test's planet (tests/test_scramble.py) on four sectors.
PLANET = dict(sectors=(1, 2, 3, 4), noise_ppm=300.0, signals=[(3.7, 1326.1, 0.12, 1500e-6)], seed=6)


def candidates(sdes):
    return pd.DataFrame(
        {
            "tic": range(len(sdes)),
            "rank": 1,
            "sde": sdes,
            "period": 3.0,
            "t0": 100.0,
            "duration": 0.1,
        }
    )


def fake_evaluate(passing_below):
    calls = []

    def evaluate(rows):
        calls.append([r["sde"] for r in rows])
        return [{**r, "passes_fa": r["sde"] < passing_below} for r in rows]

    return evaluate, calls


def test_threshold_is_the_highest_passing_sde_and_stops_early():
    evaluate, calls = fake_evaluate(passing_below=15.0)
    value, evaluated = compute_threshold(
        candidates([30.0, 25.0, 20.0, 14.0, 13.0, 10.0]), evaluate, batch=2
    )
    assert value == 14.0 and calls == [[30.0, 25.0], [20.0, 14.0]]
    assert len(evaluated) == 4


def test_no_passing_null_signal_gives_no_threshold():
    evaluate, _ = fake_evaluate(passing_below=0.0)
    value, evaluated = compute_threshold(candidates([30.0, 12.0]), evaluate, batch=10)
    assert value is None and len(evaluated) == 2


def known_table(*rows):
    base = {
        "source": "TOI",
        "kind": "candidate",
        "name": "k",
        "ra": 0.0,
        "dec": 0.0,
        "t0": 50.0,
        "duration": 0.1,
        "depth_ppm": 100.0,
    }
    return pd.DataFrame([{**base, **r} for r in rows])


def test_exclude_known_matches_period_only_on_the_same_star():
    signals = pd.DataFrame(
        {"tic": [1, 2, 3], "period": [3.0, 3.0, 6.0], "t0": [100.0, 100.0, 100.0], "duration": 0.1}
    )
    known = known_table(
        {"tic": 1, "period": 3.0, "name": "EB-1", "t0": 51.234},
        {"tic": 9, "period": 3.0},
        {"tic": 3, "period": 3.0, "name": "TCE-3"},
    )
    names = exclude_known(signals, known, HARMONICS, 2.5)
    assert list(names) == ["EB-1", "", "TCE-3"]


def provenance(criteria_sha="c", code_sha="k", continue_sde=12.0):
    return {
        "criteria": [{"sha256": criteria_sha}],
        "search_code_sha256": code_sha,
        "threshold": {"value": continue_sde},
    }


def threshold_json(value=12.0, criteria_sha="c", code_sha="k"):
    return {
        "threshold": value,
        "search_criteria_sha256": criteria_sha,
        "search_code_sha256": code_sha,
    }


def test_check_search_accepts_a_matching_search():
    assert check_search(provenance(), threshold_json(), [threshold_json()]) == []


def test_check_search_refuses_other_hashes_and_a_grown_null():
    assert any(
        "criteria" in p for p in check_search(provenance(criteria_sha="x"), threshold_json(), [])
    )
    assert any("code" in p for p in check_search(provenance(code_sha="x"), threshold_json(), []))
    grown = [threshold_json(), threshold_json(value=13.5)]
    assert any("13.5" in p for p in check_search(provenance(), threshold_json(), grown))
    assert (
        check_search(provenance(), threshold_json(), [threshold_json(value=99.0, code_sha="other")])
        == []
    )


def test_check_search_refuses_a_search_without_a_threshold():
    assert check_search({**provenance(), "threshold": None}, threshold_json(), []) != []


@pytest.mark.parametrize("ran", [11.9, float("nan"), float("inf"), None, "12.0"])
def test_check_search_refuses_a_continue_sde_below_its_threshold_or_not_a_finite_number(ran):
    problems = check_search(provenance(continue_sde=ran), threshold_json(value=12.0), [])
    assert any("continue_sde" in p for p in problems), problems


def test_check_search_accepts_a_continue_sde_above_its_threshold():
    assert check_search(provenance(continue_sde=12.5), threshold_json(value=12.0), []) == []


def write_run(runs, run_id, ended_at, value):
    path = runs / run_id
    path.mkdir(parents=True)
    (path / "provenance.json").write_text(json.dumps({"ended_at": ended_at}))
    (path / "threshold.json").write_text(json.dumps(threshold_json(value=value)))


def test_all_thresholds_reads_finished_threshold_runs_only(tmp_path):
    write_run(tmp_path, "20261013T000000Z-threshold-abc1234-0001", "2026-10-13T01:00:00", 12.0)
    write_run(tmp_path, "20261013T010000Z-threshold-abc1234-0002", None, 99.0)
    write_run(tmp_path, "20261013T020000Z-search-abc1234-0003", "2026-10-13T03:00:00", 50.0)
    assert [t["threshold"] for t in all_thresholds(tmp_path)] == [12.0]


ROW = {
    "tic": 1,
    "rank": 1,
    "period": 19.84,
    "t0": 1330.0,
    "duration": 0.12,
    "depth": 0.001,
    "sde": 10.4,
}
OTHER = {"tic": 1, "rank": 2, "period": 23.53, "t0": 1331.0, "duration": 0.1}
KNOWN = [Ephemeris(5.1, 1327.0, 0.1)]


def leo_job(**changes):
    job = {
        "row": ROW,
        "star": SUN,
        "known": KNOWN,
        "others": [OTHER],
        "seed": 3,
        "search": SEARCH.values,
        "triage": TRIAGE.values,
    }
    return {**job, **changes}


def save_star(tmp_path, monkeypatch, tic=1, **lc):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    star = make_lc(tic=tic, **(lc or PLANET))
    star.save(tmp_path / "data" / "lc" / f"{tic}.npz")
    return star


def fake_leo(outcome_for, calls=None):
    """leo_flux's stand-in; `outcome_for(star, eph)` gives the outcome and the check's reason."""

    def leo_flux(lc, star, eph, others, exclude, crit_detrend, crit_triage, fa_only=False):
        if calls is not None:
            calls.append(
                {"lc": lc, "eph": eph, "others": others, "exclude": exclude, "fa_only": fa_only}
            )
        outcome, reason = outcome_for(star, eph)
        return inconclusive("leo_flux", reason), outcome, None

    return leo_flux


def test_leo_job_judges_the_light_curve_the_null_searched(tmp_path, monkeypatch):
    lc = save_star(tmp_path, monkeypatch)
    calls = []
    passing = fake_leo(lambda star, eph: (LeoOutcome("PC"), "planet candidate"), calls)
    monkeypatch.setattr(threshold_module, "leo_flux", passing)
    _leo_job(leo_job())
    scrambled, exclude = search_input(lc, KNOWN, SEARCH.values, 3)
    (call,) = calls
    np.testing.assert_array_equal(call["lc"].time, scrambled.time)
    np.testing.assert_array_equal(call["lc"].flux, scrambled.flux)
    np.testing.assert_array_equal(call["exclude"], exclude)
    assert exclude.any() and call["fa_only"]
    assert call["eph"] == Ephemeris(19.84, 1330.0, 0.12, 0.001)
    assert call["others"] == [Ephemeris(23.53, 1331.0, 0.1)]


@pytest.mark.parametrize(
    ("outcome", "reason", "passes_fa", "judged"),
    [
        (LeoOutcome("PC"), "planet candidate at flux level", True, True),
        (LeoOutcome("FA", ["dmm"], [], ["asymmetric"]), "FA: dmm", False, True),
        (LeoOutcome(None, [], [], ["chi"]), "tests not judged: chi", True, False),
        (None, "LEO-Vetter raised ValueError: no fit", True, False),
    ],
)
def test_leo_job_counts_an_unjudged_signal_as_surviving_and_says_why(
    tmp_path, monkeypatch, outcome, reason, passes_fa, judged
):
    save_star(tmp_path, monkeypatch)
    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(lambda star, eph: (outcome, reason)))
    out = _leo_job(leo_job())
    assert (out["passes_fa"], out["judged"]) == (passes_fa, judged)
    assert out["why_unjudged"] == ("" if judged else reason)
    assert out["sde"] == ROW["sde"]


def test_leo_job_with_a_missing_stellar_value_is_unjudged(tmp_path, monkeypatch):
    save_star(tmp_path, monkeypatch)
    # targets.parquet records carry pd.NA for a missing value.
    out = _leo_job(leo_job(star={**SUN, "teff": pd.NA}))
    assert out["passes_fa"] and not out["judged"] and "stellar value" in out["why_unjudged"]


def test_leo_job_names_an_exception_and_counts_the_signal_as_surviving(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    out = _leo_job(leo_job())
    assert out["passes_fa"] and not out["judged"]
    assert out["why_unjudged"].startswith("FileNotFoundError"), out["why_unjudged"]


def null_signals(lc, seed):
    """One star's null search, as search._search_job runs it."""
    scrambled, exclude = search_input(lc, [], SEARCH.values, seed)
    flat = detrend(scrambled, SEARCH["detrend"], exclude=exclude)
    return search_star(flat, 1.0, 1.0, SEARCH["search"]).signals


def harmonic_of(period, true):
    tolerance = math.erfc(SEARCH["match"]["sigma_p"] / math.sqrt(2.0))
    return any(abs(period - true * h) / period < tolerance for h in HARMONICS)


def test_a_null_peak_made_of_the_stars_own_transits_traces_back_to_them():
    lc = make_lc(**PLANET)
    # Seed 5 leaves four of the planet's transits evenly spaced at a period that is no harmonic of its own.
    # It moves every segment, so only the trace through the scramble can find them.
    peak = null_signals(lc, 5)[0]
    assert not harmonic_of(peak.period, 3.7)
    out = own_transits(lc, SUN, [], SEARCH.values, 5, peak.ephemeris())
    assert out["built"] is True and out["overlap"] >= 0.5, out
    assert harmonic_of(out["period"], 3.7) and out["sde"] > SEARCH["search"]["continue_sde"]


def test_a_noise_peak_on_a_star_with_a_planet_does_not_trace_back_to_it():
    lc = make_lc(**PLANET)
    peak = min(null_signals(lc, 2), key=lambda s: s.sde)
    out = own_transits(lc, SUN, [], SEARCH.values, 2, peak.ephemeris())
    assert out["built"] is False and out["overlap"] < 0.5, out


def test_a_null_signal_with_no_cadence_in_transit_cannot_be_traced():
    out = own_transits(
        make_lc(**PLANET), SUN, [], SEARCH.values, 3, Ephemeris(19.84, 1330.01, 1e-6)
    )
    assert out["built"] is None and out["n_cadences"] == 0 and out["reason"]


def test_own_transits_job_names_an_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    job = {"row": ROW, "star": SUN, "known": [], "seed": 3, "search": SEARCH.values}
    out = _own_transits_job(job)
    assert out["built"] is None and out["reason"].startswith("FileNotFoundError"), out


# Four sectors, one of them recent, so the stars count as covered under search-v2.
SAMPLE_SECTORS = (94, 95, 96, 97)
NULL_SEED = 4


def null_run(tmp_path, monkeypatch):
    """A null search of star 11 (the planet) and star 12 (noise), masked with a snapshot that holds
    neither."""
    save_star(tmp_path, monkeypatch, 11, **{**PLANET, "sectors": SAMPLE_SECTORS})
    save_star(tmp_path, monkeypatch, 12, sectors=SAMPLE_SECTORS, noise_ppm=300.0, seed=7)
    targets = tmp_path / "targets.parquet"
    pd.DataFrame({**SUN, "tic": [11, 12]}).to_parquet(targets)
    mask = write_catalog_snapshot(tmp_path / "mask")
    monkeypatch.chdir(ROOT)
    argv = ["search", "--targets", str(targets), "--catalogs", str(mask), "--workers", "1"]
    assert main([*argv, "--scramble", str(NULL_SEED)]) == 0
    return targets, mask, only_run(tmp_path, "search")


def triage_snapshot(tmp_path, mask):
    """The mask snapshot's rows plus a catalogued binary on star 11 at the planet's period."""
    eb = {
        "source": "Prsa2022",
        "kind": "eb",
        "name": "EB-11",
        "tic": 11,
        "ra": 10.0,
        "dec": -60.0,
        "period": 3.7,
        "t0": 1326.1,
        "duration": 0.12,
        "depth_ppm": 1500.0,
    }
    snap = tmp_path / "triage-snap"
    snap.mkdir()
    known = pd.concat([load_known(mask), pd.DataFrame([eb])], ignore_index=True)
    known[KNOWN_COLUMNS].to_parquet(snap / "known.parquet")
    (snap / "manifest.json").write_text("{}\n")
    return snap


def only_run(tmp_path, stage):
    (run,) = [p for p in (tmp_path / "data" / "runs").iterdir() if f"-{stage}-" in p.name]
    return run


def threshold_cli(tmp_path, targets, mask, null):
    argv = ["triage", "threshold", "--null", str(null), "--targets", str(targets)]
    argv += ["--catalogs", str(triage_snapshot(tmp_path, mask)), "--mask-catalogs", str(mask)]
    assert main([*argv, "--workers", "1"]) == 0
    run = only_run(tmp_path, "threshold")
    return json.loads((run / "threshold.json").read_text()), run


def test_threshold_cli_drops_known_objects_and_traces_the_threshold_row(tmp_path, monkeypatch):
    targets, mask, null = null_run(tmp_path, monkeypatch)
    calls = []
    passing = fake_leo(lambda star, eph: (LeoOutcome("PC"), "planet candidate"), calls)
    monkeypatch.setattr(threshold_module, "leo_flux", passing)
    result, run = threshold_cli(tmp_path, targets, mask, null)
    signals = pd.read_parquet(null / "signals.parquet")
    near = (signals["tic"] == 11) & signals["period"].map(lambda p: harmonic_of(p, 3.7))
    kept = signals[~near]
    assert result["excluded"] == near.sum() >= 1
    assert result["evaluated"] == len(kept) == len(calls)
    assert len(pd.read_parquet(run / "null_leo.parquet")) == len(kept)
    # Every null signal passes here, so the highest one sets the threshold.
    assert result["threshold"] == kept["sde"].max() and result["floor_used"] is False
    top = result["top"]
    assert [r["sde"] for r in top] == sorted(kept["sde"], reverse=True)
    assert all(r["judged"] and r["why_unjudged"] == "" and "own_transits" in r for r in top)
    row = result["threshold_row"]
    assert (row["tic"], row["rank"], row["sde"]) == (top[0]["tic"], top[0]["rank"], top[0]["sde"])
    assert result["threshold_row_unjudged"] is False and result["unjudged"] == 0
    assert result["unjudged_above_threshold_row"] == 0
    # The seed leaves star 11's own transits evenly spaced at a period that is no harmonic of 3.7 d.
    assert row["tic"] == 11 and not harmonic_of(row["period"], 3.7)
    assert row["own_transits"]["built"] is True and harmonic_of(row["own_transits"]["period"], 3.7)
    assert result["threshold_row_own_transits"] is True
    assert (result["n_null_stars"], result["n_sample"], result["expected_false_alarms"]) == (
        2,
        2,
        1.0,
    )
    assert result["null_run"] == null.name and result["snapshot"] == "triage-snap"
    assert result["rule"] == TRIAGE["threshold"]["rule"]
    null_provenance = json.loads((null / "provenance.json").read_text())
    assert result["search_criteria_sha256"] == SEARCH.sha256
    assert result["search_code_sha256"] == null_provenance["search_code_sha256"]
    provenance = json.loads((run / "provenance.json").read_text())
    assert provenance["summary"]["threshold"] == result["threshold"]
    assert provenance["inputs"]["null_signals"]["sha256"] == sha256_file(null / "signals.parquet")
    assert all_thresholds(tmp_path / "data" / "runs") == [result]


def test_threshold_cli_counts_unjudged_signals_and_keeps_the_floor(tmp_path, monkeypatch):
    targets, mask, null = null_run(tmp_path, monkeypatch)

    def outcome(star, eph):
        if star["tic"] == 12:
            return None, "a stellar value LEO-Vetter needs is missing"
        return LeoOutcome("FA", ["chi"]), "FA: chi"

    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(outcome))
    result, _ = threshold_cli(tmp_path, targets, mask, null)
    signals = pd.read_parquet(null / "signals.parquet")
    noise = signals.loc[signals["tic"] == 12, "sde"]
    # Star 12's null peaks are noise, below the provisional continue_sde the null ran at.
    floor = SEARCH["search"]["continue_sde"]
    assert noise.max() < floor
    assert result["threshold"] == floor and result["floor_used"] is True
    row = result["threshold_row"]
    assert row["tic"] == 12 and row["sde"] == noise.max() and not row["judged"]
    assert row["why_unjudged"] == "a stellar value LEO-Vetter needs is missing"
    assert result["threshold_row_unjudged"] is True and result["unjudged"] == len(noise)
    assert result["unjudged_above_threshold_row"] == 0
    assert row["own_transits"]["built"] is False and result["threshold_row_own_transits"] is False


def null_provenance(tmp_path, monkeypatch, **fields):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    monkeypatch.chdir(ROOT)
    mask = write_catalog_snapshot(tmp_path / "mask")
    inputs = {
        name: {"sha256": sha256_file(mask / name)}
        for name in ("toi.csv", "ctoi.csv", "pscomppars.csv")
    }
    null = tmp_path / "null"
    null.mkdir()
    base = {
        "ended_at": "2026-10-13T00:00:00+00:00",
        "scramble": 1,
        "inputs": inputs,
        "criteria": [{"file": "criteria/search-v2.toml", "sha256": SEARCH.sha256}],
        "search_code_sha256": "0" * 64,
    }
    (null / "provenance.json").write_text(json.dumps({**base, **fields}))
    argv = ["triage", "threshold", "--null", str(null), "--targets", str(tmp_path / "t.parquet")]
    return [*argv, "--catalogs", str(mask), "--mask-catalogs", str(mask), "--workers", "1"]


@pytest.mark.parametrize(
    ("fields", "message"),
    [
        ({"scramble": None}, "not a finished null"),
        ({"ended_at": None}, "not a finished null"),
        ({"inputs": {}}, "mask-catalogs"),
        ({"criteria": [{"file": "criteria/search-v2.toml", "sha256": "x"}]}, "criteria"),
        ({}, "search code"),
    ],
)
def test_threshold_cli_refuses_a_null_it_cannot_reproduce(tmp_path, monkeypatch, fields, message):
    with pytest.raises(SystemExit, match=message):
        main(null_provenance(tmp_path, monkeypatch, **fields))
    assert not (tmp_path / "data" / "runs").exists()


@pytest.mark.parametrize(
    ("signal_tics", "target_tics", "message"),
    [([], [5], "no null signal"), ([5, 7], [5, 6], r"no row for null stars \[7\]")],
)
def test_threshold_cli_refuses_an_empty_null_or_targets_missing_its_stars(
    tmp_path, monkeypatch, signal_tics, target_tics, message
):
    argv = null_provenance(tmp_path, monkeypatch, search_code_sha256=search_code_sha256(ROOT))
    row = {"rank": 1, "period": 7.0, "t0": 1330.0, "duration": 0.1, "sde": 10.0, "control": False}
    columns = ["tic", *row]
    signals = pd.DataFrame([{**row, "tic": t} for t in signal_tics], columns=columns)
    signals.to_parquet(tmp_path / "null" / "signals.parquet")
    pd.DataFrame({**SUN, "tic": target_tics}).to_parquet(tmp_path / "t.parquet")
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert not (tmp_path / "data" / "runs").exists()
