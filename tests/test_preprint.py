import datetime as dt
import html
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import batman
import numpy as np
import pandas as pd
import pytest
import test_calls as tc
import test_dossier as td
import test_vetting as tv

from tess_hunt import calls, dossier, preprint, prereg, provenance, transit
from tess_hunt.catalogs import KNOWN_COLUMNS
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.provenance import sha256_file

NAME = td.NAME
REPO = Path(__file__).resolve().parents[1]
# A placeholder author line; the maintainer's own waits on his approval of its text (decision 0043).
AUTHOR = """\
given_names = "Vera"
family_names = "Placeholder"
affiliation = "Independent researcher"
orcid = "0000-0002-1825-0097"
repository = "https://example.org/tess-hunt"
"""
THRESHOLD_RUN = "20261014T000000Z-threshold-abc-1"
SAMPLE, NULL_STARS = 30195, 29343
# A triage row for a signal that passed every step, as triage's signals.csv carries it.
TRIAGED = {
    "novelty": "pass",
    "leo_flux": "pass",
    "leo_reason": "planet candidate at flux level",
    "pixels": "pass",
    "pixels_reason": 'centroid offset 10.9" within 15"',
    "shortlisted": True,
}
NULL_RUN = "20261013T000000Z-search-abc-0"
INJECT_RUN = "20261015T000000Z-benchmark-inject-abc-1"
PACKAGE = "20261112T000000Z-predictions-abc1234-0001"
DOI = "10.5281/zenodo.99999999"
# The preregistered test's result, as `vetting prereg` writes it for a season it judged.
PREREG = {
    "signal": {"name": NAME, "tic": 1},
    "package": PACKAGE,
    "result": "replicated",
    "status": "predicted",
    "predicted_sectors": [112, 113],
    "as_of": "2027-02-20",
    "judged_by": "2027-12-31",
    "fetched": "2027-02-14",
    "untestable_products": {},
    "depth": 0.0005,
    "err": 0.0001,
    "n": 412,
    "sigma": 5.0,
    "expected_snr": 4.8,
    "tension": 0.4,
}
# A record's files that hold Gaia DR3 data, as results/README.md lists them.
GAIA_FILES = [
    "checks.json",
    "checks-with-suspect.json",
    "neighbours.csv",
    "triceratops.json",
    "plots/centroids.png",
    "pixels.png",
    "dossier.md",
    "review.json",
    "review-scripts.tar.gz",
]
# Notes added beside two of the review's findings under decision 0037.
NOTES = """\
[[note]]
finding = "F2"
date = 2026-10-26
text = "The star is 12.4 arcsec away; the review rounds up."

[[note]]
finding = "F1"
date = 2026-10-27
text = "Sector 2 carries most of it."
"""
# Wording that would say a value lacks an uncertainty, which no sentence of the paper may (decision 0043), matched in
# lower case.
GAPS = r"\bomits?\b|no uncertainty|without the stellar-radius|carries no|\black|without an error"


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=test",
            "-c",
            "user.email=test@example.org",
            *args,
        ],
        check=True,
        capture_output=True,
    )


def commit(repo: Path) -> None:
    """Everything in `repo` committed, as the maintainer commits a published record."""
    if not (repo / ".git").is_dir():
        git(repo, "init", "-q")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "--allow-empty", "-m", "records")


def published_runs(repo: Path) -> None:
    """The search, threshold, injection-recovery and triage runs the vetting run's provenance leads to, published as
    results/ holds them."""
    results = repo / "results"
    threshold = {"file": "threshold.json", "run_id": THRESHOLD_RUN, "value": 20.24494315641701}
    search = results / "benchmarks" / tv.SEARCH_RUN
    search.mkdir(parents=True)
    criteria = [{"file": "criteria/search-v2.toml", "sha256": load_criteria(tv.SEARCH).sha256}]
    (search / "provenance.json").write_text(
        json.dumps(
            {
                "run_id": tv.SEARCH_RUN,
                "stage": "search",
                "criteria": criteria,
                "threshold": threshold,
                "summary": {"stars": SAMPLE},
            }
        )
    )
    (results / "benchmarks" / THRESHOLD_RUN).mkdir()
    (results / "benchmarks" / THRESHOLD_RUN / "threshold.json").write_text(
        json.dumps(
            {
                "threshold": threshold["value"],
                "null_run": NULL_RUN,
                "n_sample": SAMPLE,
                "n_null_stars": NULL_STARS,
                "expected_false_alarms": SAMPLE / NULL_STARS,
            }
        )
    )
    # An inject run at an earlier threshold is not the one the paper names.
    for run_id, used in (
        (INJECT_RUN, THRESHOLD_RUN),
        ("20261009T000000Z-benchmark-inject-abc-0", None),
    ):
        (results / "benchmarks" / run_id).mkdir()
        made = {
            "run_id": run_id,
            "stage": "benchmark-inject",
            "production": True,
            "summary": {"injections": 2000, "stars": 1000},
        }
        if used:
            made["threshold"] = {**threshold, "run_id": used}
        (results / "benchmarks" / run_id / "provenance.json").write_text(json.dumps(made))
    (results / "benchmarks" / INJECT_RUN / "completeness_snr.csv").write_text(
        'engine,bin,count,fraction\nbls30,"[20.0, 50.0)",290,0.686\n'
    )
    triage = results / "triage" / tv.TRIAGE_RUN
    triage.mkdir(parents=True)
    # Triage's row for each signal on the star: 1-1 shortlisted, rank 2 stopped at LEO-Vetter.
    pd.DataFrame(
        [
            {**TRIAGED, "tic": 1, "rank": 1, "sde": 31.4159},
            {
                **TRIAGED,
                "tic": 1,
                "rank": 2,
                "sde": 21.0,
                "leo_flux": "fail",
                "leo_reason": "FA: non_unique",
                "pixels": "inconclusive",
                "pixels_reason": "not run: novelty or the flux tests did not pass",
                "shortlisted": False,
            },
        ]
    ).to_csv(triage / "signals.csv", index=False)


def prepared(repo: Path, monkeypatch) -> None:
    """What `preprint run` reads beside the record: the published runs, the template, a placeholder author line and
    the claims file, all committed."""
    monkeypatch.setattr(preprint, "repo_root", lambda: repo)
    published_runs(repo)
    preprints = repo / "results" / "preprints"
    preprints.mkdir()
    shutil.copy(REPO / preprint.TEMPLATE, preprints)
    (preprints / "author.toml").write_text(AUTHOR)
    (repo / "results" / "claims.toml").write_text(
        f'["{NAME}"]\ndate = 2026-10-28\nrecord = "https://doi.org/10.5281/zenodo.23745923"\n'
    )
    commit(repo)


def held_out_passed(checks: dict) -> None:
    """The held-out check passed with each season predicted, as a pass needs; the fixture's light curve is too short
    for it to test any."""
    holdout = next(x for x in checks["checks"] if x["check"] == "holdout")
    holdout.update(outcome="pass", reason="2 held-out seasons predicted")
    for season in holdout["evidence"]["seasons"]:
        season.pop("reason", None)
        season["status"] = "predicted"


def published(tmp_path, monkeypatch, call: str = tc.PASSED) -> tuple[dict[str, Path], Path]:
    """1-1's record published from production runs with `call`, a pass by default, as
    `test_a_pass_the_record_supports_is_published` publishes it, in a repo of its own."""
    run, suspect = td.vetting_runs(tmp_path, monkeypatch)
    # Every check passed and the literature search was complete, as a pass needs.
    td.edit_json(run / "signals" / NAME / "checks.json", held_out_passed)
    complete = {**td.literature_record(run, monkeypatch), "outcome": "pass", "reason": "complete"}
    tric = td.made_run(
        tmp_path,
        "vetting-triceratops",
        run,
        {NAME: {"triceratops.json": td.triceratops_record(run), "probs.csv": "ID,prob\n1,0.98\n"}},
    )
    lit = td.made_run(tmp_path, "vetting-literature", run, {NAME: {"literature.json": complete}})
    runs = {
        "run": run,
        "suspect": suspect,
        "triceratops": tric,
        "literature": lit,
        "titles": td.titles_run(tmp_path, lit),
    }
    td.production(*runs.values())
    repo = td.results_repo(tmp_path, monkeypatch)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(tc.edit(call, "44926986-1", NAME))
    (signal / "review.json").write_text(json.dumps(td.REVIEW))
    assert main(td.publish_argv(runs, "run", "triceratops", "literature", "suspect", "titles")) == 0
    prepared(repo, monkeypatch)
    return runs, repo


def held_r2(tmp_path, monkeypatch) -> Path:
    """A passed M3 record, then a re-vet published as r2 with a held call."""
    _, repo = published(tmp_path, monkeypatch)
    later = td.revetted(tmp_path, monkeypatch, td.revet_run(tmp_path))
    td.called(repo / "results" / "vetting" / NAME / "r2")
    assert main(td.version_argv(later)) == 0
    commit(repo)
    return repo


def runs_made(tmp_path: Path) -> list[Path]:
    return sorted((tmp_path / "data" / "runs").glob("*-preprint-*"))


def paper(repo: Path) -> str:
    record = repo / "results" / "vetting" / NAME
    return preprint.render(record, preprint.load_author(repo / preprint.AUTHOR), repo)


@pytest.fixture
def no_pdf(monkeypatch):
    """`preprint run` without the optional PDF group: what it writes besides the PDF is checked wherever the suite
    runs."""
    monkeypatch.setattr(preprint, "_pdf_group", lambda: None)
    monkeypatch.setattr(
        preprint, "to_pdf", lambda text, assets, out, specimen: Path(out).write_bytes(b"%PDF-")
    )


def held(tmp_path, monkeypatch) -> Path:
    return published(tmp_path, monkeypatch, tc.HELD)[1]


def pass_problems_refuse(tmp_path, monkeypatch) -> Path:
    _, repo = published(tmp_path, monkeypatch)
    call = repo / "results" / "vetting" / NAME / "call.toml"
    answer = (
        '[answers]\nF2 = "TRICERATOPS weighed that star and the centroids sit on the target."\n'
    )
    call.write_text(tc.edit(call.read_text(), answer, ""))
    commit(repo)
    return repo


def uncommitted(tmp_path, monkeypatch) -> Path:
    _, repo = published(tmp_path, monkeypatch)
    # Still a pass that stands, but not as committed.
    call = repo / "results" / "vetting" / NAME / "call.toml"
    call.write_text(tc.edit(call.read_text(), "the one hold is answered", "the hold is answered"))
    return repo


def unreproduced(tmp_path, monkeypatch) -> Path:
    _, repo = published(tmp_path, monkeypatch)
    # A record whose density-prior summary its own light curve, criteria and seed don't give.
    td.edit_json(
        repo / "results" / "vetting" / NAME / "checks.json",
        lambda c: c["fit_prior"]["b"].update(median=0.31),
    )
    commit(repo)
    return repo


def unaccepted(tmp_path, monkeypatch) -> Path:
    _, repo = published(tmp_path, monkeypatch)
    td.edit_json(
        repo / "results" / "vetting" / NAME / "checks.json",
        lambda c: c["fit_prior"].update(acceptance=0.31),
    )
    commit(repo)
    return repo


@pytest.mark.parametrize(
    "case, message",
    [
        (held, f"{NAME}'s latest record, the M3 record, is held"),
        (held_r2, f"{NAME}'s latest record, r2, is held"),
        (pass_problems_refuse, "confirmed finding F2 has no answer"),
        (uncommitted, f"results/vetting/{NAME} has changes that are not committed"),
        (
            unreproduced,
            "the reproduced density-prior fit gives b median 0.3, not the record's 0.31",
        ),
        (
            unaccepted,
            "the reproduced density-prior fit gives acceptance 0.3, not the record's 0.31",
        ),
    ],
)
def test_preprint_refuses_unless_the_latest_version_is_a_standing_pass(
    tmp_path, monkeypatch, no_pdf, case, message
):
    case(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match=message):
        main(["preprint", "run", "--name", NAME])
    assert runs_made(tmp_path) == []


