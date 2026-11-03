"""A specimen of the preprint (decision 0043): the paper rendered from a made-up pass, so its template can be reviewed
before any real result exists. The pass is built with the tests' fixtures in a temporary repo and data directory, so
the script never touches results/ or $TESS_HUNT_DATA, and nothing it makes is deposited. It is a script, not a test:

    uv run --group preprint python tests/specimen.py --out DIR

writes specimen.md, specimen.pdf and the paper's figures to DIR.
"""

import argparse
import functools
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

from tess_hunt import literature, predict, preprint
from tess_hunt.cli import main
from tess_hunt.fit import NAMES, FitResult
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file

# The fixtures' TIC 1 is a real star (MAST, 2026-11-02). TIC v8's ids stay far below this one, which MAST has no row
# for, so it can't name a real star.
TIC = 9310582746
NAME = f"{TIC}-1"
# A Sun-like dwarf's TIC values and a signal off the fixtures' round 5-day grid, so a reader judges the prose and not a
# toy.
STAR = {"tmag": 9.43, "teff": 5712.0, "rad": 0.97, "rho": 1.07, "e_rho": 0.12, "ruwe": 0.85}
SIGNAL = {"period": 4.71836, "t0": 1326.4172, "duration": 0.126, "depth": 0.00168}
# The first field of a Tycho-2 name is a Guide Star Catalog region, 1 to 9537, so no real star has this name.
TYCHO = "TYC 9601-327-1"
# A CTOI is named after its star's TIC, so this one can't be real either.
LISTING = f"CTOI-{TIC}.01"
# The claim is the predictions deposit, as for tess-hunt's real held signals, published by decision 0040's deadline for
# a lock before the predicted sectors; the DOI is the fixtures' made-up one.
CLAIM = {"date": "2026-11-05", "record": f"https://doi.org/{tp.DOI}"}
# The paper names the papers the literature search found and what ExoFOP lists on the star, so neither may be real. An
# arXiv id's month runs to 12, so this one names no paper.
HIT = tl.paper("A placeholder paper that names the star, for the specimen only", arxiv="2613.00001")
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
AUTHOR = """\
given_names = "Placeholder"
family_names = "Author"
affiliation = "Placeholder affiliation"
repository = "https://github.com/kevinlizarazo/tess-hunt"
"""
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
HELD = tc.edit(tc.HELD, tc.NAME, NAME)
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
    "depth": 0.00161,
    "err": 0.00019,
    "sigma": 8.47,
    "expected_snr": 8.84,
    "tension": 0.37,
}


def fit(lc, eph, cfg, rho_prior=None, seed=None) -> FitResult:
    """tv.fake_fit with a posterior that has width, as a real fit's has: the fixture's has none."""
    rng = np.random.default_rng(0)
    n = 4000
    values = {
        "t0": eph.t0 + rng.normal(0.0, 1e-3, n),
        "period": eph.period + rng.normal(0.0, 1e-5, n),
        "rp_rs": rng.normal(0.04, 0.0012, n),
        "b": np.abs(rng.normal(0.3, 0.12, n)),
        "log_rho": rng.normal(0.15, 0.04, n),
        "q1": rng.uniform(0.25, 0.45, n),
        "q2": rng.uniform(0.25, 0.45, n),
    }
    return FitResult(np.column_stack([values[name] for name in NAMES]), 0.3, rho_prior)


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


def vetting_runs(tmp: Path, mp) -> tuple[Path, Path]:
    """td.vetting_runs for the made-up star and its signal, whose files that function names by TIC 1."""
    mp.setattr(tv, "CANDIDATE", {**tv.CANDIDATE, **STAR, "tic": TIC})
    mp.setattr(tv, "SIGNAL", SIGNAL)
    # The light curves setup and td.revet_run make, the transit at the signal's ephemeris.
    transit = functools.partial(make_transit_lc, period=SIGNAL["period"], t0=SIGNAL["t0"])
    mp.setattr(tv, "make_transit_lc", transit)
    mp.setattr(td, "make_transit_lc", transit)
    signal = {"name": NAME, "tic": TIC, **SIGNAL, "kind": "candidate"}
    argv, _ = tv.setup(tmp, mp, signals=[signal], suspect={64}, fit=fit)
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
        **td.later_listing("CTOI", LISTING, "2026-12-15"),
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
    """What `preprint run` reads beside the record, as tp.prepared writes it, for the made-up star, its claim, the
    predictions deposit and the placeholder author."""
    tp.published_runs(repo)
    signals = repo / "results" / "triage" / tv.TRIAGE_RUN / "signals.csv"
    pd.read_csv(signals).assign(tic=TIC).to_csv(signals, index=False)
    preprints = repo / "results" / "preprints"
    preprints.mkdir()
    shutil.copy(tp.REPO / preprint.TEMPLATE, preprints)
    (preprints / "author.toml").write_text(AUTHOR)
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
        text = preprint.render(record, author, repo, specimen=True)
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
