"""The DDT ask for a held signal (decision 0039): the proposal, rendered from the signal's published record and from
`facts.toml`, which names the source and read date of each fact about archives and dates; and the target list the
TESS office asks for. Numbers are formatted as the dossier formats them, and the template is filled with `substitute`:
a value the record lacks, or holds as null, NaN or an empty list, is left out, so its placeholder raises instead of
rendering (docs/design.md, section 5.5)."""

import json
import math
import tomllib
from datetime import datetime
from pathlib import Path
from string import Template

from astropy.time import Time

from tess_hunt import calls
from tess_hunt.config import load_criteria
from tess_hunt.dossier import _scrub, _table, _words
from tess_hunt.predict import seen_utc
from tess_hunt.provenance import repo_root

# The DDT template's Feasibility section asks how many targets are brighter than this TESS magnitude, since they may
# need extra-large pixel stamps.
BRIGHT_TMAG = 7.0
KEYWORDS = "planet candidate;transit;held-out season"


def _number(value, fmt: str) -> str | None:
    """A number as the dossier formats it, or None for a null or a NaN, so its placeholder stays unfilled."""
    if value is None or not math.isfinite(value):
        return None
    return format(value, fmt)


def _products(sources: dict) -> str | None:
    """The products of the sectors fetched, as the dossier's DDT note lists them; None when any was SPOC 2-min, since
    the proposal's case is that the star has none."""
    if any(s["provenance"] == "SPOC" and s["cadence_s"] <= 120.0 for s in sources.values()):
        return None
    products: dict[str, set[float]] = {}
    for source in sources.values():
        products.setdefault(source["provenance"], set()).add(source["cadence_s"])
    return "; ".join(
        f"{name} at {_words([f'{c:g}' for c in sorted(cadences, reverse=True)])} s"
        for name, cadences in sorted(products.items())
    )


def _vet_criteria(record: Path, checks: dict) -> dict:
    """The vet criteria the checks ran under, from the file the vetting run's provenance names, checked against the
    sha256 it recorded (as `calls` reads the run's match rule)."""
    made = json.loads((record / "provenance-checks.json").read_text())
    [used] = [c for c in made["criteria"] if Path(c["file"]).stem == checks["criteria_version"]]
    path = repo_root() / used["file"]
    criteria = load_criteria(path) if path.is_file() else None
    if criteria is None or criteria.sha256 != used["sha256"]:
        raise ValueError(f"{used['file']} is not the file the vetting run read")
    return {
        "min_training_seasons": str(criteria["holdout"]["min_training_seasons"]),
        "fpp_pass": f"{criteria['triceratops']['fpp_pass']:g}",
        "nfpp_pass": f"{criteria['triceratops']['nfpp_pass']:g}",
    }


