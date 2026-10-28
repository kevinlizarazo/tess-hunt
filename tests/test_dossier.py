import datetime as dt
import json
import re
import shutil
import stat
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
import requests
import test_calls as tc
import test_literature as tl
import test_tricera as tt
import test_vetting as tv
from synthetic import make_transit_lc, with_products

from tess_hunt import (
    calls,
    dossier,
    literature,
    predict,
    prereg,
    provenance,
    revet,
    tricera,
    vetting,
)
from tess_hunt.catalogs import load_known
from tess_hunt.cli import main
from tess_hunt.config import load_criteria
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file
from tess_hunt.serialize import jsonable

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
        "lc_run": "--lc-run",
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
        # The 1-sigma half-width is the sd itself, so the table gives it once.
        assert f"| {w['sd_minutes']:.1f} | {w['half_width_minutes']['3']:.1f} |" in looks
    assert "| sd (min) | 3 sigma half-width (min) |" in looks and "1 sigma" not in looks
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


def section(text: str, heading: str) -> str:
    return text.split(f"\n## {heading}\n")[1].split("\n## ")[0]


def table_rows(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("|")]


def without_the_1_sigma_column(rows: list[str]) -> list[str]:
    """A published windows table as a dossier rendered after M4 gives it: without the 1-sigma half-width, the sd."""
    if not rows:
        return rows
    assert rows[0].split(" | ")[5] == "1 sigma half-width (min)"
    out = []
    for row in rows:
        if set(row) <= set("|-"):
            out.append(row.replace("---|", "", 1))
        else:
            cells = row.split(" | ")
            del cells[5]
            out.append(" | ".join(cells))
    return out


def test_seen_utc_matches_the_dossier():
    # Every published record's windows table renders as it was published, less the 1-sigma column, with its times
    # from Earth now from predict.seen_utc: the same epochs, mid-times and sds, and the same UTC.
    shown = 0
    for path in sorted((REPO / "results" / "vetting").glob("*/dossier.md")):
        published = table_rows(section(path.read_text(), "Next TESS looks"))
        rendered = table_rows(section(dossier.render(path.parent), "Next TESS looks"))
        assert rendered == without_the_1_sigma_column(published), path.parent.name
        checks = json.loads((path.parent / "checks.json").read_text())
        star = checks["star"]
        for w in (w for w in checks["windows"] or [] if "epoch" in w):
            seen = predict.seen_utc(w["mid_btjd"], star["ra"], star["dec"])
            row = f"| {w['sector']} | {w['epoch']} | {w['mid_btjd']:.3f} | {seen} | {w['sd_minutes']:.1f} |"
            assert any(p.startswith(row) for p in published), (path.parent.name, row)
            shown += 1
    assert shown > 0


def test_ddt_note_follows_0039(tmp_path, monkeypatch):
    season = tc.edit(
        HELD,
        "High-resolution imaging of the 12.5 arcsec companion.",
        "A third TESS season: sectors 112 to 114 give the held-out check its training seasons.",
    )
    signal, _ = draft(tmp_path, monkeypatch, review=REVIEW, call=season)
    looks = section((signal / "dossier.md").read_text(), "Next TESS looks")
    assert (
        "Held: the DDT ask applies only on the maintainer's call and only when 2-min data would supply its "
        "deciding evidence: the transit's shape, or a season no public light curve will otherwise cover; a hold on "
        "blending does not go, since 2-min data come from the same pixels "
        "([decision 0039](../../../docs/decisions/0039-ddt-for-held-signals.md)). Deciding evidence: A third TESS "
        "season: sectors 112 to 114 give the held-out check its training seasons."
    ) in looks


def test_a_draft_without_a_call_gives_each_outcome_its_ddt_rule(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch)
    looks = " ".join(section((signal / "dossier.md").read_text(), "Next TESS looks").split())
    # The same pixels are the reason a hold on blending does not go; a killed signal needs none.
    assert (
        "If held on the transit's shape, it may on the maintainer's call; held on blending it does not, since "
        "2-min data come from the same pixels; killed, it does not." in looks
    )


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


def test_a_plot_the_vetting_run_could_not_draw_is_named_with_its_error(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch)
    # As `vetting run` leaves a vet whose phase plot raised: the vet stands, and its checks say why.
    (signal / "plots" / "phase.png").unlink()
    error = "raised RuntimeError: plotting failed"
    edit_json(signal / "checks.json", lambda c: c.update(plot_errors={"phase.png": error}))
    plots = section(dossier.render(signal), "Plots")
    assert (
        f"The whole orbit, with phase 0.5 and LEO-Vetter's ModShift secondary marked: not drawn ({error})."
        in plots
    )
    assert "](plots/phase.png)" not in plots and "](plots/folds.png)" in plots
    # Where the plot would be.
    assert (
        plots.index("plots/odd_even.png") < plots.index("not drawn") < plots.index("centroids.png")
    )


