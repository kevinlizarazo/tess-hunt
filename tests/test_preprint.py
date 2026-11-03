import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pandas as pd
import pytest
import test_calls as tc
import test_dossier as td
import test_vetting as tv

from tess_hunt import calls, dossier, preprint, prereg, provenance
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


def paper(repo: Path, specimen: bool = False) -> str:
    record = repo / "results" / "vetting" / NAME
    return preprint.render(
        record, preprint.load_author(repo / preprint.AUTHOR), repo, specimen=specimen
    )


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


@pytest.mark.parametrize(
    "case, message",
    [
        (held, f"{NAME}'s latest record, the M3 record, is held"),
        (held_r2, f"{NAME}'s latest record, r2, is held"),
        (pass_problems_refuse, "confirmed finding F2 has no answer"),
        (uncommitted, f"results/vetting/{NAME} has changes that are not committed"),
    ],
)
def test_preprint_refuses_unless_the_latest_version_is_a_standing_pass(
    tmp_path, monkeypatch, no_pdf, case, message
):
    case(tmp_path, monkeypatch)
    with pytest.raises(SystemExit, match=message):
        main(["preprint", "run", "--name", NAME])
    assert runs_made(tmp_path) == []


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
        return f"{value['median']:{fmt}} (-{value['minus']:{fmt}}, +{value['plus']:{fmt}})"

    expected = {
        "tic": str(checks["tic"]),
        "tmag": f"{star['tmag']:.2f}",
        "teff": f"{star['teff']:.0f}",
        "radius_sun": f"{star['rad']:.2f}",
        "period": f"{eph['period']['median']:.6f}",
        "period_sd_s": f"{eph['period']['sd'] * 86400:.1f}",
        "t0": f"{eph['t0']['median']:.4f}",
        "t0_sd_min": f"{eph['t0']['sd'] * 1440:.1f}",
        "duration_h": f"{checks['window_duration']['days'] * 24:.2f}",
        "depth_ppm": f"{checks['ephemeris']['depth'] * 1e6:.0f}",
        "rp_rearth": f"{rp['median']:.2f}",
        "rp_lo": f"{rp['p16']:.2f}",
        "rp_hi": f"{rp['p84']:.2f}",
        "rp_rs": spread(prior["rp_rs"], ".4f"),
        "b": spread(prior["b"]),
        "a_rs": spread(prior["a_rs"]),
        "fpp": f"{tric['fpp_mean']:.3g}",
        "nfpp": f"{tric['nfpp_mean']:.3g}",
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
        "claim_date": "2026-10-28",
        "call_date": "2026-10-28",
        "sample_stars": str(SAMPLE),
        "n_sample": str(SAMPLE),
        "n_null": str(NULL_STARS),
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
    for key in ("period", "t0", "fpp", "sde", "threshold", "inject_run", "commit", "rp_rs"):
        assert expected[key] in text
    # A value the record does not hold raises instead of rendering.
    td.edit_json(record / "checks.json", lambda c: c["fit_prior"].update(rp_rearth=None))
    assert "rp_rearth" not in preprint.values(
        record, preprint.load_author(repo / preprint.AUTHOR), repo
    )
    with pytest.raises(KeyError, match="rp_rearth"):
        paper(repo)


def test_the_paper_says_candidate_not_planet(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    assert text.startswith("# A 5.0-day transiting planet candidate around TIC 1\n")
    summary = " ".join(td.section(text, "Summary").split())
    assert "planet candidate" in summary
    assert "In the TESS light curves of TIC 1 it found a periodic dip" in summary
    assert (
        "This paper's author maintains tess-hunt and makes the call on each vetted signal: passed, held or killed."
        in summary
    )
    assert (
        "TESS light curves can't measure its mass or rule out light from every nearby star."
        in summary
    )
    # Only a record holding a preregistered result says so here.
    assert "deposited the prediction on Zenodo" not in summary
    # It is the Zenodo description too, where no other section exists.
    assert "How tess-hunt works" not in summary
    assert "the maintainer answered every finding that held up" in summary
    for claim in ("confirmed", "discovered a planet", "validated"):
        assert claim not in summary.lower()


def test_a_note_0037_added_sits_under_the_quoted_finding(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    (record / "review-notes.toml").write_text(NOTES)
    commit(repo)
    text = td.section(paper(repo), "What it can't rule out")
    note = "    - **Note ({}):** {}"
    f2 = note.format("2026-10-26", "The star is 12.4 arcsec away; the review rounds up.")
    f1 = note.format("2026-10-27", "Sector 2 carries most of it.")
    # Under the confirmed finding, after its quoted claim and the call's answer, which does not reply to it.
    assert (
        "- F2, on whether the dip is on the star. Rated hold; neither of its two refuters disproved it.\n"
        '    - Finding: "a star 12.5 arcsec away could host the dip"\n'
        '    - Answer: "TRICERATOPS weighed that star and the centroids sit on the target."\n'
        f"{f2}"
    ) in text
    assert (
        "- F1, on whether it is real and new. Rated note.\n"
        f'    - Finding: "one sector carries most of the depth"\n{f1}'
    ) in text
    # The paragraph above the findings says once what a note is.
    assert (
        "tess-hunt never edits quoted text. Where the maintainer later found a mistake in a quote, a dated note "
        "follows it. The note is not part of the review or the call (decision record 0037)."
        in " ".join(text.split())
    )
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
    left = td.section(text, "What it can't rule out")
    # Confirmed only because nothing refuted it, as the dossier marks it; F2's refuters ran.
    assert (
        "- F4, on whether it is a planet. Rated hold; no refuter tested it, so it counts as confirmed.\n"
        '    - Finding: "the depth'
    ) in left
    assert (
        "- F2, on whether the dip is on the star. Rated hold; neither of its two refuters" in left
    )
    # The refuted kill is quoted with each refuter's verdict.
    assert (
        "- F3, on whether it is a planet. Rated kill; one of its two refuters disproved it.\n"
        '    - Finding: "the secondary at phase 0.76 is an eccentric eclipse"\n'
        '    - Refuter 1 did not disprove it: "reproduced from the run"\n'
        '    - Refuter 2 disproved it: "the offset is the PSF\'s, not a shift"'
    ) in left
    vetted = " ".join(td.section(text, "How it was vetted").split())
    assert (
        "Of the review's four findings, two rated hold were confirmed, one rated kill was refuted, and one was a "
        "note." in vetted
    )
    # The flagged paper by its title and id, from the literature search's hits.
    assert (
        'The review flagged one paper for the maintainer to read, "The TESS-Keck Survey. XVI. Mass Measurements for '
        '12 Planets in Eight Systems" (arXiv 2306.16587). The call records that the maintainer read it.'
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
    vetted = " ".join(td.section(text, "How it was vetted").split())
    assert vetted.startswith(
        "This signal has two records. The first was called held on 2026-10-28. Its call gave the reason as "
        '"The public data can\'t tell the two stars apart." and named the evidence that would decide it: '
        '"High-resolution imaging of the 12.5 arcsec companion." This paper reports the second version, r2, a '
        "re-vet whose light curve adds Sector 65 (SPOC)."
    )
    m3 = json.loads((r2.parent / "provenance-checks.json").read_text())
    made = json.loads((r2 / "provenance-checks.json").read_text())
    available = td.section(text, "Data and code availability")
    assert f"used commit {made['git']['commit']}." in available
    assert (
        f"| Vetting, the first record | {m3['run_id']} | `dataset/vetting/{NAME}/provenance-checks.json` |"
        in available
    )
    assert (
        f"| Vetting, version r2 | {made['run_id']} | `dataset/vetting/{NAME}/r2/provenance-checks.json` |"
        in available
    )
    assert (
        f"The first record is in `dataset/vetting/{NAME}/` and version r2 in its `r2/` subdirectory."
        in " ".join(available.split())
    )
    assert "the one the vetting run of version r2 read" in " ".join(available.split())
    # The dataset's guide lists a re-vet's merge record.
    assert "| `merge.json` | what a re-vet's light curve changed |" in available
    # A third version counts three records and says what the second's call gave.
    r3 = r2.parent / "r3"
    shutil.copytree(r2, r3)
    history = preprint._history(r3)
    assert history.startswith(
        "This signal has three records. The first was called held on 2026-10-28."
    )
    assert (
        "Version r2, a re-vet whose light curve adds Sector 65 (SPOC), was called passed on "
        in history
    )
    assert history.endswith(
        "This paper reports the third version, r3, a re-vet whose light curve adds Sector 65 (SPOC)."
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
    public = td.section(paper(repo), "When it was made public")
    assert (
        "tess-hunt first made this signal public on 2026-10-28, in "
        "https://doi.org/10.5281/zenodo.23745923." in public
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
    public = " ".join(td.section(text, "When it was made public").split())
    assert "tess-hunt first made this signal public on 2026-10-28" in public
    assert (
        "ExoFOP lists a signal at this period on the star as TOI-7001.01 (period 5 d, disposition PC). ExoFOP first "
        "listed it on 2027-03-01, after tess-hunt made the signal public." in public
    )
    assert (
        "ExoFOP also lists TOI-7001.02 on the star (period 12.1 d, disposition PC). ExoFOP first listed it on "
        "2027-04-01, after tess-hunt made the signal public. The record doesn't say who submitted them."
        in public
    )
    assert "as TOI-7001.02" not in public
    assert "decision record 0042" in public
    assert (
        "ExoFOP's page for the star is https://exofop.ipac.caltech.edu/tess/target.php?id=1."
        in public
    )
    # The rule is stated once.
    assert " ".join(text.split()).count("doesn't count a TOI or CTOI") == 1
    # The paper says novelty failed on the snapshot and passed without the later listing.
    vetted = " ".join(td.section(text, "How it was vetted").split())
    assert "| Known objects at the period (`novelty`, see below the table) | fail |" in vetted
    assert (
        "The novelty check fails against the catalogs the vetting run read, because TOI-7001.01 matches the signal. "
        "ExoFOP first listed TOI-7001.01 and TOI-7001.02 after tess-hunt made the signal public, so decision record "
        '0042 sets them aside (see "When it was made public").' in vetted
    )
    assert "Without them, the novelty check passes: no known object matches the signal." in vetted
    # Only the listing at the signal's period is named against ExoFOP's rows at the period.
    assert (
        "Apart from TOI-7001.01, which decision record 0042 sets aside, none of ExoFOP's" in vetted
    )
    assert "TOI-7001.02, which" not in vetted
    # The claim the exception rests on must be the committed one.
    claims = repo / "results" / "claims.toml"
    claims.write_text(claims.read_text().replace("2026-10-28", "2026-10-29"))
    with pytest.raises(SystemExit, match="claims.json"):
        paper(repo)


def test_the_paper_gives_the_ephemeris_with_uncertainties(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    eph = json.loads((record / "checks.json").read_text())["fit_prior"]["ephemeris"]
    text = td.section(paper(repo), "The star and the signal")
    period, t0 = eph["period"], eph["t0"]
    assert f"| Period | {period['median']:.6f} d (sd {period['sd'] * 86400:.1f} s) |" in text
    assert (
        f"| Mid-transit time t0 | BTJD {t0['median']:.4f} (sd {t0['sd'] * 1440:.1f} min) |" in text
    )


def test_credits_and_disclosure_are_present(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    text = " ".join(paper(repo).split())
    assert f"This paper {prereg.TESS_CREDIT}" in text
    # The fixture's light curve is SPOC's in Sectors 1, 2 and 64.
    name, doi, papers = prereg.CREDITED["SPOC 2-min"]
    assert f"{name} from Sectors 1, 2 and 64 (doi:{doi})" in text
    assert all(f"{who}, {where}" in text for who, where in papers)
    assert prereg.QLP_CREDIT not in text
    assert "Stassun et al. 2019" in text and "Paegert et al. 2021" in text
    assert "European Space Agency (ESA) mission Gaia" in text
    assert "tess-hunt's code and this paper's text were written with LLM assistance" in text
    assert (
        "Adversarial reviews this paper quotes were assisted by LLMs. "
        "More information on models is available on GitHub." in " ".join(text.split())
    )
    # The review and its refuters are described as the disclosure describes them, and no model is named.
    assert (
        f"An LLM-assisted adversarial review, dated {td.REVIEW['date']}, looked for reasons" in text
    )
    assert "Refuters are separate LLM-assisted checks, each asked to disprove one finding." in text
    assert td.REVIEW["model"] not in text
    record = repo / "results" / "vetting" / NAME
    found = preprint.values(record, preprint.load_author(repo / preprint.AUTHOR), repo)
    assert td.REVIEW["model"] not in found.values()
    # Gaia is credited when the dataset holds Gaia data.
    monkeypatch.setattr(preprint, "GAIA_FILES", set())
    assert "European Space Agency (ESA) mission Gaia" not in paper(repo)


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
    assert "Vera Placeholder, Independent researcher, ORCID 0000-0002-1825-0097" in text
    assert "https://example.org/tess-hunt" in text
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
    template.write_text(template.read_text().replace("## Summary", "## Abstract"))
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
    # The description names the files the second licence covers.
    description = form.split("## Description\n")[1].split("\n## ")[0]
    gaia = sorted(name for name in GAIA_FILES if (record / name).is_file())
    assert (
        f"({dossier._words([f'`{name}`' for name in gaia])}, in each record's directory)"
        in description
    )
    assert "https://example.org/tess-hunt" in form
    assert "zenodo.99999999" not in form
    assert td.REVIEW["model"] not in form

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
    text = td.section(
        (second / "preprint.md").read_text(), "The held-out seasons and the preregistered test"
    )
    text = " ".join(text.split())
    assert (
        "Before TESS observed Sectors 112 and 113, tess-hunt deposited on Zenodo a prediction of the signal's "
        f"transits in them (doi:{DOI})." in text
    )
    assert (
        "Zenodo published the deposit on 2026-11-05, and TESS began observing Sector 112 on 2026-12-22."
        in text
    )
    assert (
        "As of 2027-02-20, the new sectors replicate the signal. In the cores of the predicted transits, 412 "
        "cadences give a depth of 500 ± 100 ppm, 5.00 times its error, where the test expected 4.80 times it. The "
        "tension with the earlier seasons is 0.40 sigma. That is the largest across the light-curve product "
        "families, each compared with its own depth in the earlier seasons" in text
    )
    assert "It doesn't show the dip is on the target." in text
    assert "The maintainer's call (2026-10-28) came before this result." in text
    assert PACKAGE not in text
    summary = " ".join(td.section((second / "preprint.md").read_text(), "Summary").split())
    assert (
        "Before TESS observed Sectors 112 and 113, tess-hunt deposited on Zenodo a prediction of the signal's "
        "transits in them. The transits appeared where predicted." in summary
    )
    # The claim made in the predictions deposit is named as that deposit.
    claims = repo / "results" / "claims.toml"
    claims.write_text(claims.read_text().replace("10.5281/zenodo.23745923", DOI))
    assert (
        f"tess-hunt first made this signal public on 2026-10-28, in its predictions deposit (doi:{DOI})."
        in paper(repo)
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
        document = preprint.document(paper(repo, specimen), plots, specimen)
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
    # The header and the footer of every page.
    assert all(page == ["@bottom-center", "@top-center"] for page in marked)
    assert all(page == [] for page in marks(specimen=False))
    # The review's finding keeps its quoted claim and the call's answer nested under it.
    page = preprint.html(paper(repo), specimen=False)
    assert re.search(
        r"<li>F2, on whether the dip is on the star\. Rated hold; [^<]*<ul>\s*<li>Finding: ",
        page,
    )


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
    assert "Zenodo published the deposit on 2026-12-21" in " ".join(paper(repo).split())
    for result, said, summary in (
        (
            {
                "result": "pending",
                "status": "pending",
                "reason": "no light curve the test can use yet in S112",
            },
            'As of 2027-02-20, the test is pending ("no light curve the test can use yet in S112").',
            "Before TESS observed Sectors 112 and 113, tess-hunt deposited on Zenodo a prediction of the signal's "
            "transits in them. The preregistered test of that prediction is not yet judged.",
        ),
        (
            {
                "result": "untested",
                "status": "untestable",
                "reason": "1 training season(s), need 2",
            },
            'As of 2027-02-20, the new data could not test the prediction ("1 training season(s), need 2").',
            "The new data could not test that prediction.",
        ),
        (
            {"result": "missed", "status": "missed"},
            "As of 2027-02-20, the new sectors miss the prediction. In the cores of the predicted transits",
            "The transits were missing where predicted.",
        ),
    ):
        (record / "prereg.json").write_text(json.dumps({**PREREG, **result}))
        written = paper(repo)
        text = " ".join(written.split())
        assert said in text and summary in " ".join(td.section(written, "Summary").split())
        assert "untestable" not in text and "Replication shows" not in text


def test_the_paper_says_how_the_signal_was_found(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    found = " ".join(td.section(text, "How it was found").split())
    sample = tomllib.loads(tv.SEARCH.read_text())["sample"]
    assert (
        f"to look for periodic dips of 1 to 40 days in {SAMPLE} stars from the TESS Input Catalog."
        in found
    )
    assert (
        f"Each star has: - an effective temperature above {sample['teff_min']:g} K and up to "
        f"{sample['teff_max']:g} K;" in found
    )
    assert (
        f"- light curves in at least {preprint._spell(sample['min_sectors'])} sectors, one of them in Sectors "
        in found
    )
    # The single null signal is said once.
    assert (
        f"Scaled by the ratio of the sample's {SAMPLE} stars to the {NULL_STARS} stars the null search covered, the "
        "null search gives an expected 1.03 false alarms at or above the threshold. This estimate comes from a "
        "single null signal." in found
    )
    assert found.count("null signal") == 1
    assert (
        "The injection-recovery run injected 2000 synthetic transits into the light curves of 1000 sample stars"
        in found
    )
    assert f"`results/benchmarks/{INJECT_RUN}/completeness_snr.csv`" in found
    # Triage's row for the signal, under the criteria the vetting run recorded for it.
    assert (
        "Triage (criteria triage-v1) screened every signal at or above the threshold. This signal passed the novelty "
        'check, LEO-Vetter\'s false-alarm and flux-level tests (LEO-Vetter calls it "planet candidate at flux level") '
        "and the pixel check, so it was shortlisted." in found
    )
    # Run ids sit in the runs table, not in the prose.
    assert tv.SEARCH_RUN not in found and NULL_RUN not in found
    available = td.section(text, "Data and code availability")
    for step, run, where in (
        ("Search", tv.SEARCH_RUN, "benchmarks"),
        ("Null search", NULL_RUN, "benchmarks"),
        ("Threshold", THRESHOLD_RUN, "benchmarks"),
        ("Injection recovery", INJECT_RUN, "benchmarks"),
        ("Triage", tv.TRIAGE_RUN, "triage"),
    ):
        assert f"| {step} | {run} | `results/{where}/{run}/` |" in available
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
        "Triage screened every signal at or above the threshold. This signal's novelty check passed, "
        "LEO-Vetter's tests failed and triage did not run its pixel check, so triage did not shortlist it."
    )
    ran = pd.Series({**row, "pixels": "fail", "pixels_reason": 'centroid offset 20.1" beyond 15"'})
    second = preprint._triage(ran, made, {"signal": {"kind": "second"}})
    assert "and its pixel check failed, so triage did not shortlist it." in second
    assert second.endswith(
        "It came to vetting on tess-hunt's second list of SPOC threshold-crossing events that never became TOIs "
        "(decision record 0028)."
    )
    # A novelty check's outcome as a verb with what it matched; its reason quoted where it lists no match.
    passed = {"outcome": "pass", "reason": "no known object matches", "evidence": {}}
    assert (
        preprint._novelty_said(passed)
        == "the novelty check passes: no known object matches the signal"
    )
    two = {
        "outcome": "fail",
        "reason": "matches A",
        "evidence": {"matches": [{"name": "A"}, {"name": "B"}]},
    }
    assert (
        preprint._novelty_said(two) == "the novelty check fails, because A and B match the signal"
    )
    assert preprint._novelty_against(two) == (
        "The novelty check fails against the catalogs the vetting run read, because A and B match the signal."
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
    assert promoted.endswith('It gives the reason as "ExoMiner scores it 0.98".')
    ended = preprint._novelty(
        tmp_path,
        {"checks": [{"check": "novelty", **spoc}]},
        {"promotion": "ExoMiner scores it 0.98."},
    )
    assert ended.endswith('It gives the reason as "ExoMiner scores it 0.98."')


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
        "a re-vet whose light curve adds Sector 66 (SPOC), replaces Sector 64's timing-suspect delivery with a newer "
        "one and replaces Sector 65's QLP light curve with TESS-SPOC's"
    )
    (version / "merge.json").write_text(json.dumps({"1": {"sectors": {"64": {"status": "kept"}}}}))
    assert preprint._changed(version) == "a re-vet on the same light curve"


def test_each_count_reads_as_words():
    # Counts up to nine are words, two is "both" or "neither" where the sentence takes it, and the noun agrees.
    assert [preprint._count(n, "paper") for n in (0, 1, 2, 12)] == [
        "no papers",
        "one paper",
        "two papers",
        "12 papers",
    ]
    for args, said in (
        ((1, 0, 0), "Its one season was not testable."),
        ((1, 1, 0), "Its one season was testable and was not predicted."),
        ((2, 0, 0), "Neither of its two seasons was testable."),
        ((2, 1, 1), "Of its two seasons, one was testable and it was predicted."),
        ((2, 2, 2), "Both seasons were testable and both were predicted."),
        ((2, 2, 0), "Both seasons were testable and neither was predicted."),
        ((3, 0, 0), "None of its three seasons was testable."),
        ((3, 2, 1), "Of its three seasons, two were testable and one was predicted."),
        ((3, 3, 3), "All three seasons were testable and all were predicted."),
        ((4, 3, 0), "Of its four seasons, three were testable and none was predicted."),
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
        (finding("hold"), ["F1"], "Rated hold; no refuter tested it, so it counts as confirmed."),
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
        assert preprint._label(found, confirmed) == f"F1, on whether it is a planet. {said}"

    def rated(*ratings: str) -> list[dict]:
        return [{"id": f"F{i}", "rating": r} for i, r in enumerate(ratings, 1)]

    for findings, confirmed, said in (
        ([], [], "The review raised no findings."),
        (rated("note"), [], "The review's one finding was a note."),
        (rated("hold"), ["F1"], "The review's one finding, rated hold, was confirmed."),
        (rated("kill", "kill"), [], "Both of the review's findings, rated kill, were refuted."),
        (rated("note", "note", "note"), [], "All three of the review's findings were notes."),
        (
            rated("hold", "note", "note"),
            ["F1"],
            "Of the review's three findings, one rated hold was confirmed, and two were notes.",
        ),
    ):
        assert preprint._fates(findings, confirmed) == said
    assert (
        preprint._flagged({"hits_flagged": []}, {})
        == "The review flagged no papers for the maintainer to read."
    )

    # The neighbour check's possible hosts, by how many there are and how many lie inside the pixel check's reach.
    def hosts(*seps: float) -> list[dict]:
        return [{"sep_arcsec": s} for s in seps]

    assert preprint._blends([], 15, []) == "The neighbour check found no possible hosts."
    assert preprint._blends(hosts(5, 6), 15, []) == (
        "Both of the neighbour check's possible hosts are within 15 arcsec of the target, too close for the pixel "
        "check to tell apart. Photometry that resolves the stars near the target could rule them out."
    )
    assert preprint._blends(hosts(20, 30), 15, [1, 2]) == (
        "Neither of the neighbour check's two possible hosts is within 15 arcsec of the target. TRICERATOPS weighed "
        "no scenario on either of them. Photometry that resolves the stars near the target could rule them out."
    )
    assert preprint._blends(hosts(5, 6, 7), 15, []).startswith(
        "All three of the neighbour check's possible hosts are within 15 arcsec"
    )
    assert preprint._blends(hosts(5, 20, 30), 15, [1]) == (
        "One of the neighbour check's three possible hosts is within 15 arcsec of the target, too close for the "
        "pixel check to tell apart. TRICERATOPS weighed no scenario on one of them. Photometry that resolves the "
        "stars near the target could rule them out."
    )
    assert preprint._blends(hosts(20, 30, 40), 15, [1, 2, 3]).endswith(
        "TRICERATOPS weighed no scenario on any of them. Photometry that resolves the stars near the target could "
        "rule them out."
    )
    assert preprint._tdepth_zero({"hosts_tdepth_zero": []}, hosts(5)) == ""
    for many, zero, which in (
        (1, 1, "the neighbour check's one possible host for that star"),
        (2, 2, "both of the neighbour check's possible hosts for those stars"),
        (3, 3, "all three of the neighbour check's possible hosts for those stars"),
        (3, 1, "one of the neighbour check's three possible hosts for that star"),
    ):
        said = preprint._tdepth_zero({"hosts_tdepth_zero": list(range(zero))}, hosts(*[5] * many))
        assert said.startswith(
            f" Its apertures take in too little light from {which} to make the dip."
        )

    # Red noise left unmeasured in one sector and in two.
    def unmeasured(*sectors: int) -> str:
        return preprint._red_noise(
            {"red_noise": {str(s): {"note": "too few bins"} for s in sectors}}
        )

    assert unmeasured(1).endswith(
        "Sector 1 had too few binned points to measure it, so beta is 1 there and its errors assume white noise."
    )
    assert unmeasured(1, 2).endswith(
        "Sectors 1 and 2 had too few binned points to measure it, so beta is 1 there and their errors assume white "
        "noise."
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
        "These runs had no contrast curve, so the label doesn't apply."
    )
    assert validated(fpp_mean=0.5).endswith(
        f"These runs had no FPP under {limit:g}, no contrast curve and no 2-minute data, so the label doesn't apply."
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
            "each would need.",
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


def test_the_paper_says_what_vetting_leaves_open(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    text = paper(repo)
    vetted = " ".join(td.section(text, "How it was vetted").split())
    left = " ".join(td.section(text, "What it can't rule out").split())
    # The neighbour check is described once, by that name, where the table introduces it.
    assert vetted.count("Gaia DR3 star near the target that could make the dip") == 1
    assert "neighbour table" not in text
    assert (
        "The neighbour check lists the possible hosts: every Gaia DR3 star near the target that could make the dip "
        "if all its light fell in the aperture. It never fails:" in vetted
    )
    # TRICERATOPS gave the neighbour check's one possible host zero depth (decision 0026, Ruling M).
    assert (
        "The neighbour check found one possible host. The dataset's `neighbours.csv` gives the eclipse depth it "
        "would need." in vetted
    )
    assert (
        "Its apertures take in too little light from the neighbour check's one possible host for that star to make "
        "the dip. TRICERATOPS gave it zero depth and weighed no scenario on it (decision record 0026)."
        in vetted
    )
    assert (
        "TRICERATOPS ran three times on Sectors 1 and 2 at 1800-s exposures, folded and binned in phase."
        in vetted
    )
    assert (
        "These runs had neither a contrast curve nor 2-minute data, so the label doesn't apply."
        in vetted
    )
    # Each sector's offset, and the timing-suspect sector the pass comes from.
    assert (
        "The offsets were 10.9 arcsec in Sector 1 (quality 0.92), 12.8 arcsec in Sector 2 (quality 0.84) and 9.7 "
        "arcsec in Sector 64 (quality 0.95)." in vetted
    )
    assert (
        "Sector 64 has the best quality, so the pass comes from it, though the vetting run left Sector 64 out for "
        "suspect timestamps." in vetted
    )
    assert (
        "TOI-1399.01's dip comes from a nearby binary inside that limit, and it passes the check (decision record "
        "0032)." in vetted
    )
    assert "11.6" not in vetted
    assert (
        "The neighbour check's one possible host is within 15 arcsec of the target, too close for the pixel check "
        "to tell apart, and TRICERATOPS weighed no scenario on it. Photometry that resolves the stars near the "
        "target could rule it out." in left
    )
    # ModShift's secondary at any phase, from triage's evidence.
    m = tv.MODSHIFT
    assert (
        f"The strongest secondary it finds is {m['sig_sec']:.3g} sigma at phase {m['phs_sec']:.3g} (depth "
        f"{m['dep_sec'] * 1e6:.0f} ppm). The primary is {m['sig_pri']:.3g} sigma, and ModShift's red-noise factor, "
        f"Fred, is {m['Fred']:.3g}." in vetted
    )
    assert (
        "An eccentric orbit can put it elsewhere, and only ModShift looks there. Its strongest secondary is "
        f"{m['sig_sec']:.3g} sigma." in left
    )
    assert "Each sector's depth errors are scaled by a red-noise factor, beta" in vetted
    # ExoFOP's listings on the star, by the names the novelty check uses, and the imaging that did not go into
    # TRICERATOPS. The fixture's ExoFOP rows, as the literature search keeps them.
    assert (
        "ExoFOP lists two TOIs (TOI-266.01 with disposition CP and TOI-266.02 with disposition CP), one CTOI "
        "(CTOI-164767175.03, disposition PC), two confirmed planets (HIP 8152 b and HIP 8152 c) and one "
        "high-resolution imaging observation for the star." in vetted
    )
    assert (
        "ExoFOP lists one high-resolution imaging observation of the star, which TRICERATOPS did not use."
        in left
    )
    held_out = " ".join(td.section(text, "The held-out seasons and the preregistered test").split())
    # The fixture's light curve gives one season.
    assert (
        "For this signal the check passed. Its one season was testable and was predicted."
        in held_out
    )
    assert (
        "This record holds no preregistered test of a later season (decision record 0040)."
        in held_out
    )
    made = json.loads((record / "provenance-checks.json").read_text())
    assert (
        f"At the time of the vetting run ({made['started_at'][:10]}), tess-point (Burke et al. 2020) showed TESS "
        "would observe the star in Sectors 110, 111 and 115." in " ".join(text.split())
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
        "The pass comes from the best-quality offset, which no single sector above reports. The vetting run left "
        "Sector 64 out for suspect timestamps." in text
    )
    assert "Beta is 1.30 in Sector 1." in text
    assert "Its one season was not testable." in text
    assert (
        "was not testable, because the depth expected there is too small against its error." in text
    )
    assert "weighed no scenario" not in text
    assert "The neighbour check's one possible host is not within 15 arcsec of the target." in text
    assert (
        "These runs meet those conditions, but this paper still calls the signal a planet candidate."
        in text
    )
    assert 'The record holds no ModShift result ("no --triage-run given").' in text
    assert (
        "An eccentric orbit can put it elsewhere, and the record holds no ModShift result." in text
    )


def test_how_tess_hunt_works_is_said_once(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    made = json.loads((record / "provenance-checks.json").read_text())
    works = " ".join(td.section(paper(repo), "How tess-hunt works").split())
    assert (
        f"(https://example.org/tess-hunt/tree/{made['git']['commit']}/docs/decisions). This paper cites each by its "
        "number." in works
    )
    holdout = tomllib.loads(tv.VET3.read_text())["holdout"]
    assert f"no gap longer than {holdout['season_gap_days']:g} days between them." in works
    assert "- no row of ExoFOP's planet parameters for the star matches its period;" in works
    assert (
        "For the novelty check and for ExoFOP's rows, a TOI or CTOI that ExoFOP first listed after tess-hunt made "
        "the signal public does not count (decision record 0042)." in works
    )
    # A second-list row's bar names its promotion (decision 0013).
    pixels = json.loads((record / "checks.json").read_text())["pixels"]
    (record / "pixels.json").write_text(json.dumps(pixels))
    td.edit_json(record / "checks.json", lambda c: c["signal"].update(kind="second"))
    found = preprint.values(record, preprint.load_author(repo / preprint.AUTHOR), repo)
    assert found["bar_promotion"] == (
        " For a SPOC threshold-crossing event that never became a TOI, the maintainer's promotion can replace the "
        "novelty check's pass (decision record 0013)."
    )


def test_the_figures_and_references_are_the_papers_own(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    for i, name in enumerate(preprint.FIGURES, 1):
        assert f"*Figure {i}. {preprint.CAPTIONS[name]}.*" in text
    references = td.section(text, "References")
    for cited in (
        "Ricker, G. R., Winn, J. N., Vanderspek, R., et al. 2015, JATIS, 1, 014003",
        "Kipping, D. M. 2013, MNRAS, 435, 2152",
        "Bryson, S. T., Jenkins, J. M., Gilliland, R. L., et al. 2013, PASP, 125,",
        "Pont, F., Zucker, S., & Queloz, D. 2006, MNRAS, 373, 231",
        "ModShift: Rowe, J. F., Coughlin, J. L., Antoci, V., et al. 2015, ApJS, 217, 16; Coughlin, J. L., Mullally, "
        "F., Thompson, S. E., et al. 2016, ApJS, 224, 12",
    ):
        assert cited in " ".join(references.split())
    assert "(Rowe et al. 2015; Coughlin et al. 2016)" in " ".join(text.split())
    # The fixture's light curve is SPOC's, whose flux is PDCSAP.
    assert preprint.PDCSAP_PAPERS in references
    available = " ".join(td.section(text, "Data and code availability").split())
    assert "tess-hunt's code, under the MIT licence," in available
    assert "or in a note, stays under ESA's CC BY-NC 3.0 IGO terms" in available
    assert "the ExoFOP listings the paper names stay under ExoFOP's terms" in available
    assert "| `checks.json` | each vetting check's outcome" in td.section(
        text, "Data and code availability"
    )
