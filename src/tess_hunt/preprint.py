"""The preprint and dataset for a passed signal (decision 0043; M5 design, section 4.4). `tess-hunt preprint run`
renders a short paper from the signal's latest published record, whose call must be a pass that stands on it, and
lays beside it the dataset its numbers come from: each published record of the signal up to that one and the light
curve the passing vet read. The template is filled with `substitute`, each value read by its key from the record, its
runs' provenance and the published runs they name, so a value they lack raises instead of rendering (docs/design.md,
section 5.5). The PDF needs the optional `preprint` dependency group."""

import datetime as dt
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path
from string import Template

import pandas as pd

from tess_hunt import calls, prereg, vetting
from tess_hunt.claims import CLAIMS, load_claims
from tess_hunt.config import runs_dir
from tess_hunt.ddt import _criteria, _from_triceratops, _number, _ppm
from tess_hunt.dossier import (
    SENTENCES,
    _f,
    _paper_id,
    _scrub,
    _summary,
    _table,
    _words,
)
from tess_hunt.provenance import publish_run, repo_root, sha256_file, start_run
from tess_hunt.tricera import TWO_MINUTES_S

TEMPLATE = "results/preprints/preprint.template.md"
# Its text changes only with the maintainer's approval (decision 0043).
AUTHOR = "results/preprints/author.toml"
AUTHOR_KEYS = ("given_names", "family_names", "affiliation", "repository")
AUTHOR_OPTIONAL = ("orcid", "email")
DOIS = "results/predictions/dois.toml"
SECTORS = "benchmarks/tess_sectors.csv"
# The injection-recovery run's recovered fraction by expected SNR, which the paper points to.
COMPLETENESS = "completeness_snr.csv"
EXOFOP_STAR = "https://exofop.ipac.caltech.edu/tess/target.php?id={}"
# The record's plots the paper shows. Its centroid plots draw Gaia DR3 stars, so they stay in the dataset under Gaia's
# terms and the paper is CC BY 4.0 whole.
FIGURES = ("transits.png", "folds.png", "odd_even.png", "phase.png")
# The paper's own captions for them, as plots.py draws them: the dossier's assume a reader inside the project.
CAPTIONS = {
    "transits.png": "Every predicted transit in the light curve, one panel each. Panel titles give the epoch (counted "
    "from t0) and the sector. Flux in ppm against hours from the predicted mid-transit time. Grey points are cadences, "
    "and blue points are their medians in bins an eighth of the transit's duration wide. The shaded band spans the "
    "duration. A panel with few points falls at the edge of a gap in the data",
    "folds.png": "The light curve folded on the ephemeris, one panel per season and light-curve product family. Panel "
    "titles give the family (`pdcsap` for SPOC's and TESS-SPOC's PDCSAP flux, `qlp` for QLP's), the season (counted "
    "from 0) and its sectors. Points and band as in Figure 1",
    "odd_even.png": "Odd-numbered (left) and even-numbered (right) transits, folded separately. Points and band as in "
    "Figure 1. The red line is the median flux in each one's core, the central half of the transit",
    "phase.png": "Flux against orbital phase over the whole orbit, with the transit at phase 0. Grey points are "
    "cadences, and blue points are their medians in bins half the transit's duration wide. The dashed line marks phase "
    "0.5, where a circular orbit puts a secondary eclipse. The red line marks the strongest secondary eclipse ModShift "
    "finds at any phase, labelled with its phase and significance",
}
PACKAGE = ["preprint.md", "preprint.pdf", "manifest.json", "provenance.json", *FIGURES]
CC_BY = "CC BY 4.0"
GAIA = "CC BY-NC 3.0 IGO"
# A record's files that hold Gaia DR3 data, as results/README.md lists them, by their path in the record.
GAIA_FILES = {
    "checks.json",
    "checks-with-suspect.json",
    "neighbours.csv",
    "triceratops.json",
    "plots/centroids.png",
    "pixels.png",
    "review.json",
    "review-scripts.tar.gz",
    "dossier.md",
}
# A record's files that hold ExoFOP's rows, which stay under ExoFOP's terms whatever the file's licence.
EXOFOP_FILES = {"literature.json", "claims.json", "dossier.md"}
EXOFOP = "ExoFOP's rows stay under ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php)"
SPECIMEN = "SPECIMEN: not a candidate"
# What each check asks, for a reader outside the project; a check missing here raises, so a new one is named first.
CHECKS = {
    "novelty": "Known objects at the period",
    "odd_even": "Odd against even transit depths",
    "secondary": "A dip at phase 0.5",
    "sector_depth": "Depth from sector to sector",
    "holdout": "Held-out seasons",
    "signal_present": "The dip's significance",
    "shape": "Transit shape",
    "density": "Transit stellar density against the TIC's",
    "radius": "The transiting body's radius",
    "neighbours": "Gaia DR3 neighbours that could make the dip",
    "pixels": "Difference-image centroid offset",
    "triceratops": "TRICERATOPS's false-positive probabilities",
    "literature": "Papers and ExoFOP listings",
}
# The question each of the review's lenses concerns: the dossier's short labels read as verdicts beside a finding.
QUESTIONS = {
    "on_star": "whether the dip is on the star",
    "planet": "whether it is a planet",
    "real_new": "whether it is real and new",
}
IS = {"pass": "passes", "fail": "fails", "inconclusive": "is inconclusive"}
WAS = {"pass": "passed", "fail": "failed", "inconclusive": "was inconclusive"}
# Counts from one to nine are spelled out in the paper's prose; measured values stay numerals.
SPELLED = ("no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")
ORDINALS = {
    2: "second",
    3: "third",
    4: "fourth",
    5: "fifth",
    6: "sixth",
    7: "seventh",
    8: "eighth",
    9: "ninth",
}
# How a listing's period relates to the signal's, by the novelty harmonic k it matched at (the signal's period is the
# listing's times k).
HARMONICS = {
    1.0: "this period",
    0.5: "twice this period",
    2.0: "half this period",
    1 / 3: "three times this period",
    3.0: "a third of this period",
}
# Why the held-out check could not test a season whose record gives a status and no reason.
UNTESTED = {
    "underpowered": "the depth expected there is too small against its error",
    "no_predicted_transit_in_data": "too few cadences fall in the predicted cores",
}
# The Summary's word on a preregistered result, after the sentence on the deposit.
SUMMARY_RESULT = {
    "replicated": " The transits appeared where predicted.",
    "missed": " The transits were missing where predicted.",
    "pending": " That test is not yet judged.",
    "untested": " The new data could not test that prediction.",
}
PDCSAP = ("SPOC 2-min", "TESS-SPOC")
PDCSAP_PAPERS = (
    "\n- PDCSAP flux: Smith, J. C., et al. 2012, PASP, 124, 1000; Stumpe, M. C., et al. 2012, PASP, 124, 985; "
    "Stumpe, M. C., et al. 2014, PASP, 126, 100"
)
# What each of a record's files holds, for the dataset's guide, in the order the paper lists them. A pattern ending in
# "/" is a directory; one with "*" matches file names.
GUIDE = (
    (
        "checks.json",
        "each vetting check's outcome, reason and evidence, both fits, the red-noise factors and the neighbour table",
    ),
    (
        "neighbours.csv",
        "the Gaia DR3 stars near the target, with the eclipse depth each would need to make the dip",
    ),
    (
        "checks-with-suspect.json",
        "the same checks with the timing-suspect sectors kept in, for comparison only",
    ),
    (
        "triceratops.json",
        "TRICERATOPS's runs: its probabilities, the stars it weighed and the depth it gave each",
    ),
    ("probs.csv", "TRICERATOPS's probability for each scenario"),
    ("pixels.json", "the second list's pixel check"),
    (
        "literature.json",
        "the literature search: the names searched, the papers found and ExoFOP's rows for the star",
    ),
    (
        "claims.json",
        "the claim, the listings decision record 0042 sorted and the novelty check run again",
    ),
    ("prereg.json", "the preregistered test's result"),
    ("merge.json", "what a re-vet's light curve changed"),
    ("review.json", "the review: each finding with its rating and its refuters' verdicts"),
    ("review-notes.toml", "the dated notes on the review's quoted text"),
    ("review-scripts.tar.gz", "the scripts the review ran"),
    ("call.toml", "the call"),
    (
        "provenance-*.json",
        "one run's commit, criteria and command, for the files that run wrote",
    ),
    ("plots/", "the record's figures, the centroid plot among them"),
    ("pixels.png", "the second list's centroid plot"),
    ("dossier.md", "tess-hunt's account of the record, in prose"),
)
# ACKNOWLEDGEMENTS.md's Gaia acknowledgement and the Gaia DR3 papers it asks for.
GAIA_CREDIT = (
    " This work has made use of data from the European Space Agency (ESA) mission Gaia (https://www.cosmos.esa.int/gaia), "
    "processed by the Gaia Data Processing and Analysis Consortium (DPAC, "
    "https://www.cosmos.esa.int/web/gaia/dpac/consortium). Funding for the DPAC has been provided by national "
    "institutions, in particular the institutions participating in the Gaia Multilateral Agreement."
)
GAIA_PAPERS = (
    "\n- Gaia: Gaia Collaboration, Prusti, T., et al. 2016, A&A, 595, A1; Gaia Collaboration, Vallenari, A., et al. "
    "2023 (doi:10.1051/0004-6361/202243940); Lindegren, L., Klioner, S., Hernández, J., et al. 2021, A&A, 649, A2; "
    "Riello, M., et al. 2021, A&A, 649, A3; Mowlavi et al. 2023, A&A, 674, A16; Creevey et al., arXiv:2206.05864"
)
STYLE = """
@page { size: A4; margin: 2cm; @bottom-right { content: counter(page); font-size: 9pt; } }
body { font-family: serif; font-size: 10.5pt; line-height: 1.35; }
h1 { font-size: 16pt; }
h2 { font-size: 12.5pt; margin-top: 1.2em; }
table { border-collapse: collapse; font-size: 9pt; }
th, td { border: 0.5pt solid #999; padding: 2pt 4pt; vertical-align: top; }
img { max-width: 100%; }
code { font-size: 9pt; }
"""
SPECIMEN_STYLE = f"""
@page {{ @top-center {{ content: "{SPECIMEN}"; }} @bottom-center {{ content: "{SPECIMEN}"; }} }}
"""
ZENODO = Template("""\
# Zenodo deposit form for $run_id

## Resource type

Publication / Preprint

## Title

$title

## Creators

$creators

## Description

$description

## Licence

- Creative Commons Attribution 4.0 International (CC BY 4.0): the paper, its figures and the dataset's other files
- Creative Commons Attribution-NonCommercial 3.0 IGO (CC BY-NC 3.0 IGO), ESA's terms for Gaia data
  (https://www.cosmos.esa.int/web/gaia-users/license): the dataset's files that hold Gaia DR3 data, which the
  description lists
- ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php): ExoFOP's rows in the dataset's `literature.json`,
  `claims.json` and `dossier.md`, and the ExoFOP listings the paper names

## Related identifiers

$related

## Keywords

- TESS
- transiting exoplanets
- planet candidates

## Files

Upload `preprint.pdf`, `preprint.md`, the figures (`$figures`), `manifest.json` and `provenance.json` from the run
directory. Upload its `dataset/` directory as one zip archive, so its folders are kept. `manifest.json` lists every
file in `dataset/` with its sha256.
""")


