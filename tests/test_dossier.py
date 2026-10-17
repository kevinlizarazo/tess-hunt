import json
import shutil
import stat
from pathlib import Path

import pytest
import test_calls as tc
import test_literature as tl
import test_vetting as tv

from tess_hunt import dossier, literature, vetting
from tess_hunt.cli import main
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file

NAME = "1-1"
FPP = [0.011, 0.013, 0.012]
NFPP = [0.0004, 0.0005, 0.0003]
REVIEW = {**tc.REVIEW, "signal": NAME}
HELD = tc.edit(tc.HELD, 'signal = "44926986-1"', f'signal = "{NAME}"')


def writable(path: Path) -> None:
    """Finished runs are read-only; a test that edits one makes it writable first."""
    for p in [path, *path.rglob("*")]:
        p.chmod(p.stat().st_mode | stat.S_IWUSR)


def edit_json(path: Path, change) -> None:
    writable(path.parent)
    data = json.loads(path.read_text())
    change(data)
    path.write_text(json.dumps(data))


def vetting_runs(tmp_path, monkeypatch) -> tuple[Path, Path]:
    """A vetting run with triage's evidence beside it, and its evidence-only twin."""
    # The targets row as the sample's carries it: a TIC Teff and a Gaia DR3 RUWE.
    monkeypatch.setattr(tv, "CANDIDATE", {**tv.CANDIDATE, "teff": 5800.0, "ruwe": 0.85})
    argv, _ = tv.setup(tmp_path, monkeypatch, signals=tv.SIGNALS[:1], suspect={64}, fit=tv.fake_fit)
    # Fetched SPOC sources carry CROWDSAP; the synthetic ones don't.
    path = tmp_path / "data" / "lc" / "1.npz"
    lc = LightCurve.load(path)
    for i, source in enumerate(lc.sources.values()):
        source["crowdsap"] = 0.9 + 0.01 * i
    lc.save(path)
    triage = tv.triage_run(tmp_path)
    assert main([*argv, "--triage-run", str(triage)]) == 0
    assert main([*argv, "--triage-run", str(triage), "--include-suspect"]) == 0
    runs = {
        json.loads((p / "provenance.json").read_text())["evidence_only"]: p
        for p in (tmp_path / "data" / "runs").glob("*-vetting-run-*")
    }
    return runs[False], runs[True]


def made_run(tmp_path: Path, stage: str, vetting_run: Path, files: dict, tag: str = "a") -> Path:
    """A finished `stage` run made from `vetting_run`, holding `files` ({name: {file name: content}})."""
    made = json.loads((vetting_run / "provenance.json").read_text())
    run_id = f"20261020T000000Z-{stage}-abc1234-{tag}"
    path = tmp_path / "data" / "runs" / run_id
    path.mkdir(parents=True)
    for name, contents in files.items():
        (path / "signals" / name).mkdir(parents=True)
        for file, content in contents.items():
            text = content if isinstance(content, str) else json.dumps(content, indent=2)
            (path / "signals" / name / file).write_text(text)
    provenance = {
        "run_id": run_id,
        "stage": stage,
        "production": False,
        "started_at": "2026-10-20T00:00:00+00:00",
        "ended_at": "2026-10-20T01:00:00+00:00",
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
        "criteria": made["criteria"],
        "vetting_run": vetting_run.name,
        "inputs": {
            f"checks_{name}": {
                "file": "checks.json",
                "sha256": sha256_file(vetting_run / "signals" / name / "checks.json"),
            }
            for name in files
        },
        "summary": {},
    }
    (path / "provenance.json").write_text(json.dumps(provenance, indent=2))
    return path


