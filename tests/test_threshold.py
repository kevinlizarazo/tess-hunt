import json
import math
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from synthetic import make_lc, write_catalog_snapshot

from tess_hunt import threshold as threshold_module
from tess_hunt.catalogs import KNOWN_COLUMNS, load_known, snapshot_inputs
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
    check_leo_code,
    check_null_light_curves,
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


def fake_evaluate(passing_below, unjudged=()):
    """Signals below `passing_below` pass; those in `unjudged` were not judged, so they count as passing."""
    calls = []

    def evaluate(rows):
        calls.append([r["sde"] for r in rows])
        return [
            {
                **r,
                "passes_fa": r["sde"] < passing_below or r["sde"] in unjudged,
                "judged": r["sde"] not in unjudged,
            }
            for r in rows
        ]

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


def test_an_unjudged_pass_sets_the_threshold_and_evaluation_goes_on_to_a_judged_one():
    evaluate, calls = fake_evaluate(passing_below=15.0, unjudged=(25.0,))
    value, evaluated = compute_threshold(
        candidates([30.0, 25.0, 20.0, 14.0, 13.0, 10.0]), evaluate, batch=2
    )
    assert value == 25.0 and calls == [[30.0, 25.0], [20.0, 14.0]]
    assert len(evaluated) == 4


def test_without_a_judged_pass_every_candidate_is_evaluated():
    evaluate, calls = fake_evaluate(passing_below=0.0, unjudged=(25.0,))
    value, evaluated = compute_threshold(candidates([30.0, 25.0, 20.0]), evaluate, batch=1)
    assert value == 25.0 and calls == [[30.0], [25.0], [20.0]]
    assert len(evaluated) == 3


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


def git(root, *args) -> str:
    out = subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)
    return out.stdout.strip()


@pytest.fixture
def leo_repo(tmp_path):
    """A checkout with a LEO-Vetter wrapper and a lock committed, and the provenance of a run made there."""
    root = tmp_path / "repo"
    (root / "src" / "tess_hunt").mkdir(parents=True)
    (root / "src" / "tess_hunt" / "leo.py").write_text("MAX_SES_TO_MES = 0.88\n")
    (root / "uv.lock").write_text("lock\n")
    git(root, "init", "-b", "main")
    git(root, "config", "user.email", "t@example.com")
    git(root, "config", "user.name", "t")
    git(root, "add", ".")
    git(root, "commit", "-m", "init")
    provenance = {
        "uv_lock_sha256": sha256_file(root / "uv.lock"),
        "git": {"commit": git(root, "rev-parse", "HEAD"), "dirty_paths": []},
    }
    return root, provenance


def test_check_leo_code_passes_the_same_lock_and_wrapper(leo_repo):
    root, provenance = leo_repo
    assert check_leo_code(provenance, root) == []


def test_check_leo_code_refuses_another_lock(leo_repo):
    root, provenance = leo_repo
    problems = check_leo_code({**provenance, "uv_lock_sha256": "0" * 64}, root)
    assert len(problems) == 1 and "uv.lock" in problems[0], problems


def test_check_leo_code_refuses_a_changed_wrapper(leo_repo):
    root, provenance = leo_repo
    (root / "src" / "tess_hunt" / "leo.py").write_text("MAX_SES_TO_MES = 0.8\n")
    problems = check_leo_code(provenance, root)
    assert len(problems) == 1 and "src/tess_hunt/leo.py differs" in problems[0], problems


@pytest.mark.parametrize(
    ("state", "message"),
    [
        # The commit's wrapper is not the one that ran when the run's tree had changed it.
        ({"dirty_paths": ["src/tess_hunt/leo.py"]}, "uncommitted"),
        ({"commit": "0" * 40}, "cannot be read"),
    ],
)
def test_check_leo_code_refuses_a_wrapper_it_cannot_trace(leo_repo, state, message):
    root, provenance = leo_repo
    problems = check_leo_code({**provenance, "git": {**provenance["git"], **state}}, root)
    assert len(problems) == 1 and message in problems[0], problems