def passed_record(signal: Path) -> Path:
    """The signal's latest published record, when its call is a pass that stands on it and git shows no change under
    the signal's directory. Raises SystemExit otherwise, before anything is made."""
    where = f"results/vetting/{signal.name}"
    # The paper reads the record as it was published and committed; checked first, so the reasons below are the
    # committed record's.
    if prereg._uncommitted(signal):
        raise SystemExit(
            f"{where} has changes that are not committed; the paper reads the record as published"
        )
    records = vetting._records(signal)
    if not records:
        raise SystemExit(f"no published record in {where}")
    record = records[-1]
    label = vetting._label(record)
    found = calls.problems(record)
    if found:
        raise SystemExit(
            f"refused: the call in {signal.name}'s latest record, {label}, does not stand on it:\n"
            + "\n".join(f"- {p}" for p in found)
        )
    outcome = calls.load(record / "call.toml")["outcome"]
    if outcome != "passed":
        raise SystemExit(
            f"{signal.name}'s latest record, {label}, is {outcome}: only a pass that stands gets a preprint"
        )
    return record


def load_author(path: Path) -> dict:
    """The author line and the repository URL the paper gives, from `author.toml`."""
    if not path.is_file():
        raise SystemExit(
            f"no {AUTHOR}: the author line waits on the maintainer's approval (decision 0043)"
        )
    author = tomllib.loads(path.read_text())
    keys = set(author)
    if (
        not set(AUTHOR_KEYS) <= keys <= set(AUTHOR_KEYS + AUTHOR_OPTIONAL)
        or not all(isinstance(v, str) and v.strip() for v in author.values())
        or not author["repository"].startswith("https://")
    ):
        raise SystemExit(
            f"{path.name} needs {', '.join(AUTHOR_KEYS)} as text, repository an https URL, and may give "
            f"{' and '.join(AUTHOR_OPTIONAL)}"
        )
    return author


def _versions(record: Path) -> list[Path]:
    """The signal's published records before `record`, in order, then `record` itself."""
    number = calls.version(record) or 1
    earlier = [
        r for r in vetting._records(vetting._signal_dir(record)) if (calls.version(r) or 1) < number
    ]
    return [*earlier, record]


def _record_paths(record: Path) -> dict[str, Path]:
    """Each file in the directories of the signal's published records up to `record`, by its path under the
    dataset's `vetting/`, as results/vetting/ holds it."""
    signal = vetting._signal_dir(record)
    out = {}
    for r in _versions(record):
        for path in sorted(r.rglob("*")):
            # A version's directory sits inside the M3 record's and is a record of its own.
            if path.is_file() and calls.version(r / path.relative_to(r).parts[0]) is None:
                out[f"vetting/{signal.name}/{path.relative_to(signal)}"] = path
    return out


def record_files(record: Path) -> dict[str, Path]:
    """The records' files that git tracks: a file git ignores, such as macOS's .DS_Store, is no part of a record."""
    signal = vetting._signal_dir(record)
    listed = subprocess.run(
        ["git", "ls-files", "-z"], cwd=signal, capture_output=True, text=True, check=True
    ).stdout
    tracked = {signal / name for name in listed.split("\0") if name}
    return {name: path for name, path in _record_paths(record).items() if path in tracked}


def _light_curve(record: Path) -> tuple[str, Path]:
    """The light curve `record`'s vetting run read, by its path under the dataset, checked against the sha256 the run
    recorded."""
    made = json.loads((record / "provenance-checks.json").read_text())
    tic = int(json.loads((record / "checks.json").read_text())["tic"])
    path = vetting._light_curves(made) / f"{tic}.npz"
    if not path.is_file() or sha256_file(path) != made["inputs"].get(f"light_curve_{tic}", {}).get(
        "sha256"
    ):
        raise SystemExit(
            f"the light curve on disk for TIC {tic} is not the one {made['run_id']} read"
        )
    return f"lc/{tic}.npz", path


def dataset(record: Path) -> dict[str, Path]:
    """The dataset's files by their path under `dataset/`: the signal's published records up to `record` and the
    light curve its vetting run read."""
    name, path = _light_curve(record)
    return record_files(record) | {name: path}


def _in_record(path: str) -> str:
    """A dataset file's path within its record, from its path under `dataset/`: `vetting/NAME/r2/plots/x.png` is
    `plots/x.png`."""
    parts = Path(path).parts
    inside = parts[2:] if parts[0] == "vetting" else parts
    if inside and calls.version(Path(inside[0])):
        inside = inside[1:]
    return "/".join(inside)


def licence(path: str) -> dict[str, str]:
    """A dataset file's licence by its path under `dataset/` (results/README.md): a record's file holding Gaia DR3 data
    stays under ESA's terms, ExoFOP's rows stay under ExoFOP's, and the rest is CC BY 4.0."""
    name = _in_record(path)
    found = {"licence": GAIA if name in GAIA_FILES else CC_BY}
    if name in EXOFOP_FILES:
        found["exofop"] = EXOFOP
    return found


def _spell(n: int) -> str:
    return SPELLED[n] if 0 <= n < len(SPELLED) else str(n)


def _count(n: int, word: str) -> str:
    return f"{_spell(n)} {word}" + ("" if n in (0, 1) else "s")


def _quote(text: str) -> str:
    """Quoted text in quotation marks, which mark it apart from the paper's own words without changing it (decision
    0037)."""
    return f'"{_scrub(text)}"'


def _beside(notes: list[dict]) -> str:
    """The notes added on a quoted finding under decision 0037, each nested under the finding after its quoted lines.
    Python-Markdown nests a list only at four spaces."""
    return "".join(f"\n    - **Note ({n['date']}):** {_scrub(n['text'])}" for n in notes)


def _claims(record: Path) -> dict | None:
    """claims.json, the record's sort under decision 0042, or None when the record holds none."""
    path = record / "claims.json"
    return json.loads(path.read_text()) if path.is_file() else None


def _excepted(record: Path) -> list[dict]:
    """The later listings decision 0042 excepts for the record."""
    found = _claims(record)
    return [] if found is None else found["excepted"]