def test_render_fails_on_a_missing_value(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch)
    dossier.render(signal)
    path = signal / "checks.json"
    good = path.read_text()
    for change in (
        lambda c: c["star"].pop("teff"),
        lambda c: next(w for w in c["windows"] if "epoch" in w).pop("sd_minutes"),
        lambda c: c["checks"][0].pop("reason"),
        # A radius or shape check that passed or failed measured Rp and b.
        lambda c: next(x for x in c["checks"] if x["check"] == "radius")["evidence"].pop(
            "rp_rearth"
        ),
        lambda c: next(x for x in c["checks"] if x["check"] == "shape")["evidence"].pop("b_median"),
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


def test_a_finding_no_refuter_ran_on_says_so():
    # It stands, as decision 0028 has it, but nothing refuted or failed to refute it.
    unchecked = {**REVIEW["findings"][1], "id": "F4", "refuters": []}
    text = dossier.render_review({**REVIEW, "findings": [*REVIEW["findings"], unchecked]})
    assert "### F4 (on the star, hold): confirmed, no refuter ran on it\n" in text
    assert "### F2 (on the star, hold): confirmed\n" in text
    assert "### F1 (real and new, note)\n" in text


def test_page_one_names_the_triage_run_and_its_criteria(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch)

    def shown() -> str:
        return section(dossier.render(signal), "Signal and star")

    assert f"| Triage | triage run {tv.TRIAGE_RUN}, under triage-v1 |" in shown()
    # A vetting run made before it recorded triage's criteria file names the run alone.
    edit_json(signal / "provenance-checks.json", lambda p: p["inputs"].pop("triage_criteria"))
    assert (
        f"| Triage | triage run {tv.TRIAGE_RUN} (the vetting run recorded no criteria file for it) |"
        in shown()
    )
    edit_json(signal / "provenance-checks.json", lambda p: p.update(triage_run=None))
    assert "| Triage | none: the vetting run read no triage run |" in shown()


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
    # Drafts go outside the repository, so `vetting publish` stays the only way into its results/.
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    for inside in (repo / "results" / "vetting", repo / "drafts"):
        with pytest.raises(SystemExit, match="outside the repository"):
            main(["vetting", "dossier", "--run", str(run), "--out", str(inside)])
        assert not inside.exists()


def test_a_draft_call_that_breaks_the_schema_is_not_rendered(tmp_path, monkeypatch):
    runs = all_runs(tmp_path, monkeypatch)
    out = tmp_path / "drafts"
    (out / NAME).mkdir(parents=True)
    (out / NAME / "call.toml").write_text(tc.edit(HELD, 'outcome = "held"', 'outcome = "maybe"'))
    roles = ("run", "suspect", "triceratops", "literature")
    with pytest.raises(calls.CallError, match="outcome 'maybe' is not one of"):
        main(["vetting", "dossier", *flags(runs, *roles), "--out", str(out)])
    assert not (out / NAME / "dossier.md").exists()


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


def called_m3(tmp_path, monkeypatch) -> tuple[dict[str, Path], Path, list[str]]:
    """1-1's production runs, its call and review written in a repo of its own, and the publish arguments."""
    runs = all_runs(tmp_path, monkeypatch)
    production(*runs.values())
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(HELD)
    (signal / "review.json").write_text(json.dumps(REVIEW))
    return runs, repo, publish_argv(runs, "run", "triceratops", "literature", "suspect", "titles")


def test_publish_renders_the_readme_before_it_copies_anything(tmp_path, monkeypatch):
    _, repo, argv = called_m3(tmp_path, monkeypatch)
    before = published(repo)

    def fails(*args):
        raise RuntimeError("the README does not render")

    monkeypatch.setattr(dossier, "readme", fails)
    with pytest.raises(RuntimeError, match="does not render"):
        main(argv)
    assert published(repo) == before


def test_a_copy_that_fails_partway_leaves_no_new_file(tmp_path, monkeypatch):
    _, repo, argv = called_m3(tmp_path, monkeypatch)
    signal = repo / "results" / "vetting" / NAME
    before = published(repo)
    copyfile = shutil.copyfile
    into = []

    def fails_on_the_third(src, dst, **kwargs):
        if Path(dst).is_relative_to(signal):
            into.append(dst)
            if len(into) == 3:
                raise OSError("no space left on the device")
        return copyfile(src, dst, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", fails_on_the_third)
    with pytest.raises(OSError, match="no space"):
        main(argv)
    assert published(repo) == before
    monkeypatch.setattr(shutil, "copyfile", copyfile)
    assert main(argv) == 0
    assert (signal / "dossier.md").read_text() == dossier.render(signal)


def test_a_pass_the_record_supports_is_published(tmp_path, monkeypatch):
    run, suspect = vetting_runs(tmp_path, monkeypatch)
    # Every check passed and the literature search was complete, as a pass needs; the rest is the fixture's.
    edit_json(
        run / "signals" / NAME / "checks.json",
        lambda c: next(x for x in c["checks"] if x["check"] == "holdout").update(
            outcome="pass", reason="every held-out season predicted"
        ),
    )
    complete = {**literature_record(run, monkeypatch), "outcome": "pass", "reason": "complete"}
    tric = made_run(
        tmp_path,
        "vetting-triceratops",
        run,
        {NAME: {"triceratops.json": triceratops_record(run), "probs.csv": "ID,prob\n1,0.98\n"}},
    )
    lit = made_run(tmp_path, "vetting-literature", run, {NAME: {"literature.json": complete}})
    runs = {
        "run": run,
        "suspect": suspect,
        "triceratops": tric,
        "literature": lit,
        "titles": titles_run(tmp_path, lit),
    }
    production(*runs.values())
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(tc.edit(tc.PASSED, '"44926986-1"', f'"{NAME}"'))
    (signal / "review.json").write_text(json.dumps(REVIEW))
    assert main(publish_argv(runs, "run", "triceratops", "literature", "suspect", "titles")) == 0
    assert calls.problems(signal) == []
    text = (signal / "dossier.md").read_text()
    assert text == dossier.render(signal) and "Call: **passed** on 2026-10-28." in text
    readme = (repo / "results" / "vetting" / "README.md").read_text()
    assert f"| [{NAME}]({NAME}/dossier.md) | passed | 2026-10-28 |" in readme


def test_publish_refuses_a_review_naming_the_home_directory_or_the_maintainer(
    tmp_path, monkeypatch
):
    home = tmp_path / "home" / "someone"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(provenance, "maintainer", lambda: ("Ada", "Lovelace"))
    runs = all_runs(tmp_path, monkeypatch)
    production(*runs.values())
    repo = tmp_path / "repo"
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(HELD)
    argv = publish_argv(runs, "run", "triceratops", "literature", "titles")
    for summary in (
        f"Read in {home}/code/tess-hunt.",
        f"Read in {tmp_path / 'data'}/runs.",
        "Notes for Ada.",
    ):
        (signal / "review.json").write_text(json.dumps({**REVIEW, "summary": summary}))
        before = published(repo)
        with pytest.raises(SystemExit, match="names the home or data directory or the maintainer"):
            main(argv)
        assert published(repo) == before
    # Written as the scrub writes it, it publishes.
    (signal / "review.json").write_text(
        json.dumps({**REVIEW, "summary": "Notes for the maintainer."})
    )
    assert main(argv) == 0


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
    # Another titles run would overwrite the record: refused, unless asked for by name.
    other = titles_run(tmp_path, runs["literature"], lookups, tag="c")
    production(other)
    with pytest.raises(SystemExit, match="another titles run"):
        main([*argv[:-1], str(other)])
    assert published(repo) == after
    replace = [*argv[:-1], str(other), "--replace-titles-run"]
    assert main(replace) == 0
    trim = json.loads((signal / "literature.json").read_text())["trim"]
    assert trim["titles_run"] == other.name and trim["replaced_titles_run"] == titles.name
    assert sha256_file(signal / "provenance-titles.json") == sha256_file(other / "provenance.json")
    assert f"titles {other.name}" in (signal / "dossier.md").read_text()
    # Again, with or without the flag: the record still names the run it replaced, and nothing changes.
    replaced = published(repo)
    for again in (replace, replace[:-1]):
        assert main(again) == 0
        assert published(repo) == replaced
    # Publishing the record's own runs again with the new titles run renders the dossier again and changes nothing
    # else; with the run it replaced, it is refused.
    republish = [*publish_argv(runs, "run", "triceratops", "literature"), "--titles", str(other)]
    (signal / "dossier.md").write_text("stale\n")
    assert main(republish) == 0
    assert published(repo) == replaced
    with pytest.raises(SystemExit, match="another literature.json"):
        main([*republish[:-1], str(titles)])
    assert published(repo) == replaced
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
        review = {**tc.REVIEW, "signal": name}
        path = tc.signal_dir(parent, call=call, review=review, name=name, **kwargs)
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


def test_the_committed_readme_is_its_render():
    # With no version published, the README renders the M3 records exactly as they were published.
    root = REPO / "results" / "vetting"
    assert dossier.readme(root) == (root / "README.md").read_text()


def test_readme_lists_the_latest_standing_call(tmp_path):
    root = tmp_path / "vetting"

    def published_dir(call, name, parent=root, signal=None, **kwargs):
        call = tc.edit(call, f'signal = "{tc.NAME}"', f'signal = "{signal or name}"')
        review = {**tc.REVIEW, "signal": signal or name}
        path = tc.signal_dir(parent, call=call, review=review, name=name, **kwargs)
        (path / "dossier.md").write_text("rendered\n")
        return path

    held = published_dir(tc.HELD, tc.NAME)
    # Its re-vet killed it; a third version's call no longer stands on its record (a kill resting on a check that
    # passed), so the README shows the second.
    killed = tc.edit(tc.KILLED, "date = 2026-10-28", "date = 2027-01-20")
    r2 = published_dir(killed, "r2", parent=held, signal=tc.NAME, outcomes={"odd_even": "fail"})
    published_dir(tc.KILLED, "r3", parent=held, signal=tc.NAME)
    other = published_dir(tc.HELD, "48010903-1")
    # A version written before it is published is no row and no earlier version.
    (other / "r2").mkdir()
    (other / "r2" / "call.toml").write_text(tc.edit(tc.HELD, f'"{tc.NAME}"', '"48010903-1"'))
    rows = [line for line in dossier.readme(root).splitlines() if line.startswith("| [")]
    assert rows == [
        f"| [{tc.NAME} r2]({tc.NAME}/r2/dossier.md) (earlier: [M3 record]({tc.NAME}/dossier.md)) | killed | "
        "2027-01-20 | It fails odd and even. |",
        "| [48010903-1](48010903-1/dossier.md) | held | 2026-10-28 | The public data can't tell the two stars "
        "apart. |",
    ]
    shown, left = dossier.listed(root)
    assert shown == [held, r2, other]
    assert set(left) == {f"{tc.NAME}/r3", "48010903-1/r2"}
    assert "rests on" in left[f"{tc.NAME}/r3"][0]
    # A staged version stands in for its directory, as `vetting publish` renders the README before copying.
    staged = published_dir(
        killed,
        "r3",
        parent=tmp_path / "staging" / tc.NAME,
        signal=tc.NAME,
        outcomes={"odd_even": "fail"},
    )
    assert (
        f"| [{tc.NAME} r3]({tc.NAME}/r3/dossier.md) (earlier: [M3 record]({tc.NAME}/dossier.md), "
        f"[r2]({tc.NAME}/r2/dossier.md)) | killed |"
    ) in dossier.readme(root, staged)


def results_repo(tmp_path, monkeypatch) -> Path:
    """A repo of its own for `vetting` to publish into, holding the criteria and the sectors file later vetting runs
    read from it."""
    repo = tmp_path / "repo"
    shutil.copytree(REPO / "criteria", repo / "criteria")
    (repo / "benchmarks").mkdir()
    shutil.copy(REPO / "benchmarks" / "tess_sectors.csv", repo / "benchmarks")
    monkeypatch.setattr(vetting, "repo_root", lambda: repo)
    return repo


def published_m3(tmp_path, monkeypatch) -> tuple[dict[str, Path], Path]:
    """1-1's M3 record, published from production runs into a repo of its own."""
    runs = all_runs(tmp_path, monkeypatch)
    production(*runs.values())
    repo = results_repo(tmp_path, monkeypatch)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(HELD)
    (signal / "review.json").write_text(json.dumps(REVIEW))
    assert main(publish_argv(runs, "run", "triceratops", "literature", "suspect", "titles")) == 0
    return runs, repo


def revet_run(
    tmp_path,
    tics=(1,),
    tag="a",
    base: Path | None = None,
    sector: int = 65,
    started: str = "2026-12-01T00:00:00+00:00",
) -> Path:
    """A finished production revet fetch run, started at `started`, that merged a new SPOC sector onto each star's
    light curve in `base`, the shared cache by default."""
    base = base or tmp_path / "data" / "lc"
    run_id = f"20261201T000000Z-revet-fetch-abc1234-{tag}"
    path = tmp_path / "data" / "runs" / run_id
    stars, inputs = {}, {}
    for tic in tics:
        fresh = make_transit_lc(
            rp_rs=0.04, sectors=(sector,), cadences={sector: 30.0}, noise_ppm={sector: 200.0}
        )
        fresh.tic = tic
        with_products(fresh, {sector: "SPOC"})
        # Fetched SPOC sources carry CROWDSAP; the synthetic ones don't.
        fresh.sources[str(sector)]["crowdsap"] = 0.95
        merged, sectors = revet.merge(LightCurve.load(base / f"{tic}.npz"), fresh)
        merged.save(path / "lc" / f"{tic}.npz")
        stars[str(tic)] = {
            "base_sha256": sha256_file(base / f"{tic}.npz"),
            "lc_sha256": sha256_file(path / "lc" / f"{tic}.npz"),
            "sectors": sectors,
            "fetch": {"status": "ok", "problems": {}},
        }
        inputs[f"base_light_curve_{tic}"] = {
            "file": f"{tic}.npz",
            "sha256": sha256_file(base / f"{tic}.npz"),
        }
    (path / "merge.json").write_text(json.dumps(jsonable(stars), indent=2, sort_keys=True) + "\n")
    made = {
        "run_id": run_id,
        "stage": "revet-fetch",
        "production": True,
        "started_at": started,
        "ended_at": started,
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
        "criteria": [
            {"file": "criteria/search-v2.toml", "sha256": load_criteria(tv.SEARCH).sha256}
        ],
        "inputs": inputs,
        "summary": {"stars": len(tics), "failed": []},
    }
    (path / "provenance.json").write_text(json.dumps(made, indent=2))
    return path


def revetted(
    tmp_path, monkeypatch, lc_run: Path, lc_dir: Path | None = None, triage: bool = True
) -> dict[str, Path]:
    """A re-vet's runs, all production: a vetting run on `lc_run`'s light curves (or `lc_dir`'s), with the M3
    record's triage run unless `triage` is false, its evidence-only twin, and the TRICERATOPS, literature and titles
    runs made from it."""
    runs_dir = tmp_path / "data" / "runs"
    before = set(runs_dir.glob("*-vetting-run-*"))
    argv = [
        *tv.run_argv(tmp_path),
        *(("--triage-run", str(runs_dir / tv.TRIAGE_RUN)) if triage else ()),
        *("--lc-dir", str(lc_dir or lc_run / "lc")),
    ]
    assert main(argv) == 0
    assert main([*argv, "--include-suspect"]) == 0
    made = {
        json.loads((p / "provenance.json").read_text())["evidence_only"]: p
        for p in set(runs_dir.glob("*-vetting-run-*")) - before
    }
    run = made[False]
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
        tag=run.name[-4:],
    )
    lit = made_run(
        tmp_path,
        "vetting-literature",
        run,
        {NAME: {"literature.json": literature_record(run, monkeypatch)}},
        tag=run.name[-4:],
    )
    runs = {
        "run": run,
        "suspect": made[True],
        "triceratops": tric,
        "literature": lit,
        "titles": titles_run(tmp_path, lit, tag=run.name[-4:]),
    }
    production(*runs.values())
    return {**runs, "lc_run": lc_run}


VERSION_ROLES = ("run", "suspect", "triceratops", "literature", "titles", "lc_run")


def version_argv(runs: dict[str, Path], version: int = 2, roles=VERSION_ROLES) -> list[str]:
    return ["vetting", "publish", "--name", NAME, "--version", str(version), *flags(runs, *roles)]


def called(version: Path, call: str = HELD) -> Path:
    """The maintainer's call and the review, written into a version's directory before it is published."""
    version.mkdir(parents=True, exist_ok=True)
    (version / "call.toml").write_text(tc.edit(call, "date = 2026-10-28", "date = 2027-01-20"))
    (version / "review.json").write_text(json.dumps(REVIEW))
    return version


def record_files(files: dict[str, str], prefix: str) -> set[str]:
    return {
        k.removeprefix(prefix)
        for k in files
        if k.startswith(prefix) and "r2/" not in k.removeprefix(prefix)
    }


def test_version_published_beside_the_m3_record(tmp_path, monkeypatch):
    m3, repo = published_m3(tmp_path, monkeypatch)
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path))
    root = repo / "results" / "vetting"
    version = called(root / NAME / "r2")
    before = published(repo)
    assert main(version_argv(runs)) == 0
    after = published(repo)

    # Every M3 file's bytes unchanged; of the files outside r2 only the README is rendered again.
    assert {k: after[k] for k in before} == {**before, "README.md": after["README.md"]}
    assert after["README.md"] != before["README.md"]
    assert all(k.startswith(f"{NAME}/r2/") for k in set(after) - set(before))
    # r2 holds the record: an M3 record's files, and the merge record of the light curve it vetted.
    m3_files = record_files(before, f"{NAME}/")
    r2_files = {k.removeprefix(f"{NAME}/r2/") for k in after if k.startswith(f"{NAME}/r2/")}
    assert r2_files == m3_files | {"merge.json", "provenance-merge.json"}
    vetted = runs["run"] / "signals" / NAME
    assert after[f"{NAME}/r2/checks.json"] == sha256_file(vetted / "checks.json")
    assert after[f"{NAME}/r2/plots/transits.png"] == sha256_file(vetted / "plots" / "transits.png")
    assert after[f"{NAME}/r2/provenance-checks.json"] == sha256_file(
        runs["run"] / "provenance.json"
    )
    tric = runs["triceratops"] / "signals" / NAME / "triceratops.json"
    assert after[f"{NAME}/r2/triceratops.json"] == sha256_file(tric)
    assert after[f"{NAME}/r2/merge.json"] == sha256_file(runs["lc_run"] / "merge.json")
    assert after[f"{NAME}/r2/provenance-merge.json"] == sha256_file(
        runs["lc_run"] / "provenance.json"
    )
    assert "65" in json.loads((version / "checks.json").read_text())["sources"]
    text = (version / "dossier.md").read_text()
    assert text == dossier.render(version)
    assert text.startswith(f"# {NAME} r2: TIC 1\n")
    readme = (root / "README.md").read_text()
    assert (
        f"| [{NAME} r2]({NAME}/r2/dossier.md) (earlier: [M3 record]({NAME}/dossier.md)) | held | "
        "2027-01-20 |"
    ) in readme