def stars_table(lc_sha256: dict, status=None) -> pd.DataFrame:
    rows = [
        {"tic": t, "control": False, "status": (status or {}).get(t, "ok"), "lc_sha256": s}
        for t, s in lc_sha256.items()
    ]
    return pd.DataFrame(rows)


def test_null_and_search_light_curves_must_match():
    null = stars_table({1: "a", 2: "b", 3: "c", 4: "d"})
    search = stars_table({1: "a", 2: "x", 3: "c", 4: "y"})
    # Star 4 changed as well, but none of its signals is triaged.
    assert check_null_light_curves(null, search, [1, 2, 3]) == [2]


def test_a_light_curve_the_null_did_not_search_does_not_match():
    null = stars_table({1: "a", 3: None}, status={3: "no_light_curve"})
    search = stars_table({1: "a", 2: "b", 3: "c"})
    assert check_null_light_curves(null, search, [1, 2, 3]) == [2, 3]


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
                {
                    "lc": lc,
                    "eph": eph,
                    "others": others,
                    "exclude": exclude,
                    "crit_detrend": crit_detrend,
                    "crit_triage": crit_triage,
                    "fa_only": fa_only,
                }
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
    # Real leo_flux reads these as it is called, outside its own try: a wrong dict would leave every
    # null signal unjudged.
    assert call["crit_detrend"] == SEARCH["detrend"] and call["crit_triage"] == TRIAGE.values


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
    why = out["why_unjudged"]
    # threshold.json is published under results/, so the data directory's path is scrubbed.
    assert why.startswith("FileNotFoundError") and "$TESS_HUNT_DATA/lc/1.npz" in why, why
    assert str(tmp_path) not in why


def test_leo_job_scrubs_the_data_directory_from_leo_vetters_reason(tmp_path, monkeypatch):
    save_star(tmp_path, monkeypatch)
    reason = f"LEO-Vetter raised OSError: {tmp_path / 'data' / 'tdi'} is not writable"
    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(lambda star, eph: (None, reason)))
    why = _leo_job(leo_job())["why_unjudged"]
    assert why == "LEO-Vetter raised OSError: $TESS_HUNT_DATA/tdi is not writable", why


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


def test_a_star_whose_unscrambled_search_finds_nothing_is_not_built():
    # Fewer cadences than a search needs: detrend keeps no sector, so the unscrambled search finds nothing.
    lc = make_lc(sectors=(1,), seed=6)
    lc = lc.select(np.arange(len(lc.time)) < 90)
    out = own_transits(lc, SUN, [], SEARCH.values, 3, Ephemeris(1.0, float(lc.time[10]), 0.1))
    assert out["built"] is False and out["overlap"] == 0.0 and out["n_cadences"] > 0, out
    assert out["reason"] == "the unscrambled search found no signal"


def test_own_transits_job_names_an_exception(tmp_path, monkeypatch):
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    job = {"row": ROW, "star": SUN, "known": [], "seed": 3, "search": SEARCH.values}
    out = _own_transits_job(job)
    assert out["built"] is None and out["reason"].startswith("FileNotFoundError"), out
    assert "$TESS_HUNT_DATA/lc/1.npz" in out["reason"] and str(tmp_path) not in out["reason"]


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


def triage_snapshot(tmp_path, mask, kind="tce"):
    """The mask snapshot's rows, a catalogued object of `kind` on star 11 at the planet's period, and a
    TCE and a binary on stars outside the sample, so the snapshot holds both as a v2 snapshot does."""
    base = {"ra": 10.0, "dec": -60.0, "t0": 1326.1, "duration": 0.12, "depth_ppm": 1500.0}
    rows = [
        {**base, "source": "catalog", "kind": kind, "name": f"{kind}-11", "tic": 11, "period": 3.7},
        {**base, "source": "catalog", "kind": "tce", "name": "far TCE", "tic": 995, "period": 4.5},
        {**base, "source": "catalog", "kind": "eb", "name": "far EB", "tic": 996, "period": 5.5},
    ]
    snap = tmp_path / "triage-snap"
    snap.mkdir()
    known = pd.concat([load_known(mask), pd.DataFrame(rows)], ignore_index=True)
    known[KNOWN_COLUMNS].to_parquet(snap / "known.parquet")
    (snap / "manifest.json").write_text("{}\n")
    return snap