def _upcoming(upcoming: list[int] | None, vetted_on: str) -> str | None:
    if upcoming is None:
        return None
    if not upcoming:
        return (
            f"At the time of the vetting run ({vetted_on}), tess-point (Burke et al. 2020) showed no TESS sector "
            "still to come for the star."
        )
    return (
        f"At the time of the vetting run ({vetted_on}), tess-point (Burke et al. 2020) showed TESS would observe the "
        f"star in {prereg._sectors_words(upcoming)}."
    )


def _star(checks: dict, made: dict) -> dict:
    star, eph, prior = checks["star"], checks["ephemeris"], checks["fit_prior"]
    found = {
        "tic": str(checks["tic"]),
        "tmag": _number(star["tmag"], ".2f"),
        "teff": _number(star["teff"], ".0f"),
        "radius_sun": _number(star["rad"], ".2f"),
        "depth_ppm": _ppm(eph["depth"]),
        "upcoming": _upcoming(checks["upcoming_sectors"], made["started_at"][:10]),
    }
    if prior is None:
        return found
    fit, rp = prior["ephemeris"], prior["rp_rearth"] or {}
    duration = checks["window_duration"]
    return found | {
        "period": _number(fit["period"]["median"], ".6f"),
        "period_short": _number(fit["period"]["median"], ".1f"),
        "period_sd_s": _number(fit["period"]["sd"] * 86400, ".1f"),
        "t0": _number(fit["t0"]["median"], ".4f"),
        "t0_sd_min": _number(fit["t0"]["sd"] * 1440, ".1f"),
        "rp_rs": _summary(prior["rp_rs"], ".4f"),
        "rp_rearth": _number(rp.get("median"), ".2f"),
        "rp_lo": _number(rp.get("p16"), ".2f"),
        "rp_hi": _number(rp.get("p84"), ".2f"),
        "b": _summary(prior["b"], ".2f"),
        "a_rs": _summary(prior["a_rs"], ".2f"),
        # The duration is the density-prior fit's only when the record says so.
        "duration_h": _number(duration["days"] * 24, ".2f")
        if duration["from"] == "fit_prior"
        else None,
    }


def _changed(version: Path) -> str:
    """What a re-vet's light curve changed, from its merge record (decision 0041)."""
    tic = json.loads((version / "checks.json").read_text())["tic"]
    merged = json.loads((version / "merge.json").read_text())[str(tic)]["sectors"]
    rows = sorted(merged.items(), key=lambda item: int(item[0]))
    said = []
    added = [f"Sector {s} ({x['fresh']['provenance']})" for s, x in rows if x["status"] == "added"]
    if added:
        said.append(f"adds {_words(added)}")
    said += [
        f"replaces Sector {s}'s timing-suspect delivery with a newer one"
        for s, x in rows
        if x["status"] == "redelivered"
    ]
    said += [
        f"replaces Sector {s}'s {x['base']['provenance']} light curve with {x['fresh']['provenance']}'s"
        for s, x in rows
        if x["status"] == "upgraded"
    ]
    if not said:
        return "a re-vet on the same light curve"
    return f"a re-vet whose light curve {_words(said)}"


def _history(record: Path) -> str:
    """Each published record of the signal up to `record`: an earlier one's call, quoted, and what each re-vet's light
    curve changed."""
    versions = _versions(record)
    if len(versions) == 1:
        return "This paper reports the signal's only record."
    said = [f"This signal has {_count(len(versions), 'record')}."]
    for r in versions[:-1]:
        n = calls.version(r)
        call = calls.load(r / "call.toml")
        name = "The first" if n is None else f"Version r{n}, {_changed(r)},"
        said.append(f"{name} was called {call['outcome']} on {call['date']}.")
        gave = f"Its call gave the reason as {_quote(call['reasons'])}"
        if call["deciding_evidence"]:
            gave += (
                f" and named the evidence that would decide it: {_quote(call['deciding_evidence'])}"
            )
        said.append(gave)
    n = calls.version(record)
    said.append(
        f"This paper reports the {ORDINALS.get(n, 'latest')} version, r{n}, {_changed(record)}."
    )
    return " ".join(said)


def _matched(check: dict) -> list[str]:
    """The listings a novelty check matched to the signal, by name."""
    return [m["name"] for m in check["evidence"].get("matches") or []]


def _novelty_said(check: dict) -> str:
    """A novelty check's outcome as a verb with what it matched; its reason, quoted, where its evidence lists no
    match."""
    matched = _matched(check)
    if check["outcome"] == "pass":
        return "the novelty check passes: no known object matches the signal"
    if matched:
        return (
            f"the novelty check {IS[check['outcome']]}, because {_words(matched)} "
            f"{'matches' if len(matched) == 1 else 'match'} the signal"
        )
    return f"the novelty check {IS[check['outcome']]}, for the reason {_quote(check['reason'])}"


def _novelty_against(check: dict) -> str:
    """The vetting run's own novelty check, against the catalogs it read, said as _novelty_said says a check."""
    head = f"The novelty check {IS[check['outcome']]} against the catalogs the vetting run read"
    matched = _matched(check)
    if check["outcome"] == "pass":
        return f"{head}: no known object matches the signal."
    if matched:
        return f"{head}, because {_words(matched)} {'matches' if len(matched) == 1 else 'match'} the signal."
    return f"{head}, for the reason {_quote(check['reason'])}."


def _novelty(record: Path, checks: dict, call: dict) -> str:
    """What the checks table's novelty row leaves out: a rerun under decision 0042 and a promotion under 0013."""
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    judged = calls.novelty(record, checks)
    excepted = _excepted(record)
    said = []
    if excepted:
        line = _novelty_against(own)
        one = len(excepted) == 1
        which = (
            f"that {excepted[0]['source']}"
            if one and excepted[0]["name"] in _matched(own)
            else _words([r["name"] for r in excepted])
        )
        it = "it" if one else "them"
        line += (
            f" ExoFOP first listed {which} after tess-hunt made the signal public, so decision record 0042 sets {it} "
            f'aside (see "When it was made public"). Without {it}, {_novelty_said(judged)}.'
        )
        said.append(line)
    if judged["outcome"] != "pass":
        said.append(
            f"T{_novelty_said(judged)[1:]}. The rows at the signal's period are SPOC threshold-crossing events or "
            "ExoMiner rows that never became TOIs. Decision record 0013 lets the call promote such a signal, and this "
            f"call does. It gives the reason as {_quote(call['promotion'])}"
        )
    return "\n\n".join(said)


def _modshift(checks: dict) -> str:
    m = checks["modshift"]
    if m is None:
        return f"The record holds no ModShift result ({_quote(checks['triage_reason'])})."
    depth = None if m["dep_sec"] is None else m["dep_sec"] * 1e6
    return (
        "ModShift, the model-shift uniqueness test (Rowe et al. 2015; Coughlin et al. 2016), looks for a secondary "
        "eclipse at any phase. LEO-Vetter runs it during triage. The strongest secondary it finds is "
        f"{_f(m['sig_sec'], '.3g')} sigma at phase {_f(m['phs_sec'], '.3g')} (depth {_f(depth, '.0f')} ppm). The "
        f"primary is {_f(m['sig_pri'], '.3g')} sigma, and ModShift's red-noise factor, Fred, is {_f(m['Fred'], '.3g')}."
    )


def _eccentric(checks: dict) -> str:
    m = checks["modshift"]
    there = (
        f"An eccentric orbit can put it elsewhere, and only ModShift looks there. Its strongest secondary is "
        f"{_f(m['sig_sec'], '.3g')} sigma."
        if m is not None
        else "An eccentric orbit can put it elsewhere, and the record holds no ModShift result."
    )
    return (
        "The secondary check only looks at phase 0.5, where a circular orbit puts an eclipsing binary's secondary "
        f"eclipse. {there}"
    )


def _red_noise(checks: dict) -> str:
    rows = sorted(checks["red_noise"].items(), key=lambda item: int(item[0]))
    measured = [f"{r['beta']:.2f} in Sector {s}" for s, r in rows if "note" not in r]
    unmeasured = [int(s) for s, r in rows if "note" in r]
    said = [
        "Each sector's depth errors are scaled by a red-noise factor, beta, measured from the residuals binned at the "
        "timescale of the transit core (Pont et al. 2006; decision record 0006)."
    ]
    if measured:
        said.append(f"Beta is {_words(measured)}.")
    if unmeasured:
        their = "its errors assume" if len(unmeasured) == 1 else "their errors assume"
        said.append(
            f"{prereg._sectors_words(unmeasured)} had too few binned points to measure it, so beta is 1 there and "
            f"{their} white noise."
        )
    return " ".join(said)