def test_the_reproduced_fit_reads_the_light_curve_vet_fitted(tmp_path, monkeypatch):
    # The fake fit ignores its light curve, so the summary check cannot see a wrong rebuild in the tests: the light
    # curve each density-prior fit receives is compared instead, with a catalogued signal masked and a timing-suspect
    # sector dropped.
    fake, seen = tv.fake_fit, []

    def recording(lc, eph, cfg, rho_prior=None, seed=None):
        if rho_prior is not None:
            seen.append(lc)
        return fake(lc, eph, cfg, rho_prior, seed)

    monkeypatch.setattr(tv, "fake_fit", recording)
    snapshot = tv.v2_snapshot(tmp_path / "catalogs")
    known = pd.read_parquet(snapshot / "known.parquet")
    ctoi = {
        "tic": 1,
        "ra": tv.CANDIDATE["ra"],
        "dec": tv.CANDIDATE["dec"],
        "depth_ppm": 900.0,
        "source": "CTOI",
        "kind": "candidate",
        "name": "CTOI-1.01",
        "period": 7.3,
        "t0": 1330.0,
        "duration": 0.1,
    }
    rows = pd.concat([known, pd.DataFrame([ctoi])[KNOWN_COLUMNS]], ignore_index=True)
    rows.to_parquet(snapshot / "known.parquet")
    run, _ = td.vetting_runs(tmp_path, monkeypatch, snapshot=snapshot)
    vetted = seen[0]
    record = tmp_path / "record"
    record.mkdir()
    shutil.copy(run / "signals" / NAME / "checks.json", record)
    shutil.copy(run / "provenance.json", record / "provenance-checks.json")
    checks = json.loads((record / "checks.json").read_text())
    assert [m["period"] for m in checks["masked"]] == [7.3] and checks["dropped_suspect"] == [64]
    seen.clear()
    preprint.reproduce(record)
    [rebuilt] = seen
    for column in ("time", "flux", "flux_err"):
        assert np.array_equal(getattr(rebuilt, column), getattr(vetted, column)), column