def only_run(tmp_path, stage):
    (run,) = [p for p in (tmp_path / "data" / "runs").iterdir() if f"-{stage}-" in p.name]
    return run


def threshold_cli(tmp_path, targets, mask, null, *extra, kind="tce"):
    argv = ["triage", "threshold", "--null", str(null), "--targets", str(targets)]
    argv += ["--catalogs", str(triage_snapshot(tmp_path, mask, kind)), "--mask-catalogs", str(mask)]
    assert main([*argv, "--workers", "1", *extra]) == 0
    run = only_run(tmp_path, "threshold")
    return json.loads((run / "threshold.json").read_text()), run


def kept_signals(null):
    """The null's signals less star 11's leftovers of its catalogued 3.7 d object."""
    signals = pd.read_parquet(null / "signals.parquet")
    near = (signals["tic"] == 11) & signals["period"].map(lambda p: harmonic_of(p, 3.7))
    return signals[~near], int(near.sum())


def test_threshold_cli_drops_known_objects_and_traces_the_threshold_row(tmp_path, monkeypatch):
    targets, mask, null = null_run(tmp_path, monkeypatch)
    calls = []

    def outcome(star, eph):
        if star["tic"] == 12:
            return LeoOutcome(None, [], [], ["chi"]), "tests not judged: chi"
        return LeoOutcome("PC"), "planet candidate"

    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(outcome, calls))
    result, run = threshold_cli(tmp_path, targets, mask, null)
    kept, near = kept_signals(null)
    assert result["excluded"] == near >= 1
    # Star 11's only catalogued object is a TCE, so it stays in the null and can set the threshold.
    assert (result["excluded_host_stars"], result["excluded_host_signals"]) == (0, 0)
    dropped = pd.read_csv(run / "null_dropped.csv")
    assert list(dropped["reason"]) == ["harmonic"] * near
    assert set(dropped["detail"]) == {"tce-11"} and set(dropped["tic"]) == {11}
    assert result["evaluated"] == len(kept) == len(calls)
    assert len(pd.read_parquet(run / "null_leo.parquet")) == len(kept)
    # Every null signal survives here, so the highest one sets the threshold.
    assert result["threshold"] == kept["sde"].max() and result["floor_used"] is False
    top = result["top"]
    assert [r["sde"] for r in top] == sorted(kept["sde"], reverse=True)
    assert all("own_transits" in r for r in top)
    assert [(r["judged"], r["why_unjudged"]) for r in top if r["tic"] == 11] == [(True, "")] * 2
    row = result["threshold_row"]
    assert (row["tic"], row["rank"], row["sde"]) == (top[0]["tic"], top[0]["rank"], top[0]["sde"])
    assert result["threshold_row_unjudged"] is False
    # Star 12's unjudged peak is the lowest, below the judged pass that sets the threshold.
    noise = kept.loc[kept["tic"] == 12, "sde"]
    assert noise.max() < kept.loc[kept["tic"] == 11, "sde"].min()
    assert result["unjudged"] == len(noise) and result["unjudged_above_judged_pass"] == 0
    assert result["highest_judged_pass_sde"] == result["threshold"]
    assert result["why_no_judged_pass"] == ""
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
    # n_null_stars and the host counts come from the null's stars table, and the masks from this snapshot.
    assert provenance["inputs"]["null_stars"]["sha256"] == sha256_file(null / "stars.parquet")
    masks = {f"mask_{name}": sha256_file(path) for name, path in snapshot_inputs(mask).items()}
    assert {k: provenance["inputs"][k]["sha256"] for k in masks} == masks
    assert all_thresholds(tmp_path / "data" / "runs") == [result]