def _tdepth_zero(evidence: dict, hosts: list[dict]) -> str:
    """The neighbour table's possible hosts TRICERATOPS gave zero depth: it weighed no scenario on them (decision 0026,
    Ruling M)."""
    zero = evidence["hosts_tdepth_zero"]
    if not zero:
        return ""
    one = len(zero) == 1
    if len(zero) == len(hosts):
        which = (
            "the neighbour table's one possible host"
            if one
            else f"all {_spell(len(hosts))} of the neighbour table's possible hosts"
        )
    else:
        which = (
            f"{_spell(len(zero))} of the neighbour table's {_count(len(hosts), 'possible host')}"
        )
    star, it = ("that star", "it") if one else ("those stars", "them")
    return (
        f" Its apertures take in too little light from {which} for {star} to make the dip. TRICERATOPS gave {it} "
        f"zero depth and weighed no scenario on {it} (decision record 0026). Ruling {star} out depends on "
        "TRICERATOPS's model of the light in its apertures and on the pixel check, not on a probability."
    )


def _validated(record: Path, version: str, triceratops: dict) -> str:
    """Whether Giacalone et al.'s "validated planet" label applies, by decision 0026's conditions."""
    limit = _criteria(record, "provenance-triceratops.json", version)["triceratops"][
        "fpp_validated"
    ]
    e = triceratops["evidence"]
    said = (
        'Giacalone et al. also define a "validated planet" label. Decision record 0026 allows it only with an FPP '
        f"under {limit:g}, a high-resolution contrast curve and 2-minute data."
    )
    if e["validated_label"]:
        return f"{said} These runs meet those conditions, but this paper still calls the signal a planet candidate."
    lacking = [
        (a, no)
        for a, no, met in (
            (f"an FPP under {limit:g}", f"no FPP under {limit:g}", e["fpp_mean"] < limit),
            ("a contrast curve", "no contrast curve", bool(triceratops["contrast"])),
            ("2-minute data", "no 2-minute data", e["exposure_s"] == TWO_MINUTES_S),
        )
        if not met
    ]
    if len(lacking) == 2:
        had = f"neither {lacking[0][0]} nor {lacking[1][0]}"
    else:
        had = _words([no for _, no in lacking])
    return f"{said} These runs had {had}, so the label doesn't apply."


def _offsets(pixel: dict, suspect: set[int]) -> dict:
    """Each sector's centroid offset, and the sector the outcome comes from: the pixel check judges the best-quality
    sector's offset, and the row holding that offset is its sector (as the dossier finds it)."""
    sectors = sorted(pixel["evidence"]["sectors"], key=lambda s: s["sector"])
    offsets = (
        "The offsets were "
        + _words(
            [
                f"{_f(s['offset_arcsec'], '.1f')} arcsec in Sector {s['sector']} (quality {_f(s['quality'], '.2f')})"
                for s in sectors
            ]
        )
        + "."
    )
    judged_offset = pixel["evidence"]["offset_qual_arcsec"]
    judged = [
        s["sector"]
        for s in sectors
        if judged_offset is not None and s["offset_arcsec"] == judged_offset
    ]
    outcome = pixel["outcome"]
    if len(judged) == 1:
        n = judged[0]
        said = f"Sector {n} has the best quality, so the {outcome} comes from it"
        said += (
            f", though the vetting run left Sector {n} out for suspect timestamps."
            if n in suspect
            else "."
        )
    else:
        said = f"The {outcome} comes from the best-quality offset, which no single sector above reports."
    others = sorted(
        s["sector"] for s in sectors if s["sector"] in suspect and s["sector"] not in judged
    )
    if others:
        said += f" The vetting run left {prereg._sectors_words(others)} out for suspect timestamps."
    return {"offsets": offsets, "rests_on": said}


def _blends(hosts: list[dict], limit: float, zero: list) -> str:
    """The possible hosts neither the pixel check nor TRICERATOPS can exclude. The paper gives their count, not their
    Gaia values."""
    if not hosts:
        return "The neighbour table lists no star that could make the dip."
    inside = [h for h in hosts if h["sep_arcsec"] is not None and h["sep_arcsec"] < limit]
    within = f"within {limit:g} arcsec of the target, too close for the pixel check to tell apart"
    if len(hosts) == 1:
        said = (
            f"The neighbour table's one possible host is {within}"
            if inside
            else f"The neighbour table's one possible host is not within {limit:g} arcsec of the target"
        )
        said += ", and TRICERATOPS weighed no scenario on it." if zero else "."
    else:
        if not inside:
            said = (
                f"None of the neighbour table's {_spell(len(hosts))} possible hosts is within {limit:g} arcsec of the "
                "target."
            )
        elif len(inside) == len(hosts):
            said = f"All {_spell(len(hosts))} of the neighbour table's possible hosts are {within}."
        else:
            are = "is" if len(inside) == 1 else "are"
            said = (
                f"{_spell(len(inside)).capitalize()} of the neighbour table's {_spell(len(hosts))} possible hosts "
                f"{are} {within}."
            )
        if zero:
            on = "any of them" if len(zero) == len(hosts) else f"{_spell(len(zero))} of them"
            said += f" TRICERATOPS weighed no scenario on {on}."
    if inside or zero:
        them = "it" if len(hosts) == 1 else "them"
        said += f" Photometry that resolves the stars near the target could rule {them} out."
    return said


def _companions(triceratops: dict, exofop: dict) -> str:
    contrast = triceratops["contrast"]
    if contrast:
        return (
            "TRICERATOPS judged unresolved companions and background stars from its priors, limited by "
            f"{_count(len(contrast), 'high-resolution contrast curve')} of the star from ExoFOP."
        )
    said = (
        "TRICERATOPS judged unresolved companions and background stars from its priors alone, because no "
        "high-resolution contrast curve went into it."
    )
    if exofop["imaging"]:
        said += (
            f" ExoFOP lists {_count(len(exofop['imaging']), 'high-resolution imaging observation')} of the star, "
            "which TRICERATOPS did not use."
        )
    return said


def _listing(raw: str, kind: str) -> str:
    """An ExoFOP TOI or CTOI by the name the novelty check gives it (catalogs.py): "TOI 266.01" is "TOI-266.01" and "TIC
    164767175.03" is "CTOI-164767175.03"."""
    if kind == "TOI":
        return re.sub(r"^TOI[ -]?", "TOI-", raw.strip())
    return re.sub(r"^(TIC|CTOI)[ -]?", "CTOI-", raw.strip())


def _listed(rows: list[dict], kind: str, field: str, disposition: str) -> str:
    """ExoFOP's TOIs or CTOIs on the star, counted and named, each with its disposition."""
    if not rows:
        return f"no {kind}"
    named = [
        f"{_listing(r[field], kind)}, disposition {r.get(disposition) or 'none'}"
        if len(rows) == 1
        else f"{_listing(r[field], kind)} with disposition {r.get(disposition) or 'none'}"
        for r in rows
    ]
    return f"{_count(len(rows), kind)} ({_words(named)})"


def _exofop(exofop: dict) -> str:
    """What ExoFOP lists on the star besides the planet-parameter rows: TOIs, CTOIs, confirmed planets and imaging."""
    if exofop["status"] != "ok":
        return f"ExoFOP's records for the star could not be read ({_quote(exofop['error'])})."
    planets = [p.strip() for p in (exofop["confirmed_planets"] or "").split(",") if p.strip()]
    parts = [
        _listed(exofop["tois"], "TOI", "toi", "disp_tfop"),
        _listed(exofop["ctois"], "CTOI", "ctoi", "cdisp"),
        f"{_count(len(planets), 'confirmed planet')} ({_words(planets)})"
        if planets
        else "no confirmed planet",
        _count(len(exofop["imaging"]), "high-resolution imaging observation"),
    ]
    return f"ExoFOP lists {_words(parts)} for the star."


