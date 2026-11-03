"""The preprint and dataset for a passed signal (decision 0043; M5 design, section 4.4). `tess-hunt preprint run`
renders a short paper from the signal's latest published record, whose call must be a pass that stands on it, and
lays beside it the dataset its numbers come from: each published record of the signal up to that one and the light
curve the passing vet read. The template is filled with `substitute`, each value read by its key from the record, its
runs' provenance and the published runs they name, so a value they lack raises instead of rendering (docs/design.md,
section 5.5). The PDF needs the optional `preprint` dependency group."""

import datetime as dt
import json
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
    PIXEL_CHECK,
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
    "transits.png": "Each transit the ephemeris predicts in the light curve, one panel per transit, titled with its "
    "epoch (transits counted from t0) and its sector: flux in ppm against hours from the predicted mid-time. Grey points "
    "are cadences, blue points their medians in bins an eighth of the transit's duration wide, and the shaded band "
    "spans the duration. A panel with few points falls at the edge of a gap in the data",
    "folds.png": "The light curve folded on the ephemeris, one panel per season and light-curve product family, titled "
    "with the family (`pdcsap` for SPOC's and TESS-SPOC's PDCSAP flux, `qlp` for QLP's), the season, counted from 0, "
    "and its sectors. Points and band as in Figure 1",
    "odd_even.png": "Odd-numbered (left) and even-numbered (right) transits folded apart. Points and band as in Figure "
    "1; the red line is the median flux in each one's core, the central half of the transit",
    "phase.png": "Flux against orbital phase over the whole orbit, the transit at phase 0. Grey points are cadences, "
    "blue points their medians in bins half the transit's duration wide. The dashed line marks phase 0.5, where a "
    "circular orbit puts a secondary eclipse; the red line marks the strongest secondary eclipse ModShift finds at any "
    "phase, labelled with its phase and significance",
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
# The question each of the review's lenses bears on: the dossier's short labels read as verdicts beside a finding.
QUESTIONS = {
    "on_star": "whether the dip is on the star",
    "planet": "whether it is a planet",
    "real_new": "whether it is real and new",
}
IS = {"pass": "passes", "fail": "fails", "inconclusive": "is inconclusive"}
WAS = {"pass": "passed", "fail": "failed", "inconclusive": "was inconclusive"}
# Why the held-out check could not test a season whose record gives a status and no reason.
UNTESTED = {
    "underpowered": "the depth expected there is too small against its error",
    "no_predicted_transit_in_data": "too few cadences fall in the predicted cores",
}
# The Summary's word on a preregistered result, after "...before TESS observed them;".
SUMMARY_RESULT = {
    "replicated": " the transits were found where predicted.",
    "missed": " the transits were missing where predicted.",
    "pending": " that test is not yet judged.",
    "untested": " the new data could not test that prediction.",
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
    ("review-notes.toml", "the dated notes beside the review's quoted text"),
    ("review-scripts.tar.gz", "the scripts the review ran"),
    ("call.toml", "the call"),
    (
        "provenance-*.json",
        "the run, its commit, its criteria and its command behind each file beside it",
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

## Related identifiers

$related

## Keywords

- TESS
- transiting exoplanets
- planet candidates

## Files

`preprint.pdf`, `preprint.md`, the figures (`$figures`), `manifest.json` and `provenance.json` from the run directory,
and its `dataset/` directory as one zip archive, which keeps its folders. `manifest.json` lists every file in
`dataset/` with its sha256.
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


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _quote(text: str) -> str:
    """Quoted text in quotation marks, which mark it apart from the paper's own words without changing it (decision
    0037)."""
    return f'"{_scrub(text)}"'


def _beside(notes: list[dict]) -> str:
    """The notes added beside a quoted finding under decision 0037, each nested under the finding after its quoted
    lines. Python-Markdown nests a list only at four spaces."""
    return "".join(
        f"\n    - **Note added on {n['date']} under decision record 0037, not part of the review or the call:** "
        f"{_scrub(n['text'])}"
        for n in notes
    )


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
    where = (
        f"in TESS {prereg._sectors_words(upcoming)}, still to be observed then"
        if upcoming
        else "in no TESS sector still to come"
    )
    return f"As of the vetting run ({vetted_on}), tess-point (Burke et al. 2020) placed the star {where}."


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
    redelivered = [f"Sector {s}" for s, x in rows if x["status"] == "redelivered"]
    if redelivered:
        said.append(
            f"takes a newer delivery of {_words(redelivered)}, whose earlier one had suspect timestamps"
        )
    upgraded = [
        f"Sector {s}'s {x['base']['provenance']} light curve with {x['fresh']['provenance']}'s"
        for s, x in rows
        if x["status"] == "upgraded"
    ]
    if upgraded:
        said.append(f"replaces {_words(upgraded)}")
    if not said:
        return "a re-vet on the same light curve"
    return f"a re-vet on a light curve that {_words(said)}"


def _history(record: Path) -> str:
    """Each published record of the signal up to `record`: an earlier one's call, quoted, and what each re-vet's light
    curve changed."""
    versions = _versions(record)
    if len(versions) == 1:
        return "This is the signal's only record, and this paper reports it."
    said = [f"This signal has {len(versions)} records."]
    for r in versions:
        n = calls.version(r)
        name = "The first record" if n is None else f"Version r{n}, {_changed(r)},"
        if r == record:
            said.append(f"{name} is the one this paper reports.")
            continue
        call = calls.load(r / "call.toml")
        line = (
            f"{name} was called {call['outcome']} on {call['date']}, for these reasons, quoted from its call: "
            f"{_quote(call['reasons'])}"
        )
        if call["deciding_evidence"]:
            line += f" The evidence it named as deciding: {_quote(call['deciding_evidence'])}"
        said.append(line)
    return " ".join(said)


def _novelty(record: Path, checks: dict, call: dict) -> str:
    """What the checks table's novelty row leaves out: a rerun under decision 0042 and a promotion under 0013."""
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    judged = calls.novelty(record, checks)
    excepted = _excepted(record)
    said = []
    if excepted:
        them = "it" if len(excepted) == 1 else "them"
        said.append(
            f"Against the catalogs the vetting run read, the novelty check {IS[own['outcome']]}: {own['reason']}. "
            f"ExoFOP first listed {_words([r['name'] for r in excepted])} only after tess-hunt made the signal public, "
            f"so decision record 0042 sets {them} aside (see When it was made public). Run again without {them}, the "
            f"novelty check {IS[judged['outcome']]}: {judged['reason']}."
        )
    if judged["outcome"] != "pass":
        said.append(
            f"The novelty check {IS[judged['outcome']]} ({judged['reason']}): the rows at the signal's period are SPOC "
            "threshold-crossing events or ExoMiner rows that never became TOIs. The call promotes the signal, as "
            f"decision record 0013 allows, in the maintainer's words: {_quote(call['promotion'])}"
        )
    return "\n\n".join(said)


def _modshift(checks: dict) -> str:
    m = checks["modshift"]
    if m is None:
        return f"The record holds no ModShift result ({checks['triage_reason']})."
    depth = None if m["dep_sec"] is None else m["dep_sec"] * 1e6
    return (
        "ModShift, as LEO-Vetter (Kunimoto et al. 2025) runs it in triage, looks for a secondary eclipse at any phase: "
        f"its strongest is {_f(m['sig_sec'], '.3g')} sigma at phase {_f(m['phs_sec'], '.3g')} (depth "
        f"{_f(depth, '.0f')} ppm), against a primary of {_f(m['sig_pri'], '.3g')} sigma and a red-noise factor, Fred, "
        f"of {_f(m['Fred'], '.3g')}."
    )


def _eccentric(checks: dict) -> str:
    m = checks["modshift"]
    where = (
        f"where only ModShift looks: its strongest secondary is at {_f(m['sig_sec'], '.3g')} sigma (How it was vetted)"
        if m is not None
        else "and the record holds no ModShift result to look there"
    )
    return (
        "The secondary check in the table looks only at phase 0.5, where a circular orbit puts an eclipsing binary's "
        f"secondary eclipse; an eccentric orbit can put it elsewhere, {where}."
    )


def _red_noise(checks: dict) -> str:
    rows = sorted(checks["red_noise"].items(), key=lambda item: int(item[0]))
    measured = [f"{r['beta']:.2f} in Sector {s}" for s, r in rows if "note" not in r]
    unmeasured = [int(s) for s, r in rows if "note" in r]
    said = []
    if measured:
        said.append(f"it is {_words(measured)}")
    if unmeasured:
        said.append(
            f"in {prereg._sectors_words(unmeasured)} too few binned points could measure it, so it is 1 there and "
            "those errors assume white noise"
        )
    return (
        "Each sector's depth errors are scaled by its red-noise factor, beta, measured from the residuals binned at the "
        f"transit core's timescale (Pont et al. 2006; decision record 0006): {'; '.join(said)}."
    )


def _tdepth_zero(evidence: dict, hosts: list[dict]) -> str:
    """The neighbour table's possible hosts TRICERATOPS gave zero depth: it weighed no scenario on them (decision 0026,
    Ruling M)."""
    zero = evidence["hosts_tdepth_zero"]
    if not zero:
        return ""
    one = len(zero) == 1
    it = "it" if one else "them"
    return (
        f" Its apertures take too little light from {len(zero)} of the neighbour table's "
        f"{_count(len(hosts), 'possible host')} to make the dip, so it gave {'that star' if one else 'those stars'} zero "
        f"depth and weighed no scenario on {it} (decision record 0026). For {it}, the case rests on TRICERATOPS's model "
        "of the light in its apertures and on the pixel check, not on a probability."
    )


def _validated(record: Path, version: str, triceratops: dict) -> str:
    """Why the FPP does or does not earn Giacalone et al.'s "validated planet" label, by decision 0026's conditions."""
    limit = _criteria(record, "provenance-triceratops.json", version)["triceratops"][
        "fpp_validated"
    ]
    e = triceratops["evidence"]
    conditions = f"an FPP under {limit:g}, a high-resolution contrast curve and 2-minute data"
    if e["validated_label"]:
        return (
            f'The runs also meet the conditions decision record 0026 sets for Giacalone et al.\'s "validated planet" '
            f"label, {conditions}; this paper still calls the signal a planet candidate."
        )
    lacking = [
        what
        for what, met in (
            (f"an FPP under {limit:g}", e["fpp_mean"] < limit),
            ("a contrast curve", bool(triceratops["contrast"])),
            ("2-minute data", e["exposure_s"] == TWO_MINUTES_S),
        )
        if not met
    ]
    return (
        f'Giacalone et al. also give a "validated planet" label, which decision record 0026 grants only with '
        f"{conditions}; these runs lack {_words(lacking)}, so their FPP does not earn it."
    )


def _offsets(pixel: dict, suspect: set[int]) -> dict:
    """Each sector's centroid offset, and the sector the outcome rests on: the pixel check judges the best-quality
    sector's offset, and the row holding that offset is its sector (as the dossier finds it)."""
    sectors = sorted(pixel["evidence"]["sectors"], key=lambda s: s["sector"])
    offsets = "; ".join(
        f"Sector {s['sector']}, {_f(s['offset_arcsec'], '.1f')} arcsec (quality {_f(s['quality'], '.2f')})"
        + (", a timing-suspect sector the vetting run left out" if s["sector"] in suspect else "")
        for s in sectors
    )
    judged_offset = pixel["evidence"]["offset_qual_arcsec"]
    judged = [
        s["sector"]
        for s in sectors
        if judged_offset is not None and s["offset_arcsec"] == judged_offset
    ]
    if len(judged) == 1:
        rests = (
            f"Its {pixel['outcome']} rests on Sector {judged[0]}'s offset, the best-quality sector's"
            + (
                ", from a sector the vetting run left out for suspect timestamps."
                if judged[0] in suspect
                else "."
            )
        )
    else:
        rests = f"Its {pixel['outcome']} rests on the best-quality sector's offset, which no single sector above reports."
    return {"offsets": offsets, "rests_on": rests}


def _blends(hosts: list[dict], limit: float, zero: list) -> str:
    """The possible hosts neither the pixel check nor TRICERATOPS can exclude. The paper gives their count, not their
    Gaia values."""
    if not hosts:
        return "The neighbour table lists no star that could make the dip."
    listed = _count(len(hosts), "possible host")
    inside = [h for h in hosts if h["sep_arcsec"] is not None and h["sep_arcsec"] < limit]
    if inside:
        one = len(inside) == 1
        said = (
            f"{len(inside)} of the neighbour table's {listed} {'lies' if one else 'lie'} within the pixel check's "
            f"{limit:g} arcsec of the target, where the pixel check can't tell {'that star' if one else 'them'} from "
            "the target."
        )
    else:
        said = f"None of the neighbour table's {listed} lies within the pixel check's {limit:g} arcsec of the target."
    if zero:
        on = (
            ("it" if len(hosts) == 1 else "any of them")
            if len(zero) == len(hosts)
            else f"{len(zero)} of them"
        )
        said += f" TRICERATOPS weighed no scenario on {on}."
    if inside or zero:
        said += " Photometry that resolves the stars near the target could rule them out."
    return said


def _companions(triceratops: dict, exofop: dict) -> str:
    contrast = triceratops["contrast"]
    if contrast:
        return (
            "TRICERATOPS weighed companions and background stars too close to resolve by its priors, limited by "
            f"{_count(len(contrast), 'high-resolution contrast curve')} of the star from ExoFOP."
        )
    said = (
        "TRICERATOPS weighed companions and background stars too close to resolve by its priors alone: no "
        "high-resolution contrast curve of the star went into it."
    )
    if exofop["imaging"]:
        said += (
            f" ExoFOP lists {_count(len(exofop['imaging']), 'high-resolution imaging observation')} of the star, "
            "which did not go into it."
        )
    return said


def _exofop(exofop: dict) -> str:
    """What ExoFOP lists on the star besides the planet-parameter rows: TOIs, CTOIs, confirmed planets and imaging."""
    if exofop["status"] != "ok":
        return f"ExoFOP's records for the star could not be read ({exofop['error']})."
    tois = [f"{t['toi']} ({t.get('disp_tfop') or 'no disposition'})" for t in exofop["tois"]]
    ctois = [f"{t['ctoi']} ({t.get('cdisp') or 'no disposition'})" for t in exofop["ctois"]]
    imaging = len(exofop["imaging"])
    parts = [
        f"{'TOI' if len(tois) == 1 else 'TOIs'} {_words(tois)}" if tois else "no TOI",
        f"{'CTOI' if len(ctois) == 1 else 'CTOIs'} {_words(ctois)}" if ctois else "no CTOI",
        f"the confirmed planets {exofop['confirmed_planets']}"
        if exofop["confirmed_planets"]
        else "no confirmed planet",
        _count(imaging, "high-resolution imaging observation")
        if imaging
        else "no high-resolution imaging observation",
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
    excepted = _excepted(record)
    second = checks["signal"]["kind"] == "second"
    exofop = literature["search"]["exofop"]
    limit = pixel["max_offset_arcsec"]
    holdout = next(c for c in checks["checks"] if c["check"] == "holdout")
    seasons = holdout["evidence"]["seasons"]
    tested = [s for s in seasons if s["status"] in ("predicted", "missed")]
    predicted = sum(s["status"] == "predicted" for s in tested)
    untested = "".join(
        f" The season from BTJD {s['start']:.1f} to {s['end']:.1f} could not be tested: "
        f"{s.get('reason') or UNTESTED.get(s['status'], s['status'])}."
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
        "bar_promotion": ", or the maintainer promoted a SPOC threshold-crossing event that never became a TOI "
        "(decision record 0013)"
        if second
        else "",
        "vetted_products": _words(
            sorted({prereg.PRODUCTS[sources[str(s)]["provenance"]] for s in vetted})
        ),
        "vetted_sectors": prereg._sectors_words(vetted),
        "suspect": f" It left out {prereg._sectors_words(dropped)}, flagged for suspect timestamps (decision record "
        "0022)."
        if dropped
        else "",
        "checks": _table(
            ["Check", "Outcome", "Reason"],
            [
                [
                    f"{CHECKS[name]} (`{name}`"
                    + ("; see below the table)" if name == "novelty" and novelty else ")"),
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
        "hosts": f"{_count(len(hosts), 'such star')} here, each with the eclipse depth it would need, in "
        "`neighbours.csv` in the dataset"
        if hosts
        else "no such star here",
        "tdepth_zero": _tdepth_zero(tric, hosts),
        "tric_data": f"{prereg._sectors_words(tric['sectors'])} at {tric['exposure_s']:g}-s exposures"
        + (", folded and binned in phase" if tric["bin_phase"] else ""),
        "validated": _validated(record, version, triceratops),
        "pixel_check": PIXEL_CHECK[second][0] + (", run as triage runs it" if second else ""),
        "max_offset": f"{limit:g}",
        **_offsets(pixel, set(dropped)),
        "blends": _blends(hosts, limit, tric["hosts_tdepth_zero"]),
        # results/README.md leaves a bare Gaia DR3 source id under CC BY 4.0; the paper leaves it out anyway, so its own
        # text holds nothing from Gaia.
        "names": _words([n for n in literature["search"]["names"] if not n.startswith("Gaia ")]),
        "papers": _count(len(literature["evidence"]["hits"]), "paper"),
        "exofop": _exofop(exofop),
        "excepted": ""
        if not excepted
        else f", apart from {_words([r['name'] for r in excepted])}, which decision record 0042 sets aside (see "
        "When it was made public)",
        "triceratops_runs": _count(len(tric["fpp"]), "run"),
        "companions": _companions(triceratops, exofop),
        "holdout": f"For this signal the check {WAS[holdout['outcome']]}: of its "
        f"{_count(len(seasons), 'season')}, {len(tested)} could be tested and {predicted} "
        f"{'was' if predicted == 1 else 'were'} predicted.{untested}",
    }


def _label(finding: dict, confirmed: list[str]) -> str:
    """A finding's id, the question it bears on, its rating and what its refuters did."""
    question = QUESTIONS[finding["lens"]]
    if finding["rating"] == "note":
        return f"{finding['id']}, on {question} (rated note)"
    n = len(finding["refuters"])
    if finding["id"] not in confirmed:
        refuted = sum(v["refuted"] for v in finding["refuters"])
        said = f"refuted by {refuted} of its {_count(n, 'refuter')}"
    # Confirmed only because nothing refuted it, as the dossier says: the reader should not take it for tested.
    elif n == 0:
        said = "no refuter tested it, so it counts as confirmed by default"
    elif n == 1:
        said = "its one refuter did not refute it"
    elif n == 2:
        said = "neither of its 2 refuters refuted it"
    else:
        said = f"none of its {n} refuters refuted it"
    return f"{finding['id']}, on {question} (rated {finding['rating']}; {said})"


def _fates(findings: list[dict], confirmed: list[str]) -> str:
    counts = Counter(
        ("note", "note")
        if f["rating"] == "note"
        else ("confirmed" if f["id"] in confirmed else "refuted", f["rating"])
        for f in findings
    )
    said = [
        f"{counts['confirmed', rating]} rated {rating} stood as confirmed"
        for rating in ("kill", "hold")
        if counts["confirmed", rating]
    ]
    said += [
        f"{n} rated {rating} {'was' if n == 1 else 'were'} refuted"
        for rating in ("kill", "hold")
        if (n := counts["refuted", rating])
    ]
    if n := counts["note", "note"]:
        said.append(f"{n} {'was' if n == 1 else 'were'} rated note")
    return _words(said) or "none stood as confirmed"


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

    return (
        f"The review flagged {_count(len(flagged), 'paper')} for the maintainer to read, "
        f"{_words([paper(i) for i in flagged])}, and the call records that the maintainer read "
        f"{'it' if len(flagged) == 1 else 'each'}."
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
                f"Refuter {i} {'refuted it' if v['refuted'] else 'did not refute it'}: {_quote(v['reason'])}"
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
        "answers": answers or "None: the review confirmed no finding.",
        "refuted": "Findings a refuter refuted, quoted with each refuter's verdict:\n\n" + verdicts
        if refuted
        else "No refuter refuted any finding.",
        "notes": "Findings the review rated note, which need no answer, quoted:\n\n"
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
    under = f", under its criteria {Path(used['file']).stem}" if used else ""
    said = f"Triage then screened every signal at or above the threshold{under}."
    if bool(row["shortlisted"]):
        return (
            f"{said} This signal passed its novelty check, LEO-Vetter's false-alarm and flux-level tests "
            f"({row['leo_reason']}) and its pixel check, and was shortlisted."
        )
    said += (
        f" This signal's novelty check {WAS[row['novelty']]}, LEO-Vetter's tests {WAS[row['leo_flux']]} and its "
        f"pixel check {WAS[row['pixels']]}, so triage did not shortlist it."
    )
    if checks["signal"]["kind"] == "second":
        said += (
            " It came to vetting on tess-hunt's second list, of SPOC threshold-crossing events that never became TOIs "
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
    one = row.iloc[0] if len(row) == 1 else None
    return {
        "search_run": made["search_run"],
        "sde": None if one is None else _number(float(one["sde"]), ".2f"),
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
        "triage": None if one is None else _triage(one, made, checks),
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
    listings = [
        f" ExoFOP lists a signal at this period on the star as {r['name']} (period {r['period']:.6g} d), first listed "
        f"on {r['first_listed']} with "
        + (f"disposition {_words(r['dispositions'])}" if r["dispositions"] else "no disposition")
        + ", after tess-hunt made this signal public; the record does not say who submitted it."
        for r in found["excepted"]
    ]
    if listings:
        listings.append(
            " A listing made after tess-hunt made a signal public, which the claim itself may have prompted, can't show "
            "the signal was known before it. So tess-hunt does not count a TOI or CTOI on the signal's own star as "
            "making the signal known when ExoFOP first listed it after that claim and each of its dispositions is PC "
            "or empty (decision record 0042). The rule orders the public claims by date; it says nothing about when or "
            f"how others found the signal. ExoFOP's page for the star is {EXOFOP_STAR.format(tic)}."
        )
    return {
        "claim_date": None if claim is None else claim.date.isoformat(),
        "claim_where": where,
        "listings": "".join(listings),
    }


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
    summary = (
        f" tess-hunt predicted the signal's transits in TESS {prereg._sectors_words(sectors)} and deposited the "
        f"prediction on Zenodo before TESS observed {them};" + SUMMARY_RESULT[p["result"]]
    )
    as_of = dt.date.fromisoformat(p["as_of"])
    if p["result"] == "pending":
        said = f"As of {as_of} the test is pending: {p['reason']}."
    elif p["result"] == "untested":
        said = f"As of {as_of} the new data could not test it ({p['status']}): {p['reason']}."
    else:
        depth, err = _ppm(p["depth"]), _ppm(p["err"])
        if depth is None or err is None:
            return {"summary_prereg": summary}
        tension = (
            f"{p['tension']:.2f} sigma from the depth the earlier seasons give, which the deposit's `references.json` "
            "holds"
            if "tension" in p
            else f"with no tension measured: {p['tension_skipped']}"
        )
        verb = "replicate the signal" if p["result"] == "replicated" else "miss the prediction"
        said = (
            f"As of {as_of} the new sectors {verb}: in the cores of the predicted transits, {p['n']} cadences give a "
            f"depth of {depth} ± {err} ppm, {p['sigma']:.2f} times its error, where the test expected "
            f"{p['expected_snr']:.2f} times it, and {tension}."
        )
        if p["result"] == "replicated":
            said += (
                " A replicated season shows the dip is real, periodic and where the prediction put it; it does not "
                "show that the dip is on the target."
            )
    order = (
        "before" if call["date"] < as_of else "after" if call["date"] > as_of else "on the day of"
    )
    return {
        "prereg": f"Before TESS observed {prereg._sectors_words(sectors)}, tess-hunt deposited on Zenodo "
        f"(doi:{deposit['doi']}) a prediction of the signal's transits in "
        f"{'that sector' if len(sectors) == 1 else 'those sectors'} and the test that would judge {them}: the held-out "
        "check's test, applied to the deposited prediction (decision record 0040). Zenodo published the deposit on "
        f"{published}, and TESS began observing Sector {first} on {start}. {said} The maintainer's call "
        f"({call['date']}) came {order} this result.",
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
        "records": f"The record is in `dataset/vetting/{signal}/`."
        if version is None
        else f"The first record is in `dataset/vetting/{signal}/`, and each later version is in its own subdirectory "
        f"there, {_words([f'`r{n}/`' for n in range(2, version + 1)])}; this paper reports version r{version}.",
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
        "The deposit holds the paper (`preprint.pdf`, rendered from `preprint.md`), its figures and its dataset: the "
        "signal's published vetting records and the light curve the vetting run of the paper's record read, which "
        "`manifest.json` lists with each file's sha256 and licence. The files are CC BY 4.0, except the dataset's "
        f"files that hold Gaia DR3 data ({_words([f'`{name}`' for name in gaia])}, in each record's directory) and "
        "any Gaia value in the paper's quoted text or in a note beside it, which stay under ESA's CC BY-NC 3.0 IGO "
        "terms, and ExoFOP's rows in the dataset and the ExoFOP listings the paper names, which stay under ExoFOP's "
        "terms.",
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