@pytest.mark.parametrize("kind", ["planet", "candidate", "community", "eb"])
def test_threshold_cli_drops_every_signal_on_a_star_that_hosts_a_catalogued_object(
    tmp_path, monkeypatch, kind
):
    targets, mask, null = null_run(tmp_path, monkeypatch)
    judged = []

    def outcome(star, eph):
        judged.append(int(star["tic"]))
        return LeoOutcome("PC"), "planet candidate"

    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(outcome))
    result, run = threshold_cli(tmp_path, targets, mask, null, kind=kind)
    signals = pd.read_parquet(null / "signals.parquet")
    host = signals[signals["tic"] == 11]
    noise = signals[signals["tic"] == 12]
    _, near = kept_signals(null)
    assert 1 <= near < len(host) and len(noise) >= 1
    # Star 11's leftovers at its object's period count once, under the harmonic exclusion; the rest of its
    # signals count as host signals.
    assert result["excluded"] == near
    assert (result["excluded_host_stars"], result["excluded_host_signals"]) == (
        1,
        len(host) - near,
    )
    assert sorted(judged) == [12] * len(noise) and result["evaluated"] == len(noise)
    # Only star 12 is left in the null; its noise peaks are below the floor.
    assert (result["n_null_stars"], result["n_sample"], result["expected_false_alarms"]) == (
        1,
        2,
        2.0,
    )
    assert result["floor_used"] is True and result["threshold_row"]["tic"] == 12
    dropped = pd.read_csv(run / "null_dropped.csv")
    assert list(dropped.columns) == ["tic", "rank", "period", "sde", "reason", "detail"]
    assert sorted(dropped["rank"]) == sorted(host["rank"]) and set(dropped["tic"]) == {11}
    assert dropped["reason"].value_counts().to_dict() == {
        "harmonic": near,
        "host": len(host) - near,
    }
    assert set(dropped.loc[dropped["reason"] == "harmonic", "detail"]) == {f"{kind}-11"}
    assert set(dropped.loc[dropped["reason"] == "host", "detail"]) == {kind}
    summary = json.loads((run / "provenance.json").read_text())["summary"]
    assert (summary["excluded_host_stars"], summary["excluded_host_signals"]) == (
        1,
        len(host) - near,
    )
    assert summary["n_null_stars"] == 1


def test_threshold_cli_counts_unjudged_signals_and_keeps_the_floor(tmp_path, monkeypatch, capsys):
    targets, mask, null = null_run(tmp_path, monkeypatch)

    def outcome(star, eph):
        if star["tic"] == 12:
            return None, "a stellar value LEO-Vetter needs is missing"
        return LeoOutcome("FA", ["chi"]), "FA: chi"

    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(outcome))
    result, _ = threshold_cli(tmp_path, targets, mask, null)
    kept, _ = kept_signals(null)
    noise = kept.loc[kept["tic"] == 12, "sde"]
    # Star 12's null peaks are noise, below the provisional continue_sde the null ran at.
    floor = SEARCH["search"]["continue_sde"]
    assert noise.max() < floor
    assert result["threshold"] == floor and result["floor_used"] is True
    row = result["threshold_row"]
    assert row["tic"] == 12 and row["sde"] == noise.max() and not row["judged"]
    assert row["why_unjudged"] == "a stellar value LEO-Vetter needs is missing"
    assert result["threshold_row_unjudged"] is True and result["unjudged"] == len(noise)
    # No signal passed with LEO-Vetter's judgement, so every candidate was evaluated.
    assert result["evaluated"] == len(kept) and result["highest_judged_pass_sde"] is None
    assert result["why_no_judged_pass"] == f"no judged pass among {len(kept)} evaluated"
    assert result["unjudged_above_judged_pass"] == len(noise)
    assert row["own_transits"]["built"] is False and result["threshold_row_own_transits"] is False
    # Under the floor, that row does not set the threshold.
    assert "the highest surviving null signal (TIC 12" in capsys.readouterr().out


def test_threshold_cli_goes_past_an_unjudged_pass_to_a_judged_one(tmp_path, monkeypatch):
    targets, mask, null = null_run(tmp_path, monkeypatch)
    kept, _ = kept_signals(null)
    first, second = kept.sort_values("sde", ascending=False).iloc[:2].to_dict("records")

    def outcome(star, eph):
        if eph.period == first["period"]:
            return LeoOutcome(None, [], [], ["chi"]), "tests not judged: chi"
        return LeoOutcome("PC"), "planet candidate"

    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(outcome))
    # One signal per batch, so the unjudged top signal fills a batch of its own.
    text = (ROOT / "criteria" / "triage-v1.toml").read_text()
    assert "batch = 200" in text
    triage = tmp_path / "triage.toml"
    triage.write_text(text.replace("batch = 200", "batch = 1"))
    result, _ = threshold_cli(tmp_path, targets, mask, null, "--criteria-triage", str(triage))
    assert result["evaluated"] == 2 < len(kept)
    assert result["threshold"] == first["sde"] and result["threshold_row_unjudged"] is True
    assert result["highest_judged_pass_sde"] == second["sde"] and result["why_no_judged_pass"] == ""
    assert result["unjudged"] == result["unjudged_above_judged_pass"] == 1