def test_version_refuses_a_gap_or_an_existing_version(tmp_path, monkeypatch):
    m3, repo = published_m3(tmp_path, monkeypatch)
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path))
    root = repo / "results" / "vetting"
    for n in (2, 3):
        called(root / NAME / f"r{n}")
    before = published(repo)
    m3_again = [*publish_argv(m3, "run", "triceratops", "literature", "titles")]
    for argv, message in (
        (version_argv(runs, 3), f"no r2 published in results/vetting/{NAME}"),
        (version_argv(runs, 1), "counts from 2"),
        (version_argv(runs, roles=VERSION_ROLES[:-1]), "give --lc-run"),
        ([*m3_again, "--lc-run", str(runs["lc_run"])], "--lc-run is for a version"),
    ):
        with pytest.raises(SystemExit, match=message):
            main(argv)
        assert published(repo) == before
    assert main(version_argv(runs)) == 0
    after = published(repo)
    # Published once, never again, not even from the same runs.
    with pytest.raises(SystemExit, match=f"results/vetting/{NAME}/r2 is already published"):
        main(version_argv(runs))
    assert published(repo) == after
    # Without the M3 record there is no version.
    empty = tmp_path / "empty"
    called(empty / "results" / "vetting" / NAME / "r2")
    monkeypatch.setattr(vetting, "repo_root", lambda: empty)
    with pytest.raises(SystemExit, match="no M3 record published"):
        main(version_argv(runs))