def triceratops_record(vetting_run: Path, outcome: str = "pass") -> dict:
    mean = {"fpp_mean": sum(FPP) / 3, "nfpp_mean": sum(NFPP) / 3}
    return {
        "check": "triceratops",
        "outcome": outcome,
        "reason": f"mean FPP {mean['fpp_mean']:.3g} < 0.5 and mean NFPP {mean['nfpp_mean']:.3g} < 0.001 "
        "over 3 run(s): likely a planet",
        "signal": {"name": NAME, "tic": 1},
        "vetting_run": vetting_run.name,
        "ephemeris_from": {"ephemeris": "fit_prior", "duration": "fit_prior"},
        "contrast": [],
        "evidence": {
            "fpp": FPP,
            "nfpp": NFPP,
            **mean,
            "fpp_sd": 0.001,
            "nfpp_sd": 0.0001,
            "blockers": [],
            "validated_label": False,
            "ruwe": 0.85,
            "runs": 3,
            "draws": 100000,
            "bin_phase": True,
            "exposure_s": 1800.0,
            "sectors": [1, 2],
            "left_out": [],
            "hosts": [
                {
                    "source_id": 7,
                    "sep_arcsec": 12.0,
                    "required_depth": 0.17,
                    "tic": "99",
                    "distance_arcsec": 0.4,
                    "tdepth": 0.0,
                }
            ],
            "missing_hosts": [],
            "hosts_tdepth_zero": [7],
            "stopped": None,
            "field_population": True,
        },
    }


def literature_record(vetting_run: Path, monkeypatch) -> dict:
    monkeypatch.setattr(literature.time, "sleep", lambda s: None)
    web = tl.Web(names={1: ["TIC 1", "HD 1"]}, hits={("arxiv", "HD 1"): [tl.AKANA]})
    # Without the ADS token, as every literature run so far: inconclusive.
    search = {
        "simbad": literature.simbad_record(1, web),
        **literature.search_all(1, ["TIC 1", "HD 1"], web, None, tl.CFG),
    }
    check = literature.literature_check(search).to_dict()
    return {
        "signal": {"name": NAME, "tic": 1},
        "vetting_run": vetting_run.name,
        "search": search,
        **check,
    }


def all_runs(tmp_path, monkeypatch) -> dict[str, Path]:
    run, suspect = vetting_runs(tmp_path, monkeypatch)
    tric = made_run(
        tmp_path,
        "vetting-triceratops",
        run,
        {
            NAME: {
                "triceratops.json": triceratops_record(run),
                "probs.csv": "ID,scenario,prob\n1,TP,0.98\n",
            }
        },
    )
    lit = made_run(
        tmp_path,
        "vetting-literature",
        run,
        {NAME: {"literature.json": literature_record(run, monkeypatch)}},
    )
    return {"run": run, "suspect": suspect, "triceratops": tric, "literature": lit}


def flags(runs: dict[str, Path], *roles: str) -> list[str]:
    flag = {
        "run": "--run",
        "suspect": "--evidence-only",
        "triceratops": "--triceratops",
        "literature": "--literature",
    }
    return [a for role in roles for a in (flag[role], str(runs[role]))]


def draft(tmp_path, monkeypatch, review=None, call=None) -> tuple[Path, dict[str, Path]]:
    runs = all_runs(tmp_path, monkeypatch)
    out = tmp_path / "drafts"
    if review or call:
        (out / NAME).mkdir(parents=True)
        if review:
            (out / NAME / "review.json").write_text(json.dumps(review))
        if call:
            (out / NAME / "call.toml").write_text(call)
    roles = ("run", "suspect", "triceratops", "literature")
    assert main(["vetting", "dossier", *flags(runs, *roles), "--out", str(out)]) == 0
    return out / NAME, runs


