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
        "triceratops_runs": f"{len(tric['fpp'])} runs",
        "findings": f"{len(review['findings'])} findings",
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
        "min_sectors": str(sample["min_sectors"]),
        "recent_min": str(sample["recent_sector_min"]),
        "triage_run": tv.TRIAGE_RUN,
        "season_gap_days": f"{holdout['season_gap_days']:g}",
        "min_sigma": f"{holdout['min_sigma']:g}",
        "max_tension": f"{holdout['max_depth_tension']:g}",
        "max_offset": f"{checks['pixels']['max_offset_arcsec']:g}",
    }
    assert {key: found[key] for key in expected} == expected
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
        "this paper's author, makes the call on each vetted signal, passed, held or killed"
        in summary
    )
    assert "they don't rule out every other star's light" in summary
    # Only a record holding a preregistered result says so here.
    assert "deposited the prediction on Zenodo" not in summary
    # It is the Zenodo description too, where no other section exists.
    assert "How tess-hunt works" not in summary
    for claim in ("confirmed", "discovered a planet", "validated"):
        assert claim not in summary.lower()


def test_a_note_0037_added_sits_under_the_quoted_finding(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    (record / "review-notes.toml").write_text(NOTES)
    commit(repo)
    text = td.section(paper(repo), "What it can't rule out")
    note = "    - **Note added on {} under decision record 0037, not part of the review or the call:** {}"
    f2 = note.format("2026-10-26", "The star is 12.4 arcsec away; the review rounds up.")
    f1 = note.format("2026-10-27", "Sector 2 carries most of it.")
    # Under the confirmed finding, after its quoted claim and the call's answer, which does not reply to it.
    assert (
        "- F2, on whether the dip is on the star (rated hold; neither of its 2 refuters refuted it)\n"
        '    - Finding: "a star 12.5 arcsec away could host the dip"\n'
        '    - Answer: "TRICERATOPS weighed that star and the centroids sit on the target."\n'
        f"{f2}"
    ) in text
    assert (
        "- F1, on whether it is real and new (rated note)\n"
        f'    - Finding: "one sector carries most of the depth"\n{f1}'
    ) in text
    assert "tess-hunt never edits quoted text" in " ".join(text.split())
    # Worded as the dossier words a note, but for its link to the decision.
    review = calls.load_review(record / "review.json")
    quoted = dossier.render_review(review, calls.load_notes(record / "review-notes.toml", review))
    said = re.sub(r"\[decision (0037)\]\([^)]*\)", r"decision record \1", quoted)
    for line in (f1, f2):
        assert line.removeprefix("    - ") in said


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
        "- F4, on whether it is a planet (rated hold; no refuter tested it, so it counts as confirmed by "
        'default)\n    - Finding: "the depth'
    ) in left
    assert "- F2, on whether the dip is on the star (rated hold; neither of its 2 refuters" in left
    # The refuted kill is quoted with each refuter's verdict.
    assert (
        "- F3, on whether it is a planet (rated kill; refuted by 1 of its 2 refuters)\n"
        '    - Finding: "the secondary at phase 0.76 is an eccentric eclipse"\n'
        '    - Refuter 1 did not refute it: "reproduced from the run"\n'
        '    - Refuter 2 refuted it: "the offset is the PSF\'s, not a shift"'
    ) in left
    vetted = " ".join(td.section(text, "How it was vetted").split())
    assert (
        "Of its 4 findings, 2 rated hold stood as confirmed, 1 rated kill was refuted and 1 was rated note."
        in vetted
    )
    # The flagged paper by its title and id, from the literature search's hits.
    assert (
        'The review flagged 1 paper for the maintainer to read, "The TESS-Keck Survey. XVI. Mass Measurements for '
        '12 Planets in Eight Systems" (arXiv 2306.16587), and the call records that the maintainer read it.'
        in vetted
    )
    # A review with no refuted finding says so.
    review["findings"] = [f for f in review["findings"] if f["id"] != "F3"]
    (record / "review.json").write_text(json.dumps(review))
    assert "No refuter refuted any finding." in paper(repo)


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
        "This signal has 2 records. The first record was called held on 2026-10-28, for these reasons, quoted from "
        'its call: "The public data can\'t tell the two stars apart." The evidence it named as deciding: '
        '"High-resolution imaging of the 12.5 arcsec companion." Version r2, a re-vet on a light curve that adds '
        "Sector 65 (SPOC), is the one this paper reports."
    )
    m3 = json.loads((r2.parent / "provenance-checks.json").read_text())
    made = json.loads((r2 / "provenance-checks.json").read_text())
    available = td.section(text, "Data and code availability")
    assert f"at commit {made['git']['commit']}" in available
    assert (
        f"| Vetting, the first record | {m3['run_id']} | `dataset/vetting/{NAME}/provenance-checks.json` |"
        in available
    )
    assert (
        f"| Vetting, version r2 | {made['run_id']} | `dataset/vetting/{NAME}/r2/provenance-checks.json` |"
        in available
    )
    assert (
        f"The first record is in `dataset/vetting/{NAME}/`, and each later version is in its own subdirectory "
        "there, `r2/`; this paper reports version r2." in " ".join(available.split())
    )
    assert "the one the vetting run of version r2 read" in " ".join(available.split())
    # The dataset's guide lists a re-vet's merge record.
    assert "| `merge.json` | what a re-vet's light curve changed |" in available
    # A record with no version before it says it is the only one.
    single = tmp_path / "single"
    single.mkdir()
    one = paper(published(single, monkeypatch)[1])
    assert "This is the signal's only record, and this paper reports it." in one
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
        "ExoFOP lists a signal at this period on the star as TOI-7001.01 (period 5 d), first listed on 2027-03-01 "
        "with disposition PC, after tess-hunt made this signal public; the record does not say who submitted it."
        in public
    )
    assert (
        "ExoFOP lists TOI-7001.02 on the star (period 12.1 d), first listed on 2027-04-01 with disposition PC, after "
        "tess-hunt made this signal public" in public
    )
    assert "as TOI-7001.02" not in public
    assert "decision record 0042" in public
    assert (
        "ExoFOP's page for the star is https://exofop.ipac.caltech.edu/tess/target.php?id=1."
        in public
    )
    # The rule is stated once.
    assert " ".join(text.split()).count("does not count a TOI or CTOI") == 1
    # The paper says novelty failed on the snapshot and passed without the later listing.
    vetted = " ".join(td.section(text, "How it was vetted").split())
    assert "| Known objects at the period (`novelty`; see below the table) | fail |" in vetted
    assert (
        "Against the catalogs the vetting run read, the novelty check fails: TOI-7001.01 matches the signal. ExoFOP "
        "first listed TOI-7001.01 and TOI-7001.02 only after tess-hunt made the signal public, so decision record "
        "0042 sets them aside" in vetted
    )
    assert (
        "Run again without them, the novelty check passes: no known object matches the signal."
        in vetted
    )
    # Only the listing at the signal's period is named against ExoFOP's rows at the period.
    assert ", apart from TOI-7001.01, which decision record 0042 sets aside" in vetted
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
        f"An adversarial review, assisted by an LLM and dated {td.REVIEW['date']}, looked for reasons"
        in text
    )
    assert "a separate LLM-assisted check asked to disprove that finding" in text
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
        f"Before TESS observed Sectors 112 and 113, tess-hunt deposited on Zenodo (doi:{DOI}) a prediction"
        in text
    )
    assert (
        "Zenodo published the deposit on 2026-11-05, and TESS began observing Sector 112 on 2026-12-22."
        in text
    )
    assert (
        "As of 2027-02-20 the new sectors replicate the signal: in the cores of the predicted transits, 412 "
        "cadences give a depth of 500 ± 100 ppm, 5.00 times its error, where the test expected 4.80 times it, and "
        "a tension of 0.40 sigma, the largest across the light-curve product families, each family's depth here "
        "against its own depth in the earlier seasons" in text
    )
    assert "it does not show that the dip is on the target" in text
    assert "The maintainer's call (2026-10-28) came before this result." in text
    assert PACKAGE not in text
    summary = " ".join(td.section((second / "preprint.md").read_text(), "Summary").split())
    assert (
        "tess-hunt predicted the signal's transits in TESS Sectors 112 and 113 and deposited the prediction on "
        "Zenodo before TESS observed them; the transits were found where predicted." in summary
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
        r"<li>F2, on whether the dip is on the star \(rated hold; [^)]*\)\s*<ul>\s*<li>Finding: ",
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
            'As of 2027-02-20 the test is pending ("no light curve the test can use yet in S112").',
            "that test is not yet judged.",
        ),
        (
            {
                "result": "untested",
                "status": "untestable",
                "reason": "1 training season(s), need 2",
            },
            'As of 2027-02-20 the new data could not test it ("1 training season(s), need 2").',
            "the new data could not test that prediction.",
        ),
        (
            {"result": "missed", "status": "missed"},
            "As of 2027-02-20 the new sectors miss the prediction: in the cores of the predicted transits",
            "the transits were missing where predicted.",
        ),
    ):
        (record / "prereg.json").write_text(json.dumps({**PREREG, **result}))
        text = " ".join(paper(repo).split())
        assert said in text and summary in text
        assert "untestable" not in text and "A replicated season" not in text