def test_version_refuses_a_light_curve_not_from_its_lc_run(tmp_path, monkeypatch):
    m3, repo = published_m3(tmp_path, monkeypatch)
    called(repo / "results" / "vetting" / NAME / "r2")
    before = published(repo)
    # The evidence-only twin read another light curve than the version's vetting run: the M3 one.
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path, tag="c"))
    with pytest.raises(SystemExit, match="the evidence-only run read another light curve"):
        main(version_argv({**runs, "suspect": m3["suspect"]}))
    assert published(repo) == before
    # The version's vetting run read the shared cache, not the revet fetch run's light curve.
    lc_run = revet_run(tmp_path)
    shared = revetted(tmp_path, monkeypatch, lc_run, lc_dir=tmp_path / "data" / "lc")
    with pytest.raises(SystemExit, match="did not vet the light curve revet fetch run"):
        main(version_argv(shared))
    assert published(repo) == before
    # The revet fetch run merged its sectors onto another light curve than the one the M3 record's vetting run read.
    other = tmp_path / "other-lc"
    other.mkdir()
    lc = LightCurve.load(tmp_path / "data" / "lc" / "1.npz")
    lc.flux = lc.flux * 1.0001
    lc.save(other / "1.npz")
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path, tag="b", base=other))
    with pytest.raises(SystemExit, match="onto another light curve"):
        main(version_argv(runs))
    assert published(repo) == before
    # A revet fetch run holding the same bytes is not the run the vetting run read them from.
    lc_run = revet_run(tmp_path, tag="d")
    runs = revetted(tmp_path, monkeypatch, lc_run)
    twin = lc_run.parent / "20261201T000000Z-revet-fetch-abc1234-e"
    shutil.copytree(lc_run, twin)
    edit_json(twin / "provenance.json", lambda p: p.update(run_id=twin.name))
    with pytest.raises(
        SystemExit,
        match=f"read its light curves from {lc_run.name}, not revet fetch run {twin.name}",
    ):
        main(version_argv({**runs, "lc_run": twin}))
    assert published(repo) == before