def test_page_one_answers_the_three_questions(tmp_path, monkeypatch):
    signal, runs = draft(tmp_path, monkeypatch, review=REVIEW, call=HELD)
    text = (signal / "dossier.md").read_text()
    assert text == dossier.render(signal)
    page_one, rest = text.split("\n## Plots\n")
    checks = json.loads((signal / "checks.json").read_text())
    tric = json.loads((signal / "triceratops.json").read_text())["evidence"]

    # The signal, the star and the criteria it was judged under.
    assert "TIC 1" in page_one and "Gaia DR3 101" in page_one and "HD 1" in page_one
    assert "5800 K" in page_one and "RUWE" in page_one and "0.85" in page_one
    assert "CROWDSAP" in page_one and "0.900" in page_one
    assert "search-v2" in page_one and "vet-v3" in page_one and runs["run"].name in page_one
    # Every check with its outcome and reason.
    for c in checks["checks"]:
        assert f"| {c['check']} | {c['outcome']} | {c['reason']} |" in page_one

    on_star = section(page_one, "On the star?")
    assert "| 1 | 10.9 | 0.92 |" in on_star and "| 2 | 12.8 | 0.84 |" in on_star
    # Beside each possible host, the TRICERATOPS star matched to it and the depth TRICERATOPS gave that star.
    [host] = checks["neighbours"]["evidence"]["possible_hosts"]
    needed = f"{100 * host['required_depth']:.3g}%"
    assert f'| Gaia DR3 7 | 12.0 | {needed} | TIC 99 (0.4") | 0% |' in on_star
    assert f"{tric['nfpp_mean']:.3g}" in on_star
    assert "zero depth" in on_star and "RUWE 0.85" in on_star

    planet = section(page_one, "A planet rather than a binary?")
    for name in ("odd_even", "secondary", "shape", "density", "radius"):
        reason = next(c["reason"] for c in checks["checks"] if c["check"] == name)
        assert reason in planet, name
    assert "3.1 sigma" in planet and "0.759" in planet and "Fred 1.12" in planet
    assert "period ratio 1.5" in planet
    assert f"{tric['fpp_mean']:.3g}" in planet
    # Which fit each number comes from, and Rp from both.
    assert "flat-prior fit" in planet and "density-prior fit" in planet
    assert "the radius check reads the flat-prior fit" in planet
    rp = checks["fit_prior"]["rp_rearth"]
    assert f"{rp['median']:.2f}" in planet and f"{rp['p16']:.2f}" in planet

    real = section(page_one, "Real and new?")
    for name in ("signal_present", "holdout", "sector_depth", "novelty"):
        reason = next(c["reason"] for c in checks["checks"] if c["check"] == name)
        assert reason in real, name
    assert "inconclusive" in real and "ads TIC 1: not_searched" in real
    assert "TOI 266.01" in real and "HIP 8152 b" in real

    looks = section(page_one, "Next TESS looks")
    assert "110, 111 and 115" in looks
    for w in (w for w in checks["windows"] if "epoch" in w):
        assert f"{w['mid_btjd']:.3f}" in looks and f"{w['sd_minutes']:.1f}" in looks
    assert "2-min" in looks and "DDT" in looks

    # Then the rest, in the design's order.
    order = [
        "## Catalogued rows on the star",
        "## With the timing-suspect sectors",
        "## Review",
        "## Call",
    ]
    assert [rest.index(h) for h in order] == sorted(rest.index(h) for h in order)
    assert "plots/transits.png" in rest and "evidence only" in rest
    assert "High-resolution imaging" in rest


def section(text: str, heading: str) -> str:
    return text.split(f"\n## {heading}\n")[1].split("\n## ")[0]


def test_render_fails_on_a_missing_value(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch)
    dossier.render(signal)
    path = signal / "checks.json"
    good = path.read_text()
    for change in (
        lambda c: c["star"].pop("teff"),
        lambda c: next(w for w in c["windows"] if "epoch" in w).pop("sd_minutes"),
        lambda c: c["checks"][0].pop("reason"),
    ):
        path.write_text(good)
        edit_json(path, change)
        with pytest.raises(KeyError):
            dossier.render(signal)
    path.write_text(good)
    # A template that names a value nobody filled in raises too.
    monkeypatch.setattr(dossier, "PAGE", dossier.Template(dossier.PAGE.template + "$unfilled\n"))
    with pytest.raises(KeyError, match="unfilled"):
        dossier.render(signal)


def test_review_renders_findings_ratings_and_both_refuters(tmp_path):
    text = dossier.render_review(REVIEW)
    assert "claude-opus-5-5" in text and "2026-10-27" in text and "One hold stands." in text
    for finding in REVIEW["findings"]:
        assert finding["claim"] in text and finding["evidence"] in text
    assert "F2 (on the star, hold): confirmed" in text
    assert "F3 (a planet, kill): refuted" in text
    assert "F1 (real and new, note)" in text
    assert tc.REFUTED["reason"] in text and tc.STANDS["reason"] in text
    assert "2306.16587" in text


