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
    (search / "provenance.json").write_text(
        json.dumps({"run_id": tv.SEARCH_RUN, "stage": "search", "threshold": threshold})
    )
    (results / "benchmarks" / THRESHOLD_RUN).mkdir()
    (results / "benchmarks" / THRESHOLD_RUN / "threshold.json").write_text(
        json.dumps(
            {
                "threshold": threshold["value"],
                "null_run": NULL_RUN,
                "expected_false_alarms": 1.0290358859012372,
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
    triage = results / "triage" / tv.TRIAGE_RUN
    triage.mkdir(parents=True)
    pd.DataFrame(
        [{"tic": 1, "rank": 1, "sde": 31.4159}, {"tic": 1, "rank": 2, "sde": 21.0}]
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


def published(tmp_path, monkeypatch, call: str = tc.PASSED) -> tuple[dict[str, Path], Path]:
    """1-1's record published from production runs with `call`, a pass by default, as
    `test_a_pass_the_record_supports_is_published` publishes it, in a repo of its own."""
    run, suspect = td.vetting_runs(tmp_path, monkeypatch)
    # Every check passed and the literature search was complete, as a pass needs.
    td.edit_json(
        run / "signals" / NAME / "checks.json",
        lambda c: next(x for x in c["checks"] if x["check"] == "holdout").update(
            outcome="pass", reason="every held-out season predicted"
        ),
    )
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

    def spread(value: dict) -> str:
        return f"{value['median']:.2f} (-{value['minus']:.2f}, +{value['plus']:.2f})"

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
    }
    assert {key: found[key] for key in expected} == expected
    text = paper(repo)
    for key in ("period", "t0", "fpp", "sde", "threshold", "inject_run", "commit"):
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
    summary = td.section(paper(repo), "Summary")
    assert "planet candidate" in summary
    for claim in ("confirmed", "discovered a planet", "validated"):
        assert claim not in summary.lower()


def test_a_note_0037_added_sits_under_the_quoted_finding(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    record = repo / "results" / "vetting" / NAME
    (record / "review-notes.toml").write_text(NOTES)
    commit(repo)
    text = td.section(paper(repo), "What it can't rule out")
    note = "    - **Note added on {} under decision 0037, not part of the review or the call:** {}"
    f2 = note.format("2026-10-26", "The star is 12.4 arcsec away; the review rounds up.")
    f1 = note.format("2026-10-27", "Sector 2 carries most of it.")
    # Under the confirmed finding's quoted claim, before the call's answer.
    assert (
        "- F2 (on the star, hold)\n"
        "    - Finding: a star 12.5 arcsec away could host the dip\n"
        f"{f2}\n"
        "    - Answer: TRICERATOPS weighed that star and the centroids sit on the target."
    ) in text
    assert f"- F1 (real and new): one sector carries most of the depth\n{f1}" in text
    # Worded as the dossier words a note, but for its link to the decision.
    review = calls.load_review(record / "review.json")
    quoted = dossier.render_review(review, calls.load_notes(record / "review-notes.toml", review))
    said = re.sub(r"\[(decision 0037)\]\([^)]*\)", r"\1", quoted)
    for line in (f1, f2):
        assert line.removeprefix("    - ") in said


def test_a_versions_paper_names_its_records(tmp_path, monkeypatch):
    repo = held_r2(tmp_path, monkeypatch)
    r2 = repo / "results" / "vetting" / NAME / "r2"
    # r2 called passed, to render it; the bar is passed_record's, tested above.
    (r2 / "call.toml").write_text(tc.edit(tc.PASSED, "44926986-1", NAME))
    text = preprint.render(r2, preprint.load_author(repo / preprint.AUTHOR), repo)
    made = json.loads((r2 / "provenance-checks.json").read_text())
    available = td.section(text, "Data and code availability")
    assert f"vetting run {made['run_id']} ran it" in available
    assert f"at commit {made['git']['commit']}" in available
    assert "records, from the first to version r2, from which this paper is rendered" in available
    assert "the one the vetting run of version r2 read" in available
    assert f"Vetting run {made['run_id']} applied" in text


def test_the_paper_names_the_claim_date_and_any_0042_listing(tmp_path, monkeypatch):
    _, repo = published(tmp_path, monkeypatch)
    public = td.section(paper(repo), "When it was made public")
    assert (
        "tess-hunt first made this signal public on 2026-10-28, in "
        "https://doi.org/10.5281/zenodo.23745923." in public
    )
    assert "ExoFOP first listed" not in public

    # A pass that stands because decision 0042 excepts a TOI listed after the claim.
    other = tmp_path / "claimed"
    other.mkdir()
    runs, repo, argv = td.claimed_pass(other, monkeypatch)
    assert main([*argv, *td.flags(runs, "claims")]) == 0
    prepared(repo, monkeypatch)
    text = paper(repo)
    public = td.section(text, "When it was made public")
    assert "tess-hunt first made this signal public on 2026-10-28" in public
    assert "ExoFOP first listed TOI-7001.01 on the star on 2027-03-01, after that day" in public
    assert "decision record 0042" in public
    # The paper says novelty failed on the snapshot and passed without the later listing.
    vetted = td.section(text, "How it was vetted")
    assert "novelty is fail: matches TOI TOI-7001.01" in vetted
    assert "novelty is pass: no known object matches" in vetted
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
    assert "written by an AI model, claude-opus-5-5" in text
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
    # The description names the files the second licence covers.
    description = form.split("## Description\n")[1].split("\n## ")[0]
    gaia = sorted(name for name in GAIA_FILES if (record / name).is_file())
    assert (
        f"({dossier._words([f'`{name}`' for name in gaia])}, in each record's directory)"
        in description
    )
    assert "https://example.org/tess-hunt" in form
    assert "zenodo.99999999" not in form

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
    assert f"doi:{DOI}" in text and "replicated (predicted): depth 500 ppm" in text
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
    assert re.search(r"<li>F2 \(on the star, hold\)\s*<ul>\s*<li>Finding: ", page)