def null_provenance(tmp_path, monkeypatch, change=None):
    """A finished null that the checkout can reproduce, with `change` applied to its provenance, and the
    command line that computes its threshold."""
    monkeypatch.setenv("TESS_HUNT_DATA", str(tmp_path / "data"))
    monkeypatch.chdir(ROOT)
    mask = write_catalog_snapshot(tmp_path / "mask")
    targets = tmp_path / "t.parquet"
    pd.DataFrame({**SUN, "tic": [5, 6]}).to_parquet(targets)
    inputs = {
        name: {"sha256": sha256_file(mask / name)}
        for name in ("toi.csv", "ctoi.csv", "pscomppars.csv")
    }
    null = tmp_path / "null"
    null.mkdir()
    provenance = {
        "ended_at": "2026-10-13T00:00:00+00:00",
        "scramble": 1,
        "inputs": {**inputs, "targets": {"sha256": sha256_file(targets)}},
        "criteria": [{"file": "criteria/search-v2.toml", "sha256": SEARCH.sha256}],
        "search_code_sha256": search_code_sha256(ROOT),
    }
    if change:
        change(provenance)
    (null / "provenance.json").write_text(json.dumps(provenance))
    argv = ["triage", "threshold", "--null", str(null), "--targets", str(targets)]
    argv += ["--catalogs", str(triage_snapshot(tmp_path, mask)), "--mask-catalogs", str(mask)]
    return [*argv, "--workers", "1"]


def null_tables(tmp_path, signal_tics, lc_sha256, status=None, controls=()):
    """The null's signals and stars tables; every star is an ok sample star unless `status` or `controls`
    says otherwise."""
    row = {
        "rank": 1,
        "period": 7.0,
        "t0": 1330.0,
        "duration": 0.1,
        "depth": 0.001,
        "sde": 10.0,
        "control": False,
    }
    signals = pd.DataFrame([{**row, "tic": t} for t in signal_tics], columns=["tic", *row])
    signals.to_parquet(tmp_path / "null" / "signals.parquet")
    stars = [
        {
            "tic": t,
            "control": t in controls,
            "status": (status or {}).get(t, "ok"),
            "lc_sha256": s,
        }
        for t, s in lc_sha256.items()
    ]
    pd.DataFrame(stars).to_parquet(tmp_path / "null" / "stars.parquet")


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda p: p.update(scramble=None), "not a finished null"),
        (lambda p: p.update(ended_at=None), "not a finished null"),
        (lambda p: p["inputs"].pop("toi.csv"), "mask-catalogs"),
        (lambda p: p["inputs"].update(targets={"sha256": "x"}), "targets"),
        (lambda p: p["criteria"][0].update(sha256="x"), "criteria"),
        (lambda p: p.update(search_code_sha256="0" * 64), "search code"),
    ],
)
def test_threshold_cli_refuses_a_null_it_cannot_reproduce(tmp_path, monkeypatch, change, message):
    with pytest.raises(SystemExit, match=message):
        main(null_provenance(tmp_path, monkeypatch, change))
    assert not (tmp_path / "data" / "runs").exists()


def drop_eb_rows(tmp_path):
    known = pd.read_parquet(tmp_path / "triage-snap" / "known.parquet")
    known[known["kind"] != "eb"].to_parquet(tmp_path / "triage-snap" / "known.parquet")