def test_version_keeps_the_previous_records_triage_run(tmp_path, monkeypatch):
    # Triage's pixel and ModShift evidence stay the M3 record's (decision 0041): a vetting run without that triage
    # run, or with another, makes no version.
    _, repo = published_m3(tmp_path, monkeypatch)
    called(repo / "results" / "vetting" / NAME / "r2")
    before = published(repo)
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path), triage=False)
    with pytest.raises(SystemExit, match=f"another triage run than the previous record of {NAME}"):
        main(version_argv(runs))
    assert published(repo) == before


def test_an_interrupted_version_is_finished(tmp_path, monkeypatch):
    _, repo = published_m3(tmp_path, monkeypatch)
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path))
    version = called(repo / "results" / "vetting" / NAME / "r2")
    readme = (repo / "results" / "vetting" / "README.md").read_text()
    write_text = Path.write_text

    def crashes(path, *args, **kwargs):
        if path == version / "dossier.md":
            raise RuntimeError("the machine went down")
        return write_text(path, *args, **kwargs)

    # The record's files copied, and nothing after: no dossier, no README.
    monkeypatch.setattr(Path, "write_text", crashes)
    with pytest.raises(RuntimeError, match="went down"):
        main(version_argv(runs))
    monkeypatch.setattr(Path, "write_text", write_text)
    assert (version / "checks.json").is_file() and not (version / "dossier.md").exists()
    assert (repo / "results" / "vetting" / "README.md").read_text() == readme
    # Not published until its dossier is there: no version follows it, and another run's file is refused.
    called(repo / "results" / "vetting" / NAME / "r3")
    with pytest.raises(SystemExit, match="no r2 published"):
        main(version_argv(runs, 3))
    other = made_run(
        tmp_path,
        "vetting-triceratops",
        runs["run"],
        {NAME: {"triceratops.json": triceratops_record(runs["run"], "inconclusive")}},
        tag="x",
    )
    production(other)
    half = published(repo)
    with pytest.raises(SystemExit, match="already holds another .*triceratops.json"):
        main(
            [
                *version_argv(runs, roles=("run", "suspect", "literature", "titles", "lc_run")),
                "--triceratops",
                str(other),
            ]
        )
    assert published(repo) == half
    # The same runs finish it.
    assert main(version_argv(runs)) == 0
    assert (version / "dossier.md").read_text() == dossier.render(version)
    assert (
        f"[{NAME} r2]({NAME}/r2/dossier.md)"
        in (repo / "results" / "vetting" / "README.md").read_text()
    )
    with pytest.raises(SystemExit, match="is already published"):
        main(version_argv(runs))


def test_a_version_is_drafted_beside_its_previous_record(tmp_path, monkeypatch):
    m3, repo = published_m3(tmp_path, monkeypatch)
    runs = revetted(tmp_path, monkeypatch, revet_run(tmp_path))
    out = tmp_path / "drafts"
    roles = ("run", "suspect", "triceratops", "literature", "lc_run")
    argv = [
        *("vetting", "dossier", *flags(runs, *roles)),
        *("--version", "2", "--signals", NAME, "--out", str(out)),
    ]
    assert main(argv) == 0
    draft = out / NAME / "r2"
    text = (draft / "dossier.md").read_text()
    assert text == dossier.render(draft)
    assert "## Changes since the M3 record" in text
    assert sha256_file(draft / "merge.json") == sha256_file(runs["lc_run"] / "merge.json")
    # The previous record's checks beside it, as published, which the version's dossier compares with.
    published_record = repo / "results" / "vetting" / NAME
    assert sha256_file(out / NAME / "checks.json") == sha256_file(published_record / "checks.json")
    # A draft of the M3 record made again keeps the version's draft beside it.
    assert main(["vetting", "dossier", *flags(m3, "run"), "--out", str(out)]) == 0
    assert (draft / "dossier.md").is_file()
    # A version's draft is one signal's.
    with pytest.raises(SystemExit, match="--signals NAME"):
        main([a for a in argv if a not in ("--signals", NAME)])


