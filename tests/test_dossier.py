import json
import re
import shutil
import socket
import stat
from dataclasses import replace
from pathlib import Path

import pytest
import requests
import test_calls as tc
import test_literature as tl
import test_tricera as tt
import test_vetting as tv
from astropy.utils import iers

from tess_hunt import dossier, literature, provenance, tricera, vetting
from tess_hunt.cli import main
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file

NAME = "1-1"
REPO = Path(__file__).resolve().parents[1]
FPP = [0.011, 0.013, 0.012]
NFPP = [0.0004, 0.0005, 0.0003]
REVIEW = {**tc.REVIEW, "signal": NAME}
S64 = {"sector": 64, "offset_arcsec": 9.7, "quality": 0.95}
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
    # Triage measured the timing-suspect S64 too, and its pass reads S64's offset, the best-quality one.
    evidence = triage / "evidence" / "1-1.json"
    edit_json(evidence, lambda e: e["pixels"]["evidence"]["sectors"].append(S64))
    edit_json(
        evidence, lambda e: e["pixels"]["evidence"].update(offset_qual_arcsec=S64["offset_arcsec"])
    )
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
            "points": 120,
            "raised": None,
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
    simbad = literature.simbad_record(1, web)
    search = {
        "simbad": simbad,
        **literature.search_all(1, ["TIC 1", "HD 1"], web, None, tl.CFG, simbad=simbad),
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
    return {
        "run": run,
        "suspect": suspect,
        "triceratops": tric,
        "literature": lit,
        "titles": titles_run(tmp_path, lit),
    }


def titles_run(tmp_path: Path, lit: Path, titles: dict | None = None, tag: str = "a") -> Path:
    """A finished titles run made from the literature run `lit`, holding OpenAlex's `titles` by DOI."""
    run_id = f"20261026T000000Z-vetting-titles-abc1234-{tag}"
    path = tmp_path / "data" / "runs" / run_id
    path.mkdir(parents=True)
    lookups = path / "titles.json"
    lookups.write_text(json.dumps({"literature_run": lit.name, "titles": titles or {}}))
    records = sorted((lit / "signals").glob("*/literature.json"))
    provenance = {
        "run_id": run_id,
        "stage": "vetting-titles",
        "production": False,
        "started_at": "2026-10-26T00:00:00+00:00",
        "ended_at": "2026-10-26T00:01:00+00:00",
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
        "criteria": [],
        "literature_run": lit.name,
        "inputs": {
            f"literature_{p.parent.name}": {"file": p.name, "sha256": sha256_file(p)}
            for p in records
        },
        "summary": {"titles_sha256": sha256_file(lookups)},
    }
    (path / "provenance.json").write_text(json.dumps(provenance, indent=2))
    return path


def flags(runs: dict[str, Path], *roles: str) -> list[str]:
    flag = {
        "run": "--run",
        "suspect": "--evidence-only",
        "triceratops": "--triceratops",
        "literature": "--literature",
        "titles": "--titles",
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
    assert "| 1 | 10.9 | 0.92 |  |" in on_star and "| 2 | 12.8 | 0.84 |  |" in on_star
    # The suspect sector is marked, and the line above the table names the offset triage's pass rests on.
    assert (
        "| 64 | 9.7 | 0.95 | timing-suspect: vet-v3 leaves it out; the offset triage judged |"
        in on_star
    )
    assert "S64's, from a timing-suspect sector that vet-v3 leaves out." in on_star
    # Beside each possible host, the TRICERATOPS star matched to it and the depth TRICERATOPS gave that star.
    [host] = checks["neighbours"]["evidence"]["possible_hosts"]
    needed = f"{100 * host['required_depth']:.3g}%"
    assert f'| Gaia DR3 7 | 12.0 | {needed} | TIC 99 (0.4") | 0% |' in on_star
    # And what the separations run from (decision 0034).
    assert "its separation from the target (Gaia DR3 101, J2016.0)" in on_star
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


def test_decisions_are_linked_from_where_the_dossier_is_published(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch, review=REVIEW, call=HELD)
    text = (signal / "dossier.md").read_text()
    # A dossier sits in results/vetting/<name>/, three levels below the repo's root.
    linked = re.findall(r"\]\(\.\./\.\./\.\./(docs/decisions/[^)]+)\)", text)
    assert len(set(linked)) >= 3
    assert all((REPO / path).is_file() for path in linked)
    assert "M3 design" not in text and not re.search(r"(?<!\[)decision \d{4}", text)


def test_mid_utc_is_when_the_transit_is_seen_from_earth(monkeypatch):
    # Offline: no socket opens, and an IERS lookup would read only astropy's bundled table, which ends before these
    # dates and raises. A table another test loaded is dropped first, so none hides a lookup.
    def refuse(*args, **kwargs):
        raise OSError("no network in this test")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(iers.conf, "auto_download", False)
    monkeypatch.setattr(iers.IERS_Auto, "iers_table", None)
    # The milestone review's times from Earth, from Earth's barycentric position. Read as TDB without the light's
    # travel time, 423100454-1's epoch 197 was 15:27.
    stars = {
        "423100454-1": {"ra": 240.065424623734, "dec": -55.5634985842455},
        "241522065-1": {"ra": 206.303246517049, "dec": -53.3085956790006},
        "103312990-1": {"ra": 156.829227880851, "dec": -47.5203964706134},
    }
    for name, btjd, seen in (
        ("423100454-1", 4426.14466314464, "2027-01-20 15:31"),
        ("423100454-1", 4440.330851772605, "2027-02-03 19:58"),
        ("241522065-1", 4397.964907870579, "2026-12-23 11:12"),
        ("241522065-1", 4415.401623187308, "2027-01-09 21:40"),
        ("241522065-1", 4432.83834174134, "2027-01-27 08:07"),
        ("103312990-1", 4344.562970275405, "2026-10-31 01:33"),
        ("103312990-1", 4352.086115150675, "2026-11-07 14:06"),
        ("103312990-1", 4359.609270087955, "2026-11-15 02:39"),
    ):
        assert dossier._utc(btjd, stars[name]) == seen, (name, btjd)


def section(text: str, heading: str) -> str:
    return text.split(f"\n## {heading}\n")[1].split("\n## ")[0]


def test_real_and_new_says_when_ads_searched_only_the_phrase(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch)
    # With the token, and TIC 1 in neither SIMBAD nor NED: ADS's object service resolved nothing.
    web = tl.Web(names={})
    simbad = literature.simbad_record(1, web)
    search = {
        "simbad": simbad,
        **literature.search_all(1, ["TIC 1"], web, tl.TOKEN, tl.CFG, simbad=simbad),
    }
    check = literature.literature_check(search).to_dict()
    edit_json(signal / "literature.json", lambda r: r.update(search=search, **check))
    real = section(dossier.render(signal), "Real and new?")
    # Still a complete search: the by-name searches cover the star's other names.
    assert (
        "NASA ADS: pass, complete: 0 hits to screen. No catalog resolved the star, so ADS searched only the phrase "
        '"TIC 1" in the abstracts, titles and keywords of its astronomy collection. The hits are listed below.'
    ) in real


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


def test_the_review_and_the_call_are_quoted_with_notes_beside_them(tmp_path, monkeypatch):
    signal, runs = draft(tmp_path, monkeypatch, review=REVIEW, call=HELD)
    (signal / "review-notes.toml").write_text(tc.NOTE)
    # A draft made again keeps the notes beside the review and the call.
    roles = ("run", "suspect", "triceratops", "literature")
    assert main(["vetting", "dossier", *flags(runs, *roles), "--out", str(signal.parent)]) == 0
    text = (signal / "dossier.md").read_text()
    review, call = section(text, "Review"), section(text, "Call")
    # Each section says it quotes its file rather than rendering the runs (decision 0037).
    assert review.strip().startswith("Quoted from `review.json`")
    assert call.strip().startswith("Quoted from `call.toml`, the maintainer's words")
    assert "the review and the call are quoted" in text.split("\n## ")[0]
    # The note sits under F2, after its refuters and before F3; the review's own text is unchanged.
    f2 = review.split("### F2")[1].split("### F3")[0]
    assert f2.rstrip().endswith(
        "**Note added on 2026-10-26 under [decision 0037](../../../docs/decisions/0037-quoted-text-in-the-dossier.md), "
        "not part of the review or the call:** The magnitudes give 0.358."
    )
    assert REVIEW["findings"][1]["evidence"] in f2


def test_the_dossier_shows_no_machine_path_from_the_review_or_the_call(tmp_path, monkeypatch):
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    signal, _ = draft(tmp_path, monkeypatch, review=REVIEW, call=HELD)
    data = tmp_path / "data"
    evidence = (
        f"{data}/drafts/m3-r2/1-1/checks.json, run as {home}/code/tess-hunt/.venv/bin/python; the M3 design, "
        "C:\\code\\docs\\m3-design.md (/mnt/c/code/docs/m3-design.md), and C:/Users/someone/notes.md; "
        "/tmp/t13/1-1/two_star.py, docs/design.md and https://exofop.ipac.caltech.edu/tess/target.php stay"
    )
    review = {**REVIEW, "findings": [{**REVIEW["findings"][1], "evidence": evidence}]}
    (signal / "review.json").write_text(json.dumps(review))
    (signal / "call.toml").write_text(
        tc.edit(HELD, "can't tell the two stars apart.", f"can't tell, per {home}/notes.txt.")
    )
    text = dossier.render(signal)
    assert str(home) not in text and str(data) not in text
    assert "C:" not in text and "/mnt/c" not in text and "Users" not in text
    assert (
        "$TESS_HUNT_DATA/drafts/m3-r2/1-1/checks.json, run as ~/code/tess-hunt/.venv/bin/python; the M3 design, "
        "m3-design.md (m3-design.md), and notes.md; /tmp/t13/1-1/two_star.py, docs/design.md and "
        "https://exofop.ipac.caltech.edu/tess/target.php stay"
    ) in text
    assert "can't tell, per ~/notes.txt." in section(text, "Call")
    # review.json itself stays as written.
    assert json.loads((signal / "review.json").read_text())["findings"][0]["evidence"] == evidence


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
    argv = publish_argv(runs, "run", "triceratops", "literature", "suspect", "titles")
    # A literature record is published trimmed, which takes the titles run (decision 0038).
    with pytest.raises(SystemExit, match="give --titles"):
        main(publish_argv(runs, "run", "triceratops", "literature", "suspect"))
    # The maintainer has written another signal's call, not yet published.
    other = repo / "results" / "vetting" / "2-1"
    other.mkdir(parents=True)
    (other / "call.toml").write_text(tc.edit(HELD, f'signal = "{NAME}"', 'signal = "2-1"'))
    before = published(repo)
    with pytest.raises(SystemExit, match="no call.toml"):
        main(argv)
    assert published(repo) == before

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
    trimmed = literature.trim(
        json.loads(lit.read_text()), sha256_file(lit), {}, runs["titles"].name
    )
    assert json.loads((signal / "literature.json").read_text()) == trimmed
    assert trimmed["trim"]["source_sha256"] == sha256_file(lit)
    assert files[f"{NAME}/provenance-titles.json"] == sha256_file(
        runs["titles"] / "provenance.json"
    )
    suspect = runs["suspect"] / "signals" / NAME / "checks.json"
    assert files[f"{NAME}/checks-with-suspect.json"] == sha256_file(suspect)
    assert (signal / "dossier.md").read_text() == dossier.render(signal)
    assert (signal / "checks.json").stat().st_mode & 0o777 == 0o644
    readme = (repo / "results" / "vetting" / "README.md").read_text()
    assert f"[{NAME}]({NAME}/dossier.md) | held |" in readme
    # The unpublished call stands in no row, and it did not stop the publish.
    assert "2-1" not in readme

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
        main([*publish_argv(runs, "run", "literature", "titles"), "--triceratops", str(other)])
    assert published(repo) == before


def test_trim_applies_decision_0038_to_a_record_published_before_it(tmp_path, monkeypatch):
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    # The maintainer as CITATION.cff would name them; the review names them too.
    monkeypatch.setattr(provenance, "maintainer", lambda: ("Ada", "Lovelace"))
    runs = all_runs(tmp_path, monkeypatch)
    # The literature run's record holds ADS's hits and ExoFOP's comments, files and observers, as LIT3_RUN's did.
    record = {
        **tl.full_record(),
        "signal": {"name": NAME, "tic": 1},
        "vetting_run": runs["run"].name,
    }
    source = runs["literature"] / "signals" / NAME / "literature.json"
    source.write_text(json.dumps(record, indent=2))
    edit_json(
        runs["literature"] / "provenance.json",
        lambda p: p.update(summary={"signals": {NAME: {"sha256": sha256_file(source)}}}),
    )
    web = tl.Web(titles=tl.TITLES)
    lookups = {d: literature.openalex_title(web, d) for d in literature.to_look_up(record)}
    titles = titles_run(tmp_path, runs["literature"], lookups, tag="b")
    production(*runs.values(), titles)
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    # Published as before decision 0038: the runs' files unchanged, and a review naming the home directory and the
    # maintainer.
    signal = repo / "results" / "vetting" / NAME
    roles = {
        "checks": runs["run"],
        "triceratops": runs["triceratops"],
        "literature": runs["literature"],
    }
    vetting._copy(vetting._signal_files(roles, NAME), signal)
    data = tmp_path / "data"
    review = {
        **REVIEW,
        "summary": f"Read in {home}/code/tess-hunt and {data}/drafts/m3-r2/1-1/checks.json. Notes for Ada.",
    }
    (signal / "review.json").write_text(json.dumps(review, indent=2) + "\n")
    (signal / "call.toml").write_text(HELD)
    (signal / "dossier.md").write_text(dossier.render(signal))
    before = published(repo)

    argv = ["vetting", "trim", "--name", NAME, *flags(runs, "literature"), "--titles", str(titles)]
    assert main(argv) == 0
    after = published(repo)
    assert {k for k in after if before.get(k) != after[k]} == {
        f"{NAME}/literature.json",
        f"{NAME}/provenance-titles.json",
        f"{NAME}/review.json",
        f"{NAME}/dossier.md",
        "README.md",
    }
    assert json.loads((signal / "literature.json").read_text()) == literature.trim(
        record, sha256_file(source), lookups, titles.name
    )
    assert after[f"{NAME}/provenance-titles.json"] == sha256_file(titles / "provenance.json")
    # review.json changes only where it names the home and data directories, and the maintainer.
    text = (signal / "review.json").read_text()
    assert str(home) not in text and str(data) not in text
    summary = "Read in ~/code/tess-hunt and $TESS_HUNT_DATA/drafts/m3-r2/1-1/checks.json. Notes for the maintainer."
    assert json.loads(text) == {**review, "summary": summary}
    # The dossier: titles only from open sources, a blank one where none has the paper, no ExoFOP comment text.
    page = (signal / "dossier.md").read_text()
    assert page == dossier.render(signal)
    hits = section(page, "Literature hits")
    assert "Titles come only from open sources" in hits
    assert f"| {tl.AKANA['title']} | arXiv 2306.16587 |" in hits
    assert f"| {tl.TITLES[tl.ADS_DOI['doi']]} | doi {tl.ADS_DOI['doi']} |" in hits
    assert "|  | arXiv 2410.00002 |" in hits and "|  | 2023AJ....166..153A |" in hits
    for gone in (
        tl.ADS_ARXIV["title"],
        tl.ADS_BARE["title"],
        "a note on TOI 266.01",
        "observer1",
    ):
        assert gone not in page
    assert "Comments on ExoFOP" not in page and f"titles {titles.name}" in page

    # Again: nothing changes.
    assert main(argv) == 0
    assert published(repo) == after
    # Another titles run would overwrite the record.
    other = titles_run(tmp_path, runs["literature"], lookups, tag="c")
    production(other)
    with pytest.raises(SystemExit, match="another titles run"):
        main([*argv[:-1], str(other)])
    # A literature.json that is neither the run's file nor its trim is refused, and nothing is touched.
    edit_json(signal / "literature.json", lambda r: r["trim"].update(source_sha256="0" * 64))
    edited = published(repo)
    with pytest.raises(SystemExit, match="neither"):
        main(argv)
    assert published(repo) == edited


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
        main(publish_argv(runs, "run", "triceratops", "literature", "titles"))
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
        main(["vetting", "publish", "--name", NAME, *argv(tmp_path, runs), *flags(runs, "titles")])
    assert published(repo) == before


def test_readme_lists_every_call(tmp_path):
    root = tmp_path / "vetting"

    def published_dir(call, name, parent=root, **kwargs):
        call = tc.edit(call, f'signal = "{tc.NAME}"', f'signal = "{name}"')
        path = tc.signal_dir(parent, call=call, name=name, **kwargs)
        (path / "dossier.md").write_text("rendered\n")
        return path

    held = published_dir(tc.HELD, tc.NAME)
    killed = published_dir(
        tc.KILLED.replace("It fails", "It | fails"), "48010903-1", outcomes={"odd_even": "fail"}
    )
    # A record with no call, a call with no record (written before publishing), and a published call that no
    # longer stands on its record (a kill resting on a check that passed): none is a row.
    published_dir(tc.HELD, "103312990-1").joinpath("call.toml").unlink()
    (root / "2-1").mkdir()
    (root / "2-1" / "call.toml").write_text(
        tc.edit(tc.HELD, f'signal = "{tc.NAME}"', 'signal = "2-1"')
    )
    published_dir(tc.KILLED, "399023421-1")
    shutil.copy(held / "call.toml", root / "not-a-signal.toml")
    text = dossier.readme(root)
    # The key to the reviews' paths and run variables follows the rows.
    assert "`/tmp/t13/<name>/` was the review's scratch directory" in text
    assert "`$TESS_HUNT_DATA` the data directory" in text and "| `VET2_RUN` |" in text
    assert "are both that private design on the maintainer's machine" in text
    assert '"The maintainer" in the reviews, the brief and the tarballs' in text
    rows = [line for line in text.splitlines() if line.startswith("| [")]
    assert rows == [
        f"| [{held.name}]({held.name}/dossier.md) | held | 2026-10-28 | The public data can't tell the two stars "
        "apart. |",
        f"| [{killed.name}]({killed.name}/dossier.md) | killed | 2026-10-28 | It \\| fails odd and even. |",
    ]
    shown, left = dossier.listed(root)
    assert shown == [held, killed]
    assert left["2-1"] == ["not published: a call with no record beside it"]
    assert "rests on" in left["399023421-1"][0]
    # A staged directory stands in for its published one, as `vetting publish` renders the README before copying.
    staged = published_dir(
        tc.KILLED, "399023421-1", parent=tmp_path / "staging", outcomes={"odd_even": "fail"}
    )
    assert "399023421-1" in dossier.readme(root, staged)


@pytest.mark.parametrize(
    "path, said",
    [
        (
            "raised",
            "It raised before any calc_probs run finished: ConnectionError: TESScut did not answer.",
        ),
        (
            "raised later",
            f"Then it raised, after 1 of {tt.CFG['runs']} calc_probs run(s): RuntimeError: PyTransit failed.",
        ),
        (
            "raised first",
            "TRICERATOPS (inconclusive) raised before it chose its data: ConnectionError: TESScut did not answer.",
        ),
        ("no group", "It stopped before calc_probs: no cadence group"),
        ("no depth", "It stopped before calc_probs: no usable transit depth (nan)."),
        ("no cutout", "It stopped before calc_probs: TESScut gave"),
        ("no light", "It stopped before calc_probs: calc_depths left the target no light"),
    ],
)
def test_a_triceratops_record_from_any_path_renders(tmp_path, monkeypatch, path, said):
    """The dossier says exactly how far the record shows TRICERATOPS got, on every path."""
    run, _ = vetting_runs(tmp_path, monkeypatch)

    def down(*args):
        raise requests.ConnectionError("TESScut did not answer")

    if path == "raised":
        # After the cadence group and the fold.
        monkeypatch.setattr(tricera, "new_target", down)
    elif path == "raised later":
        tt.install(monkeypatch, raises=RuntimeError("PyTransit failed"), runs_before_raise=1)
    elif path == "raised first":
        monkeypatch.setattr(tricera, "cadence_group", down)
    elif path == "no group":
        monkeypatch.setattr(tricera, "cadence_group", lambda lc, eph, n: (None, [], []))
    elif path == "no depth":
        fold = vetting._fold_ephemeris

        def no_depth(checks):
            eph, source = fold(checks)
            return replace(eph, depth=float("nan")), source

        monkeypatch.setattr(vetting, "_fold_ephemeris", no_depth)
    else:
        tt.install(monkeypatch, **({"cutouts": 1} if path == "no cutout" else {"dark": True}))
    criteria = ("--criteria-search", str(tv.SEARCH), "--criteria-vet", str(tv.VET3))
    assert main(["vetting", "triceratops", "--run", str(run), *criteria, "--workers", "1"]) == 0
    [tric] = (tmp_path / "data" / "runs").glob("*-vetting-triceratops-*")
    record = json.loads((tric / "signals" / NAME / "triceratops.json").read_text())
    assert record["outcome"] == "inconclusive"
    assert len(record["evidence"]["fpp"]) == (1 if path == "raised later" else 0)
    out = tmp_path / "drafts"
    assert (
        main(
            ["vetting", "dossier", "--run", str(run), "--triceratops", str(tric), "--out", str(out)]
        )
        == 0
    )
    text = (out / NAME / "dossier.md").read_text()
    on_star, planet = section(text, "On the star?"), section(text, "A planet rather than a binary?")
    [said_on_star] = [p for p in on_star.split("\n\n") if p.startswith("TRICERATOPS (")]
    assert said in said_on_star
    e = record["evidence"]
    if e["exposure_s"] is None:
        assert "took sectors" not in said_on_star
    else:
        took = f"took sectors {dossier._words(e['sectors'])} at {e['exposure_s']:g} s"
        assert took in said_on_star
        # The "no usable transit depth" stop comes before the fold.
        assert (f"{took} and folded them on" in said_on_star) is (path != "no depth")
    # The reason for a raise is said once.
    if e["raised"] is not None:
        assert said_on_star.count(e["raised"]) == 1
    star_list = "It built no star list, so no possible host was matched to it."
    assert (star_list in said_on_star) is (
        path in ("raised", "raised first", "no group", "no depth")
    )
    # The vetting run's possible host sits 12.5" from the fake target's other star: not in its star list.
    if path in ("no cutout", "no light"):
        assert (
            "Possible hosts not in its star list: Gaia DR3 7. No calc_probs run weighed any star."
            in said_on_star
        )
    assert ("did not weigh" in said_on_star) is (path == "raised later")
    if path == "raised later":
        assert "TRICERATOPS (inconclusive): mean FPP" in planet and "over 1 run(s)" in planet
    else:
        assert "TRICERATOPS (inconclusive): no calc_probs run finished, so no FPP." in planet


def stopped_before_calc_probs(record: dict) -> None:
    record["outcome"] = "inconclusive"
    record["evidence"].update(
        fpp=[],
        nfpp=[],
        fpp_mean=None,
        nfpp_mean=None,
        fpp_sd=None,
        nfpp_sd=None,
        stopped="TESScut gave 1 of 2 sectors' cutouts",
        hosts_tdepth_zero=None,
    )


@pytest.mark.parametrize(
    "change, said",
    [
        (lambda r: None, "Possible hosts it did not weigh: none."),
        (
            stopped_before_calc_probs,
            "Every possible host is in its star list, and no calc_probs run weighed them.",
        ),
        (
            lambda r: (stopped_before_calc_probs(r), r["evidence"].update(missing_hosts=[7])),
            "Possible hosts not in its star list: Gaia DR3 7. No calc_probs run weighed any star.",
        ),
    ],
    ids=["weighed", "listed, not weighed", "not listed"],
)
def test_the_possible_hosts_sentence_says_what_the_record_shows(
    tmp_path, monkeypatch, change, said
):
    """A host in the star list of a run that stopped before calc_probs was never weighed."""
    signal, _ = draft(tmp_path, monkeypatch)
    edit_json(signal / "triceratops.json", change)
    on_star = section(dossier.render(signal), "On the star?")
    [said_on_star] = [p for p in on_star.split("\n\n") if p.startswith("TRICERATOPS (")]
    assert said in said_on_star
    if said != "Possible hosts it did not weigh: none.":
        assert "did not weigh" not in said_on_star
    # The neighbour table passed: it judged every star.
    assert "could not judge" not in said_on_star


def test_a_neighbour_table_from_before_0034_says_it_ran_from_the_tic_position(
    tmp_path, monkeypatch
):
    signal, _ = draft(tmp_path, monkeypatch)
    edit_json(signal / "checks.json", lambda c: c["neighbours"]["evidence"].pop("centre"))
    on_star = section(dossier.render(signal), "On the star?")
    assert "its separation from the target (TIC position, J2000)" in on_star


@pytest.mark.parametrize(
    "dr3_from, reason",
    [
        # A re-run fixes this one.
        (
            "missing",
            "the Gaia DR3 join failed: Gaia archive failed 3 times: OSError: archive unavailable",
        ),
        # Not this one.
        ("dr3_join", "Gaia DR3 101 has no RUWE"),
    ],
    ids=["join failed", "none in DR3"],
)
def test_a_missing_ruwe_says_why(tmp_path, monkeypatch, dr3_from, reason):
    signal, _ = draft(tmp_path, monkeypatch)
    edit_json(
        signal / "checks.json",
        lambda c: c["star"].update(ruwe=None, dr3_from=dr3_from, dr3_reason=reason),
    )
    text = dossier.render(signal)
    assert f"RUWE missing (Gaia DR3), because {reason}." in section(text, "On the star?")
    # Page one's star table says why too.
    assert f"| RUWE (Gaia DR3) | missing, because {reason} |" in text


def no_table(neighbours: dict) -> None:
    """The neighbour check's record when the Gaia cone failed: no table, so no possible hosts key."""
    kept = {
        k: neighbours["evidence"][k]
        for k in ("depth", "depth_from", "tmag", "target_source_id", "centre")
    }
    neighbours.update(
        outcome="inconclusive",
        reason="no neighbour table: Gaia archive failed",
        evidence={**kept, "error": "Gaia archive failed"},
    )


def none_possible(neighbours: dict) -> None:
    neighbours["evidence"]["possible_hosts"] = []
    for row in neighbours["evidence"]["table"]:
        row["possible"] = False


NO_G = "1 Gaia DR3 star(s) within the radius have no G magnitude"


def none_possible_unjudged(neighbours: dict) -> None:
    """A table built, with a star it could not judge: never marked possible, so the list is empty (296819076-1)."""
    none_possible(neighbours)
    neighbours.update(outcome="inconclusive", reason=NO_G)


def weighed(record: dict) -> None:
    # With no possible host, TRICERATOPS matches none and misses none.
    record["evidence"].update(hosts=[], missing_hosts=[], hosts_tdepth_zero=[])


def stopped_with_no_hosts(record: dict) -> None:
    stopped_before_calc_probs(record)
    record["evidence"].update(hosts=[], missing_hosts=[])


def raised_before_its_data(record: dict) -> None:
    """TRICERATOPS raised in `target()`: no cadence group, no star list."""
    stopped_before_calc_probs(record)
    record["evidence"].update(
        stopped=None,
        raised="ConnectionError: TESScut did not answer",
        groups=None,
        exposure_s=None,
        points=None,
        hosts=None,
        missing_hosts=None,
    )


@pytest.mark.parametrize(
    "triceratops",
    [weighed, stopped_with_no_hosts, raised_before_its_data],
    ids=["weighed", "stopped before calc_probs", "raised before its data"],
)
@pytest.mark.parametrize(
    "neighbours, said",
    [
        (none_possible, "The neighbour table lists no possible host for it to weigh."),
        (
            none_possible_unjudged,
            f"The neighbour table lists no possible host, but it could not judge every star: {NO_G}.",
        ),
        (no_table, "No neighbour table was built, so whether a possible host exists is unknown."),
    ],
    ids=["none possible", "none possible, some unjudged", "no table"],
)
def test_the_triceratops_paragraph_claims_no_host_the_neighbour_table_lacks(
    tmp_path, monkeypatch, neighbours, said, triceratops
):
    signal, _ = draft(tmp_path, monkeypatch)
    edit_json(signal / "checks.json", lambda c: neighbours(c["neighbours"]))
    edit_json(signal / "triceratops.json", triceratops)
    on_star = section(dossier.render(signal), "On the star?")
    [said_on_star] = [p for p in on_star.split("\n\n") if p.startswith("TRICERATOPS (")]
    assert said in said_on_star
    # Nothing else in the paragraph speaks of possible hosts or a star list.
    rest = said_on_star.replace(said, "").lower()
    assert "possible host" not in rest and "star list" not in rest


@pytest.mark.parametrize(
    "triceratops, hosts_said",
    [
        (lambda r: None, "Possible hosts it did not weigh: none."),
        (
            stopped_before_calc_probs,
            "Every possible host is in its star list, and no calc_probs run weighed them.",
        ),
        (raised_before_its_data, "It built no star list, so no possible host was matched to it."),
    ],
    ids=["weighed", "stopped before calc_probs", "raised before its data"],
)
def test_the_triceratops_paragraph_says_the_table_listing_hosts_could_not_judge_every_star(
    tmp_path, monkeypatch, triceratops, hosts_said
):
    """The fixture's table lists Gaia DR3 7 as a possible host; a star it could not judge may be one too."""
    signal, _ = draft(tmp_path, monkeypatch)
    edit_json(
        signal / "checks.json",
        lambda c: c["neighbours"].update(outcome="inconclusive", reason=NO_G),
    )
    edit_json(signal / "triceratops.json", triceratops)
    on_star = section(dossier.render(signal), "On the star?")
    [said_on_star] = [p for p in on_star.split("\n\n") if p.startswith("TRICERATOPS (")]
    assert (
        f"The neighbour table lists possible hosts, but it could not judge every star: {NO_G}."
        in said_on_star
    )
    assert hosts_said in said_on_star