@pytest.mark.parametrize(
    ("catalogs", "change", "message"),
    [
        # The v1 mask snapshot: TOIs, CTOIs and archive planets only, so no binary star is a host.
        ("mask", lambda tmp_path: None, "mask is not a v2 snapshot"),
        ("triage-snap", drop_eb_rows, "no rows of kind eb"),
    ],
)
def test_threshold_cli_refuses_catalogs_without_tce_or_binary_rows(
    tmp_path, monkeypatch, catalogs, change, message
):
    argv = null_provenance(tmp_path, monkeypatch)
    null_tables(tmp_path, [5], {5: "0" * 64})
    change(tmp_path)
    argv[argv.index("--catalogs") + 1] = str(tmp_path / catalogs)
    with pytest.raises(SystemExit, match=message):
        main(argv)
    assert not (tmp_path / "data" / "runs").exists()


def test_threshold_cli_refuses_a_null_that_leaves_no_signal(tmp_path, monkeypatch):
    argv = null_provenance(tmp_path, monkeypatch)
    null_tables(tmp_path, [], {})
    with pytest.raises(SystemExit, match="no null signal"):
        main(argv)
    assert not (tmp_path / "data" / "runs").exists()


def test_threshold_cli_refuses_light_curves_other_than_the_ones_the_null_searched(
    tmp_path, monkeypatch
):
    argv = null_provenance(tmp_path, monkeypatch)
    for tic in (5, 6, 7):
        save_star(tmp_path, monkeypatch, tic, sectors=(1,), seed=tic)
    lc = tmp_path / "data" / "lc"
    # Star 5 is as the null searched it; 6 was refetched since; 7 is gone.
    same = sha256_file(lc / "5.npz")
    null_tables(tmp_path, [5, 6, 7], {5: same, 6: "0" * 64, 7: sha256_file(lc / "7.npz")})
    (lc / "7.npz").unlink()
    with pytest.raises(SystemExit, match=r"2 null stars .*\[6, 7\]"):
        main(argv)
    assert not (tmp_path / "data" / "runs").exists()


def test_threshold_cli_counts_ok_sample_hosts_and_checks_only_candidates_light_curves(
    tmp_path, monkeypatch
):
    argv = null_provenance(tmp_path, monkeypatch)
    snap = tmp_path / "triage-snap" / "known.parquet"
    base = {"source": "catalog", "ra": 1.0, "dec": -70.0, "period": 11.0, "t0": 1330.0}
    hosts = {6: "candidate", 7: "eb", 8: "planet", 10: "community"}
    rows = [
        {**base, "kind": k, "name": f"{k}-{t}", "tic": t, "duration": 0.1, "depth_ppm": 1000.0}
        for t, k in hosts.items()
    ]
    known = pd.concat([pd.read_parquet(snap), pd.DataFrame(rows)], ignore_index=True)
    known[KNOWN_COLUMNS].to_parquet(snap)
    save_star(tmp_path, monkeypatch, 5, sectors=(1,), seed=5)
    # Star 6 is a host whose light curve changed since the null: the run must not refuse over a star whose
    # signals it does not judge. 7 is an ok host with no signal, 8 a host the null could not search, 10 a
    # control on a host star, and 9 an ok star with no signal and no catalogued object.
    null_tables(
        tmp_path,
        [5, 6],
        {
            5: sha256_file(tmp_path / "data" / "lc" / "5.npz"),
            6: "0" * 64,
            7: "0" * 64,
            8: None,
            9: "0" * 64,
            10: "0" * 64,
        },
        status={8: "no_light_curve"},
        controls=(10,),
    )
    judged = []

    def outcome(star, eph):
        judged.append(int(star["tic"]))
        return LeoOutcome("PC"), "planet candidate"

    monkeypatch.setattr(threshold_module, "leo_flux", fake_leo(outcome))
    assert main(argv) == 0
    run = only_run(tmp_path, "threshold")
    result = json.loads((run / "threshold.json").read_text())
    assert judged == [5]
    # The ok sample stars are 5, 6, 7 and 9; the hosts among them are 6 and 7.
    assert (result["excluded_host_stars"], result["excluded_host_signals"]) == (2, 1)
    assert (result["n_null_stars"], result["n_sample"], result["expected_false_alarms"]) == (
        2,
        2,
        1.0,
    )
    dropped = pd.read_csv(run / "null_dropped.csv")
    assert dropped[["tic", "reason", "detail"]].values.tolist() == [[6, "host", "candidate"]]