def _from_checks(checks: dict, sectors: list[int]) -> dict:
    star, eph = checks["star"], checks["ephemeris"]
    check = {c["check"]: c for c in checks["checks"]}
    holdout = check["holdout"]
    seasons = holdout["evidence"]["seasons"]
    training = {s["training_seasons"] for s in seasons}
    others = [c for c in checks["checks"] if c["outcome"] != "pass"]
    vetted = sorted(s for family in checks["families"].values() for s in family)
    cadences = sorted({checks["sources"][str(s)]["cadence_s"] for s in vetted}, reverse=True)
    tmag = _number(star["tmag"], ".2f")
    depth = eph["depth"]
    found = {
        "signal": checks["signal"]["name"],
        "tic": str(star["tic"]),
        "criteria": checks["criteria_version"],
        "teff": _number(star["teff"], ".0f"),
        "tmag": tmag,
        "radius_sun": _number(star["rad"], ".2f"),
        "depth_ppm": None if depth is None else _number(depth * 1e6, ".0f"),
        "sectors": _words(sectors),
        "first_sector": str(sectors[0]),
        "last_sector": str(sectors[-1]),
        "bright_tmag": f"{BRIGHT_TMAG:g}",
        "bright": None if tmag is None else str(int(star["tmag"] < BRIGHT_TMAG)),
        "families": _words([name.upper() for name in sorted(checks["families"])]),
        "vetted_sectors": _words(vetted),
        "vetted_cadences": _words([f"{c:g}" for c in cadences]),
        "suspect_sectors": _words(checks["dropped_suspect"]),
        "n_transits": str(len(checks["catalogued"]["transits"])),
        "products": _products(checks["sources"]),
        "n_checks": str(len(check)),
        "n_passed": str(len(check) - len(others)),
        # The checks that did not pass are named as inconclusive only when none of them failed.
        "inconclusive": _words([c["check"] for c in others])
        if all(c["outcome"] == "inconclusive" for c in others)
        else None,
        "tce": _words([t["name"] for t in check["novelty"]["evidence"].get("tce_matches") or []]),
        "snr": _number(check["signal_present"]["evidence"]["snr"], ".1f"),
        "holdout_outcome": holdout["outcome"],
        "n_seasons": str(len(seasons)),
        "n_tested": str(sum(s["status"] in ("predicted", "missed") for s in seasons)),
        # One count stands for every season only when they all have the same number of training seasons.
        "season_training": str(training.pop()) if len(training) == 1 else None,
        "season_years": _words(
            [Time(s["start"] + 2457000.0, format="jd", scale="tdb").datetime.year for s in seasons]
        ),
    }
    prior = checks["fit_prior"]
    if prior is not None:
        fit = prior["ephemeris"]
        rp = prior["rp_rearth"] or {}
        duration = checks["window_duration"]
        found |= {
            "period": _number(fit["period"]["median"], ".6f"),
            "period_sd": _number(fit["period"]["sd"], ".2g"),
            "t0": _number(fit["t0"]["median"], ".4f"),
            "t0_sd": _number(fit["t0"]["sd"], ".2g"),
            "rp_rearth": _number(rp.get("median"), ".2f"),
            "rp_lo": _number(rp.get("p16"), ".2f"),
            "rp_hi": _number(rp.get("p84"), ".2f"),
            # The windows' duration is the density-prior fit's only when the record says so.
            "duration_h": _number(duration["days"] * 24, ".2f")
            if duration["from"] == "fit_prior"
            else None,
        }
    dated = [w for w in checks["windows"] or [] if "epoch" in w and w["sector"] in sectors]
    if dated:
        rows = [
            [
                w["sector"],
                w["epoch"],
                f"{w['mid_btjd']:.3f}",
                seen_utc(w["mid_btjd"], star["ra"], star["dec"]),
                f"{w['sd_minutes']:.1f}",
            ]
            for w in dated
        ]
        found["windows"] = _table(["Sector", "Epoch", "Mid (BTJD)", "Mid (UTC)", "sd (min)"], rows)
        found["n_windows"] = str(len(dated))
    return found


def _from_triceratops(path: Path) -> dict:
    if not path.is_file():
        return {}
    record = json.loads(path.read_text())
    evidence = record["evidence"]
    return {
        "fpp": _number(evidence["fpp_mean"], ".3g"),
        "nfpp": _number(evidence["nfpp_mean"], ".3g"),
        "tric_outcome": record["outcome"],
        # The runs that finished, as the dossier counts them.
        "tric_runs": str(len(evidence["fpp"])),
    }


def _from_literature(path: Path) -> dict:
    if not path.is_file():
        return {}
    names = json.loads(path.read_text())["search"]["names"]
    # A Gaia DR3 source id is Gaia data, which stays out of results/ddt/, CC BY 4.0 whole (results/README.md); the
    # TIC name is the proposal's own `tic`.
    return {"names": ", ".join(n for n in names if not n.startswith(("Gaia ", "TIC ")))}


def _from_review(path: Path) -> dict:
    review = calls.load_review(path)
    confirmed = len(calls.confirmed(review))
    # Each finding's claim, quoted word for word under decision 0037, as the dossier quotes it.
    return {f"review_{f['id']}": _scrub(f["claim"]) for f in review["findings"]} | {
        "review_date": str(review["date"]),
        "review_findings": str(len(review["findings"])),
        "review_confirmed": str(confirmed) if confirmed else "no",
    }


def _from_facts(facts: dict, sectors: list[int]) -> dict:
    read = {str(fact["read"]) for fact in facts.values()}
    return {f"fact_{key}": str(fact["value"]) for key, fact in facts.items()} | {
        # The dates of the sectors asked for: a sector facts.toml gives no date for raises, naming the fact.
        "first_start": str(facts[f"s{sectors[0]}_start"]["value"]),
        "last_end": str(facts[f"s{sectors[-1]}_end"]["value"]),
        "fact_sources": "; ".join(dict.fromkeys(fact["source"] for fact in facts.values())),
        # One date stands for every fact, and the sources go without theirs, only when all were read that day.
        "facts_read": read.pop() if len(read) == 1 else None,
    }


