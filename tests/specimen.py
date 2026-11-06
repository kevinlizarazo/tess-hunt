"""A specimen of the preprint (decision 0043): the paper rendered from a made-up pass, so its template can be reviewed
before any real result exists. The pass is built with the tests' fixtures in a temporary repo and data directory, so
the script never touches results/ or $TESS_HUNT_DATA, and nothing it makes is deposited. It is a script, not a test:

    uv run --group preprint python tests/specimen.py --out DIR

writes specimen.md, specimen.pdf and the paper's figures to DIR. The record's fits are vet's own, seeded, and the paper
reproduces one of them, so a run takes about ten minutes.
"""

import argparse
import datetime as dt
import json
import logging
import shutil
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import test_calls as tc
import test_dossier as td
import test_literature as tl
import test_preprint as tp
import test_vetting as tv
from synthetic import make_transit_lc

from tess_hunt import literature, predict, preprint, provenance
from tess_hunt.cli import main
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file

# The fixtures' TIC 1 is a real star (MAST, 2026-11-02). TIC v8's ids stay far below this one, which MAST has no row
# for, so it can't name a real star.
TIC = 9310582746
NAME = f"{TIC}-1"
# A Sun-like dwarf's TIC values, with errors of the size TIC v8 gives such a star, and a signal off the fixtures' round
# 5-day grid, so a reader judges the prose and not a toy.
STAR = {
    "tmag": 9.43,
    "teff": 5712.0,
    "e_teff": 126.0,
    "rad": 0.97,
    "e_rad": 0.052,
    "rho": 1.07,
    "e_rho": 0.12,
    "ruwe": 0.85,
}
SIGNAL = {"period": 4.71836, "t0": 1326.4172, "duration": 0.126, "depth": 0.00168}
# SPOC's 2-minute cadence, at the fixtures' own 2-minute noise.
CADENCE_MIN, NOISE_PPM = 2.0, 600.0
# The first field of a Tycho-2 name is a Guide Star Catalog region, 1 to 9537, so no real star has this name.
TYCHO = "TYC 9601-327-1"
# A CTOI is named after its star's TIC, so this one can't be real either.
LISTING = f"CTOI-{TIC}.01"
# One order for the made-up story, which the paper prints: the first vetting run, then its review and held call
# (2026-10-27, 2026-10-28), the predictions package (tp.PACKAGE, made 2026-11-12) and its Zenodo deposit, which is the
# claim, then ExoFOP's later CTOI, then version r2's vetting run before Sector 112 starts (2026-12-22), its review and
# call, the preregistered result (2027-02-20) and the paper. The runs take their ids from this clock, not today's.
FIRST_VETTING = dt.datetime(2026, 10, 20, 9, 0, tzinfo=dt.UTC)
R2_VETTING = dt.datetime(2026, 12, 18, 9, 0, tzinfo=dt.UTC)
VERSION = dt.date(2027, 2, 24)
# The claim is the predictions deposit, as for tess-hunt's real held signals, published by decision 0040's deadline for
# a lock before the predicted sectors; the DOI is the fixtures' made-up one.
CLAIM = {"date": "2026-11-14", "record": f"https://doi.org/{tp.DOI}"}
CTOI_LISTED = "2026-12-15"
PIXEL_REASON = f'centroid offset {td.S64["offset_arcsec"]}" within 15"'
# The paper names the papers the literature search found and what ExoFOP lists on the star, so neither may be real. An
# arXiv id's month runs to 12, so this one names no paper. Its title reads as a paper that would list the star by its
# Tycho-2 name without reporting a transit, and with no spectrum of it, as the call and the review's F4 say.
HIT = tl.paper(
    "Rotation Periods of Bright Southern Solar Analogues from TESS Full-Frame Images",
    arxiv="2613.00001",
)
EXOFOP = {
    "status": "ok",
    "error": None,
    "tois": [],
    # The CTOI decision 0042 sets aside, as ExoFOP lists it on the star.
    "ctois": [{"ctoi": f"TIC {TIC}.01", "cdisp": "PC"}],
    "planets": [],
    "confirmed_planets": None,
    "imaging": [
        {"itype": "Speckle", "itel": "Gemini (8 m)", "iinst": "'Alopeke", "icont": "4.49 @ 0.5"}
    ],
}
REVIEW = {**tc.REVIEW, "signal": NAME, "hits_flagged": [HIT["arxiv"]]}
# r2's review adds a confirmed finding no refuter ran on, beside F2, whose refuters did.
REVIEW_R2 = {
    **REVIEW,
    "date": "2027-01-18",
    "findings": [
        *REVIEW["findings"],
        {
            "id": "F4",
            "lens": "planet",
            "rating": "hold",
            "claim": "the radius rests on the TIC's stellar radius, which no spectrum has checked",
            "evidence": "fit_prior",
            "refuters": [],
        },
    ],
}
# The first record held on its one season, which the held-out check needs two of; r2's Sector 65 is the second, and its
# held-out check passes, so the pass follows from the evidence the held call named.
HELD = tc.HELD
for old, new in (
    (tc.NAME, NAME),
    (
        "The public data can't tell the two stars apart.",
        "The held-out check has only one season to test.",
    ),
    ('rests_on = ["F2"]', 'rests_on = ["holdout"]'),
    (
        "High-resolution imaging of the 12.5 arcsec companion.",
        "A second season of TESS data, which the held-out check can test against the first.",
    ),
):
    HELD = tc.edit(HELD, old, new)