def _vetting(record: Path, checks: dict, call: dict, literature: dict) -> dict:
    sources, vetted = checks["sources"], sorted(s for f in checks["families"].values() for s in f)
    dropped = checks["dropped_suspect"]
    version = checks["criteria_version"]
    vet = _criteria(record, "provenance-checks.json", version)
    pixel = calls.pixels(record, checks)
    triceratops = json.loads((record / "triceratops.json").read_text())
    tric = triceratops["evidence"]
    hosts = checks["neighbours"]["evidence"]["possible_hosts"]
    novelty = _novelty(record, checks, call)
    rows = [[c["check"], c["outcome"], c["reason"]] for c in checks["checks"]]
    rows += [
        ["neighbours", checks["neighbours"]["outcome"], checks["neighbours"]["reason"]],
        ["pixels", pixel["outcome"], pixel["reason"]],
        ["triceratops", triceratops["outcome"], triceratops["reason"]],
        ["literature", literature["outcome"], literature["reason"]],
    ]
    # Only a listing the novelty check matched is at the signal's period or a harmonic of it: decision 0042 excepts
    # later ones at any period.
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    at_period = [r["name"] for r in _excepted(record) if r["name"] in _matched(own)]
    second = checks["signal"]["kind"] == "second"
    exofop = literature["search"]["exofop"]
    limit = pixel["max_offset_arcsec"]
    holdout = next(c for c in checks["checks"] if c["check"] == "holdout")
    seasons = holdout["evidence"]["seasons"]
    tested = [s for s in seasons if s["status"] in ("predicted", "missed")]
    predicted = sum(s["status"] == "predicted" for s in tested)
    untested = "".join(
        f" The season from BTJD {s['start']:.1f} to {s['end']:.1f} was not testable"
        + (
            f" ({_quote(s['reason'])})."
            if s.get("reason")
            else f", because {UNTESTED.get(s['status'], s['status'])}."
        )
        for s in seasons
        if s not in tested
    )
    return {
        "vetting_run": json.loads((record / "provenance-checks.json").read_text())["run_id"],
        "criteria_version": version,
        "season_gap_days": f"{vet['holdout']['season_gap_days']:g}",
        "core": f"{100 * vet['depth']['core_fraction']:g}%",
        "min_sigma": f"{vet['holdout']['min_sigma']:g}",
        "max_tension": f"{vet['holdout']['max_depth_tension']:g}",
        "bar_promotion": " For a SPOC threshold-crossing event that never became a TOI, the maintainer's promotion "
        "can stand in for the novelty check (decision record 0013)."
        if second
        else "",
        "vetted_products": _words(
            sorted({prereg.PRODUCTS[sources[str(s)]["provenance"]] for s in vetted})
        ),
        "vetted_sectors": prereg._sectors_words(vetted),
        "suspect": f" It left out {prereg._sectors_words(dropped)} for suspect timestamps (decision record 0022)."
        if dropped
        else "",
        "checks": _table(
            ["Check", "Outcome", "Reason, as the record gives it"],
            [
                [
                    f"{CHECKS[name]} (`{name}`"
                    + (", see below the table)" if name == "novelty" and novelty else ")"),
                    outcome,
                    reason,
                ]
                for name, outcome, reason in rows
            ],
        ),
        "novelty": novelty,
        "modshift": _modshift(checks),
        "eccentric": _eccentric(checks),
        "red_noise": _red_noise(checks),
        "hosts": f"It found {_count(len(hosts), 'such star')}. The dataset's `neighbours.csv` gives the eclipse depth "
        f"{'it' if len(hosts) == 1 else 'each'} would need."
        if hosts
        else "It found no such star.",
        "tdepth_zero": _tdepth_zero(tric, hosts),
        "tric_data": f"{prereg._sectors_words(tric['sectors'])} at {tric['exposure_s']:g}-s exposures"
        + (", folded and binned in phase" if tric["bin_phase"] else ""),
        "validated": _validated(record, version, triceratops),
        "pixel_check": "the second list's, run as triage runs it" if second else "triage's",
        "max_offset": f"{limit:g}",
        **_offsets(pixel, set(dropped)),
        "blends": _blends(hosts, limit, tric["hosts_tdepth_zero"]),
        # results/README.md leaves a bare Gaia DR3 source id under CC BY 4.0; the paper leaves it out anyway, so its own
        # text holds nothing from Gaia.
        "names": _words([n for n in literature["search"]["names"] if not n.startswith("Gaia ")]),
        "papers": _count(len(literature["evidence"]["hits"]), "paper"),
        "exofop": _exofop(exofop),
        "exofop_rows": "None of ExoFOP's planet-parameter rows for the star matches the signal's period or a "
        "harmonic of it."
        if not at_period
        else f"Apart from {_words(at_period)}, which decision record 0042 sets aside, none of ExoFOP's "
        "planet-parameter rows for the star matches the signal's period or a harmonic of it.",
        "tric_times": {1: "once", 2: "twice"}.get(
            len(tric["fpp"]), f"{_spell(len(tric['fpp']))} times"
        ),
        "companions": _companions(triceratops, exofop),
        "holdout": f"For this signal the check {WAS[holdout['outcome']]}. "
        + _seasons(len(seasons), len(tested), predicted)
        + untested,
    }


def _seasons(n: int, testable: int, predicted: int) -> str:
    """How many of the signal's seasons the held-out check could test, and how many it predicted."""
    if n == 1:
        if not testable:
            return "Its one season was not testable."
        return f"Its one season was testable and was{'' if predicted else ' not'} predicted."
    if n == testable == predicted == 2:
        return "Both seasons were testable and both were predicted."

    def were(k: int) -> str:
        return f"{'none' if k == 0 else _spell(k)} {'was' if k in (0, 1) else 'were'}"

    return f"Of its {_spell(n)} seasons, {were(testable)} testable and {were(predicted)} predicted."


def _label(finding: dict, confirmed: list[str]) -> str:
    """A finding's id, the question it concerns, its rating and what its refuters did."""
    head = f"{finding['id']}, on {QUESTIONS[finding['lens']]}."
    if finding["rating"] == "note":
        return f"{head} Rated note."
    n = len(finding["refuters"])
    if finding["id"] not in confirmed:
        k = sum(v["refuted"] for v in finding["refuters"])
        if n == 1:
            who = "its one refuter"
        elif k == n:
            who = "both of its refuters" if n == 2 else f"all {_spell(n)} of its refuters"
        else:
            who = f"{_spell(k)} of its {_spell(n)} refuters"
        said = f"{who} disproved it"
    # Confirmed only because nothing tested it, as the dossier says: the reader should not take it for tested.
    elif n == 0:
        said = "no refuter tested it, so it counts as confirmed"
    elif n == 1:
        said = "its one refuter did not disprove it"
    elif n == 2:
        said = "neither of its two refuters disproved it"
    else:
        said = f"none of its {_spell(n)} refuters disproved it"
    return f"{head} Rated {finding['rating']}; {said}."


def _fates(findings: list[dict], confirmed: list[str]) -> str:
    counts = Counter(
        ("note", "note")
        if f["rating"] == "note"
        else ("confirmed" if f["id"] in confirmed else "refuted", f["rating"])
        for f in findings
    )

    def told(k: int, rating: str, fate: str) -> str:
        return f"{_spell(k)} rated {rating} {'was' if k == 1 else 'were'} {fate}"

    said = [
        told(k, rating, fate)
        for fate in ("confirmed", "refuted")
        for rating in ("kill", "hold")
        if (k := counts[fate, rating])
    ]
    if k := counts["note", "note"]:
        said.append("one was a note" if k == 1 else f"{_spell(k)} were notes")
    if not said:
        return "none was confirmed"
    return said[0] if len(said) == 1 else ", ".join(said[:-1]) + ", and " + said[-1]


def _flagged(review: dict, literature: dict) -> str:
    """The papers the review flagged, each by its title and id where the literature search found it."""
    flagged = review["hits_flagged"]
    if not flagged:
        return "The review flagged no paper for the maintainer to read."
    hits = literature["evidence"]["hits"]

    def paper(ident: str) -> str:
        hit = next((h for h in hits if ident in (h["arxiv"], h["doi"])), None)
        if hit is None:
            return ident
        return f'"{hit["title"]}" ({_paper_id(hit)})' if hit["title"] else _paper_id(hit)

    one = len(flagged) == 1
    return (
        f"The review flagged {_count(len(flagged), 'paper')} for the maintainer to read{',' if one else ':'} "
        f"{_words([paper(i) for i in flagged])}. The call records that the maintainer read {'it' if one else 'each'}."
    )


def _review(record: Path, review: dict, call: dict, literature: dict) -> dict:
    """The review's counts and its quoted findings, each with any note decision 0037 added beside it in
    review-notes.toml, and the call's answers and sentences."""
    path = record / "review-notes.toml"
    added = calls.load_notes(path, review) if path.is_file() else {}
    confirmed = calls.confirmed(review)
    findings = review["findings"]
    by_id = {f["id"]: f for f in findings}
    refuted = [f for f in findings if f["rating"] != "note" and f["id"] not in confirmed]
    noted = [f for f in findings if f["rating"] == "note"]

    def quoted(finding: dict, lines: list[str]) -> str:
        return (
            f"- {_label(finding, confirmed)}"
            + "".join(
                f"\n    - {line}" for line in [f"Finding: {_quote(finding['claim'])}", *lines]
            )
            + _beside(added.get(finding["id"], []))
        )

    answers = "\n".join(
        quoted(by_id[f], [f"Answer: {_quote(call['answers'][f])}"]) for f in confirmed
    )
    verdicts = "\n".join(
        quoted(
            f,
            [
                f"Refuter {i} {'disproved it' if v['refuted'] else 'did not disprove it'}: {_quote(v['reason'])}"
                for i, v in enumerate(f["refuters"], 1)
            ],
        )
        for f in refuted
    )
    return {
        "call_date": str(call["date"]),
        "review_date": str(review["date"]),
        "findings": _count(len(findings), "finding"),
        "n_confirmed": str(len(confirmed)),
        "fates": _fates(findings, confirmed),
        "hits_read": _flagged(review, literature),
        "answers": answers or "The review confirmed no finding.",
        "refuted": "Refuted findings, with each refuter's verdict:\n\n" + verdicts
        if refuted
        else "No refuter disproved any finding.",
        "notes": "Findings rated note, which need no answer:\n\n"
        + "\n".join(quoted(f, []) for f in noted)
        if noted
        else "The review rated no finding note.",
        "sentences": "\n".join(
            f"- {label}: {_quote(call['sentences'][key])}" for key, label in SENTENCES.items()
        ),
    }