def version_dir(signal: Path) -> Path:
    """A version of the draft record in `signal`, laid out as `publish` lays one out, its files edited as a re-vet on a
    fresh catalog snapshot would change them."""
    version = signal / "r2"
    version.mkdir()
    for path in signal.iterdir():
        if path.is_file():
            shutil.copyfile(path, version / path.name)
    shutil.copytree(signal / "plots", version / "plots")
    checks = json.loads((version / "checks.json").read_text())
    checks["sources"] |= {"65": {**checks["sources"]["2"]}, "110": {**checks["sources"]["2"]}}
    checks["masked"].append({"period": 7.3, "t0": 1330.0, "duration": 0.1, "depth": None})
    checks["catalogued"]["rows"].append(
        {
            "source": "CTOI",
            "kind": "candidate",
            "name": "CTOI-1.01",
            "period": 7.3,
            "t0": 1330.0,
            "duration": 0.1,
            "masked": True,
            "matches_signal": False,
            "overlaps": [],
        }
    )
    novelty = next(c for c in checks["checks"] if c["check"] == "novelty")
    novelty.update(outcome="inconclusive", reason="matches only SPOC TCE or ExoMiner rows")
    novelty["evidence"].update(
        category="known_to_spoc",
        tce_matches=[
            {
                "source": "ExoMiner-v2",
                "kind": "tce",
                "name": "ExoMiner vetting_catalog_FFI 1-1-S65",
                "period": 5.0,
                "ratio": 1.0,
                "tic": 1,
            }
        ],
    )
    (version / "checks.json").write_text(json.dumps(checks))
    edit_json(
        version / "provenance-checks.json",
        lambda p: p.update(
            run_id="20261201T010000Z-vetting-run-abc1234-0002", catalogs="2026-12-01T000000Z"
        ),
    )

    def product(provenance, key, suspect):
        return {
            "provenance": provenance,
            "s3_key": key,
            "sha256": "0" * 64,
            "timing_suspect": suspect,
        }

    spoc = product("SPOC", "mast/spoc/s0002_lc.fits", False)
    sectors = {
        "1": {"status": "kept", "base": spoc, "fresh": spoc},
        "2": {
            "status": "kept_m2",
            "base": spoc,
            "fresh": product("TESS-SPOC", "mast/tess-spoc/s0002.fits", False),
        },
        "64": {
            "status": "redelivered",
            "base": product("QLP", "mast/qlp/s0064/hlsp_qlp_v01_llc.fits", True),
            "fresh": product("QLP", "mast/qlp/s0064/hlsp_qlp_v02_llc.fits", False),
        },
        "65": {"status": "added", "base": None, "fresh": spoc},
        "110": {"status": "added", "base": None, "fresh": spoc},
    }
    merge = {
        "1": {
            "base_sha256": "1" * 64,
            "lc_sha256": "2" * 64,
            "fetch": {"status": "ok", "problems": {}},
            "sectors": sectors,
        }
    }
    (version / "merge.json").write_text(json.dumps(merge))
    revet_made = {
        "run_id": "20261201T000000Z-revet-fetch-abc1234-0001",
        "stage": "revet-fetch",
        "production": True,
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
    }
    (version / "provenance-merge.json").write_text(json.dumps(revet_made))
    return version


PACKAGE = "20261112T000000Z-predictions-abc1234-0001"


def test_dossier_says_what_changed(tmp_path, monkeypatch):
    signal, _ = draft(tmp_path, monkeypatch, review=REVIEW, call=HELD)
    m3_text = (signal / "dossier.md").read_text()
    version = version_dir(signal)
    prereg_result = {
        "package": PACKAGE,
        "as_of": "2027-01-20",
        "judged_by": "2027-12-31",
        "predicted_sectors": [112, 113, 114],
        "result": "untested",
        "status": "untestable",
        "reason": "no training cadences in the held-out season's qlp family",
    }
    (version / "prereg.json").write_text(json.dumps(prereg_result))
    text = dossier.render(version)
    assert text.startswith("# 1-1 r2: TIC 1\n")
    changes = " ".join(section(text, "Changes since the M3 record").split())
    assert "[The M3 record](../dossier.md) stays as it was published" in changes
    assert "revet fetch run 20261201T000000Z-revet-fetch-abc1234-0001" in changes
    assert "Sectors added: S65 (SPOC) and S110 (SPOC)." in changes
    assert (
        "Redelivered (a timing-suspect product replaced by the same product's newer delivery): S64 (QLP, "
        "hlsp_qlp_v01_llc.fits replaced by hlsp_qlp_v02_llc.fits)." in changes
    )
    assert "S2 (SPOC kept, TESS-SPOC not taken)" in changes
    # A window in a sector the light curve already holds was not a prediction.
    assert "The windows for S110 under Next TESS looks are post-dictions" in changes
    # What a fresh snapshot changed, read from the two checks.json files alone.
    assert "catalog snapshot `snap`" in changes and "`2026-12-01T000000Z`" in changes
    assert "Masked rows: new: 7.30000 d (t0 BTJD 1330.0000)." in changes
    assert "Catalogued rows on the star: new: CTOI candidate CTOI-1.01 at 7.30000 d." in changes
    assert (
        "Novelty: pass (no known object matches) in the M3 record, inconclusive (matches only SPOC TCE or "
        "ExoMiner rows) in this version." in changes
    )
    assert (
        "Its matches: new: ExoMiner-v2 ExoMiner vetting_catalog_FFI 1-1-S65 at 5 d, ratio 1."
        in changes
    )
    # The preregistered test beside vet-v3's own held-out result.
    real = section(text, "Real and new?").strip().split("\n")
    at = next(i for i, line in enumerate(real) if line.startswith("- Held-out seasons: "))
    assert real[at + 1] == (
        "- The preregistered test of the new season "
        "([decision 0040](../../../../docs/decisions/0040-predictions-for-held-signals.md)), package "
        f"{PACKAGE}, as of 2027-01-20: untested (untestable): no training cadences in the held-out season's qlp "
        "family. It judges only the new season, against the prediction published before that season; vet-v3's "
        "held-out check above holds out each season in turn and refits on the rest."
    )
    replicated = {
        **{k: v for k, v in prereg_result.items() if k != "reason"},
        **{"result": "replicated", "status": "predicted", "depth": 0.0016, "err": 0.0002, "n": 40},
        **{"sigma": 8.0, "expected_snr": 8.5, "tension": 0.5},
    }
    (version / "prereg.json").write_text(json.dumps(replicated))
    assert (
        "as of 2027-01-20: replicated (predicted): depth 1600 ppm (error 200 ppm, 40 cadences in the cores), "
        "8.00 sigma, expected SNR 8.50, tension 0.50 sigma."
    ) in dossier.render(version)
    # A value the record lacks raises rather than rendering.
    (version / "prereg.json").write_text(
        json.dumps({k: v for k, v in replicated.items() if k != "sigma"})
    )
    with pytest.raises(KeyError, match="sigma"):
        dossier.render(version)
    (version / "prereg.json").write_text(json.dumps(prereg_result))
    text = dossier.render(version)
    # Its links climb one level more than the M3 record's, and lead where they did.
    linked = re.findall(r"\]\(\.\./\.\./\.\./\.\./(docs/decisions/[^)]+)\)", text)
    assert "docs/decisions/0041-revets-as-versions.md" in linked
    assert all((REPO / path).is_file() for path in linked)
    assert "](../../../docs/" not in text and "[The vetting README](../../README.md)" in text
    # The M3 record renders as it did.
    assert dossier.render(signal) == m3_text
    assert "Changes since" not in m3_text and "preregistered test" not in m3_text