def test_dossier_draft_says_what_it_lacks(tmp_path, monkeypatch):
    run, _ = vetting_runs(tmp_path, monkeypatch)
    out = tmp_path / "drafts"
    assert main(["vetting", "dossier", "--run", str(run), "--out", str(out)]) == 0
    text = (out / NAME / "dossier.md").read_text()
    assert "No TRICERATOPS run was given." in text and "No literature run was given." in text
    assert "No review yet." in text and "No call yet." in text
    assert (out / NAME / "plots" / "transits.png").is_file()
    # A TRICERATOPS run that never judged the signal (a check killed it) is named, not taken for a pass.
    tric = made_run(tmp_path, "vetting-triceratops", run, {})
    argv = ["vetting", "dossier", "--run", str(run), "--triceratops", str(tric), "--out", str(out)]
    assert main(argv) == 0
    text = (out / NAME / "dossier.md").read_text()
    assert f"TRICERATOPS run {tric.name} did not judge this signal." in text
    assert not (out / NAME / "triceratops.json").exists()
    # Drafts go outside the repo's results.
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    with pytest.raises(SystemExit, match="outside"):
        main(["vetting", "dossier", "--run", str(run), "--out", str(repo / "results" / "vetting")])


def production(*runs: Path) -> None:
    for run in runs:
        edit_json(run / "provenance.json", lambda p: p.update(production=True))


def published(repo: Path) -> dict[str, str]:
    root = repo / "results" / "vetting"
    return {str(p.relative_to(root)): sha256_file(p) for p in root.rglob("*") if p.is_file()}


def publish_argv(runs, *roles) -> list[str]:
    return ["vetting", "publish", "--name", NAME, *flags(runs, *roles)]


def test_publish_refuses_without_a_call(tmp_path, monkeypatch):
    runs = all_runs(tmp_path, monkeypatch)
    production(*runs.values())
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    argv = publish_argv(runs, "run", "triceratops", "literature", "suspect")
    with pytest.raises(SystemExit, match="no call.toml"):
        main(argv)
    assert not (repo / "results" / "vetting").exists() or published(repo) == {}

    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(HELD)
    (signal / "review.json").write_text(json.dumps(REVIEW))
    assert main(argv) == 0
    files = published(repo)
    run = runs["run"] / "signals" / NAME
    assert files[f"{NAME}/checks.json"] == sha256_file(run / "checks.json")
    assert files[f"{NAME}/neighbours.csv"] == sha256_file(run / "neighbours.csv")
    assert files[f"{NAME}/plots/transits.png"] == sha256_file(run / "plots" / "transits.png")
    assert files[f"{NAME}/provenance-checks.json"] == sha256_file(runs["run"] / "provenance.json")
    tric = runs["triceratops"] / "signals" / NAME
    assert files[f"{NAME}/triceratops.json"] == sha256_file(tric / "triceratops.json")
    assert files[f"{NAME}/probs.csv"] == sha256_file(tric / "probs.csv")
    lit = runs["literature"] / "signals" / NAME / "literature.json"
    assert files[f"{NAME}/literature.json"] == sha256_file(lit)
    suspect = runs["suspect"] / "signals" / NAME / "checks.json"
    assert files[f"{NAME}/checks-with-suspect.json"] == sha256_file(suspect)
    assert (signal / "dossier.md").read_text() == dossier.render(signal)
    assert (signal / "checks.json").stat().st_mode & 0o777 == 0o644
    readme = (repo / "results" / "vetting" / "README.md").read_text()
    assert f"[{NAME}]({NAME}/dossier.md) | held |" in readme

    # Publishing the same runs again re-renders only the dossier and the README.
    (signal / "dossier.md").write_text("stale\n")
    assert main(argv) == 0
    assert (signal / "dossier.md").read_text() == dossier.render(signal)
    # Another TRICERATOPS run would overwrite published files: refused, nothing touched.
    other = made_run(
        tmp_path,
        "vetting-triceratops",
        runs["run"],
        {NAME: {"triceratops.json": triceratops_record(runs["run"], "inconclusive")}},
        tag="b",
    )
    production(other)
    before = published(repo)
    with pytest.raises(SystemExit, match="never overwritten"):
        main([*publish_argv(runs, "run", "literature"), "--triceratops", str(other)])
    assert published(repo) == before