def _inject_run(benchmarks: Path, threshold_run: str) -> dict:
    """The published production injection-recovery run made at the search's threshold. No provenance of the record
    names it, so it is found by the threshold run it recorded; exactly one must match."""
    found = [
        made
        for made in (
            json.loads(path.read_text())
            for path in sorted(benchmarks.glob("*-benchmark-inject-*/provenance.json"))
        )
        if made.get("production") and (made.get("threshold") or {}).get("run_id") == threshold_run
    ]
    if len(found) != 1:
        raise SystemExit(
            f"{len(found)} published injection-recovery runs were made at threshold run {threshold_run}; the paper "
            "names one"
        )
    return found[0]


def _triage(row: pd.Series, made: dict, checks: dict) -> str:
    """What triage made of the signal, from its row in the triage run's signals.csv."""
    used = made["inputs"].get("triage_criteria")
    # A vetting run made before M4's deferred minors recorded no triage criteria file.
    under = f" (criteria {Path(used['file']).stem})" if used else ""
    said = f"Triage{under} screened every signal at or above the threshold."
    if bool(row["shortlisted"]):
        return (
            f"{said} This signal passed the novelty check, LEO-Vetter's false-alarm and flux-level tests (LEO-Vetter "
            f"calls it {_quote(row['leo_reason'])}) and the pixel check, so it was shortlisted."
        )
    # Triage records a pixel check it never ran as inconclusive, "not run: ...".
    pixels = (
        "triage did not run its pixel check"
        if str(row["pixels_reason"]).startswith("not run")
        else f"its pixel check {WAS[row['pixels']]}"
    )
    said += (
        f" This signal's novelty check {WAS[row['novelty']]}, LEO-Vetter's tests {WAS[row['leo_flux']]} and "
        f"{pixels}, so triage did not shortlist it."
    )
    if checks["signal"]["kind"] == "second":
        said += (
            " It came to vetting on tess-hunt's second list of SPOC threshold-crossing events that never became TOIs "
            "(decision record 0028)."
        )
    return said


def _found(repo: Path, checks: dict, made: dict) -> dict:
    """The search, its sample, its threshold, the injection recovery and triage, from the published runs the vetting
    run's provenance leads to."""
    results = repo / "results"
    searched = results / "benchmarks" / made["search_run"]
    search = json.loads((searched / "provenance.json").read_text())
    if len(search["criteria"]) != 1:
        raise SystemExit(f"search run {made['search_run']} names no single criteria file")
    criteria = _criteria(searched, "provenance.json", Path(search["criteria"][0]["file"]).stem)
    sample, cfg = criteria["sample"], criteria["search"]
    threshold_run = search["threshold"]["run_id"]
    threshold = json.loads((results / "benchmarks" / threshold_run / "threshold.json").read_text())
    inject = _inject_run(results / "benchmarks", threshold_run)
    if not (results / "benchmarks" / inject["run_id"] / COMPLETENESS).is_file():
        raise SystemExit(
            f"injection-recovery run {inject['run_id']} holds no {COMPLETENESS}, which the paper points to"
        )
    # Triage names a signal <tic>-<rank> and lists every signal at or above the threshold.
    rank = int(checks["signal"]["name"].rsplit("-", 1)[1])
    rows = pd.read_csv(results / "triage" / made["triage_run"] / "signals.csv")
    row = rows[(rows["tic"] == int(checks["tic"])) & (rows["rank"] == rank)]
    if len(row) != 1:
        raise SystemExit(
            f"triage run {made['triage_run']} holds {len(row)} rows for {checks['signal']['name']}, not one; the "
            "paper gives the signal's SDE and triage's steps from it"
        )
    one = row.iloc[0]
    return {
        "search_run": made["search_run"],
        "sde": _number(float(one["sde"]), ".2f"),
        "sample_stars": str(search["summary"]["stars"]),
        "period_min": f"{cfg['period_min_days']:g}",
        "period_max": f"{cfg['period_max_days']:g}",
        "teff_min": f"{sample['teff_min']:g}",
        "teff_max": f"{sample['teff_max']:g}",
        "tmag_max": f"{sample['tmag_max']:g}",
        "logg_min": f"{sample['logg_min']:g}",
        "logg_max": f"{sample['logg_max']:g}",
        "flame_logg_min": f"{sample['flame_logg_min']:g}",
        "min_sectors": str(sample["min_sectors"]),
        "recent_min": str(sample["recent_sector_min"]),
        "recent_max": str(sample["recent_sector_max"]),
        "threshold": _number(search["threshold"]["value"], ".2f"),
        "threshold_run": threshold_run,
        "null_run": threshold["null_run"],
        "n_sample": str(threshold["n_sample"]),
        "n_null": str(threshold["n_null_stars"]),
        "false_alarms": _number(threshold["expected_false_alarms"], ".2f"),
        "inject_run": inject["run_id"],
        "injections": str(inject["summary"]["injections"]),
        "inject_stars": str(inject["summary"]["stars"]),
        "completeness": COMPLETENESS,
        "triage_run": made["triage_run"],
        "triage": _triage(one, made, checks),
    }


def _deposit(record: Path, repo: Path) -> dict | None:
    """results/predictions/dois.toml's entry for the predictions package whose preregistered test the record holds,
    with the package's run id; None when it holds none."""
    path = record / "prereg.json"
    if not path.is_file():
        return None
    package = json.loads(path.read_text())["package"]
    dois = repo / DOIS
    entry = tomllib.loads(dois.read_text()).get(package) if dois.is_file() else None
    if entry is None or "doi" not in entry:
        raise SystemExit(f"{DOIS} gives no DOI for package {package}, whose test the record holds")
    return {"package": package, **entry}


def predictions_doi(record: Path, repo: Path) -> str | None:
    """The DOI of the predictions package whose preregistered test the record holds; None when it holds none."""
    deposit = _deposit(record, repo)
    return None if deposit is None else deposit["doi"]


def _public(record: Path, repo: Path, checks: dict) -> dict:
    """The claim results/claims.toml gives the signal (decision 0042), and each later listing its record excepts, with
    decision 0042's rule stated once."""
    name, tic = checks["signal"]["name"], int(checks["tic"])
    claim = load_claims(repo / CLAIMS).get(name)
    found = _claims(record) or {"claim": None, "excepted": []}
    rested = found["claim"]
    # The exception rests on the claim the claims run read; the paper states one claim, so the two must agree.
    if rested is not None and (
        claim is None or rested != {"date": claim.date.isoformat(), "record": claim.record}
    ):
        raise SystemExit(
            f"the record's claims.json rests on the claim {rested['date']} ({rested['record']}), not the one "
            f"{CLAIMS} gives {name}"
        )
    deposit = _deposit(record, repo)
    if claim is None:
        where = None
    elif deposit is not None and claim.record == f"https://doi.org/{deposit['doi']}":
        where = f"in its predictions deposit (doi:{deposit['doi']})"
    else:
        where = f"in {claim.record}"
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    ratios = {m["name"]: m.get("ratio") for m in own["evidence"].get("matches") or []}
    listings = []
    for r in found["excepted"]:
        dispositions = r["dispositions"]
        disposition = (
            f"disposition{'s' if len(dispositions) > 1 else ''} {_words(dispositions)}"
            if dispositions
            else "no disposition"
        )
        if r["name"] in ratios:
            listings.append(
                f" ExoFOP lists a signal at {_harmonic(ratios[r['name']])} on the star as {r['name']} (period "
                f"{r['period']:.6g} d, {disposition})."
            )
        else:
            also = " also" if listings else ""
            listings.append(
                f" ExoFOP{also} lists {r['name']} on the star (period {r['period']:.6g} d, {disposition})."
            )
        listings.append(
            f" ExoFOP first listed it on {r['first_listed']}, after tess-hunt made the signal public."
        )
    if listings:
        them = "it" if len(found["excepted"]) == 1 else "them"
        listings.append(
            f" The record doesn't say who submitted {them}. A listing made after tess-hunt's claim, possibly prompted "
            "by it, can't show the signal was known before the claim. So tess-hunt doesn't count a TOI or CTOI on the "
            "same star as already known when ExoFOP first listed it after the claim and its dispositions are all PC or "
            "empty (decision record 0042). The rule only compares public dates. It says nothing about when or how "
            f"anyone else found the signal. ExoFOP's page for the star is {EXOFOP_STAR.format(tic)}."
        )
    return {
        "claim_date": None if claim is None else claim.date.isoformat(),
        "claim_where": where,
        "listings": "".join(listings),
    }