PASSED = tc.PASSED
for old, new in (
    (tc.NAME, NAME),
    ("2026-10-28", "2027-01-20"),
    ("the one hold is answered", "both holds are answered"),
    (
        "[answers]\n",
        "[answers]\nF4 = \"The radius scales with the TIC's stellar radius; a spectrum of the star is "
        'follow-up work."\n',
    ),
    ("nobody lists it", "no listing before our claim names it"),
    (tc.REVIEW["hits_flagged"][0], HIT["arxiv"]),
):
    PASSED = tc.edit(PASSED, old, new)
# One note beside a confirmed finding and one beside a note, under decision 0037.
NOTES = """\
[[note]]
finding = "F2"
date = 2027-01-25
text = "neighbours.csv gives that star's separation as 12.0 arcsec, not 12.5."

[[note]]
finding = "F1"
date = 2027-01-25
text = "The sector_depth check in checks.json finds the three sectors' depths agree."
"""
PREREG = {
    **tp.PREREG,
    "signal": {"name": NAME, "tic": TIC},
    # After the deposit, as the paper requires.
    "predicted_sectors": [112, 113],
    # Near the earlier seasons' core depths, which the record's odd-even check gives as about 1790 ppm.
    "depth": 0.00172,
    "err": 0.00019,
    "sigma": 9.05,
    "expected_snr": 9.42,
    "tension": 0.37,
}


def triage_run(tmp: Path) -> Path:
    """tv.triage_run's run, its rows moved from TIC 1 to the made-up star and its signal, with the S64 offset
    td.vetting_runs adds."""
    run = tv.triage_run(tmp)
    rows = tmp / "data" / "runs" / tv.SEARCH_RUN / "signals.parquet"
    found = pd.read_parquet(rows).replace({"tic": {1: TIC}})
    found.loc[(found["tic"] == TIC) & (found["rank"] == 1), list(SIGNAL)] = list(SIGNAL.values())
    found.to_parquet(rows)
    td.edit_json(
        run / "provenance.json",
        lambda p: p["inputs"]["search_signals"].update(sha256=sha256_file(rows)),
    )
    old = run / "evidence" / "1-1.json"
    evidence = json.loads(old.read_text())
    evidence["signal"]["tic"] = TIC
    evidence["pixels"]["evidence"]["sectors"].append(td.S64)
    evidence["pixels"]["evidence"]["offset_qual_arcsec"] = td.S64["offset_arcsec"]
    # The reason names the best-quality offset the pass rests on, as the pixel check writes it.
    evidence["pixels"]["reason"] = PIXEL_REASON
    (run / "evidence" / f"{NAME}.json").write_text(json.dumps(evidence))
    old.unlink()
    return run


def vetted(tmp: Path, argv: list[str]) -> tuple[Path, Path]:
    """The vetting run `argv` makes, and its evidence-only twin."""
    runs = tmp / "data" / "runs"
    before = set(runs.glob("*-vetting-run-*"))
    assert main(argv) == 0
    assert main([*argv, "--include-suspect"]) == 0
    made = {
        json.loads((p / "provenance.json").read_text())["evidence_only"]: p
        for p in set(runs.glob("*-vetting-run-*")) - before
    }
    return made[False], made[True]


def transit_lc(cadences: dict, noise_ppm: dict, **kwargs) -> LightCurve:
    """The light curves setup and td.revet_run make, with the transit at the signal's ephemeris and each sector at
    SPOC's 2-minute cadence, which the paper's "SPOC 2-minute light curves" and TRICERATOPS's 120-s data name: the
    fixtures' 30-minute cadence would contradict both."""
    return make_transit_lc(
        period=SIGNAL["period"],
        t0=SIGNAL["t0"],
        cadences=dict.fromkeys(cadences, CADENCE_MIN),
        noise_ppm=dict.fromkeys(cadences, NOISE_PPM),
        **kwargs,
    )