def test_publish_refuses_a_pass_the_evidence_does_not_support(tmp_path, monkeypatch):
    runs = all_runs(tmp_path, monkeypatch)
    production(*runs.values())
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(
        tc.edit(tc.PASSED, 'signal = "44926986-1"', f'signal = "{NAME}"')
    )
    (signal / "review.json").write_text(json.dumps(REVIEW))
    before = published(repo)
    # The literature search went without ADS, so it is inconclusive and can't carry a pass.
    with pytest.raises(SystemExit, match="the literature search is inconclusive"):
        main(publish_argv(runs, "run", "triceratops", "literature"))
    assert published(repo) == before


def other_vetting_run(tmp_path, runs) -> list[str]:
    tric = made_run(
        tmp_path,
        "vetting-triceratops",
        runs["suspect"],
        {NAME: {"triceratops.json": triceratops_record(runs["suspect"])}},
        tag="c",
    )
    production(tric)
    return [
        "--run",
        str(runs["run"]),
        "--triceratops",
        str(tric),
        "--literature",
        str(runs["literature"]),
    ]


def other_criteria(tmp_path, runs) -> list[str]:
    edit_json(
        runs["literature"] / "provenance.json",
        lambda p: p["criteria"][1].update(sha256="0" * 64),
    )
    return flags(runs, "run", "triceratops", "literature")


def changed_checks(tmp_path, runs) -> list[str]:
    edit_json(
        runs["triceratops"] / "provenance.json",
        lambda p: p["inputs"][f"checks_{NAME}"].update(sha256="0" * 64),
    )
    return flags(runs, "run", "triceratops", "literature")


def main_as_evidence_only(tmp_path, runs) -> list[str]:
    return [*flags(runs, "run", "triceratops", "literature"), "--evidence-only", str(runs["run"])]


def evidence_only_as_main(tmp_path, runs) -> list[str]:
    return ["--run", str(runs["suspect"]), *flags(runs, "triceratops", "literature")]


def not_production(tmp_path, runs) -> list[str]:
    edit_json(runs["literature"] / "provenance.json", lambda p: p.update(production=False))
    return flags(runs, "run", "triceratops", "literature")


@pytest.mark.parametrize(
    "argv, message",
    [
        (other_vetting_run, "was made from"),
        (other_criteria, "criteria"),
        (changed_checks, "checks.json"),
        (main_as_evidence_only, "not an evidence-only"),
        (evidence_only_as_main, "evidence-only"),
        (not_production, "not a production"),
    ],
)
def test_publish_refuses_runs_that_do_not_belong_together(tmp_path, monkeypatch, argv, message):
    runs = all_runs(tmp_path, monkeypatch)
    production(*runs.values())
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(HELD)
    before = published(repo)
    with pytest.raises(SystemExit, match=message):
        main(["vetting", "publish", "--name", NAME, *argv(tmp_path, runs)])
    assert published(repo) == before


def test_readme_lists_every_call(tmp_path):
    root = tmp_path / "vetting"
    held = tc.signal_dir(root, call=tc.HELD)
    killed = tc.signal_dir(
        root,
        call=tc.KILLED.replace("It fails", "It | fails"),
        name="48010903-1",
        outcomes={"odd_even": "fail"},
    )
    tc.signal_dir(root, call=None, name="103312990-1")
    shutil.copy(held / "call.toml", root / "not-a-signal.toml")
    text = dossier.readme(root)
    rows = [line for line in text.splitlines() if line.startswith("| [")]
    assert rows == [
        f"| [{held.name}]({held.name}/dossier.md) | held | 2026-10-28 | The public data can't tell the two stars "
        "apart. |",
        f"| [{killed.name}]({killed.name}/dossier.md) | killed | 2026-10-28 | It \\| fails odd and even. |",
    ]