def predictions_package(tmp_path: Path, vetting_run: Path, record: Path) -> Path:
    """A finished production predictions package for 1-1, from its published record and the light curve its vetting
    run read, holding the files the test reads as `predictions run` writes them."""
    crit_search, crit_vet = load_criteria(tv.SEARCH), load_criteria(tv.VET3)
    # The fixture's tess-point puts the star in S115 too, which the sectors file does not date yet.
    s115 = {"sector": 115, "start_utc": "2027-03-14T00:00:00", "end_utc": "2027-04-10T00:00:00"}
    sectors = pd.concat(
        [pd.read_csv(REPO / crit_vet["predict"]["sectors_file"]), pd.DataFrame([s115])],
        ignore_index=True,
    )
    prediction = prereg.predict_signal(
        record,
        LightCurve.load(tmp_path / "data" / "lc" / "1.npz"),
        load_known(tmp_path / "snap"),
        crit_search.values,
        crit_vet.values,
        sectors,
        dt.date(2026, 10, 1),
    )
    path = tmp_path / "data" / "runs" / PACKAGE
    path.mkdir(parents=True)
    references = {
        "test": {
            "holdout": crit_vet["holdout"],
            "core_fraction": crit_vet["depth"]["core_fraction"],
            "families": crit_vet["families"],
        },
        "signals": {NAME: {k: v for k, v in prediction.items() if k != "transits"}},
    }
    (path / "references.json").write_text(
        json.dumps(jsonable(references), indent=2, sort_keys=True) + "\n"
    )
    rows = [{"signal": NAME, "tic": 1, **t} for t in prediction["transits"]]
    pd.DataFrame(rows).to_csv(path / "predictions.csv", index=False)
    made = {
        "run_id": PACKAGE,
        "stage": "predictions",
        "production": True,
        "started_at": "2026-11-12T00:00:00+00:00",
        "ended_at": "2026-11-12T00:01:00+00:00",
        "git": {"commit": "abc1234" + "0" * 33, "dirty_paths": []},
        "criteria": json.loads((vetting_run / "provenance.json").read_text())["criteria"],
        "vetting_run": vetting_run.name,
        # A package records the light curve each signal's vetting run read.
        "inputs": {
            "light_curve_1": json.loads((vetting_run / "provenance.json").read_text())["inputs"][
                "light_curve_1"
            ]
        },
        "summary": {},
    }
    (path / "provenance.json").write_text(json.dumps(made, indent=2))
    return path


def prereg_argv(runs: dict[str, Path], package: Path, as_of: str) -> list[str]:
    return [
        *("vetting", "prereg", "--run", str(runs["run"]), "--package", str(package)),
        *("--catalogs", str(runs["run"].parents[2] / "snap"), "--as-of", as_of),
        *("--criteria-search", str(tv.SEARCH), "--criteria-vet", str(tv.VET3)),
    ]


def prereg_runs(tmp_path) -> set[Path]:
    return set((tmp_path / "data" / "runs").glob("*-vetting-prereg-*"))


def passing_gates(package: Path) -> Path:
    """A copy of `package` whose counts pass holdout's two training gates, so the test reaches the rules after them."""
    path = package.parent / PACKAGE.replace("-0001", "-0002")
    shutil.copytree(package, path)

    def two_seasons(references: dict) -> None:
        for p in references["signals"].values():
            p["training_seasons"] = [{**p["training_seasons"][0], "holds_transits": True}] * 2

    edit_json(path / "references.json", two_seasons)
    edit_json(path / "provenance.json", lambda p: p.update(run_id=path.name))
    return path


def test_the_fetch_date_is_known_only_for_a_light_curve_a_finished_revet_fetch_run_wrote(
    tmp_path, monkeypatch
):
    m3, repo = published_m3(tmp_path, monkeypatch)
    package = predictions_package(tmp_path, m3["run"], repo / "results" / "vetting" / NAME)
    today = dt.datetime.now(dt.UTC).date().isoformat()
    # The light curve the package was made from: no fetch date.
    assert main(prereg_argv(m3, package, today)) == 0
    [own] = prereg_runs(tmp_path)
    assert json.loads((own / "signals" / NAME / "prereg.json").read_text())["fetched"] is None
    # A light curve no revet fetch run made.
    elsewhere = tmp_path / "elsewhere"
    shutil.copytree(revet_run(tmp_path, tag="x") / "lc", elsewhere)
    runs = revetted(tmp_path, monkeypatch, None, lc_dir=elsewhere)
    with pytest.raises(SystemExit, match="so when it was fetched is unknown"):
        main(prereg_argv(runs, package, today))
    # One its revet fetch run's merge record does not name: the date would be another file's.
    lc_run = revet_run(tmp_path, tag="y")
    runs = revetted(tmp_path, monkeypatch, lc_run)
    merged = (lc_run / "merge.json").read_text()
    edit_json(lc_run / "merge.json", lambda m: m["1"].update(lc_sha256="0" * 64))
    with pytest.raises(
        SystemExit, match=f"another light curve for TIC 1 than revet fetch run {lc_run.name} made"
    ):
        main(prereg_argv(runs, package, today))
    (lc_run / "merge.json").write_text(merged)
    # And one from a revet fetch run that never finished.
    edit_json(lc_run / "provenance.json", lambda p: p.update(ended_at=None))
    with pytest.raises(SystemExit, match="so when it was fetched is unknown"):
        main(prereg_argv(runs, package, today))
    assert prereg_runs(tmp_path) == {own}