def vetting_runs(tmp: Path, mp) -> tuple[Path, Path]:
    """td.vetting_runs for the made-up star and its signal, whose files that function names by TIC 1."""
    mp.setattr(tv, "CANDIDATE", {**tv.CANDIDATE, **STAR, "tic": TIC})
    mp.setattr(tv, "SIGNAL", SIGNAL)
    mp.setattr(tv, "make_transit_lc", transit_lc)
    mp.setattr(td, "make_transit_lc", transit_lc)
    signal = {"name": NAME, "tic": TIC, **SIGNAL, "kind": "candidate"}
    # vet's own fit, seeded by the criteria, so the paper's reproduction of it is checked as a real record's is.
    argv, _ = tv.setup(tmp, mp, signals=[signal], suspect={64})
    # A deposit predicts only sectors tess-point placed the star in.
    mp.setattr(
        predict,
        "tess_stars2px_function_entry",
        lambda tic, ra, dec: (None, None, None, np.array([35, 112, 113, 115])),
    )
    path = tmp / "data" / "lc" / f"{TIC}.npz"
    lc = LightCurve.load(path)
    for i, source in enumerate(lc.sources.values()):
        source["crowdsap"] = 0.9 + 0.01 * i
    lc.save(path)
    mp.setattr(provenance, "_now", lambda: FIRST_VETTING)
    return vetted(tmp, [*argv, "--triage-run", str(triage_run(tmp))])


def literature_record(run: Path, mp) -> dict:
    """td.literature_record for the made-up star, whose fixture names TIC 1 and HD 1, complete as a pass needs."""
    mp.setattr(literature.time, "sleep", lambda s: None)
    names = [f"TIC {TIC}", TYCHO]
    web = tl.Web(names={TIC: names}, hits={("arxiv", TYCHO): [HIT]})
    simbad = literature.simbad_record(TIC, web)
    search = {
        "simbad": simbad,
        **literature.search_all(TIC, names, web, None, tl.CFG, simbad=simbad),
        # The fixture's ExoFOP answer is a real star's.
        "exofop": EXOFOP,
    }
    return {
        "signal": {"name": NAME, "tic": TIC},
        "vetting_run": run.name,
        "search": search,
        **literature.literature_check(search).to_dict(),
        "outcome": "pass",
        "reason": "complete",
    }


def made_from(tmp: Path, mp, run: Path, suspect: Path, tag: str) -> dict[str, Path]:
    """The TRICERATOPS, literature and titles runs made from the vetting run `run`, as td.all_runs makes them."""
    tric = {**td.triceratops_record(run), "signal": {"name": NAME, "tic": TIC}}
    # TRICERATOPS read the vetting run's own 2-minute SPOC light curves, as a real run on them would.
    tric["evidence"] = {**tric["evidence"], "exposure_s": 120.0}
    tric_run = td.made_run(
        tmp,
        "vetting-triceratops",
        run,
        {NAME: {"triceratops.json": tric, "probs.csv": "ID,prob\n1,0.98\n"}},
        tag=tag,
    )
    lit = td.made_run(
        tmp,
        "vetting-literature",
        run,
        {NAME: {"literature.json": literature_record(run, mp)}},
        tag=tag,
    )
    return {
        "run": run,
        "suspect": suspect,
        "triceratops": tric_run,
        "literature": lit,
        "titles": td.titles_run(tmp, lit, tag=tag),
    }


def judged(checks: dict) -> None:
    """r2's checks as a pass needs them, as test_preprint.published and td.claimed_pass set them: the held-out check
    passed, and novelty failed on a CTOI listed after the claim, which decision 0042 sets aside."""
    tp.held_out_passed(checks)
    for c in checks["checks"]:
        if c["check"] == "novelty":
            match = {"source": "CTOI", "name": LISTING, "period": SIGNAL["period"], "ratio": 1.0}
            c.update(
                outcome="fail",
                reason=f"matches {LISTING}",
                evidence={"category": "known", "matches": [match]},
            )


def claims_run(tmp: Path, run: Path, lit: Path, tag: str) -> Path:
    """td.claims_run for the made-up star: the claims run that sets aside the later CTOI."""
    listing = {
        **td.later_listing("CTOI", LISTING, CTOI_LISTED),
        "tic": TIC,
        "period": SIGNAL["period"],
    }
    record = {
        **td.claims_record(run, lit, [listing], td.RERUN),
        "signal": {"name": NAME, "tic": TIC},
        "claim": CLAIM,
    }
    path = td.made_run(tmp, "vetting-claims", run, {NAME: {"claims.json": record}}, tag=tag)
    written = path / "signals" / NAME / "claims.json"
    read = lit / "signals" / NAME / "literature.json"

    def provenance(p):
        p["literature_run"] = lit.name
        p["inputs"][f"literature_{NAME}"] = {"file": read.name, "sha256": sha256_file(read)}
        p["summary"] = {"signals": {NAME: {"tic": TIC, "sha256": sha256_file(written)}}}

    td.edit_json(path / "provenance.json", provenance)
    return path


