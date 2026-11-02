"""The preprint and dataset for a passed signal (decision 0043; M5 design, section 4.4). `tess-hunt preprint run`
renders a short paper from the signal's latest published record, whose call must be a pass that stands on it, and
lays beside it the dataset its numbers come from: each published record of the signal up to that one and the light
curve the passing vet read. The template is filled with `substitute`, each value read by its key from the record, its
runs' provenance and the published runs they name, so a value they lack raises instead of rendering (docs/design.md,
section 5.5). The PDF needs the optional `preprint` dependency group."""

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from string import Template

import pandas as pd

from tess_hunt import calls, prereg, vetting
from tess_hunt.claims import CLAIMS, load_claims
from tess_hunt.config import runs_dir
from tess_hunt.ddt import _from_triceratops, _number, _ppm
from tess_hunt.dossier import (
    LENSES,
    PIXEL_CHECK,
    PLOTS,
    SENTENCES,
    _scrub,
    _summary,
    _table,
    _words,
)
from tess_hunt.provenance import publish_run, repo_root, sha256_file, start_run

TEMPLATE = "results/preprints/preprint.template.md"
# Its text changes only with the maintainer's approval (decision 0043).
AUTHOR = "results/preprints/author.toml"
AUTHOR_KEYS = ("given_names", "family_names", "affiliation", "repository")
AUTHOR_OPTIONAL = ("orcid", "email")
DOIS = "results/predictions/dois.toml"
# The record's plots the paper shows. Its centroid plots draw Gaia DR3 stars, so they stay in the dataset under Gaia's
# terms and the paper is CC BY 4.0 whole.
FIGURES = ("transits.png", "folds.png", "odd_even.png", "phase.png")
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