def values(record: Path, facts: Path, sectors: list[int]) -> dict[str, str]:
    """Every placeholder the proposal's template may use, read from the signal's record and `facts`, with the
    predicted windows of `sectors` only. A value the record does not hold is left out."""
    checks = json.loads((record / "checks.json").read_text())
    sectors = sorted(sectors)
    elsewhere = [s for s in sectors if s not in (checks["upcoming_sectors"] or [])]
    if elsewhere:
        raise ValueError(
            f"tess-point does not place TIC {checks['star']['tic']} in sector(s) {_words(elsewhere)}"
        )
    call = calls.load(record / "call.toml")
    search_run = json.loads((record / "provenance-checks.json").read_text())["search_run"]
    found = (
        _from_checks(checks, sectors)
        | _vet_criteria(record, checks)
        | _from_triceratops(record / "triceratops.json")
        | _from_literature(record / "literature.json")
        | _from_review(record / "review.json")
        | _from_facts(tomllib.loads(facts.read_text()), sectors)
        | {
            "call_date": str(call["date"]),
            "deciding_evidence": call["deciding_evidence"] and _scrub(call["deciding_evidence"]),
            "search_run": search_run,
            # A run id opens with the UTC time the run started.
            "search_date": datetime.strptime(search_run.split("-")[0], "%Y%m%dT%H%M%SZ")
            .date()
            .isoformat(),
        }
    )
    # A null, a NaN or an empty list gives no text, so its placeholder stays unfilled rather than rendering blank.
    return {key: value for key, value in found.items() if value}


def render(template: Path, record: Path, facts: Path, sectors: list[int]) -> str:
    return Template(template.read_text()).substitute(values(record, facts, sectors))


def targets_csv(record: Path, keywords: str) -> str:
    """The target list in the shape of the TESS office's template (ddt-template-target-list-3.csv): its header block
    and column line, then one row at priority 1, with the template's CRLF line ends. The DDT PI and who made the file
    when stay the template's placeholders, for the maintainer to fill when sending: nothing in the repo names a
    person."""
    checks = json.loads((record / "checks.json").read_text())
    tic = checks["star"]["tic"]
    rows = [f"{tic},1.0,{keywords}"]
    lines = [
        "# DDT PI: <proposer name>",
        "# Cadence: 2m",
        f"# Subject: Planet candidate {checks['signal']['name']} on TIC {tic}",
        "# DDT: <to be supplied by TESS team>",
        "#",
        "# Original filename: targets.csv",
        "# Created by: Name",
        "# Created on: date",
        f"# Number of targets: {len(rows)}",
        "# ",
        "# Column 1: TIC ID",
        "# Column 2: Priority (floating point: 0=low, 1=high)",
        "# Column 3: Keywords (separated by semi-colon)",
        "# tic,priority,keywords",
        *rows,
    ]
    return "\r\n".join(lines) + "\r\n"


def add_parser(sub) -> None:
    p = sub.add_parser("ddt", help="the DDT ask for a held signal (decision 0039)")
    modes = p.add_subparsers(dest="mode", required=True)
    r = modes.add_parser(
        "render", help="render the proposal and its target list from a published record"
    )
    r.add_argument(
        "--record", type=Path, required=True, help="the signal's record, results/vetting/<name>"
    )
    r.add_argument("--template", type=Path, required=True, help="the proposal's template")
    r.add_argument(
        "--facts", type=Path, required=True, help="facts.toml: archive and date facts, with sources"
    )
    r.add_argument("--sectors", type=int, nargs="+", required=True, help="the sectors asked for")
    r.add_argument(
        "--out", type=Path, required=True, help="the directory for proposal.md and targets.csv"
    )
    r.set_defaults(func=cmd_render)


def cmd_render(args) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    proposal = args.out / "proposal.md"
    proposal.write_text(render(args.template, args.record, args.facts, args.sectors))
    targets = args.out / "targets.csv"
    targets.write_text(targets_csv(args.record, KEYWORDS), newline="")
    print(f"ddt: {proposal}, {targets}")
    return 0