def publish(runs: dict[str, Path], *roles: str) -> list[str]:
    return ["vetting", "publish", "--name", NAME, *td.flags(runs, *roles)]


def prepared(repo: Path) -> None:
    """What `preprint run` reads beside the record, as tp.prepared writes it, for the made-up star, its claim and the
    predictions deposit, with the repository's own author line: the maintainer reads the author block the paper will
    print."""
    tp.published_runs(repo)
    signals = repo / "results" / "triage" / tv.TRIAGE_RUN / "signals.csv"
    rows = pd.read_csv(signals).assign(tic=TIC)
    rows.loc[rows["rank"] == 1, "pixels_reason"] = PIXEL_REASON
    rows.to_csv(signals, index=False)
    preprints = repo / "results" / "preprints"
    preprints.mkdir()
    shutil.copy(tp.REPO / preprint.TEMPLATE, preprints)
    shutil.copy(tp.REPO / preprint.AUTHOR, preprints)
    (repo / "results" / "claims.toml").write_text(
        f'["{NAME}"]\ndate = {CLAIM["date"]}\nrecord = "{CLAIM["record"]}"\n'
    )
    predictions = repo / "results" / "predictions"
    predictions.mkdir()
    (predictions / "dois.toml").write_text(
        f'["{tp.PACKAGE}"]\ndoi = "{tp.DOI}"\nconcept = "10.5281/zenodo.99999998"\n'
        f"published = {CLAIM['date']}\n"
    )


def build(tmp: Path, mp) -> tuple[Path, Path]:
    """The made-up pass in a repo of its own: an M3 record that held, then a re-vet published as r2 that passed, with
    a later CTOI set aside under decision 0042, notes under decision 0037 and a preregistered result. Returns the repo
    and the record the paper is rendered from."""
    run, suspect = vetting_runs(tmp, mp)
    m3 = made_from(tmp, mp, run, suspect, "a")
    td.production(*m3.values())
    repo = td.results_repo(tmp, mp)
    signal = repo / "results" / "vetting" / NAME
    signal.mkdir(parents=True)
    (signal / "call.toml").write_text(HELD)
    (signal / "review.json").write_text(json.dumps(REVIEW))
    assert main(publish(m3, "run", "triceratops", "literature", "suspect", "titles")) == 0
    prepared(repo)
    tp.commit(repo)

    lc_run = td.revet_run(tmp, tics=(TIC,))
    triage = tmp / "data" / "runs" / tv.TRIAGE_RUN
    # After ExoFOP lists the CTOI the run's novelty check matches, and before Sector 112, which tess-point places the
    # star in, begins.
    mp.setattr(provenance, "_now", lambda: R2_VETTING)
    run, suspect = vetted(
        tmp, [*tv.run_argv(tmp), "--triage-run", str(triage), "--lc-dir", str(lc_run / "lc")]
    )
    td.edit_json(run / "signals" / NAME / "checks.json", judged)
    tag = run.name[-4:]
    r2 = made_from(tmp, mp, run, suspect, tag)
    r2["claims"] = claims_run(tmp, run, r2["literature"], tag)
    td.production(*r2.values())
    r2["lc_run"] = lc_run
    version = signal / "r2"
    version.mkdir()
    (version / "call.toml").write_text(PASSED)
    (version / "review.json").write_text(json.dumps(REVIEW_R2))
    argv = [*publish(r2, *td.VERSION_ROLES, "claims"), "--version", "2"]
    assert main(argv) == 0
    (version / "review-notes.toml").write_text(NOTES)
    (version / "prereg.json").write_text(json.dumps(PREREG))
    tp.commit(repo)
    return repo, preprint.passed_record(signal)


def specimen(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp, pytest.MonkeyPatch.context() as mp:
        repo, record = build(Path(tmp), mp)
        author = preprint.load_author(repo / preprint.AUTHOR)
        text = preprint.render(record, author, repo, version=VERSION)
        out.mkdir(parents=True, exist_ok=True)
        for name in preprint.FIGURES:
            shutil.copyfile(record / "plots" / name, out / name)
        (out / "specimen.md").write_text(text)
        # The CLI logs at INFO, which would print each step of WeasyPrint's layout and font subsetting.
        logging.getLogger().setLevel(logging.WARNING)
        preprint.to_pdf(text, out, out / "specimen.pdf", specimen=True)
    print(f"specimen: {NAME}, rendered from {record.relative_to(repo)} -> {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", type=Path, required=True, help="where the specimen is written")
    specimen(parser.parse_args().out.expanduser())