def _harmonic(ratio: float | None) -> str:
    """Where a listing the novelty check matched lies against the signal's period, by the harmonic it matched at."""
    return next(
        (said for k, said in HARMONICS.items() if ratio is not None and abs(ratio - k) < 1e-6),
        "a harmonic of this period",
    )


def _sector_start(repo: Path, sector: int) -> dt.date:
    rows = pd.read_csv(repo / SECTORS)
    found = rows.loc[rows["sector"] == sector, "start_utc"]
    if len(found) != 1:
        raise SystemExit(f"{SECTORS} gives no start for Sector {sector}")
    return dt.date.fromisoformat(str(found.iloc[0])[:10])


def _prereg(record: Path, repo: Path, call: dict) -> dict:
    """The preregistered test of a later season (decision 0040): when it was deposited, its result and what the result
    shows, and the Summary's sentence on it. A judged result without its depth or error leaves the paper's placeholder
    unfilled, so it raises. Refuses, before any run directory, a deposit Zenodo published on or after the day TESS
    began observing the first sector it predicts, since the paper says the prediction came first."""
    path = record / "prereg.json"
    if not path.is_file():
        return {
            "prereg": "This record holds no preregistered test of a later season (decision record 0040).",
            "summary_prereg": "",
        }
    p = json.loads(path.read_text())
    deposit = _deposit(record, repo)
    sectors = p["predicted_sectors"]
    first, published = min(sectors), deposit["published"]
    start = _sector_start(repo, first)
    if not published < start:
        raise SystemExit(
            f"refused: Zenodo published predictions package {p['package']} on {published}, not before TESS began "
            f"observing Sector {first} on {start}; the paper would say the prediction came before the data"
        )
    them = "it" if len(sectors) == 1 else "them"
    deposited = (
        f"Before TESS observed {prereg._sectors_words(sectors)}, tess-hunt deposited on Zenodo a prediction of the "
        f"signal's transits in {them}"
    )
    summary = f" {deposited}." + SUMMARY_RESULT[p["result"]]
    as_of = dt.date.fromisoformat(p["as_of"])
    if p["result"] == "pending":
        said = f"As of {as_of}, the test is pending ({_quote(p['reason'])})."
    elif p["result"] == "untested":
        said = f"As of {as_of}, the new data could not test the prediction ({_quote(p['reason'])})."
    else:
        depth, err = _ppm(p["depth"]), _ppm(p["err"])
        if depth is None or err is None:
            return {"summary_prereg": summary}
        verb = "replicate the signal" if p["result"] == "replicated" else "miss the prediction"
        said = (
            f"As of {as_of}, the new sectors {verb}. In the cores of the predicted transits, {p['n']} cadences give a "
            f"depth of {depth} ± {err} ppm, {p['sigma']:.2f} times its error, where the test expected "
            f"{p['expected_snr']:.2f} times it."
        )
        if "tension" in p:
            said += (
                f" The tension with the earlier seasons is {p['tension']:.2f} sigma. That is the largest across the "
                "light-curve product families, each compared with its own depth in the earlier seasons, as the "
                "deposit's `references.json` records."
            )
        else:
            said += f" No tension was measured ({_quote(p['tension_skipped'])})."
        if p["result"] == "replicated":
            said += (
                " Replication shows the dip is real, periodic and where the prediction put it. It doesn't show the dip "
                "is on the target."
            )
    order = (
        "before" if call["date"] < as_of else "after" if call["date"] > as_of else "on the day of"
    )
    return {
        "prereg": f"{deposited} (doi:{deposit['doi']}). The deposit also fixed the test that would judge the "
        "prediction: the held-out check's test, applied to the predicted transits (decision record 0040). Zenodo "
        f"published the deposit on {published}, and TESS began observing Sector {first} on {start}. {said} The "
        f"maintainer's call ({call['date']}) came {order} this result.",
        "summary_prereg": summary,
    }


def _files(record: Path) -> str:
    """The dataset's guide: what each kind of file in the records holds, for the kinds the records have."""
    names = {_in_record(path) for path in _record_paths(record)}

    def held(pattern: str) -> bool:
        if pattern.endswith("/"):
            return any(n.startswith(pattern) for n in names)
        if "*" in pattern:
            head, tail = pattern.split("*")
            return any(n.startswith(head) and n.endswith(tail) and "/" not in n for n in names)
        return pattern in names

    return _table(
        ["File", "What it holds"],
        [[f"`{pattern}`", what] for pattern, what in GUIDE if held(pattern)],
    )


def _records(signal: str, version: int | None) -> str:
    """Where the dataset holds each record: the first at the top of the signal's directory, each version below it."""
    if version is None:
        return f"The record is in `dataset/vetting/{signal}/`."
    if version == 2:
        return f"The first record is in `dataset/vetting/{signal}/` and version r2 in its `r2/` subdirectory."
    later = range(2, version + 1)
    return (
        f"The first record is in `dataset/vetting/{signal}/`, and versions {_words([f'r{n}' for n in later])} are in "
        f"its {_words([f'`r{n}/`' for n in later])} subdirectories."
    )


def _data(record: Path, checks: dict, made: dict) -> dict:
    """The light curves' products and DOIs, the dataset's records, and the credits they ask for."""
    sectors: dict[str, list[int]] = {}
    for sector, source in checks["sources"].items():
        sectors.setdefault(prereg.PRODUCTS[source["provenance"]], []).append(int(sector))
    used = {product: sorted(sectors[product]) for product in prereg.CREDITED if product in sectors}
    signal = vetting._signal_dir(record).name
    gaia = any(licence(path)["licence"] == GAIA for path in _record_paths(record))
    version = calls.version(record)
    return {
        "commit": made["git"]["commit"],
        "light_curve": f"lc/{int(checks['tic'])}.npz",
        "products": _words(
            [
                f"{prereg.CREDITED[p][0]} from {prereg._sector_runs(s)} (doi:{prereg.CREDITED[p][1]})"
                for p, s in used.items()
            ]
        ),
        "product_papers": "; ".join(
            f"{prereg.CREDITED[p][0]}, "
            + ", and ".join(f"{who}, {where}" for who, where in prereg.CREDITED[p][2])
            for p in used
        ),
        "pdcsap_papers": PDCSAP_PAPERS if any(p in PDCSAP for p in used) else "",
        "records": _records(signal, version),
        "rendered_from": "that record" if version is None else f"version r{version}",
        "files": _files(record),
        "tess_credit": prereg.TESS_CREDIT,
        "qlp_credit": f" {prereg.QLP_CREDIT}" if "QLP" in used else "",
        "gaia_credit": GAIA_CREDIT if gaia else "",
        "gaia_papers": GAIA_PAPERS if gaia else "",
    }


def _runs(record: Path, repo: Path, found: dict) -> str:
    """The runs the paper reads, each by its run id and where its files are published."""
    signal = vetting._signal_dir(record).name
    benchmarks = [
        ("Search", found["search_run"]),
        ("Null search", found["null_run"]),
        ("Threshold", found["threshold_run"]),
        ("Injection recovery", found["inject_run"]),
    ]
    rows = [[step, run, f"`results/benchmarks/{run}/`"] for step, run in benchmarks]
    rows.append(["Triage", found["triage_run"], f"`results/triage/{found['triage_run']}/`"])
    for r in _versions(record):
        n = calls.version(r)
        made = json.loads((r / "provenance-checks.json").read_text())
        inside = "" if n is None else f"r{n}/"
        rows.append(
            [
                "Vetting, the first record" if n is None else f"Vetting, version r{n}",
                made["run_id"],
                f"`dataset/vetting/{signal}/{inside}provenance-checks.json`",
            ]
        )
    deposit = _deposit(record, repo)
    if deposit is not None:
        rows.append(
            [
                "Predictions package",
                deposit["package"],
                f"`results/predictions/{deposit['package']}/`, doi:{deposit['doi']}",
            ]
        )
    return _table(["Step", "Run id", "Where its files are"], rows)


def _figures(record: Path) -> str | None:
    """The figures from the record's plots, each with the paper's caption; None when the record lacks one."""
    if any(not (record / "plots" / name).is_file() for name in FIGURES):
        return None
    return "\n\n".join(
        f"![Figure {i}]({name})\n\n*Figure {i}. {CAPTIONS[name]}.*"
        for i, name in enumerate(FIGURES, 1)
    )


def _author(author: dict) -> dict:
    parts = [f"{author['given_names']} {author['family_names']}", author["affiliation"]]
    if "orcid" in author:
        parts.append(f"ORCID {author['orcid']}")
    if "email" in author:
        parts.append(author["email"])
    return {"author_line": ", ".join(parts), "repository": author["repository"]}