def test_the_paper_says_how_the_signal_was_found(tmp_path, monkeypatch, no_pdf):
    _, repo = published(tmp_path, monkeypatch)
    text = paper(repo)
    found = " ".join(td.section(text, "How it was found").split())
    sample = tomllib.loads(tv.SEARCH.read_text())["sample"]
    assert (
        f"in the light curves of its sample: {SAMPLE} stars from the TESS Input Catalog with an effective "
        f"temperature above {sample['teff_min']:g} K and up to {sample['teff_max']:g} K" in found
    )
    assert f"the sample's {SAMPLE} stars to the {NULL_STARS} stars the null search covered" in found
    assert "gives an expected 1.03 false alarms at or above the threshold" in found
    assert f"`results/benchmarks/{INJECT_RUN}/completeness_snr.csv`" in found
    # Triage's row for the signal, under the criteria the vetting run recorded for it.
    assert (
        "Triage then screened every signal at or above the threshold, under its criteria triage-v1. This signal "
        "passed its novelty check, LEO-Vetter's false-alarm and flux-level tests (planet candidate at flux level) "
        "and its pixel check, and was shortlisted." in found
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


def test_triage_and_the_novelty_check_are_said_in_words(tmp_path):
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
        "Triage then screened every signal at or above the threshold. This signal's novelty check passed, "
        "LEO-Vetter's tests failed and triage did not run its pixel check, so triage did not shortlist it."
    )
    ran = pd.Series({**row, "pixels": "fail", "pixels_reason": 'centroid offset 20.1" beyond 15"'})
    second = preprint._triage(ran, made, {"signal": {"kind": "second"}})
    assert "and its pixel check failed, so triage did not shortlist it." in second
    assert second.endswith(
        "It came to vetting on tess-hunt's second list, of SPOC threshold-crossing events that never became TOIs "
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
    assert preprint._novelty_said(two) == "the novelty check fails: A and B match the signal"
    spoc = {
        "outcome": "inconclusive",
        "reason": "known to SPOC only",
        "evidence": {"category": "known_to_spoc"},
    }
    assert (
        preprint._novelty_said(spoc) == 'the novelty check is inconclusive ("known to SPOC only")'
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
        "a re-vet on a light curve that adds Sector 66 (SPOC), takes a newer delivery of Sector 64, whose earlier "
        "one had suspect timestamps and replaces Sector 65's QLP light curve with TESS-SPOC's"
    )
    (version / "merge.json").write_text(json.dumps({"1": {"sectors": {"64": {"status": "kept"}}}}))
    assert preprint._changed(version) == "a re-vet on the same light curve"


def test_the_paper_says_what_vetting_leaves_open(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    text = paper(repo)
    vetted = " ".join(td.section(text, "How it was vetted").split())
    left = " ".join(td.section(text, "What it can't rule out").split())
    # TRICERATOPS gave the neighbour table's one possible host zero depth (decision 0026, Ruling M).
    assert (
        "Its apertures take too little light from 1 of the neighbour table's 1 possible host to make the dip, so "
        "it gave that star zero depth and weighed no scenario on it (decision record 0026)."
        in vetted
    )
    assert (
        "Over 3 runs on Sectors 1 and 2 at 1800-s exposures, folded and binned in phase," in vetted
    )
    assert (
        "these runs lack a contrast curve and 2-minute data, so their FPP does not earn it."
        in vetted
    )
    # Each sector's offset, and the timing-suspect sector the pass rests on.
    assert (
        "Sector 64, 9.7 arcsec (quality 0.95), a timing-suspect sector the vetting run left out."
        in vetted
    )
    assert (
        "Its pass rests on Sector 64's offset, the best-quality sector's, from a sector the vetting run left out "
        "for suspect timestamps." in vetted
    )
    assert (
        "TOI-1399.01, whose dip comes from a nearby binary inside that limit, passes the check (decision record "
        "0032)." in vetted
    )
    assert "11.6" not in vetted
    assert (
        "1 of the neighbour table's 1 possible host lies within the pixel check's 15 arcsec of the target"
        in left
    )
    assert "TRICERATOPS weighed no scenario on it." in left
    # ModShift's secondary at any phase, from triage's evidence.
    m = tv.MODSHIFT
    assert (
        f"its strongest is {m['sig_sec']:.3g} sigma at phase {m['phs_sec']:.3g} (depth {m['dep_sec'] * 1e6:.0f} "
        f"ppm), against a primary of {m['sig_pri']:.3g} sigma and a red-noise factor, Fred, of {m['Fred']:.3g}."
        in vetted
    )
    assert (
        f"where only ModShift looks: its strongest secondary is at {m['sig_sec']:.3g} sigma" in left
    )
    assert "Each sector's depth errors are scaled by its red-noise factor, beta" in vetted
    # ExoFOP's listings on the star, and the imaging that did not go into TRICERATOPS.
    # The fixture's ExoFOP rows, as the literature search keeps them.
    assert (
        "ExoFOP lists TOIs TOI 266.01 (CP) and TOI 266.02 (CP), CTOI TIC 164767175.03 (PC), the confirmed planets "
        "HIP 8152 b, HIP 8152 c and 1 high-resolution imaging observation for the star." in vetted
    )
    assert "1 high-resolution imaging observation of the star, which did not go into it." in left
    held_out = " ".join(td.section(text, "The held-out seasons and the preregistered test").split())
    # The fixture's light curve gives one season.
    assert (
        "For this signal the check passed: of its 1 season, 1 could be tested and 1 was predicted."
        in held_out
    )
    assert (
        "This record holds no preregistered test of a later season (decision record 0040)."
        in held_out
    )
    made = json.loads((record / "provenance-checks.json").read_text())
    assert (
        f"As of the vetting run ({made['started_at'][:10]}), tess-point (Burke et al. 2020) placed the star in "
        "TESS Sectors 110, 111 and 115, still to be observed then." in " ".join(text.split())
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
        "Its pass rests on the best-quality sector's offset, which no single sector above reports."
        in text
    )
    assert "it is 1.30 in Sector 1." in text
    assert "of its 1 season, 0 could be tested and 0 were predicted." in text
    assert "could not be tested: the depth expected there is too small against its error." in text
    assert "weighed no scenario" not in text
    assert (
        "None of the neighbour table's 1 possible host lies within the pixel check's 15 arcsec"
        in text
    )
    assert (
        "The runs also meet the conditions decision record 0026 sets for Giacalone et al.'s \"validated"
        in text
    )
    assert "The record holds no ModShift result (no --triage-run given)." in text
    assert "and the record holds no ModShift result to look there." in text


def test_how_tess_hunt_works_is_said_once(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    made = json.loads((record / "provenance-checks.json").read_text())
    works = " ".join(td.section(paper(repo), "How tess-hunt works").split())
    assert (
        f"(https://example.org/tess-hunt/tree/{made['git']['commit']}/docs/decisions); this paper cites each by its "
        "number" in works
    )
    holdout = tomllib.loads(tv.VET3.read_text())["holdout"]
    assert f"no gap longer than {holdout['season_gap_days']:g} days between them." in works
    assert "set aside (decision record 0042); no row of ExoFOP's planet parameters" in works
    assert "a row of a listing set aside that way apart" in works
    # A second-list row's bar names its promotion (decision 0013).
    pixels = json.loads((record / "checks.json").read_text())["pixels"]
    (record / "pixels.json").write_text(json.dumps(pixels))
    td.edit_json(record / "checks.json", lambda c: c["signal"].update(kind="second"))
    found = preprint.values(record, preprint.load_author(repo / preprint.AUTHOR), repo)
    assert found["bar_promotion"] == (
        ", or the maintainer promoted a SPOC threshold-crossing event that never became a TOI (decision record "
        "0013)"
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
    assert "or in a note beside it, stays under ESA's CC BY-NC 3.0 IGO terms" in available
    assert "the ExoFOP listings the paper names stay under ExoFOP's terms" in available
    assert "| `checks.json` | each vetting check's outcome" in td.section(
        text, "Data and code availability"
    )