def test_every_number_comes_from_the_record(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    found = preprint.values(record, preprint.load_author(repo / preprint.AUTHOR), repo)
    checks = json.loads((record / "checks.json").read_text())
    star, prior = checks["star"], checks["fit_prior"]
    eph, rp = prior["ephemeris"], prior["rp_rearth"]
    tric = json.loads((record / "triceratops.json").read_text())["evidence"]
    made = json.loads((record / "provenance-checks.json").read_text())
    # The bars TRICERATOPS was judged against, from the criteria its run recorded.
    bars = tomllib.loads((REPO / "criteria" / "vet-v3.toml").read_text())["triceratops"]
    review = calls.load_review(record / "review.json")
    # The sample and the held-out check as the criteria files the runs recorded give them.
    search = tomllib.loads(tv.SEARCH.read_text())
    sample, holdout = search["sample"], tomllib.loads(tv.VET3.read_text())["holdout"]

    def spread(value: dict, fmt: str = ".2f") -> str:
        """A median with its percentile offsets, one ± when they agree as printed (AAS)."""
        plus, minus = f"{value['plus']:{fmt}}", f"{value['minus']:{fmt}}"
        median = f"{value['median']:{fmt}}"
        return (
            f"{median} ± {plus}"
            if plus == minus
            else f'{median}<span class="pm"><sup>+{plus}</sup><sub>−{minus}</sub></span>'
        )

    radius = {
        "median": rp["median"],
        "plus": rp["p84"] - rp["median"],
        "minus": rp["median"] - rp["p16"],
    }
    # The depth, the duration and the radius come from the reproduced density-prior posterior. The duration's median
    # is the one the record keeps, and each depth is the model's at mid-transit with no exposure smearing. The fixture's
    # star has no TIC error on its radius, so Rp's percentiles are the record's own.
    posterior = preprint.reproduce(record)
    assert np.median(posterior["t14_days"]) == checks["window_duration"]["days"]
    t0, period, rp_rs, b, log_rho, q1, q2 = posterior["samples"][0]
    u1, u2 = 2 * np.sqrt(q1) * q2, np.sqrt(q1) * (1 - 2 * q2)
    a_rs = transit.a_rs_from_density(10**log_rho, period)
    unsmeared = batman.TransitParams()
    unsmeared.t0, unsmeared.per, unsmeared.rp, unsmeared.a = t0, period, rp_rs, a_rs
    unsmeared.inc, unsmeared.ecc, unsmeared.w = np.degrees(np.arccos(b / a_rs)), 0.0, 90.0
    unsmeared.u, unsmeared.limb_dark = [u1, u2], "quadratic"
    model = batman.TransitModel(unsmeared, np.array([t0]))
    assert posterior["depth"][0] == pytest.approx(1 - model.light_curve(unsmeared)[0], rel=1e-12)
    assert np.percentile(posterior["rp_rearth"], [16, 50, 84]).tolist() == [
        rp["p16"],
        rp["median"],
        rp["p84"],
    ]

    def percentiles(values) -> dict:
        p16, median, p84 = np.percentile(values, [16, 50, 84])
        return {"median": median, "minus": median - p16, "plus": p84 - median}

    expected = {
        "tic": str(checks["tic"]),
        "tmag": f"{star['tmag']:.2f}",
        "teff": f"{star['teff']:.0f}",
        "radius_sun": f"{star['rad']:.2f}",
        "radius_error": " The TIC gives no error for the star's radius.",
        # Value ± error in the value's own unit: the posterior sd in days, not seconds or minutes.
        "period_pm": f"{eph['period']['median']:.6f} ± {eph['period']['sd']:.6f}",
        "t0_pm": f"{eph['t0']['median']:.4f} ± {eph['t0']['sd']:.4f}",
        "duration_pm": spread(percentiles(posterior["t14_days"] * 24)),
        "depth_pm": spread(percentiles(posterior["depth"] * 1e6), ".0f"),
        "rp_pm": spread(radius),
        "rp_from": "",
        "rp_rs": spread(prior["rp_rs"], ".4f"),
        "b": spread(prior["b"]),
        "a_rs": spread(prior["a_rs"]),
        "fpp": f"{tric['fpp_mean']:.3g}",
        "nfpp": f"{tric['nfpp_mean']:.3g}",
        "fpp_pm": preprint._mean_sd(tric["fpp_mean"], tric["fpp_sd"], len(tric["fpp"])),
        "nfpp_pm": preprint._mean_sd(tric["nfpp_mean"], tric["nfpp_sd"], len(tric["fpp"])),
        "fpp_pass": f"{bars['fpp_pass']:g}",
        "nfpp_pass": f"{bars['nfpp_pass']:g}",
        "tric_runs": str(len(tric["fpp"])),
        "tric_times": "three times",
        "n_confirmed": str(len(calls.confirmed(review))),
        "vetting_run": made["run_id"],
        "commit": made["git"]["commit"],
        "search_run": tv.SEARCH_RUN,
        # The triage run's row for the signal, and the threshold the search ran at.
        "sde": "31.42",
        "threshold": "20.24",
        "threshold_run": THRESHOLD_RUN,
        "null_run": NULL_RUN,
        "false_alarms": "1.03",
        "inject_run": INJECT_RUN,
        "injections": "2000",
        "inject_stars": "1000",
        # Dates in prose and five-digit counts as AAS prints them.
        "claim_date": "2026 October 28",
        "call_date": "2026 October 28",
        "sample_stars": f"{SAMPLE:,}",
        "n_sample": f"{SAMPLE:,}",
        "n_null": f"{NULL_STARS:,}",
        "period_min": f"{search['search']['period_min_days']:g}",
        "period_max": f"{search['search']['period_max_days']:g}",
        "teff_min": f"{sample['teff_min']:g}",
        "tmag_max": f"{sample['tmag_max']:g}",
        "min_sectors": preprint._spell(sample["min_sectors"]),
        "recent_min": str(sample["recent_sector_min"]),
        "triage_run": tv.TRIAGE_RUN,
        "season_gap_days": f"{holdout['season_gap_days']:g}",
        "min_sigma": f"{holdout['min_sigma']:g}",
        "max_tension": f"{holdout['max_depth_tension']:g}",
        "max_offset": f"{checks['pixels']['max_offset_arcsec']:g}",
    }
    assert {key: found[key] for key in expected} == expected
    assert found["fates"].startswith("Of the review's three findings, ")
    text = paper(repo)
    for key in (
        "period_pm",
        "t0_pm",
        "duration_pm",
        "depth_pm",
        "fpp_pm",
        "sde",
        "threshold",
        "inject_run",
        "commit",
        "rp_rs",
        "rp_pm",
    ):
        assert expected[key] in text
    # One depth and one duration: the search's box values appear once, in Section 4, named as the box's.
    eph = checks["ephemeris"]
    box_duration, box_depth = f"{eph['duration'] * 24:.2f} h", f"{eph['depth'] * 1e6:.0f} ppm"
    assert (found["box_duration_h"], found["box_depth_ppm"]) == (box_duration[:-2], box_depth[:-4])
    detection = " ".join(td.section(text, "Detection").split())
    assert f"with a box duration of {box_duration} and a box depth of {box_depth}." in detection
    assert (
        "The light-curve checks and the figures use the search's box duration, and the neighbour check and "
        "TRICERATOPS use its box depth." in detection
    )
    flat = " ".join(text.split())
    assert flat.count(box_duration) == 1 and flat.count(box_depth) == 1
    # Without a TIC error on the star's radius, Section 3 says so once, and Table 1's note gives Rp from the radius.
    assert text.count("The TIC gives no error for the star's radius.") == 1
    assert "times the TIC radius (Section 3)." in text
    # With the TIC's errors, Section 3 gives them, and Rp takes the radius's error through a draw per sample, from a
    # seed sequence of the criteria's seed and 1, apart from the fit's walker starts, so each render gives the same Rp.
    td.edit_json(record / "checks.json", lambda c: c["star"].update(e_rad=0.05, e_teff=120.0))
    drawn = preprint.reproduce(record)
    found = preprint.values(
        record, preprint.load_author(repo / preprint.AUTHOR), repo, posterior=drawn
    )
    assert found["radius_sun"] == f"{star['rad']:.2f} ± 0.05"
    assert found["teff"] == f"{star['teff']:.0f} ± 120"
    assert found["radius_error"] == ""
    seed = tomllib.loads(tv.VET3.read_text())["fit"]["seed"]
    radii = np.random.default_rng([seed, 1]).normal(star["rad"], 0.05, len(drawn["samples"]))
    assert np.array_equal(drawn["rad_rsun"], radii)
    rp_rs = drawn["samples"][:, preprint.NAMES.index("rp_rs")]
    assert np.array_equal(drawn["rp_rearth"], rp_rs * radii * preprint.R_EARTH_PER_R_SUN)
    assert np.array_equal(preprint.reproduce(record)["rp_rearth"], drawn["rp_rearth"])
    assert found["rp_pm"] == spread(percentiles(drawn["rp_rearth"]))
    assert found["rp_pm"] != expected["rp_pm"]
    text = paper(repo)
    host = " ".join(td.section(text, "Host Star").split())
    assert f"a radius of {star['rad']:.2f} ± 0.05 R⊙ in the TESS" in host
    assert not re.search(f"{GAPS}|no error", " ".join(text.split()).lower())
    assert (
        "times the TIC radius, drawn for each sample from its value and error (Section 3)." in text
    )
    # A value the record does not hold raises instead of rendering.
    td.edit_json(record / "checks.json", lambda c: c["fit_prior"].update(rp_rearth=None))
    assert "rp_pm" not in preprint.values(
        record, preprint.load_author(repo / preprint.AUTHOR), repo
    )
    with pytest.raises(KeyError, match="rp_pm"):
        paper(repo)


def test_numbers_read_as_aas_prints_them():
    # Percentile offsets that agree as printed collapse to ±; others are a superscript and a subscript with a minus
    # sign, not a hyphen.
    assert (
        preprint._spread({"median": 0.04, "plus": 0.0012, "minus": 0.0012}, ".4f")
        == "0.0400 ± 0.0012"
    )
    assert (
        preprint._spread({"median": 11.85, "plus": 0.37, "minus": 0.35}, ".2f")
        == '11.85<span class="pm"><sup>+0.37</sup><sub>−0.35</sub></span>'
    )
    assert preprint._spread({"median": -0.5, "plus": 0.1, "minus": 0.1}, ".2f") == "−0.50 ± 0.10"
    # A mean over TRICERATOPS's runs to its standard deviation's first significant figure, two when it is a 1; one run
    # gives the mean alone; a tiny value goes to a power of ten.
    assert preprint._mean_sd(0.0587, 0.0011, 10) == "0.0587 ± 0.0011"
    assert preprint._mean_sd(0.012, 0.001, 3) == "0.0120 ± 0.0010"
    assert preprint._mean_sd(0.0004, 0.0002, 3) == "0.0004 ± 0.0002"
    assert preprint._mean_sd(0.0123, 0.0, 1) == "0.0123"
    assert preprint._mean_sd(2.02e-5, 1.48e-5, 3) == "(2.0 ± 1.5) × 10<sup>−5</sup>"
    # Five or more digits take a separator; four don't; nine and under are words.
    assert [preprint._spell(n) for n in (4, 2000, 30195)] == ["four", "2000", "30,195"]
    assert preprint._date("2027-01-20") == "2027 January 20"


def test_the_paper_says_candidate_not_planet(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    assert text.startswith("# A 5.0-day Transiting Planet Candidate around TIC 1\n")
    summary = " ".join(td.section(text, "Abstract").split())
    assert "We report a transiting planet candidate around TIC 1" in summary
    # The search found the signal; the fit, not the search, gives its numbers.
    assert (
        "We searched public TESS light curves and found a periodic transit signal. A transit-model fit gives a period "
        "of " in summary
    )
    assert re.search(
        r"a depth at mid-transit of .+? ppm, a total duration of .+? h and, with the stellar radius from the TESS "
        r"Input Catalog, a radius of .+? R⊕ for the transiting body\.",
        summary,
    )
    # The result with its errors, the star's TIC values, and what Table 2 shows.
    assert " ± " in summary and "R⊕" in summary and "R⊙ in the TESS Input Catalog" in summary
    assert "Every vetting check passed." in summary
    assert "TRICERATOPS gives a mean false-positive probability of" in summary
    assert (
        "The TESS light curves cannot measure the transiting body's mass, and they cannot exclude every nearby star "
        "as the source of the transit." in summary
    )
    assert "**Keywords:** Exoplanets (498); Transit photometry (1709);" in summary
    # Who makes the call and its outcomes are said in Section 2, not the Abstract.
    works = " ".join(td.section(text, "The tess-hunt Search and Vetting").split())
    assert (
        "The call is our decision on the signal: passed, held pending further evidence, or killed."
        in works
    )
    assert 'The decision records call the author "the maintainer".' in works
    assert "maintainer" not in summary
    # Only a record holding a preregistered result says so here.
    assert "deposited a prediction" not in summary
    # It is the Zenodo description too, where no other section exists.
    assert "The tess-hunt Search and Vetting" not in summary
    assert "we answered every finding that its refuters did not disprove" in summary
    for claim in ("confirmed", "discovered a planet", "validated"):
        assert claim not in summary.lower()
    # The body says "we"; "the maintainer" is named once, for a reader following a decision record.
    assert " ".join(text.split()).count("the maintainer") == 1
    # Every value carries its error, and no sentence says one lacks it: the TIC's missing radius error is said once, in
    # Section 3, as a fact of the catalogue.
    conclusions = " ".join(td.section(text, "Conclusions").split())
    assert "R⊕. We passed the signal" in conclusions
    assert not re.search(GAPS, " ".join(text.split()).lower())
    # A paper with no preregistered test still says that we passed the signal, and when.
    assert not (repo / "results" / "vetting" / NAME / "prereg.json").exists()
    vetted = " ".join(td.section(text, "Vetting").split())
    assert (
        "We passed the signal on 2026 October 28, and our call answers each upheld finding."
        in vetted
    )
    assert "We passed the signal on 2026 October 28, and TRICERATOPS gives it" in conclusions


def test_a_note_0037_added_sits_under_the_quoted_finding(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    (record / "review-notes.toml").write_text(NOTES)
    commit(repo)
    written = paper(repo)
    text = td.section(written, "Discussion")
    notes = td.section(written, "Appendix C. Refuted Findings and Notes")
    note = "    - **Note ({}):** {}"
    f2 = note.format("2026 October 26", "The star is 12.4 arcsec away; the review rounds up.")
    f1 = note.format("2026 October 27", "Sector 2 carries most of it.")
    # Under the upheld finding, after its quoted claim and the call's answer, which does not reply to it.
    assert (
        "- F2, on whether the signal is on the star. Rated hold; neither of its two refuters disproved it.\n"
        '    - Finding: "a star 12.5 arcsec away could host the dip"\n'
        '    - Answer: "TRICERATOPS weighed that star and the centroids sit on the target."\n'
        f"{f2}"
    ) in text
    # A note beside a finding rated note, which sits in the appendix with the refuted ones.
    assert (
        "- F1, on whether the signal is real and new. Rated note.\n"
        f'    - Finding: "one sector carries most of the depth"\n{f1}'
    ) in notes
    # The paragraph above the findings says once what a note is, and the appendix points back to it.
    assert (
        "quoted text is reproduced without edits. Where we later found a mistake in a quote, a dated note follows "
        "it. The note is not part of the review or the call (DR 0037)." in " ".join(text.split())
    )
    assert "The rules of Section 8 on quoted text and dated notes apply here too." in notes
    # Each note's text is the one the dossier shows beside the same finding.
    review = calls.load_review(record / "review.json")
    quoted = dossier.render_review(review, calls.load_notes(record / "review-notes.toml", review))
    for text_ in (
        "The star is 12.4 arcsec away; the review rounds up.",
        "Sector 2 carries most of it.",
    ):
        assert text_ in quoted


def test_a_confirmed_finding_no_refuter_ran_on_says_so(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    untested = {
        "id": "F4",
        "lens": "planet",
        "rating": "hold",
        "claim": "the depth is shallow for the fitted radius",
        "evidence": "fit_prior",
        "refuters": [],
    }
    review = {**td.REVIEW, "findings": [*td.REVIEW["findings"], untested]}
    (record / "review.json").write_text(json.dumps(review))
    call = record / "call.toml"
    call.write_text(
        tc.edit(call.read_text(), "[answers]\n", '[answers]\nF4 = "The radius fits."\n')
    )
    text = paper(repo)
    left = td.section(text, "Discussion")
    appendix = td.section(text, "Appendix C. Refuted Findings and Notes")
    # Upheld only because nothing refuted it, as the dossier marks it; F2's refuters ran.
    assert (
        "- F4, on whether the signal is a planet. Rated hold; no refuter tested it, so it counts as upheld.\n"
        '    - Finding: "the depth'
    ) in left
    assert (
        "- F2, on whether the signal is on the star. Rated hold; neither of its two refuters"
        in left
    )
    # The refuted kill is quoted with each refuter's verdict, in the appendix.
    assert (
        "- F3, on whether the signal is a planet. Rated kill; one of its two refuters disproved it.\n"
        '    - Finding: "the secondary at phase 0.76 is an eccentric eclipse"\n'
        '    - Refuter 1 did not disprove it: "reproduced from the run"\n'
        '    - Refuter 2 disproved it: "the offset is the PSF\'s, not a shift"'
    ) in appendix
    assert "- F3," not in left
    vetted = " ".join(td.section(text, "Vetting").split())
    assert (
        "Of the review's four findings, two rated hold were upheld, one rated kill was refuted, and one was a "
        "note." in vetted
    )
    # The flagged paper by its title and id, from the literature search's hits.
    assert (
        'The review flagged one paper for us to read, "The TESS-Keck Survey. XVI. Mass Measurements for '
        '12 Planets in Eight Systems" (arXiv 2306.16587). The call records that we read it.'
        in vetted
    )
    # A review with no refuted finding says so.
    review["findings"] = [f for f in review["findings"] if f["id"] != "F3"]
    (record / "review.json").write_text(json.dumps(review))
    assert "No refuter disproved any finding." in paper(repo)


def test_a_versions_paper_names_its_records(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch, tc.HELD)
    later = td.revetted(tmp_path, monkeypatch, td.revet_run(tmp_path))
    r2 = td.called(repo / "results" / "vetting" / NAME / "r2")
    assert main(td.version_argv(later)) == 0
    # r2 called passed, to render it; the bar is passed_record's, tested above.
    (r2 / "call.toml").write_text(tc.edit(tc.PASSED, "44926986-1", NAME))
    commit(repo)
    text = preprint.render(r2, preprint.load_author(repo / preprint.AUTHOR), repo)
    vetted = " ".join(td.section(text, "Vetting").split())
    assert vetted.startswith(
        "The signal has two records. We held the signal at its first record on 2026 October 28, giving the reason "
        '"The public data can\'t tell the two stars apart." The call named the evidence that would decide the signal: '
        '"High-resolution imaging of the 12.5 arcsec companion." This paper reports the second record, version r2, a '
        "new vetting on a light curve with Sector 65 (SPOC) added."
    )
    m3 = json.loads((r2.parent / "provenance-checks.json").read_text())
    made = json.loads((r2 / "provenance-checks.json").read_text())
    available = " ".join(td.section(text, "Data Availability").split())
    assert (
        f"used commit {made['git']['commit']}, and the commit that generated this paper"
        in available
    )
    assert "the light curve that was the input to the vetting run of version r2" in available
    runs = td.section(text, "Appendix A. Runs")
    assert (
        f'| Vetting, the first record | <span class="id">{m3["run_id"]}</span> | `dataset/vetting/{NAME}/` |'
        in runs
    )
    assert (
        f'| Vetting, version r2 | <span class="id">{made["run_id"]}</span> | `dataset/vetting/{NAME}/r2/` |'
        in runs
    )
    assert (
        "A vetting run's provenance is the `provenance-checks.json` in its record's directory."
        in " ".join(runs.split())
    )
    # The sectors tess-point gave are r2's vetting run's, said after the record's own history.
    held_out = " ".join(td.section(text, "Held-Out Seasons and the Preregistered Test").split())
    assert (
        f"As of the vetting run of version r2 ({preprint._date(made['started_at'])}), tess-point"
        in held_out
    )
    files = td.section(text, "Appendix B. Dataset Files")
    assert (
        f"The first record is in `dataset/vetting/{NAME}/` and version r2 in its `r2/` subdirectory."
        in " ".join(files.split())
    )
    assert "is the input to the vetting run of version r2." in " ".join(files.split())
    # The dataset's guide lists a new vetting's merge record.
    assert "| `merge.json` | what a new vetting's light curve changed |" in files
    # A third version counts three records and says what the second's call gave.
    r3 = r2.parent / "r3"
    shutil.copytree(r2, r3)
    history = preprint._history(r3)
    assert history.startswith(
        "The signal has three records. We held the signal at its first record on 2026 October 28,"
    )
    assert (
        "We passed the signal at version r2, a new vetting on a light curve with Sector 65 (SPOC) added, on "
        in history
    )
    assert history.endswith(
        "This paper reports the third record, version r3, a new vetting on a light curve with Sector 65 (SPOC) "
        "added."
    )
    assert preprint._records(NAME, 3) == (
        f"The first record is in `dataset/vetting/{NAME}/`, and versions r2 and r3 are in its `r2/` and `r3/` "
        "subdirectories."
    )
    assert preprint._records(NAME, None) == f"The record is in `dataset/vetting/{NAME}/`."
    shutil.rmtree(r3)
    # A record with no version before it says it is the only one.
    single = tmp_path / "single"
    single.mkdir()
    one = paper(published(single, monkeypatch)[1])
    assert "This paper reports the signal's only record." in one
    assert "`merge.json`" not in one


def test_the_paper_names_the_claim_date_and_any_0042_listing(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    public = " ".join(td.section(paper(repo), "Vetting").split())
    assert (
        "We first made the signal public on 2026 October 28, in the record "
        '<span class="id">doi:10.5281/zenodo.23745923</span>.' in public
    )
    assert "ExoFOP lists a signal" not in public

    # A pass that stands because decision 0042 excepts a TOI listed after the claim.
    other = tmp_path / "claimed"
    other.mkdir()
    runs, repo, argv = td.claimed_pass(other, monkeypatch)
    # Decision 0042 also excepts a later listing on the star at another period, which novelty never matched.
    later = {**td.later_listing(name="TOI-7001.02", first="2027-04-01"), "period": 12.1}
    excepted = [td.later_listing(), later]
    record = td.claims_record(runs["run"], runs["literature"], excepted, td.RERUN)
    runs["claims"] = td.claims_run(other, runs["run"], runs["literature"], record, tag="b")
    td.production(runs["claims"])
    assert main([*argv, *td.flags(runs, "claims")]) == 0
    prepared(repo, monkeypatch)
    text = paper(repo)
    public = " ".join(td.section(text, "Vetting").split())
    assert "We first made the signal public on 2026 October 28" in public
    assert (
        "ExoFOP lists a signal at this period on the star as TOI-7001.01 (period 5 d, disposition PC). ExoFOP first "
        "listed it on 2027 March 1, after we made the signal public." in public
    )
    assert (
        "ExoFOP also lists TOI-7001.02 on the star (period 12.1 d, disposition PC). ExoFOP first listed it on "
        "2027 April 1, after we made the signal public. The vetting record does not say who submitted them."
        in public
    )
    assert "as TOI-7001.02" not in public
    assert "Under DR 0042" in public
    # The star's ExoFOP page is in Data Availability, out of the running text.
    assert "https://" not in public
    assert (
        "ExoFOP's page for the star is https://exofop.ipac.caltech.edu/tess/target.php?id=1."
        in " ".join(td.section(text, "Data Availability").split())
    )
    # The rule is stated once, and no motive is guessed at.
    assert " ".join(text.split()).count("is therefore not counted as known") == 1
    assert "prompted" not in text
    # Table 2 shows the novelty check's fail with a footnote, and the text says it failed on the snapshot and passed
    # without the later listings.
    assert "| Known objects at the period (`novelty`) | fail<sup>a</sup> |" in public
    assert (
        "<sup>a</sup> ExoFOP first listed TOI-7001.01 and TOI-7001.02 after we made the signal public, so DR 0042 "
        "sets them aside. See Section 6.4." in public
    )
    # The paragraph after the listings sets them aside without saying again when ExoFOP listed them.
    [novelty] = [
        p
        for p in td.section(text, "Vetting").split("\n\n")
        if p.startswith("Against the catalogues")
    ]
    assert novelty == (
        "Against the catalogues used in the vetting run, the novelty check fails because TOI-7001.01 matches the "
        "signal. With TOI-7001.01 and TOI-7001.02 set aside under DR 0042, no other catalogued object matches the "
        "signal, and the novelty check passes."
    )
    # The Abstract says what Table 2 shows.
    summary = " ".join(td.section(text, "Abstract").split())
    assert (
        "Every vetting check passed except the comparison with known objects, which matched TOI-7001.01. ExoFOP "
        "listed that TOI only after we made the signal public, so it does not count as a known object."
        in summary
    )
    # Only the listing at the signal's period is named against ExoFOP's rows at the period.
    assert "Apart from TOI-7001.01, none of ExoFOP's" in public
    assert "TOI-7001.02, which" not in public
    # The claim the exception rests on must be the committed one.
    claims = repo / "results" / "claims.toml"
    claims.write_text(claims.read_text().replace("2026-10-28", "2026-10-29"))
    with pytest.raises(SystemExit, match="claims.json"):
        paper(repo)


def test_the_paper_gives_the_ephemeris_with_uncertainties(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    eph = json.loads((record / "checks.json").read_text())["fit_prior"]["ephemeris"]
    text = td.section(paper(repo), "Transit Parameters")
    period, t0 = eph["period"], eph["t0"]
    # Table 1 is numbered and captioned above, with its units in the parameter column and its note below.
    assert "**Table 1.** Transit parameters of TIC 1 from the density-prior fit" in text
    assert f"| Period, <i>P</i> (d) | {period['median']:.6f} ± {period['sd']:.6f} |" in text
    assert (
        f"| Mid-transit time, <i>T</i><sub>0</sub> (BTJD) | {t0['median']:.4f} ± {t0['sd']:.4f} |"
        in text
    )
    note = " ".join(text.split("*Note.*")[1].split("\n\n")[0].split())
    assert note.startswith(
        "The <i>P</i> and <i>T</i><sub>0</sub> uncertainties are posterior standard deviations. For the other "
        "parameters, the value is the posterior median with its differences from the 16th and 84th percentiles."
    )
    # The depth is the model's, a property of the transit, so the note names no cadence's exposure.
    assert (
        "<i>T</i><sub>14</sub> runs from first to fourth contact, and the depth is the transit model's at "
        "mid-transit. Both come from the density-prior fit's posterior, which this paper's run reproduced from the "
        "record's light curve, criteria and seed and checked against the record's summary of the fit."
        in note
    )
    assert "exposure" not in note
    assert "(Section 3). BTJD = BJD<sub>TDB</sub> − 2457000." in note
    # No sentence says a value of Table 1 lacks an uncertainty.
    assert "no uncertainty" not in text and "BLS" not in text
    assert text.index("Table 1 gives") < text.index("**Table 1.**")


def test_credits_and_disclosure_are_present(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    written = paper(repo)
    text = " ".join(written.split())
    assert f"This paper {prereg.TESS_CREDIT}" in text
    # The fixture's light curve is SPOC's in Sectors 1, 2 and 64, cited by its paper and its MAST DOI entry, with
    # PDCSAP's papers.
    name, doi, papers = prereg.CREDITED["SPOC 2-min"]
    assert (
        f"{name} from Sectors 1, 2 and 64 (Jenkins et al. 2016; TESS Team 2021), with PDCSAP flux (Smith et al. "
        "2012; Stumpe et al. 2012; Stumpe et al. 2014)" in text
    )
    references = td.section(written, "References")
    assert f'<span class="id">doi: {doi}</span></p>' in references
    # Each product paper prereg.CREDITED names is the one REFERENCES gives, by journal, volume and page, for every
    # product, and the paper prints the SPOC one.
    for product, (_, product_doi, product_papers) in prereg.CREDITED.items():
        entries = [preprint.REFERENCES[k] for k in preprint.PRODUCT_REFERENCES[product]]
        assert any(f"doi: {product_doi}" in entry for _, entry in entries), product
        for who, where in product_papers:
            journal, volume, page = re.match(r"(.*) (\S+), (\S+)$", where).groups()
            assert any(
                cite.startswith(who) and f"{journal}, {volume}, {page}" in entry
                for cite, entry in entries
            ), (product, who)
    for who, where in papers:
        journal, volume, page = re.match(r"(.*) (\S+), (\S+)$", where).groups()
        assert who in text and f"{journal}, {volume}, {page}" in references
    # QLP's light curves are not the fixture's, so their credit, data entry and later papers stay out.
    assert prereg.QLP_CREDIT not in text and "Quick-Look Pipeline" not in references
    assert "Huang et al. 2020b" not in text
    assert "Stassun et al. 2019" in text and "Paegert et al. 2021" in text
    assert "European Space Agency (ESA) mission Gaia" in text
    # The disclosure, word for word and alone under its heading; the Facilities and Software lines close the
    # Acknowledgements, and the back matter is in the order AAS sets it.
    assert td.section(written, "Use of LLMs").strip() == (
        "tess-hunt's code and this paper's text were written with LLM assistance. Adversarial reviews this paper "
        "quotes were\nassisted by LLMs. More information on models is available on GitHub."
    )
    acknowledgements = td.section(written, "Acknowledgements")
    assert '<p class="names"><b>Facilities:</b> TESS, Gaia</p>' in acknowledgements
    assert '<p class="names"><b>Software:</b> Astrocut (Brasseur et al. 2019),' in acknowledgements
    # transit-diffImage asks for no citation, so Data Availability gives its author, URL and pinned commit.
    assert (
        "The pixel check's transit-diffImage, by S. Bryson, is at https://github.com/stevepur/transit-diffImage at "
        "commit 2b13199." in " ".join(td.section(written, "Data Availability").split())
    )
    order = [
        "## Conclusions",
        "## Acknowledgements",
        "<b>Facilities:</b>",
        "<b>Software:</b>",
        "## Use of LLMs",
        "## Data Availability",
        "## References",
        "## Appendix A. Runs",
    ]
    assert [written.index(h) for h in order] == sorted(written.index(h) for h in order)
    # The review and its refuters are described as the disclosure describes them, and no model is named.
    assert (
        f"An LLM-assisted adversarial review, dated {preprint._date(td.REVIEW['date'])}, looked for reasons"
        in text
    )
    assert "Refuters are separate LLM-assisted checks, each asked to disprove one finding." in text
    assert td.REVIEW["model"] not in text
    record = repo / "results" / "vetting" / NAME
    found = preprint.values(record, preprint.load_author(repo / preprint.AUTHOR), repo)
    assert td.REVIEW["model"] not in found.values()
    # Gaia is credited, and named a facility, when the dataset holds Gaia data.
    monkeypatch.setattr(preprint, "GAIA_FILES", set())
    without = paper(repo)
    assert "European Space Agency (ESA) mission Gaia" not in without
    assert '<p class="names"><b>Facilities:</b> TESS</p>' in without


def test_the_dataset_lets_a_reader_recompute(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    signal = repo / "results" / "vetting" / NAME
    # A second-list row's centroid plot and the review's scripts, as some records hold them.
    (signal / "pixels.png").write_bytes(b"\x89PNG")
    (signal / "review-scripts.tar.gz").write_bytes(b"\x1f\x8b")
    (repo / ".gitignore").write_text(".DS_Store\n")
    commit(repo)
    # A file git ignores is no part of the record.
    (signal / ".DS_Store").write_bytes(b"Finder")
    assert main(["preprint", "run", "--name", NAME]) == 0
    [run] = runs_made(tmp_path)
    expected = {
        f"dataset/vetting/{NAME}/{path.relative_to(signal)}": sha256_file(path)
        for path in signal.rglob("*")
        if path.is_file() and path.name != ".DS_Store"
    }
    # The light curve the vetting run read, under the sha256 it recorded.
    made = json.loads((signal / "provenance-checks.json").read_text())
    expected["dataset/lc/1.npz"] = made["inputs"]["light_curve_1"]["sha256"]
    # The density-prior posterior the paper's depth and duration come from, as the run reproduced it.
    posterior = run / "dataset" / preprint.POSTERIOR
    expected[f"dataset/{preprint.POSTERIOR}"] = sha256_file(posterior)
    with np.load(posterior) as saved:
        reproduced = preprint.reproduce(signal)
        assert set(saved.files) == set(reproduced)
        assert all(np.array_equal(saved[key], reproduced[key]) for key in saved.files)
        assert saved["names"].tolist() == list(preprint.NAMES)
    manifest = json.loads((run / "manifest.json").read_text())["files"]
    assert {f["path"]: f["sha256"] for f in manifest} == expected
    assert all(sha256_file(run / f["path"]) == f["sha256"] for f in manifest)
    assert not list((run / "dataset").rglob(".DS_Store"))
    licences = {f["path"]: f["licence"] for f in manifest}
    gaia = {f"dataset/vetting/{NAME}/{name}" for name in GAIA_FILES}
    assert gaia <= set(licences)
    for path, licence in licences.items():
        assert licence == ("CC BY-NC 3.0 IGO" if path in gaia else "CC BY 4.0"), path
    exofop = {f["path"] for f in manifest if "exofop" in f}
    assert exofop == {f"dataset/vetting/{NAME}/{n}" for n in ("literature.json", "dossier.md")}
    # The paper names the dataset's files and the record's commit.
    text = (run / "preprint.md").read_text()
    assert f"`dataset/vetting/{NAME}/`" in text and "`dataset/lc/1.npz`" in text
    guide = " ".join(td.section(text, "Appendix B. Dataset Files").split())
    assert (
        f"`dataset/{preprint.POSTERIOR}` holds the samples of the density-prior fit that this paper's run reproduced "
        "from that light curve, with each sample's depth at mid-transit, total duration, draw of the stellar radius "
        "and radius (Table 1)." in guide
    )
    available = " ".join(td.section(text, "Data Availability").split())
    assert (
        "and the samples of the density-prior fit behind Table 1's depth, duration and radius."
        in available
    )
    assert made["git"]["commit"] in text


def test_a_versions_dataset_holds_each_record_up_to_it(tmp_path, monkeypatch):
    repo = held_r2(tmp_path, monkeypatch)
    signal = repo / "results" / "vetting" / NAME
    files = preprint.dataset(signal / "r2")
    m3 = {
        f"vetting/{NAME}/{path.relative_to(signal)}" for path in signal.rglob("*") if path.is_file()
    }
    assert set(files) == m3 | {"lc/1.npz"}
    assert f"vetting/{NAME}/r2/checks.json" in files and f"vetting/{NAME}/checks.json" in files
    made = json.loads((signal / "r2" / "provenance-checks.json").read_text())
    # r2's light curve is the revet fetch run's, not the M3 record's.
    assert sha256_file(files["lc/1.npz"]) == made["inputs"]["light_curve_1"]["sha256"]
    assert sha256_file(files["lc/1.npz"]) != sha256_file(tmp_path / "data" / "lc" / "1.npz")


def test_the_author_line_comes_from_author_toml(tmp_path, monkeypatch, no_pdf):
    template = (REPO / preprint.TEMPLATE).read_text()
    decision = (REPO / "docs" / "decisions" / "0043-the-preprint-for-a-pass.md").read_text()
    given, family = provenance.maintainer()
    for name in (given, family, "Vera", "Placeholder"):
        assert name not in template
    assert given not in decision and family not in decision
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    # Name, affiliation and ORCID on lines of their own, and the version's date; the repository URL is in Data
    # Availability, not the author block.
    front = text.split("## Abstract")[0]
    assert (
        '<p class="author">Vera Placeholder<br>Independent researcher<br>ORCID 0000-0002-1825-0097</p>'
        in front
    )
    assert "https://example.org/tess-hunt" not in front
    assert "https://example.org/tess-hunt" in td.section(text, "Data Availability")
    dated = preprint.render(
        repo / "results" / "vetting" / NAME,
        preprint.load_author(repo / preprint.AUTHOR),
        repo,
        version=dt.date(2027, 2, 24),
    )
    assert '<p class="version">Version of 2027 February 24</p>' in dated
    # A file without a repository URL is refused.
    bad = tmp_path / "author.toml"
    bad.write_text(AUTHOR.replace('repository = "https://example.org/tess-hunt"\n', ""))
    with pytest.raises(SystemExit, match="repository"):
        preprint.load_author(bad)
    # Without the file the run refuses before it starts.
    (repo / preprint.AUTHOR).unlink()
    commit(repo)
    with pytest.raises(SystemExit, match="author.toml"):
        main(["preprint", "run", "--name", NAME])
    assert runs_made(tmp_path) == []


def test_a_production_run_reads_only_committed_results(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    template = repo / preprint.TEMPLATE
    template.write_text(template.read_text().replace("## Abstract", "## Summary"))
    with pytest.raises(SystemExit, match="results/ has changes that are not committed"):
        main(["preprint", "run", "--name", NAME, "--production"])
    assert runs_made(tmp_path) == []


def test_run_refuses_before_starting_without_the_pdf_group(tmp_path, monkeypatch):
    published(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, "weasyprint", None)
    with pytest.raises(SystemExit, match="uv sync --group preprint"):
        main(["preprint", "run", "--name", NAME])
    assert runs_made(tmp_path) == []


def test_publish_copies_the_package(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    assert main(["preprint", "run", "--name", NAME]) == 0
    [run] = runs_made(tmp_path)
    dest = repo / "results" / "preprints" / run.name
    with pytest.raises(SystemExit, match="not a production run"):
        main(["preprint", "publish", "--run", run.name])
    assert not dest.exists()
    td.production(run)
    assert main(["preprint", "publish", "--run", run.name]) == 0
    assert sorted(p.name for p in dest.iterdir()) == sorted(preprint.PACKAGE)
    for name in preprint.PACKAGE:
        assert sha256_file(dest / name) == sha256_file(run / name)
    # The dataset is deposited from the run directory; the repository keeps its manifest.
    assert (run / "dataset").is_dir()


def test_zenodo_prints_the_form_from_the_run(tmp_path, monkeypatch, no_pdf, capsys):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    assert main(["preprint", "run", "--name", NAME]) == 0
    [first] = runs_made(tmp_path)
    # The deposited copy is the committed one, and only a production run is committed.
    with pytest.raises(SystemExit, match="not a production run"):
        main(["preprint", "zenodo", "--run", first.name])
    td.production(first)
    capsys.readouterr()
    assert main(["preprint", "zenodo", "--run", first.name]) == 0
    form = capsys.readouterr().out
    title = (first / "preprint.md").read_text().splitlines()[0].removeprefix("# ")
    assert f"## Title\n\n{title}\n" in form
    assert "## Resource type\n\nPublication / Preprint\n" in form
    assert "Placeholder, Vera" in form and "0000-0002-1825-0097" in form
    licences = form.split("## Licence\n")[1].split("\n## ")[0]
    assert "Creative Commons Attribution 4.0 International (CC BY 4.0)" in licences
    assert "(CC BY-NC 3.0 IGO)" in licences
    assert "ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php)" in licences
    # The description names the dataset's parts, the density-prior samples among them, and the files the second
    # licence covers.
    description = form.split("## Description\n")[1].split("\n## ")[0]
    assert (
        "The dataset holds the signal's published vetting records, the light curve that the vetting run of the "
        "paper's record read, and the samples of the density-prior fit behind Table 1's depth, duration and radius "
        f"(`{preprint.POSTERIOR}`)." in description
    )
    gaia = sorted(name for name in GAIA_FILES if (record / name).is_file())
    assert (
        f"({dossier._words([f'`{name}`' for name in gaia])}, in each record's directory)"
        in description
    )
    assert "https://example.org/tess-hunt" in form
    assert "zenodo.99999999" not in form
    assert td.REVIEW["model"] not in form
    # The Abstract in plain text, without its keywords line, and the disclosure without the lines below it.
    assert description.lstrip().startswith("We report a transiting planet candidate around TIC 1")
    assert "<sup>" not in description and "<sub>" not in description and "<i>" not in description
    assert "Keywords" not in description and "Facilities" not in description
    assert "More information on models is available on GitHub." in description
    # Otherwise the Abstract's text as the paper prints it, with no claim the Abstract does not make.
    abstract = td.section((first / "preprint.md").read_text(), "Abstract").split("\n\n")[0]
    assert description.strip().split("\n\n")[0] == " ".join(preprint._plain(abstract).split())
    for claim in ("confirmed", "discovered a planet", "validated"):
        assert claim not in description.lower()

    # A record that holds a preregistered test's result cites the predictions' DOI.
    (record / "prereg.json").write_text(json.dumps(PREREG))
    (repo / "results" / "predictions").mkdir()
    (repo / "results" / "predictions" / "dois.toml").write_text(
        f'["{PACKAGE}"]\ndoi = "{DOI}"\nconcept = "10.5281/zenodo.99999998"\npublished = 2026-11-05\n'
    )
    commit(repo)
    assert main(["preprint", "run", "--name", NAME]) == 0
    [second] = [r for r in runs_made(tmp_path) if r != first]
    td.production(second)
    capsys.readouterr()
    assert main(["preprint", "zenodo", "--run", second.name]) == 0
    form = capsys.readouterr().out
    assert DOI in form
    written = (second / "preprint.md").read_text()
    text = " ".join(td.section(written, "Held-Out Seasons and the Preregistered Test").split())
    assert (
        "Before TESS observed Sectors 112 and 113, we deposited a prediction of the signal's transits in those "
        f'sectors on Zenodo (<span class="id">doi:{DOI}</span>).' in text
    )
    # In order: the deposit, the sectors tess-point gave at the vetting run, then the result.
    assert (
        text.index("we deposited a prediction")
        < text.index("As of the vetting run (")
        < text.index("the new sectors replicate")
    )
    assert (
        "Zenodo published the deposit on 2026 November 5, and TESS began observing Sector 112 on 2026 December 22."
        in text
    )
    assert (
        "As of 2027 February 20, the new sectors replicate the signal. The 412 cadences in the cores of the "
        "predicted transits give a depth of 500 ± 100 ppm, a significance of 5.00σ against the 4.80σ the test "
        "expected. Each light-curve family's new depth was compared with that family's depth in the earlier "
        "seasons, as recorded in the deposit's `references.json`. The largest tension is 0.40σ."
        in text
    )
    assert "Which star it comes from remains open." in text
    assert "Our call (2026 October 28) came before this result." in text
    assert PACKAGE not in text
    summary = " ".join(td.section(written, "Abstract").split())
    assert (
        "Before TESS observed Sectors 112 and 113, we deposited a prediction of the signal's transits in those "
        "sectors on Zenodo. The transits appeared at the predicted times." in summary
    )
    assert "The transits recurred at the times we preregistered." in td.section(
        written, "Conclusions"
    )
    # The claim made in the predictions deposit is named as that deposit.
    claims = repo / "results" / "claims.toml"
    claims.write_text(claims.read_text().replace("10.5281/zenodo.23745923", DOI))
    assert (
        f'We first made the signal public on 2026 October 28, in our predictions deposit (<span class="id">doi:{DOI}'
        "</span>)." in " ".join(paper(repo).split())
    )
    # A judged result without its depth raises instead of rendering.
    (record / "prereg.json").write_text(json.dumps({**PREREG, "depth": None}))
    with pytest.raises(KeyError, match="prereg"):
        paper(repo)


def test_the_pdf_renders(tmp_path, monkeypatch):
    pytest.importorskip("weasyprint")
    _, repo = published(tmp_path, monkeypatch)
    assert main(["preprint", "run", "--name", NAME]) == 0
    [run] = runs_made(tmp_path)
    assert (run / "preprint.pdf").read_bytes().startswith(b"%PDF")
    plots = repo / "results" / "vetting" / NAME / "plots"

    def text(box) -> str:
        return " ".join(b.text for b in box.descendants() if hasattr(b, "text"))

    def marks(specimen: bool) -> list[list[str]]:
        """The margin boxes on each page of WeasyPrint's layout that carry the specimen's marking (the lock holds no
        PDF reader)."""
        document = preprint.document(paper(repo), plots, specimen)
        return [
            sorted(
                box.at_keyword
                for box in page._page_box.children
                if getattr(box, "at_keyword", None) and preprint.SPECIMEN in text(box)
            )
            for page in document.pages
        ]

    marked = marks(specimen=True)
    assert len(marked) >= 1
    # The header and the footer of every page, and only there: a specimen's text is a paper's.
    assert all(page == ["@bottom-center", "@top-center"] for page in marked)
    assert all(page == [] for page in marks(specimen=False))
    assert preprint.SPECIMEN not in preprint.html(paper(repo), specimen=True).split("<body>")[1]
    # The review's finding keeps its quoted claim and the call's answer nested under it.
    page = preprint.html(paper(repo), specimen=False)
    assert re.search(
        r"<li>F2, on whether the signal is on the star\. Rated hold; [^<]*<ul>\s*<li>Finding: ",
        page,
    )
    # Hyphenation needs the page's language; the headings carry the ids the section numbers read.
    assert page.startswith('<!DOCTYPE html><html lang="en">')
    assert (
        '<h2 id="abstract">Abstract</h2>' in page and '<h2 id="references">References</h2>' in page
    )
    # Names hyphenation would split are kept whole in the page, and the Markdown keeps them plain.
    assert '<span class="id">TRICERATOPS</span> (Giacalone et al. 2021) computed' in page
    assert '<span class="id">TRICERATOPS</span>' not in paper(repo)


# A refuter's reason as reviews write them: paragraphs, Markdown's own marks and a path in angle brackets, all of which
# the paper quotes as written.
REASON = (
    "First, the depth is 1200 ppm in **every** sector.\n\n"
    "Second, `fit_depth.py` ran as python $O/<script>.py and agreed; a_b and [this] stay plain.\n\n"
    "Third, the * and the # and a | end it."
)


def laid_out(document) -> str:
    """The text WeasyPrint laid out on the pages, without the margins' page numbers and without whitespace, a word
    hyphenated at a line's end joined again, so text split over lines, pages or inline boxes still reads in order (the
    lock holds no PDF reader)."""
    texts = [
        box.text
        for page in document.pages
        for part in page._page_box.children
        if not getattr(part, "at_keyword", None)
        for box in part.descendants()
        if hasattr(box, "text")
    ]
    return re.sub(r"\s+", "", "".join(t.removesuffix("\N{HYPHEN}") for t in texts))


def squashed(text: str) -> str:
    return re.sub(r"\s+", "", text)


def test_quoted_text_reaches_the_pdf_word_for_word(tmp_path, monkeypatch):
    pytest.importorskip("weasyprint")
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    review = json.loads((record / "review.json").read_text())
    next(f for f in review["findings"] if f["id"] == "F3")["refuters"][0]["reason"] = REASON
    (record / "review.json").write_text(json.dumps(review))
    text = paper(repo)
    # The quote of three paragraphs stays on its finding's list item, inside its quotation marks.
    [quoted] = [
        line
        for line in td.section(text, "Appendix C. Refuted Findings and Notes").splitlines()
        if line.startswith("    - Refuter 1 did not disprove it: ")
    ]
    assert quoted.endswith('end it."')
    page = preprint.html(text, specimen=False)
    for made in ("<script>", "<strong>every", "<code>fit_depth", "<em>b"):
        assert made not in page
    laid = laid_out(preprint.document(text, record / "plots", specimen=False))
    assert squashed(f'Refuter 1 did not disprove it: "{REASON}"') in laid
    # Appendix D, which follows the quote, is there to its last sentence.
    assert "APPENDIXD.LICENCES" in laid
    assert (
        squashed(
            "ExoFOP's rows in its literature.json, claims.json and dossier.md files stay under ExoFOP's terms."
        )
        in laid
    )


def test_every_published_review_is_quoted_word_for_word():
    pytest.importorskip("weasyprint")
    # The paper's quoting of the 14 published records, laid out in one document: each finding's claim, the call's
    # answers, the refuted findings' verdicts, the notes, the flagged papers' titles, the call's three sentences and
    # reasons, and Table 2's reasons.
    parts, quoted = [], []
    for path in sorted((REPO / "results" / "vetting").glob("*/review.json")):
        record = path.parent
        review = calls.load_review(path)
        call = calls.load(record / "call.toml")
        checks = json.loads((record / "checks.json").read_text())
        literature = json.loads((record / "literature.json").read_text())
        confirmed = calls.confirmed(review)
        # A held or killed call need not answer every upheld finding or give the three sentences; its reasons stand in
        # for them, so every quoted word is still the record's own.
        answers = {f: call["answers"].get(f, call["reasons"]) for f in confirmed}
        sentences = {k: call["sentences"].get(k, call["reasons"]) for k in preprint.SENTENCES}
        found = preprint._review(
            record, review, {**call, "answers": answers, "sentences": sentences}, literature
        )
        said = [call[k] for k in ("reasons", "deciding_evidence", "promotion") if call[k]]
        rows = [[c["check"], c["outcome"], c["reason"]] for c in checks["checks"]]
        novelty = next(c for c in checks["checks"] if c["check"] == "novelty")
        parts += [
            f"## {record.name}",
            *(found[k] for k in ("answers", "refuted", "notes", "sentences", "hits_read")),
            *(f"The call gives the reason {preprint._quote(s)}" for s in said),
            preprint._checks_table(rows, novelty, novelty, []),
        ]
        refuted = [
            f for f in review["findings"] if f["rating"] != "note" and f["id"] not in confirmed
        ]
        notes = record / "review-notes.toml"
        hits = {h["arxiv"]: h for h in literature["evidence"]["hits"]} | {
            h["doi"]: h for h in literature["evidence"]["hits"]
        }
        quoted += [
            *(f["claim"] for f in review["findings"]),
            *(v["reason"] for f in refuted for v in f["refuters"]),
            *answers.values(),
            *sentences.values(),
            *said,
            *(
                n["text"]
                for ns in (calls.load_notes(notes, review) if notes.is_file() else {}).values()
                for n in ns
            ),
            *(hits[i]["title"] for i in review["hits_flagged"] if i in hits and hits[i]["title"]),
            *(r[2] for r in rows),
        ]
    assert len(parts) >= 14 * 7 and len(quoted) > 100
    laid = laid_out(preprint.document("\n\n".join(parts), REPO, specimen=False))
    missing = [q for q in quoted if squashed(preprint._scrub(q)) not in laid]
    assert missing == []


def deposited(repo: Path, record: Path, published: str) -> None:
    """The fixture's preregistered result in `record`, its package published on Zenodo on `published`."""
    (record / "prereg.json").write_text(json.dumps(PREREG))
    (repo / "results" / "predictions").mkdir(exist_ok=True)
    (repo / "results" / "predictions" / "dois.toml").write_text(
        f'["{PACKAGE}"]\ndoi = "{DOI}"\nconcept = "10.5281/zenodo.99999998"\npublished = {published}\n'
    )
    commit(repo)


def test_a_deposit_after_its_first_sector_is_refused(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    # TESS began observing Sector 112, the first the package predicts, on 2026-12-22.
    deposited(repo, record, "2026-12-22")
    with pytest.raises(
        SystemExit, match="not before TESS began observing Sector 112 on 2026-12-22"
    ):
        main(["preprint", "run", "--name", NAME])
    assert runs_made(tmp_path) == []
    deposited(repo, record, "2026-12-21")
    assert "Zenodo published the deposit on 2026 December 21" in " ".join(paper(repo).split())
    for result, said, summary, concluded in (
        (
            {
                "result": "pending",
                "status": "pending",
                "reason": "no light curve the test can use yet in S112",
            },
            'As of 2027 February 20, the test is pending ("no light curve the test can use yet in S112").',
            "Before TESS observed Sectors 112 and 113, we deposited a prediction of the signal's transits in those "
            "sectors on Zenodo. The preregistered test of that prediction is not yet judged.",
            "The preregistered test of the transits in later sectors is not yet judged.",
        ),
        (
            {
                "result": "untested",
                "status": "untestable",
                "reason": "1 training season(s), need 2",
            },
            'As of 2027 February 20, the new data could not test the prediction ("1 training season(s), need 2").',
            "The new data could not test that prediction.",
            "The later sectors could not test our preregistered prediction.",
        ),
        (
            {"result": "missed", "status": "missed"},
            "As of 2027 February 20, the new sectors miss the prediction. The 412 cadences in the cores of the "
            "predicted transits",
            "The transits were absent at the predicted times.",
            "The transits were absent at the times we preregistered.",
        ),
    ):
        (record / "prereg.json").write_text(json.dumps({**PREREG, **result}))
        written = paper(repo)
        text = " ".join(written.split())
        assert said in text and summary in " ".join(td.section(written, "Abstract").split())
        assert concluded in " ".join(td.section(written, "Conclusions").split())
        assert "untestable" not in text and "The replication shows" not in text


def test_the_paper_says_how_the_signal_was_found(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    found = " ".join(td.section(text, "Detection").split())
    sample = tomllib.loads(tv.SEARCH.read_text())["sample"]
    assert (
        "The search ran box least squares (BLS; Kovács et al. 2002) over periods of 1 to 40 days, on the period grid "
        f"of transitleastsquares (Hippke & Heller 2019), on the light curves of {SAMPLE:,} stars from the TESS Input "
        "Catalog." in found
    )
    assert (
        f"Each star has: - an effective temperature above {sample['teff_min']:g} K and no higher than "
        f"{sample['teff_max']:g} K;" in found
    )
    assert (
        f"- a log <i>g</i> of at least {sample['flame_logg_min']:g} from the Gaia DR3 FLAME mass and radius (Creevey "
        "et al. 2023), where Gaia gives them (DR 0009);" in found
    )
    assert (
        f"- light curves in at least {preprint._spell(sample['min_sectors'])} sectors, one of them in Sectors "
        in found
    )
    # The single null signal is said once.
    assert (
        f"Scaling the null search's count by the ratio of the sample's {SAMPLE:,} stars to the {NULL_STARS:,} stars "
        "in the null search gives an expected 1.03 false alarms at or above the threshold. The estimate rests on a "
        "single null-search signal." in found
    )
    assert found.count("single null") == 1 and "one null" not in found
    assert (
        "For the injection-recovery test, 2000 synthetic transits were injected into the light curves of 1000 sample "
        "stars" in found
    )
    # Triage's row for the signal, under the criteria the vetting run recorded for it.
    assert (
        "Under triage criteria triage-v1, this signal passed the novelty check, LEO-Vetter's false-alarm and "
        'flux-level tests (LEO-Vetter\'s disposition: "planet candidate at flux level") and the pixel check, and was '
        "shortlisted." in found
    )
    # Run ids and paths sit in the runs table, not in the prose.
    assert (
        tv.SEARCH_RUN not in found and NULL_RUN not in found and "results/benchmarks" not in found
    )
    runs = td.section(text, "Appendix A. Runs")
    assert "**Table 3.** Runs whose outputs this paper uses" in runs
    for step, run, where in (
        ("Search", tv.SEARCH_RUN, "benchmarks"),
        ("Null search", NULL_RUN, "benchmarks"),
        ("Threshold", THRESHOLD_RUN, "benchmarks"),
        ("Injection recovery", INJECT_RUN, "benchmarks"),
        ("Triage", tv.TRIAGE_RUN, "triage"),
    ):
        # Each run's id on one line, and the directory that holds the run's own, named by that id.
        assert f'| {step} | <span class="id">{run}</span> | `results/{where}/` |' in runs
    note = " ".join(runs.split("*Note.*")[1].split())
    assert note.startswith(
        "The files of the search, null-search, threshold, injection-recovery, triage and predictions runs are in a "
        "directory named by the run id under the location given."
    )
    assert (
        "The injection-recovery run's `completeness_snr.csv` holds the recovered fraction" in note
    )
    # The paper points to the recovered fractions, so an injection-recovery run without them is refused.
    (repo / "results" / "benchmarks" / INJECT_RUN / "completeness_snr.csv").unlink()
    with pytest.raises(SystemExit, match="completeness_snr.csv"):
        paper(repo)
    # The SDE and triage's steps come from the signal's row, so a triage run without it is refused.
    commit(repo)
    signals = repo / "results" / "triage" / tv.TRIAGE_RUN / "signals.csv"
    rows = pd.read_csv(signals)
    rows[rows["rank"] != 1].to_csv(signals, index=False)
    (repo / "results" / "benchmarks" / INJECT_RUN / "completeness_snr.csv").write_text(
        "engine,bin\n"
    )
    commit(repo)
    with pytest.raises(SystemExit, match=f"holds 0 rows for {NAME}, not one"):
        main(["preprint", "run", "--name", NAME])
    assert runs_made(tmp_path) == []


def test_triage_and_the_novelty_check_are_said_in_words(tmp_path, monkeypatch):
    made = {"inputs": {}}
    row = pd.Series(
        {
            **TRIAGED,
            "leo_flux": "fail",
            "pixels": "inconclusive",
            "pixels_reason": "not run: novelty or the flux tests did not pass",
            "shortlisted": False,
        }
    )
    said = preprint._triage(row, made, {"signal": {"kind": "candidate"}})
    assert said == (
        "In triage, this signal's novelty check passed, LEO-Vetter's tests failed and triage did not run its pixel "
        "check, so triage did not shortlist it."
    )
    ran = pd.Series({**row, "pixels": "fail", "pixels_reason": 'centroid offset 20.1" beyond 15"'})
    second = preprint._triage(ran, made, {"signal": {"kind": "second"}})
    assert "and its pixel check failed, so triage did not shortlist it." in second
    assert second.endswith(
        "It came to vetting on tess-hunt's second list of SPOC threshold-crossing events that never became TOIs "
        "(DR 0028)."
    )
    # A novelty check's outcome with what it matched; its reason quoted where it lists no match.
    passed = {"outcome": "pass", "reason": "no known object matches", "evidence": {}}
    assert (
        preprint._novelty_said(passed)
        == "no other catalogued object matches the signal, and the novelty check passes"
    )
    assert preprint._novelty_against(passed) == (
        "Against the catalogues used in the vetting run, the novelty check passes: no known object matches the signal."
    )
    two = {
        "outcome": "fail",
        "reason": "matches A",
        "evidence": {"matches": [{"name": "A"}, {"name": "B"}]},
    }
    assert preprint._novelty_said(two) == "the novelty check fails because A and B match the signal"
    assert preprint._novelty_against(two) == (
        "Against the catalogues used in the vetting run, the novelty check fails because A and B match the signal."
    )
    spoc = {
        "outcome": "inconclusive",
        "reason": "known to SPOC only",
        "evidence": {"category": "known_to_spoc"},
    }
    assert (
        preprint._novelty_said(spoc)
        == 'the novelty check is inconclusive, for the reason "known to SPOC only"'
    )
    # A listing the novelty check matched at a harmonic is placed against the signal's period.
    for ratio, said in (
        (1.0, "this period"),
        (0.5, "twice this period"),
        (2.0, "half this period"),
        (1 / 3, "three times this period"),
        (3.0, "a third of this period"),
        (None, "a harmonic of this period"),
    ):
        assert preprint._harmonic(ratio) == said
    # A quoted reason that ends a sentence takes the paper's full stop unless its own text ends one.
    assert preprint._stop('the reason "two TCEs agree"') == 'the reason "two TCEs agree".'
    assert preprint._stop('the reason "Two TCEs agree."') == 'the reason "Two TCEs agree."'
    assert (
        preprint._stop('the question "Is it on the star?"') == 'the question "Is it on the star?"'
    )
    assert preprint._stop("no ModShift result") == "no ModShift result."
    monkeypatch.setattr(preprint, "_excepted", lambda record: [])
    monkeypatch.setattr(preprint.calls, "novelty", lambda record, checks: spoc)
    promoted = preprint._novelty(
        tmp_path,
        {"checks": [{"check": "novelty", **spoc}]},
        {"promotion": "ExoMiner scores it 0.98"},
    )
    assert promoted.startswith(
        'The novelty check is inconclusive, for the reason "known to SPOC only".'
    )
    assert "DR 0013 lets the call promote such a signal, and we promoted this one." in promoted
    assert promoted.endswith('The call gives the reason "ExoMiner scores it 0.98".')
    ended = preprint._novelty(
        tmp_path,
        {"checks": [{"check": "novelty", **spoc}]},
        {"promotion": "ExoMiner scores it 0.98."},
    )
    assert ended.endswith('The call gives the reason "ExoMiner scores it 0.98."')
    # Table 2's footnote and the Abstract say the promotion replaced the check's pass.
    rows = [["novelty", "inconclusive", "known to SPOC only"], ["odd_even", "pass", "agree"]]
    table = preprint._checks_table(rows, spoc, spoc, [])
    assert "| inconclusive<sup>a</sup> |" in table
    assert (
        "<sup>a</sup> The call promotes the signal past this check under DR 0013. See Section 6.4."
        in table
    )
    assert preprint._abstract_checks(rows, spoc, spoc, []) == (
        "Every vetting check passed except the comparison with known objects, which was inconclusive. We promoted "
        "the signal past that check, as our rules allow for a SPOC threshold-crossing event that never became a TOI."
    )
    assert preprint._abstract_checks([["odd_even", "pass", "agree"]], passed, passed, []) == (
        "Every vetting check passed."
    )
    # Any other check is named in Table 2's words, not by its id.
    assert preprint._abstract_checks(
        [["sector_depth", "fail", "x"], ["neighbours", "inconclusive", "y"]], passed, passed, []
    ) == (
        "Every vetting check passed except the check of depth from sector to sector, which failed and the check of "
        "Gaia DR3 neighbours that could make the dip, which was inconclusive."
    )


def test_what_a_revet_changed_is_said(tmp_path):
    version = tmp_path / "r2"
    version.mkdir()
    (version / "checks.json").write_text(json.dumps({"tic": 1}))
    sectors = {
        "64": {
            "status": "redelivered",
            "base": {"provenance": "QLP"},
            "fresh": {"provenance": "QLP"},
        },
        "65": {
            "status": "upgraded",
            "base": {"provenance": "QLP"},
            "fresh": {"provenance": "TESS-SPOC"},
        },
        "66": {"status": "added", "base": None, "fresh": {"provenance": "SPOC"}},
    }
    (version / "merge.json").write_text(json.dumps({"1": {"sectors": sectors}}))
    assert preprint._changed(version) == (
        "a new vetting on a light curve with Sector 66 (SPOC) added, Sector 64's timing-suspect delivery replaced by "
        "a newer one and Sector 65's QLP light curve replaced by TESS-SPOC's"
    )
    (version / "merge.json").write_text(json.dumps({"1": {"sectors": {"64": {"status": "kept"}}}}))
    assert preprint._changed(version) == "a new vetting on the same light curve"


def test_each_count_reads_as_words():
    # Counts up to nine are words, two is "both" or "neither" where the sentence takes it, and the noun agrees.
    assert [preprint._count(n, "paper") for n in (0, 1, 2, 12)] == [
        "no papers",
        "one paper",
        "two papers",
        "12 papers",
    ]
    for args, said in (
        ((1, 0, 0), "its one season was not testable"),
        ((1, 1, 0), "its one season was testable and was not predicted"),
        ((2, 0, 0), "neither of its two seasons was testable"),
        ((2, 1, 1), "one of its two seasons was testable and it was predicted"),
        ((2, 2, 2), "both seasons were testable and both were predicted"),
        ((2, 2, 0), "both seasons were testable and neither was predicted"),
        ((3, 0, 0), "none of its three seasons was testable"),
        ((3, 2, 1), "two of its three seasons were testable and one was predicted"),
        ((3, 3, 3), "all three seasons were testable and all were predicted"),
        ((4, 3, 0), "three of its four seasons were testable and none was predicted"),
    ):
        assert preprint._seasons(*args) == said

    def finding(rating: str, *refuted: bool) -> dict:
        return {
            "id": "F1",
            "lens": "planet",
            "rating": rating,
            "refuters": [{"refuted": r} for r in refuted],
        }

    for found, confirmed, said in (
        (finding("note"), [], "Rated note."),
        (finding("hold"), ["F1"], "Rated hold; no refuter tested it, so it counts as upheld."),
        (finding("hold", False), ["F1"], "Rated hold; its one refuter did not disprove it."),
        (
            finding("hold", False, False),
            ["F1"],
            "Rated hold; neither of its two refuters disproved it.",
        ),
        (
            finding("hold", False, False, False),
            ["F1"],
            "Rated hold; none of its three refuters disproved it.",
        ),
        (finding("kill", True), [], "Rated kill; its one refuter disproved it."),
        (finding("kill", True, False), [], "Rated kill; one of its two refuters disproved it."),
        (finding("kill", True, True), [], "Rated kill; both of its refuters disproved it."),
        (
            finding("kill", True, True, True),
            [],
            "Rated kill; all three of its refuters disproved it.",
        ),
    ):
        assert preprint._label(found, confirmed) == f"F1, on whether the signal is a planet. {said}"

    def rated(*ratings: str) -> list[dict]:
        return [{"id": f"F{i}", "rating": r} for i, r in enumerate(ratings, 1)]

    for findings, confirmed, said in (
        ([], [], "The review raised no findings."),
        (rated("note"), [], "The review's one finding was a note."),
        (rated("hold"), ["F1"], "The review's one finding, rated hold, was upheld."),
        (rated("kill", "kill"), [], "Both of the review's findings, rated kill, were refuted."),
        (rated("note", "note", "note"), [], "All three of the review's findings were notes."),
        (
            rated("hold", "note", "note"),
            ["F1"],
            "Of the review's three findings, one rated hold was upheld, and two were notes.",
        ),
    ):
        assert preprint._fates(findings, confirmed) == said
    assert (
        preprint._flagged({"hits_flagged": []}, {})
        == "The review flagged no papers for us to read."
    )

    # The neighbour check's possible hosts, by how many there are and how many lie inside the pixel check's reach.
    def hosts(*seps: float) -> list[dict]:
        return [{"source_id": i, "sep_arcsec": s} for i, s in enumerate(seps)]

    assert preprint._blends([], 15, []) == "The neighbour check found no possible hosts."
    assert preprint._blends(hosts(5, 6), 15, []) == (
        "Both of the neighbour check's possible hosts lie within 15″ of the target, too close for the pixel check to "
        "separate. Photometry that resolves the stars near the target could rule those stars out."
    )
    assert preprint._blends(hosts(20, 30), 15, [0, 1]) == (
        "Neither of the neighbour check's two possible hosts lies within 15″ of the target. TRICERATOPS computed no "
        "scenario for either of them. Photometry that resolves the stars near the target could rule those stars out."
    )
    assert preprint._blends(hosts(5, 6, 7), 15, []).startswith(
        "All three of the neighbour check's possible hosts lie within 15″"
    )
    assert preprint._blends(hosts(5, 20, 30), 15, [0]) == (
        "One of the neighbour check's three possible hosts lies within 15″ of the target, too close for the pixel "
        "check to separate. TRICERATOPS computed no scenario for one of them. Photometry that resolves the stars "
        "near the target could rule those stars out."
    )
    assert preprint._blends(hosts(20, 30, 40), 15, [0, 1, 2]).endswith(
        "TRICERATOPS computed no scenario for any of them. Photometry that resolves the stars near the target could "
        "rule those stars out."
    )
    assert preprint._tdepth_zero({"hosts_tdepth_zero": []}, hosts(5), 15) == ""
    for many, zero, which, lies in (
        (1, 1, "the neighbour check's one possible host", " That star lies within 15″"),
        (2, 2, "both of the neighbour check's possible hosts", " Both of them lie within 15″"),
        (
            3,
            3,
            "all three of the neighbour check's possible hosts",
            " All three of them lie within 15″",
        ),
        (3, 1, "one of the neighbour check's three possible hosts", " That star lies within 15″"),
    ):
        said = preprint._tdepth_zero(
            {"hosts_tdepth_zero": list(range(zero))}, hosts(*[5] * many), 15
        )
        assert said.startswith(
            f" The apertures take in too little of the light of {which} to produce the transit, so TRICERATOPS "
            "assigned"
        )
        # A zero-depth host inside the pixel check's reach is said here too.
        assert (
            f"{lies} of the target, closer than the pixel check can resolve (Section 6.2)." in said
        )
    assert "pixel check can resolve" not in preprint._tdepth_zero(
        {"hosts_tdepth_zero": [0]}, hosts(20), 15
    )

    # Red noise left unmeasured in one sector and in two.
    def unmeasured(*sectors: int) -> str:
        return preprint._red_noise(
            {"red_noise": {str(s): {"note": "too few bins"} for s in sectors}}
        )

    assert unmeasured(1).endswith(
        "Sector 1 had too few binned points to measure β, so β is set to 1 for it and its depth errors assume white "
        "noise."
    )
    assert unmeasured(1, 2).endswith(
        "Sectors 1 and 2 had too few binned points to measure β, so β is set to 1 for them and their depth errors "
        "assume white noise."
    )
    assert preprint._exofop(
        {"status": "ok", "tois": [], "ctois": [], "confirmed_planets": "", "imaging": []}
    ) == (
        "ExoFOP lists no TOIs, no CTOIs, no confirmed planets and no high-resolution imaging observations for the "
        "star."
    )


def test_counts_from_the_record_read_as_words(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    author = preprint.load_author(repo / preprint.AUTHOR)
    checks = json.loads((record / "checks.json").read_text())
    triceratops = json.loads((record / "triceratops.json").read_text())
    limit = tomllib.loads((REPO / "criteria" / "vet-v3.toml").read_text())["triceratops"][
        "fpp_validated"
    ]

    def validated(**evidence) -> str:
        edited = {**triceratops, "evidence": {**triceratops["evidence"], **evidence}}
        return preprint._validated(record, checks["criteria_version"], edited)

    assert validated(exposure_s=preprint.TWO_MINUTES_S).endswith(
        "These runs had no contrast curve, so the label does not apply."
    )
    assert validated(fpp_mean=0.5).endswith(
        f"These runs had no FPP under {limit:g}, no contrast curve and no 2-minute data, so the label does not apply."
    )
    # TRICERATOPS's run count, and the neighbour check's count of possible hosts.
    host = checks["neighbours"]["evidence"]["possible_hosts"][0]
    for fpp, hosts, times, found in (
        (
            [0.01],
            [],
            "once",
            "The neighbour check found no possible hosts.",
        ),
        (
            [0.01, 0.014],
            [host, host, host],
            "twice",
            "The neighbour check found three possible hosts. The dataset's `neighbours.csv` gives the eclipse depth "
            "each would need to produce the transit.",
        ),
    ):
        td.edit_json(
            record / "triceratops.json",
            lambda t, fpp=fpp: t["evidence"].update(fpp=fpp, hosts_tdepth_zero=[]),
        )
        td.edit_json(
            record / "checks.json",
            lambda c, hosts=hosts: c["neighbours"]["evidence"].update(possible_hosts=hosts),
        )
        made = preprint.values(record, author, repo)
        assert made["tric_times"] == times
        assert made["hosts"] == found
        # One run has no spread, so the probabilities are its own; more give a mean ± standard deviation.
        if len(fpp) == 1:
            assert made["tric_probabilities"].startswith("The false-positive probability (FPP) is ")
            assert " ± " not in made["tric_probabilities"]
        else:
            assert made["tric_probabilities"].endswith("(mean ± standard deviation).")
    # The literature search's count of papers, apart from the check's rule and its outcome, which a pass needs
    # complete.
    hit = json.loads((record / "literature.json").read_text())["evidence"]["hits"][0]
    for n, returned in ((0, "no papers"), (1, "one paper"), (3, "three papers")):
        td.edit_json(
            record / "literature.json", lambda r, n=n: r["evidence"].update(hits=[hit] * n)
        )
        assert (
            f"The search returned {returned}. The literature check passes when every query completes, and all of "
            "them did." in " ".join(paper(repo).split())
        )


def test_the_paper_says_what_vetting_leaves_open(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    text = paper(repo)
    vetted = " ".join(td.section(text, "Vetting").split())
    left = " ".join(td.section(text, "Discussion").split())
    # The vetting section's subsections, numbered by the stylesheet in this order.
    subsections = [
        "### Light-Curve Tests",
        "### Location of the Signal",
        "### Statistical False-Positive Probability",
        "### Literature, Catalogues and Later Listings",
        "### Adversarial Review and the Call",
    ]
    section = td.section(text, "Vetting")
    assert [section.index(s) for s in subsections] == sorted(section.index(s) for s in subsections)
    # The neighbour check is described once, by that name, where Section 6.2 introduces it.
    assert (
        vetted.count(
            "Gaia DR3 star near the target bright enough to produce the search's box depth"
        )
        == 1
    )
    assert "neighbour table" not in text
    assert (
        "The neighbour check lists the possible hosts: every Gaia DR3 star near the target bright enough to produce "
        "the search's box depth if all its light fell in the aperture." in vetted
    )
    # The search's box values are the box's wherever the paper uses them; "duration" alone is T14.
    flat = " ".join(text.split())
    assert "the central 50% of the search's box duration, Section 4)" in flat
    assert "transit duration" not in flat and "transit's duration" not in flat
    for caption in preprint.CAPTIONS.values():
        assert "duration" not in caption.replace("box duration", "")
    assert (
        "The check has no fail outcome: a pass means only that every star near the target could be assessed"
        in vetted
    )
    # TRICERATOPS gave the neighbour check's one possible host zero depth (decision 0026, Ruling M), and it lies
    # inside the pixel check's reach.
    assert (
        "The neighbour check found one possible host. The dataset's `neighbours.csv` gives the eclipse depth that "
        "star would need to produce the transit." in vetted
    )
    assert (
        "The apertures take in too little of the light of the neighbour check's one possible host to produce the "
        "transit, so TRICERATOPS assigned it a transit depth of zero and computed no scenario for it (DR 0026)."
        in vetted
    )
    assert (
        "That star lies within 15″ of the target, closer than the pixel check can resolve (Section 6.2)."
        in vetted
    )
    assert (
        "TRICERATOPS ran three times on Sectors 1 and 2 at 1800-s exposures, folded and binned in phase."
        in vetted
    )
    assert (
        "Both are below the thresholds Giacalone et al. (2021) set for a likely planet, FPP < 0.5 and NFPP < 0.001."
        in vetted
    )
    assert (
        "These runs had neither a contrast curve nor 2-minute data, so the label does not apply."
        in vetted
    )
    # Each sector's offset, and the timing-suspect sector the pass rests on.
    assert (
        "The offsets were 10.9″ in Sector 1 (quality 0.92), 12.8″ in Sector 2 (quality 0.84) and 9.7″ in Sector 64 "
        "(quality 0.95)." in vetted
    )
    assert (
        "Sector 64 has the best quality, so the check's pass is based on its offset, even though the vetting run left "
        "Sector 64 out because its timestamps are suspect." in vetted
    )
    assert (
        "The quality measures how closely the difference image matches the pixel response function"
        in vetted
    )
    # The cutouts the check measures on, and their service.
    assert (
        "from the target, on TESScut cutouts (Brasseur et al. 2019) of the calibrated full-frame images (TESS Team "
        "2022)." in vetted
    )
    assert (
        "The signal of TOI-1399.01, for example, comes from a nearby binary inside that limit, yet TOI-1399.01 passes "
        "the check (DR 0032)." in vetted
    )
    assert "11.6" not in vetted
    assert (
        "The one possible host from the neighbour check lies within 15″ of the target, too close for the pixel check "
        "to separate, and TRICERATOPS computed no scenario for it. Photometry that resolves the stars near the "
        "target could rule that star out." in left
    )
    # ModShift's secondary at any phase, from triage's evidence, and each figure cited where it is discussed.
    m = tv.MODSHIFT
    assert (
        f"during triage. The most significant secondary event is at phase {m['phs_sec']:.3g}, with a depth of "
        f"{m['dep_sec'] * 1e6:.0f} ppm and a significance of {m['sig_sec']:.3g}σ. The primary event has a "
        f"significance of {m['sig_pri']:.3g}σ, and ModShift's red-noise factor, F<sub>red</sub>, is "
        f"{m['Fred']:.3g}." in vetted
    )
    assert (
        "Figure 3 shows the odd- and even-numbered transits" in vetted
        and "Figure 4 the whole orbit" in vetted
    )
    assert (
        "In an eccentric orbit it can fall at another phase, which only ModShift searches. ModShift's most "
        f"significant secondary event is {m['sig_sec']:.3g}σ." in left
    )
    assert "The red-noise factor β scales each sector's depth errors" in vetted
    # ExoFOP's listings on the star, by the names the novelty check uses, and the imaging that did not go into
    # TRICERATOPS. The fixture's ExoFOP rows, as the literature search keeps them.
    assert (
        "ExoFOP lists two TOIs (TOI-266.01 with disposition CP and TOI-266.02 with disposition CP), one CTOI "
        "(CTOI-164767175.03, disposition PC), two confirmed planets (HIP 8152 b and HIP 8152 c) and one "
        "high-resolution imaging observation for the star." in vetted
    )
    assert (
        "With no high-resolution contrast curve as input, TRICERATOPS evaluated the unresolved-companion and "
        "background-star scenarios from its priors alone. ExoFOP lists one high-resolution imaging observation of "
        "the star, which TRICERATOPS did not use." in left
    )
    held_out = " ".join(td.section(text, "Held-Out Seasons and the Preregistered Test").split())
    # The fixture's light curve gives one season.
    assert (
        "For this signal its one season was testable and was predicted, so the check passed."
        in held_out
    )
    made = json.loads((record / "provenance-checks.json").read_text())
    assert (
        "This record holds no preregistered test of a later season (DR 0040). As of the vetting run "
        f"({preprint._date(made['started_at'])}), tess-point (Burke et al. 2020) predicted that TESS would observe "
        "the star in Sectors 110, 111 and 115." in held_out
    )

    # Measured red noise, a season that could not be tested, no zero-depth host, a host outside the pixel check's
    # reach, a validated label and no ModShift result each read as the record says.
    def changed(checks):
        checks["red_noise"] = {"1": {"beta": 1.3, "n_bins": 30, "cadences_per_bin": 4.0}}
        holdout = next(c for c in checks["checks"] if c["check"] == "holdout")
        holdout["evidence"]["seasons"][0].update(status="underpowered")
        checks["neighbours"]["evidence"]["possible_hosts"][0]["sep_arcsec"] = 20.0
        checks["modshift"] = None
        checks["triage_reason"] = "no --triage-run given"

    td.edit_json(record / "checks.json", changed)

    def labelled(record_):
        record_["evidence"].update(hosts_tdepth_zero=[], validated_label=True)

    td.edit_json(record / "triceratops.json", labelled)
    td.edit_json(
        record / "checks.json", lambda c: c["pixels"]["evidence"].update(offset_qual_arcsec=11.5)
    )
    text = " ".join(paper(repo).split())
    assert (
        "The check's pass is based on the best-quality offset, which no single sector above reports. The vetting run "
        "left Sector 64 out because its timestamps are suspect." in text
    )
    assert "The factor is 1.30 in Sector 1." in text
    assert "For this signal its one season was not testable, so the check" in text
    assert (
        "was not testable, because the depth expected there is too small against its error." in text
    )
    assert "computed no scenario" not in text
    assert (
        "The one possible host from the neighbour check does not lie within 15″ of the target."
        in text
    )
    assert (
        "These runs meet those conditions, but this paper still calls the signal a planet candidate."
        in text
    )
    assert (
        "ModShift, the model-shift uniqueness test (Rowe et al. 2015; Coughlin et al. 2016), which LEO-Vetter runs "
        'during triage, has no result in the record ("no --triage-run given").' in text
    )
    assert (
        "In an eccentric orbit it can fall at another phase, and the record holds no ModShift result."
        in text
    )


def test_how_tess_hunt_works_is_said_once(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    made = json.loads((record / "provenance-checks.json").read_text())
    text = paper(repo)
    works = " ".join(td.section(text, "The tess-hunt Search and Vetting").split())
    # Decision records are defined once, with their short form, before any is cited; their place is the commit Data
    # Availability names.
    assert (
        "We cite the project's decision records (DRs), numbered documents in the repository at the commit named in "
        'Data Availability, as "DR 0041".' in works
    )
    first_cite = " ".join(text.split()).index("(DR 0")
    assert " ".join(text.split()).index("decision records (DRs)") < first_cite
    assert "decision record 00" not in text
    available = " ".join(td.section(text, "Data Availability").split())
    assert f"used commit {made['git']['commit']}" in available
    assert (
        "The decision records are in the repository's `docs/decisions/` directory at the vetting run's commit."
        in available
    )
    # The back matter names the author, not "we", and says what queries the archives.
    assert "The author typed the notes by hand and proofread them (DR 0037)." in available
    assert (
        "it queries MAST and the Gaia archive through astroquery (Ginsburg et al. 2019)."
        in available
    )
    holdout = tomllib.loads(tv.VET3.read_text())["holdout"]
    assert (
        "A season is a group of TESS sectors in which no gap between successive sectors exceeds "
        f"{holdout['season_gap_days']:g} days." in works
    )
    assert (
        "- no row of ExoFOP's planet parameters for the star matches the signal's period;" in works
    )
    assert (
        "For the novelty check and the ExoFOP comparison, a TOI or CTOI that ExoFOP first listed after we made the "
        "signal public is not counted as a known object (DR 0042)." in works
    )
    # The Introduction cites TESS and the TOI process, and the sections are in the conventions' order.
    intro = " ".join(td.section(text, "Introduction").split())
    assert "(TESS; Ricker et al. 2015)" in intro and "(TOIs; Guerrero et al. 2021)" in intro
    assert (
        "The SPOC (Jenkins et al. 2016) and QLP (Huang et al. 2020a) pipelines search them for transits, and the "
        "TESS Science Office releases" in intro
    )
    assert "measure the transiting body's mass." in intro and "companion" not in intro
    headings = [line for line in text.splitlines() if line.startswith("## ")]
    assert headings[:10] == [
        "## Abstract",
        "## Introduction",
        "## The tess-hunt Search and Vetting",
        "## Host Star",
        "## Detection",
        "## Transit Parameters",
        "## Vetting",
        "## Held-Out Seasons and the Preregistered Test",
        "## Discussion",
        "## Conclusions",
    ]
    assert headings[-4:] == [
        "## Appendix A. Runs",
        "## Appendix B. Dataset Files",
        "## Appendix C. Refuted Findings and Notes",
        "## Appendix D. Licences",
    ]
    # No contraction outside quoted text, and British spelling in the paper's own prose.
    own = re.sub(r'"[^"]*"', "", text)
    for word in ("can't", "doesn't", "couldn't", "isn't", "won't", " catalogs ", "modeled"):
        assert word not in own, word
    # No sentence of the paper's own text opens in lowercase or on "It" or "Its"; quoted text and the Use of LLMs
    # paragraph, which is the maintainer's word for word, are their own.
    disclosure = td.section(text, "Use of LLMs").split("\n\n")[0].strip()
    prose = " ".join(own.replace(disclosure, "").split())
    assert not re.search(r"(?:^|[.?!] )tess-hunt", prose)
    assert re.findall(r"(?:^|[.?!] )(Its?)\b", prose) == []
    # A second-list row's bar names its promotion (decision 0013).
    pixels = json.loads((record / "checks.json").read_text())["pixels"]
    (record / "pixels.json").write_text(json.dumps(pixels))
    td.edit_json(record / "checks.json", lambda c: c["signal"].update(kind="second"))
    found = preprint.values(record, preprint.load_author(repo / preprint.AUTHOR), repo)
    assert found["bar_promotion"] == (
        " For a SPOC threshold-crossing event that never became a TOI, a promotion in the call can replace the "
        "novelty check's pass (DR 0013)."
    )


def test_the_figures_and_references_are_the_papers_own(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    flat = " ".join(text.split())
    # Each figure is cited in the text where its subject is discussed and placed after that citation, with a bold
    # label and a caption that opens with no article.
    for i, name in enumerate(preprint.FIGURES, 1):
        figure = f'<img src="{name}" alt="Figure {i}">\n<figcaption><b>Figure {i}.</b> '
        assert figure in text
        assert flat.index(f"Figure {i} ") < flat.index(f'alt="Figure {i}"')
        assert not preprint.CAPTIONS[name].startswith(("The ", "A ", "An "))
    assert "(<code>pdcsap</code> for PDCSAP flux from SPOC or TESS-SPOC" in text
    # One alphabetical list in AAS form, each entry a paragraph, with the entries preprint.py adds sorted among the
    # template's citations.
    references = td.section(text, "References")
    entries = [
        html.unescape(re.sub(r"<[^>]+>", "", e)) for e in re.findall(r"<p>(.*?)</p>", references)
    ]
    key_of = {entry: key for key, (_, entry) in preprint.REFERENCES.items()}
    keys = [key_of[e] for e in entries]
    assert keys == sorted(keys, key=preprint._reference_order)
    # The order reads the citation form: a sole author before two before "et al.", then the year and its letter,
    # whatever the printed author list.
    order = sorted(
        ["caldwell2020b", "huang2020a", "caldwell2020a", "huang2020"], key=preprint._reference_order
    )
    assert order == ["caldwell2020a", "caldwell2020b", "huang2020", "huang2020a"]
    assert '<span class="id">doi: 10.1117/1.JATIS.1.1.014003</span>' in references
    assert 'Catalog for <span class="id">2-Minute</span> TESS Data' in references
    assert '<span class="id">Price-Whelan</span>, A. M.' in references
    for cited in (
        "Ricker, G. R., Winn, J. N., Vanderspek, R., et al. 2015, JATIS, 1, 014003, doi: 10.1117/1.JATIS.1.1.014003",
        "Kipping, D. M. 2013, MNRAS, 435, 2152, doi: 10.1093/mnras/stt1435",
        "Guerrero, N. M., Seager, S., Huang, C. X., et al. 2021, ApJS, 254, 39, doi: 10.3847/1538-4365/abefe1",
        "Pont, F., Zucker, S., & Queloz, D. 2006, MNRAS, 373, 231",
        "Rowe, J. F., Coughlin, J. L., Antoci, V., et al. 2015, ApJS, 217, 16",
        "Coughlin, J. L., Mullally, F., Thompson, S. E., et al. 2016, ApJS, 224, 12",
        "TESS Team 2018, TESS Input Catalog and Candidate Target List, STScI/MAST, doi: 10.17909/fwdt-2x66",
        "TESS Team 2022, TESS Calibrated Full Frame Images: All Sectors, STScI/MAST, doi: 10.17909/0cp4-2j79",
    ):
        assert any(cited in e for e in entries), cited
    assert "(Rowe et al. 2015; Coughlin et al. 2016)" in flat
    # The list is exactly the works the paper cites, and each is cited in the text by its own citation: its names
    # and year, in a parenthesis or a list of that author's years ("Stumpe et al. 2012, 2014").
    body = flat.split("## References")[0]
    expected = {
        *preprint.CITED,
        *preprint.PDCSAP_REFERENCES,
        *preprint.PRODUCT_REFERENCES["SPOC 2-min"],
    }
    assert set(keys) == expected
    for key in expected:
        names, year = preprint.REFERENCES[key][0].rsplit(" ", 1)
        assert re.search(
            re.escape(names) + r" \(?(?:\d{4}[a-z]?, )*" + re.escape(year) + r"\b", body
        ), key
    available = " ".join(td.section(text, "Data Availability").split())
    assert "The tess-hunt code, under the MIT licence," in available
    licences = " ".join(td.section(text, "Appendix D. Licences").split())
    assert "or in a note, stays under ESA's CC BY-NC 3.0 IGO terms" in licences
    assert "the ExoFOP listings the paper names stay under ExoFOP's terms" in licences
    files = td.section(text, "Appendix B. Dataset Files")
    assert "**Table 4.** Files in each record" in files
    assert "| `checks.json` | each vetting check's outcome" in files
    # URLs stay out of the running text, in Data Availability or the acknowledgements' requested credits, and there
    # are no footnotes, which WeasyPrint sets on a later page than their call.
    running = text.split("## Acknowledgements")[0]
    assert re.findall(r"https?://\S+", running) == []
    assert "footnote" not in text and "footnote" not in preprint.STYLE