def test_a_version_of_a_predicted_signal_carries_the_preregistered_test(tmp_path, monkeypatch):
    m3, repo = published_m3(tmp_path, monkeypatch)
    lc_run = revet_run(tmp_path)
    runs = revetted(tmp_path, monkeypatch, lc_run)
    record = repo / "results" / "vetting" / NAME
    package = predictions_package(tmp_path, m3["run"], record)
    # A second signal on the star, which only the r3 re-vet below vets.
    edit_json(
        package / "references.json",
        lambda r: r["signals"].update({"1-2": {**r["signals"][NAME], "signal": "1-2"}}),
    )
    rows = pd.read_csv(package / "predictions.csv")
    pd.concat([rows, rows.assign(signal="1-2")]).to_csv(package / "predictions.csv", index=False)
    today = dt.datetime.now(dt.UTC).date()
    for argv, message in (
        (prereg_argv(runs, package, (today + dt.timedelta(days=1)).isoformat()), "after today"),
        # Judged on a day before the vetting run read its light curve, a result could be pending after the
        # judging date (decision 0040 judges a signal once).
        (prereg_argv(runs, package, "2026-01-01"), "before the day .* started"),
        (prereg_argv({"run": runs["suspect"]}, package, today.isoformat()), "evidence-only"),
    ):
        with pytest.raises(SystemExit, match=message):
            main(argv)
    assert not prereg_runs(tmp_path)
    assert main(prereg_argv(runs, package, today.isoformat())) == 0
    [made] = prereg_runs(tmp_path)
    result = json.loads((made / "signals" / NAME / "prereg.json").read_text())
    # The M3 light curve holds one season with trustworthy timestamps (S64 is timing-suspect): the package's gates
    # leave the new season untested, whatever the re-vet's light curve holds.
    assert (result["result"], result["status"]) == ("untested", "untestable")
    assert result["reason"].startswith("1 training season(s), need 2")
    assert result["package"] == PACKAGE and result["vetting_run"] == runs["run"].name
    assert result["signal"] == {"name": NAME, "tic": 1}
    # When the light curve was fetched: the revet fetch run's start.
    assert result["fetched"] == "2026-12-01"
    inputs = json.loads((made / "provenance.json").read_text())["inputs"]
    assert inputs["package_references"]["sha256"] == sha256_file(package / "references.json")
    assert inputs["light_curve_1"]["sha256"] == sha256_file(lc_run / "lc" / "1.npz")
    production(made)
    # A light curve fetched on or after the judging date completes no season: on a package whose counts pass the
    # training gates, the late fetch alone leaves the season untested, and the run says when it was fetched.
    late = revetted(
        tmp_path,
        monkeypatch,
        revet_run(tmp_path, tag="late", started="2028-01-02T00:00:00+00:00"),
    )
    assert main(prereg_argv(late, passing_gates(package), today.isoformat())) == 0
    [late_made] = prereg_runs(tmp_path) - {made}
    result = json.loads((late_made / "signals" / NAME / "prereg.json").read_text())
    assert result["fetched"] == "2028-01-02"
    assert (result["result"], result["status"]) == ("untested", "fetched_after_judged_by")
    production(late_made)

    # A package not published under results/predictions/ predicts nothing a version can carry.
    version = called(record / "r2")
    before = published(repo)
    with pytest.raises(SystemExit, match=f"no package under results/predictions/ predicts {NAME}"):
        main([*version_argv(runs), "--prereg", str(made)])
    assert published(repo) == before
    # Once it is published, a version of a signal it predicts carries the test.
    published_package = repo / "results" / "predictions" / PACKAGE
    published_package.mkdir(parents=True)
    for name in ("references.json", "predictions.csv", "provenance.json"):
        shutil.copyfile(package / name, published_package / name)
    with pytest.raises(SystemExit, match="carries the preregistered test"):
        main(version_argv(runs))
    assert published(repo) == before
    assert main([*version_argv(runs), "--prereg", str(made)]) == 0
    judged = sha256_file(made / "signals" / NAME / "prereg.json")
    assert sha256_file(version / "prereg.json") == judged
    assert sha256_file(version / "provenance-prereg.json") == sha256_file(made / "provenance.json")
    real = " ".join(section((version / "dossier.md").read_text(), "Real and new?").split())
    assert (
        f"package {PACKAGE}, as of {today}: untested (untestable): 1 training season(s), need 2"
        in real
    )
    assert "Carried" not in real
    assert calls.problems(version) == []

    # r2's result is not pending, so it stands: nothing judges the signal again, and r3 carries it. A re-vet that
    # also vets 1-2, which no version judged, judges only 1-2 and says why it left 1-1 out.
    signals = tmp_path / "signals.csv"
    one = pd.read_csv(signals)
    pd.concat([one, one.assign(name="1-2")]).to_csv(signals, index=False)
    lc_run3 = revet_run(tmp_path, tag="r3", base=lc_run / "lc", sector=66)
    runs3 = revetted(tmp_path, monkeypatch, lc_run3)
    assert main(prereg_argv(runs3, package, today.isoformat())) == 0
    [skipping] = prereg_runs(tmp_path) - {made, late_made}
    assert [p.name for p in (skipping / "signals").iterdir()] == ["1-2"]
    made3 = json.loads((skipping / "provenance.json").read_text())
    judged_in = f"judged in results/vetting/{NAME}/r2 (untested)"
    assert made3["skipped"] == made3["summary"]["skipped"] == {NAME: judged_in}
    assert list(made3["summary"]["signals"]) == ["1-2"]
    assert f"checks_{NAME}" not in made3["inputs"] and "checks_1-2" in made3["inputs"]
    # A run with no signal left to judge is refused.
    with pytest.raises(SystemExit, match=f"{NAME} was judged in results/vetting/{NAME}/r2"):
        main(prereg_argv(runs, package, today.isoformat()))
    assert prereg_runs(tmp_path) == {made, late_made, skipping}
    r3 = called(record / "r3")
    before = published(repo)
    with pytest.raises(SystemExit, match="carries r2's preregistered test"):
        main(version_argv(runs3, 3))
    assert published(repo) == before
    # Another preregistered-test run, made from another vetting run, is not r2's: refused.
    with pytest.raises(SystemExit, match="was made from"):
        main([*version_argv(runs3, 3), "--prereg", str(late_made)])
    assert published(repo) == before
    # With the package gone from results/predictions/, r2's result stands all the same: still carried, still needed.
    published_package.rename(tmp_path / "unpublished")
    with pytest.raises(SystemExit, match="carries r2's preregistered test"):
        main(version_argv(runs3, 3))
    assert published(repo) == before
    assert main([*version_argv(runs3, 3), "--prereg", str(made)]) == 0
    assert sha256_file(r3 / "prereg.json") == judged
    assert sha256_file(r3 / "provenance-prereg.json") == sha256_file(made / "provenance.json")
    real = " ".join(section((r3 / "dossier.md").read_text(), "Real and new?").split())
    carried = (
        f"Carried unchanged from r2, which judged it (vetting run {runs['run'].name}): decision 0040 judges a "
        "signal once."
    )
    assert carried in real
    assert calls.problems(r3) == []

    # An r4 draft names r2 as the published render would, though r2 is not the record before it.
    lc_run4 = revet_run(tmp_path, tag="r4", base=lc_run3 / "lc", sector=67)
    runs4 = revetted(tmp_path, monkeypatch, lc_run4)
    out = tmp_path / "drafts"
    roles = ("run", "suspect", "triceratops", "literature", "lc_run")
    argv = [
        *("vetting", "dossier", *flags(runs4, *roles), "--prereg", str(made)),
        *("--version", "4", "--signals", NAME, "--out", str(out)),
    ]
    assert main(argv) == 0
    real = " ".join(
        section((out / NAME / "r4" / "dossier.md").read_text(), "Real and new?").split()
    )
    assert carried in real