def values(record: Path, author: dict, repo: Path) -> dict[str, str]:
    """Every placeholder of the template, read by key from the record, its runs' provenance, the published runs they
    name, results/claims.toml, results/predictions/dois.toml, benchmarks/tess_sectors.csv and `author`, formatted as the
    dossier formats them. A value they don't hold is left out, so its placeholder raises."""
    checks = json.loads((record / "checks.json").read_text())
    made = json.loads((record / "provenance-checks.json").read_text())
    call = calls.load(record / "call.toml")
    literature = json.loads((record / "literature.json").read_text())
    found = _found(repo, checks, made)
    out = (
        _star(checks, made)
        | _vetting(record, checks, call, literature)
        | _from_triceratops(record, checks["criteria_version"])
        | _review(record, calls.load_review(record / "review.json"), call, literature)
        | found
        | _public(record, repo, checks)
        | _data(record, checks, made)
        | _author(author)
        | _prereg(record, repo, call)
        | {
            "history": _history(record),
            "figures": _figures(record),
            "runs": _runs(record, repo, found),
        }
    )
    return {key: value for key, value in out.items() if value is not None}


def render(record: Path, author: dict, repo: Path, specimen: bool = False) -> str:
    """The paper in Markdown. A specimen opens with a line saying it is one."""
    text = Template((repo / TEMPLATE).read_text()).substitute(values(record, author, repo))
    if specimen:
        return f"**{SPECIMEN}.** Rendered from a made-up record to review this template; it is never deposited.\n\n{text}"
    return text


def html(markdown_text: str, specimen: bool) -> str:
    """The paper as the HTML page WeasyPrint lays out. With `specimen`, each page's header and footer say it is
    one."""
    # The optional preprint group's; the rest of tess-hunt runs without it.
    import markdown

    body = markdown.markdown(markdown_text, extensions=["tables"])
    style = STYLE + (SPECIMEN_STYLE if specimen else "")
    return f'<!DOCTYPE html><html><head><meta charset="utf-8"><style>{style}</style></head><body>{body}</body></html>'


def document(markdown_text: str, assets: Path, specimen: bool):
    """The paper laid out by WeasyPrint, its figures read from `assets`."""
    import weasyprint

    page = html(markdown_text, specimen)
    return weasyprint.HTML(string=page, base_url=assets.resolve().as_uri() + "/").render()


def to_pdf(markdown_text: str, assets: Path, out: Path, specimen: bool) -> None:
    document(markdown_text, assets, specimen).write_pdf(out)


def _pdf_group() -> None:
    try:
        import markdown  # noqa: F401
        import weasyprint  # noqa: F401
    # WeasyPrint raises OSError when its system library, Pango, is missing.
    except (ImportError, OSError) as exc:
        raise SystemExit(
            f"the PDF needs the preprint dependency group: run `uv sync --group preprint` ({exc})"
        ) from None


def cmd_run(args) -> int:
    # Every refusal comes before the run starts, so it leaves no unfinished run directory.
    _pdf_group()
    repo = repo_root()
    record = passed_record(repo / "results" / "vetting" / args.name)
    # start_run's clean-tree check covers the code, not results/, so a production paper could otherwise be rendered from
    # a template, an author line or a claim nobody committed.
    if args.production and prereg._uncommitted(repo / "results"):
        raise SystemExit(
            "results/ has changes that are not committed; a production run needs them committed"
        )
    author = load_author(repo / AUTHOR)
    text = render(record, author, repo)
    files = dataset(record)
    run = start_run("preprint", [], args.production, sys.argv)
    run.record("signal", args.name)
    run.record("record", str(record.relative_to(repo)))
    run.record("author", author)
    doi = predictions_doi(record, repo)
    run.record("predictions_doi", doi)
    read = [("template", TEMPLATE), ("author", AUTHOR), ("claims", CLAIMS)]
    for name, path in read + ([("dois", DOIS)] if doi else []):
        run.record_input(name, repo / path)
    (run.path / "preprint.md").write_text(text)
    for name in FIGURES:
        shutil.copyfile(record / "plots" / name, run.path / name)
    for name, path in files.items():
        target = run.path / "dataset" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    to_pdf(text, run.path, run.path / "preprint.pdf", specimen=False)
    manifest = [
        {
            "path": f"dataset/{name}",
            "sha256": sha256_file(run.path / "dataset" / name),
            **licence(name),
        }
        for name in files
    ]
    run.write_json("manifest.json", {"signal": args.name, "files": manifest})
    run.finish(
        signal=args.name,
        record=str(record.relative_to(repo)),
        files=len(manifest),
        manifest_sha256=sha256_file(run.path / "manifest.json"),
    )
    print(
        f"preprint: {args.name} from {record.relative_to(repo)}, {len(manifest)} dataset files -> {run.path}"
    )
    return 0


def _package(source: Path) -> list[Path]:
    made = json.loads((source / "provenance.json").read_text())
    if made.get("stage") != "preprint":
        raise SystemExit(f"run {source.name} is not a preprint run")
    if not made.get("production"):
        raise SystemExit(
            f"run {source.name} is not a production run; only a production preprint is published"
        )
    return [source / name for name in PACKAGE]


def cmd_publish(args) -> int:
    publish_run(args.run, repo_root(), "preprints", _package)
    return 0


def _section(text: str, heading: str) -> str:
    return text.split(f"\n## {heading}\n")[1].split("\n## ")[0].strip()


def deposit_form(run: Path) -> str:
    """The Zenodo deposit form's text for the paper and dataset a finished preprint run made, from the run's own
    files."""
    made = json.loads((run / "provenance.json").read_text())
    if made.get("stage") != "preprint":
        raise SystemExit(f"run {run.name} is not a preprint run")
    if made.get("ended_at") is None:
        raise SystemExit(f"run {run.name} has not finished")
    # The deposited copy is the committed one, and `publish` commits only a production run.
    if not made.get("production"):
        raise SystemExit(
            f"run {run.name} is not a production run; only a production preprint is deposited"
        )
    text = (run / "preprint.md").read_text()
    manifest = json.loads((run / "manifest.json").read_text())["files"]
    gaia = sorted(
        {_in_record(f["path"].removeprefix("dataset/")) for f in manifest if f["licence"] == GAIA}
    )
    author = made["author"]
    creators = f"- Name: {author['family_names']}, {author['given_names']}\n  Affiliation: {author['affiliation']}"
    if "orcid" in author:
        creators += f"\n  ORCID: {author['orcid']}"
    related = [
        f'- {author["repository"]} (URL), "Is supplemented by": tess-hunt\'s code and records'
    ]
    if made["predictions_doi"] is not None:
        related.insert(
            0,
            f'- {made["predictions_doi"]} (DOI), "References": the preregistered predictions whose test it reports',
        )
    description = [
        _section(text, "Summary"),
        "The deposit holds the paper (`preprint.pdf`, made from `preprint.md`), its figures and its dataset. The "
        "dataset holds the signal's published vetting records and the light curve that the vetting run of the paper's "
        "record read. `manifest.json` lists each of its files with its sha256 and licence. The files are CC BY 4.0, "
        "with two exceptions. The dataset's files that hold Gaia DR3 data "
        f"({_words([f'`{name}`' for name in gaia])}, in each record's directory) stay under ESA's CC BY-NC 3.0 IGO "
        "terms, as does any Gaia value in the paper's quoted text or notes. ExoFOP's rows in the dataset stay under "
        "ExoFOP's terms, as do the ExoFOP listings the paper names.",
        _section(text, "Use of LLMs"),
    ]
    return ZENODO.substitute(
        run_id=made["run_id"],
        title=text.split("\n", 1)[0].removeprefix("# "),
        creators=creators,
        # Zenodo's description editor keeps line breaks, so each paragraph is pasted as one line.
        description="\n\n".join(" ".join(p.split()) for p in description),
        related="\n".join(related),
        figures="`, `".join(FIGURES),
    )


def cmd_zenodo(args) -> int:
    run = runs_dir() / args.run
    if not (run / "provenance.json").is_file():
        raise SystemExit(f"no run {args.run} under the data directory")
    print(deposit_form(run), end="")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "preprint", help="the Zenodo preprint and dataset for a passed signal (decision 0043)"
    )
    modes = p.add_subparsers(dest="mode", required=True)
    r = modes.add_parser(
        "run",
        help="render the paper, its PDF and its dataset from a signal's latest record, a pass that stands",
    )
    r.add_argument("--name", required=True, help="the signal's name under results/vetting/")
    r.add_argument("--production", action="store_true")
    r.set_defaults(func=cmd_run)
    pub = modes.add_parser("publish", help="copy a production preprint run into results/preprints/")
    pub.add_argument("--run", required=True, help="the run id")
    pub.set_defaults(func=cmd_publish)
    z = modes.add_parser(
        "zenodo", help="print the Zenodo deposit form's text for a finished preprint run"
    )
    z.add_argument("--run", required=True, help="the run id")
    z.set_defaults(func=cmd_zenodo)