def _quoted(items: list[str]) -> str:
    return "\n".join(f"- {_scrub(item)}" for item in items)


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _beside(notes: list[dict]) -> str:
    """The notes added beside a quoted finding under decision 0037, worded as the dossier words them, each nested
    under the finding. Python-Markdown nests a list only at four spaces."""
    return "".join(
        f"\n    - **Note added on {n['date']} under decision 0037, not part of the review or the call:** "
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


def _upcoming(upcoming: list[int] | None) -> str | None:
    if upcoming is None:
        return None
    where = f"TESS {prereg._sectors_words(upcoming)}" if upcoming else "no upcoming TESS sector"
    return f"When it was vetted, tess-point (Burke et al. 2020) placed the star in {where}."


def _star(checks: dict) -> dict:
    star, eph, prior = checks["star"], checks["ephemeris"], checks["fit_prior"]
    found = {
        "tic": str(checks["tic"]),
        "tmag": _number(star["tmag"], ".2f"),
        "teff": _number(star["teff"], ".0f"),
        "radius_sun": _number(star["rad"], ".2f"),
        "depth_ppm": _ppm(eph["depth"]),
        "upcoming": _upcoming(checks["upcoming_sectors"]),
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


def _novelty(record: Path, checks: dict, call: dict) -> str:
    """What the checks table's novelty row leaves out: a rerun under decision 0042 and a promotion under 0013."""
    own = next(c for c in checks["checks"] if c["check"] == "novelty")
    judged = calls.novelty(record, checks)
    excepted = _excepted(record)
    said = []
    if excepted:
        said.append(
            f"Against the catalog snapshot, novelty is {own['outcome']}: {own['reason']}. Decision record 0042 in "
            "tess-hunt's repository sets aside a TOI or CTOI on the signal's own star that ExoFOP first listed after "
            "the signal was made public, while each of its dispositions is PC or empty. Run again without "
            f"{'it' if len(excepted) == 1 else 'them'} (When it was made public), novelty is {judged['outcome']}: "
            f"{judged['reason']}."
        )
    if judged["outcome"] != "pass":
        said.append(
            f"Novelty is {judged['outcome']} ({judged['reason']}): the rows at the signal's period are SPOC "
            "threshold-crossing events or ExoMiner rows that never became TOIs. The call promotes the signal, as "
            "decision record 0013 in tess-hunt's repository allows, in the maintainer's words: "
            + _scrub(call["promotion"])
        )
    return "\n\n".join(said)


def _vetting(record: Path, checks: dict, call: dict) -> dict:
    sources, vetted = checks["sources"], sorted(s for f in checks["families"].values() for s in f)
    dropped = checks["dropped_suspect"]
    rows = [[c["check"], c["outcome"], c["reason"]] for c in checks["checks"]]
    pixel = calls.pixels(record, checks)
    triceratops = json.loads((record / "triceratops.json").read_text())
    literature = json.loads((record / "literature.json").read_text())
    rows += [
        ["neighbours", checks["neighbours"]["outcome"], checks["neighbours"]["reason"]],
        ["pixels", pixel["outcome"], pixel["reason"]],
        ["triceratops", triceratops["outcome"], triceratops["reason"]],
        ["literature", literature["outcome"], literature["reason"]],
    ]
    excepted, contrast = _excepted(record), triceratops["contrast"]
    second = checks["signal"]["kind"] == "second"
    return {
        "vetting_run": json.loads((record / "provenance-checks.json").read_text())["run_id"],
        "criteria_version": checks["criteria_version"],
        "vetted_products": _words(
            sorted({prereg.PRODUCTS[sources[str(s)]["provenance"]] for s in vetted})
        ),
        "vetted_sectors": prereg._sectors_words(vetted),
        "suspect": f" It left out {prereg._sectors_words(dropped)}, flagged for suspect timestamps (decision record "
        "0022 in tess-hunt's repository)."
        if dropped
        else "",
        "checks": _table(
            ["Check", "Outcome", "Reason"],
            [[f"{CHECKS[name]} (`{name}`)", outcome, reason] for name, outcome, reason in rows],
        ),
        "novelty": _novelty(record, checks, call),
        "pixel_check": PIXEL_CHECK[second][0] + (", run as triage runs it" if second else ""),
        # results/README.md leaves a bare Gaia DR3 source id under CC BY 4.0; the paper leaves it out anyway, so its own
        # text holds nothing from Gaia.
        "names": _words([n for n in literature["search"]["names"] if not n.startswith("Gaia ")]),
        "excepted": ""
        if not excepted
        else f", but for the {'listing' if len(excepted) == 1 else 'listings'} decision record 0042 sets aside",
        "triceratops_runs": _count(len(triceratops["evidence"]["fpp"]), "run"),
        "companions": "TRICERATOPS weighed unresolved companions and background stars by its priors alone: no "
        "high-resolution image of the star went into it."
        if not contrast
        else "TRICERATOPS weighed unresolved companions and background stars by its priors, limited by "
        f"{_count(len(contrast), 'high-resolution contrast curve')} of the star from ExoFOP.",
        "holdout": next(
            f"{c['outcome']}, {c['reason']}" for c in checks["checks"] if c["check"] == "holdout"
        ),
    }


def _review(record: Path, review: dict, call: dict) -> dict:
    """The review's counts and its quoted findings, each with any note decision 0037 added beside it in
    review-notes.toml, and the call's answers and sentences."""
    path = record / "review-notes.toml"
    added = calls.load_notes(path, review) if path.is_file() else {}
    confirmed = calls.confirmed(review)
    findings = {f["id"]: f for f in review["findings"]}
    flagged = review["hits_flagged"]
    rated_note = [f for f in review["findings"] if f["rating"] == "note"]
    return {
        "call_date": str(call["date"]),
        "review_model": review["model"],
        "review_date": str(review["date"]),
        "findings": _count(len(findings), "finding"),
        "n_confirmed": str(len(confirmed)),
        "hits_read": f"The maintainer read each paper the review flagged, {len(flagged)} in all."
        if flagged
        else "The review flagged no paper for the maintainer to read.",
        "answers": "\n".join(
            f"- {f} ({LENSES[findings[f]['lens']]}, {findings[f]['rating']})"
            # Confirmed only because nothing refuted it, as the dossier says: the reader should not take it for tested.
            + ("" if findings[f]["refuters"] else ", no refuter ran on it")
            + f"\n    - Finding: {_scrub(findings[f]['claim'])}"
            + _beside(added.get(f, []))
            + f"\n    - Answer: {_scrub(call['answers'][f])}"
            for f in confirmed
        )
        or "None: the review confirmed no finding.",
        "notes": "The review's notes, which need no answer, quoted:\n\n"
        + "\n".join(
            f"- {f['id']} ({LENSES[f['lens']]}): {_scrub(f['claim'])}"
            + _beside(added.get(f["id"], []))
            for f in rated_note
        )
        if rated_note
        else "The review made no note.",
        "sentences": _quoted(
            [f"{label}: {call['sentences'][key]}" for key, label in SENTENCES.items()]
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


def _found(repo: Path, checks: dict, made: dict) -> dict:
    """The search, its threshold and the injection recovery, from the published runs the vetting run's provenance
    leads to."""
    results = repo / "results"
    search = json.loads(
        (results / "benchmarks" / made["search_run"] / "provenance.json").read_text()
    )
    threshold_run = search["threshold"]["run_id"]
    threshold = json.loads((results / "benchmarks" / threshold_run / "threshold.json").read_text())
    inject = _inject_run(results / "benchmarks", threshold_run)
    # Triage names a signal <tic>-<rank> and lists every signal at or above the threshold.
    rank = int(checks["signal"]["name"].rsplit("-", 1)[1])
    rows = pd.read_csv(results / "triage" / made["triage_run"] / "signals.csv")
    row = rows[(rows["tic"] == int(checks["tic"])) & (rows["rank"] == rank)]
    return {
        "search_run": made["search_run"],
        "sde": _number(float(row["sde"].iloc[0]), ".2f") if len(row) == 1 else None,
        "threshold": _number(search["threshold"]["value"], ".2f"),
        "threshold_run": threshold_run,
        "null_run": threshold["null_run"],
        "false_alarms": _number(threshold["expected_false_alarms"], ".2f"),
        "inject_run": inject["run_id"],
        "injections": str(inject["summary"]["injections"]),
        "inject_stars": str(inject["summary"]["stars"]),
    }


def _public(record: Path, repo: Path, name: str) -> dict:
    """The claim results/claims.toml gives the signal (decision 0042), and each later listing its record excepts."""
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
    listings = [
        f" ExoFOP first listed {r['name']} on the star on {r['first_listed']}, after that day, with "
        + (f"disposition {_words(r['dispositions'])}." if r["dispositions"] else "no disposition.")
        for r in found["excepted"]
    ]
    if listings:
        listings.append(
            " Under decision record 0042 in tess-hunt's repository, a TOI or CTOI on the signal's own star that "
            "ExoFOP first listed after its claim, with each disposition PC or empty, does not make it known."
        )
    return {
        "claim_date": None if claim is None else claim.date.isoformat(),
        "claim_record": None if claim is None else claim.record,
        "listings": "".join(listings),
    }


def predictions_doi(record: Path, repo: Path) -> str | None:
    """The DOI of the predictions package whose preregistered test the record holds; None when it holds none."""
    path = record / "prereg.json"
    if not path.is_file():
        return None
    package = json.loads(path.read_text())["package"]
    dois = repo / DOIS
    doi = tomllib.loads(dois.read_text()).get(package, {}).get("doi") if dois.is_file() else None
    if doi is None:
        raise SystemExit(f"{DOIS} gives no DOI for package {package}, whose test the record holds")
    return doi


def _prereg(record: Path, repo: Path) -> str | None:
    """The preregistered test of a later season (decision 0040), as the dossier gives its result; None for a judged
    result without its depth or error, so its placeholder raises."""
    path = record / "prereg.json"
    if not path.is_file():
        return "This record holds no preregistered test of a later season (decision record 0040 in tess-hunt's repository)."
    p = json.loads(path.read_text())
    if p["result"] == "pending":
        said = f"pending: {p['reason']}"
    elif p["result"] == "untested":
        said = f"untested ({p['status']}): {p['reason']}"
    else:
        depth, err = _ppm(p["depth"]), _ppm(p["err"])
        if depth is None or err is None:
            return None
        tension = f"tension {p['tension']:.2f} sigma" if "tension" in p else p["tension_skipped"]
        said = (
            f"{p['result']} ({p['status']}): depth {depth} ppm (error {err} ppm, {p['n']} cadences in the predicted "
            f"cores), {p['sigma']:.2f} sigma, expected SNR {p['expected_snr']:.2f}, {tension}"
        )
    return (
        f"Before TESS observed {prereg._sectors_words(p['predicted_sectors'])}, tess-hunt deposited a prediction of "
        f"the signal's transits there on Zenodo (doi:{predictions_doi(record, repo)}; package {p['package']}), with the "
        "test that judges the new season: the held-out check's own, on the published prediction (decision record 0040 "
        f"in tess-hunt's repository). As of {p['as_of']}, the result is {said}."
    )


def _data(record: Path, checks: dict, made: dict) -> dict:
    """The light curves' products and DOIs, the dataset's records, and the credits they ask for."""
    sectors: dict[str, list[int]] = {}
    for sector, source in checks["sources"].items():
        sectors.setdefault(prereg.PRODUCTS[source["provenance"]], []).append(int(sector))
    used = {product: sorted(sectors[product]) for product in prereg.CREDITED if product in sectors}
    signal = vetting._signal_dir(record).name
    gaia = any(licence(path)["licence"] == GAIA for path in _record_paths(record))
    folder = f"`dataset/vetting/{signal}/`"
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
        "records": f"The signal's published vetting record, from which this paper is rendered, is in {folder}."
        if calls.version(record) is None
        else f"The signal's published vetting records, from the first to version r{calls.version(record)}, from "
        f"which this paper is rendered, are in {folder}, each version in its own `r<N>/` directory.",
        "rendered_from": "that record"
        if calls.version(record) is None
        else f"version r{calls.version(record)}",
        "tess_credit": prereg.TESS_CREDIT,
        "qlp_credit": f" {prereg.QLP_CREDIT}" if "QLP" in used else "",
        "gaia_credit": GAIA_CREDIT if gaia else "",
        "gaia_papers": GAIA_PAPERS if gaia else "",
    }


def _figures(record: Path) -> str | None:
    """The figures from the record's plots, each with the dossier's caption; None when the record lacks one."""
    if any(not (record / "plots" / name).is_file() for name in FIGURES):
        return None
    return "\n\n".join(
        f"![Figure {i}]({name})\n\n*Figure {i}. {PLOTS[name]}.*"
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
    name, results/claims.toml, results/predictions/dois.toml and `author`, formatted as the dossier formats them. A
    value they don't hold is left out, so its placeholder raises."""
    checks = json.loads((record / "checks.json").read_text())
    made = json.loads((record / "provenance-checks.json").read_text())
    call = calls.load(record / "call.toml")
    found = (
        _star(checks)
        | _vetting(record, checks, call)
        | _from_triceratops(record, checks["criteria_version"])
        | _review(record, calls.load_review(record / "review.json"), call)
        | _found(repo, checks, made)
        | _public(record, repo, checks["signal"]["name"])
        | _data(record, checks, made)
        | _author(author)
        | {"prereg": _prereg(record, repo), "figures": _figures(record)}
    )
    return {key: value for key, value in found.items() if value is not None}


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
        "any Gaia value in the paper's quoted text, which stay under ESA's CC BY-NC 3.0 IGO terms, and ExoFOP's rows "
        "in the dataset, which stay under ExoFOP's terms.",
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
