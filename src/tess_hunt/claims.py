"""`tess-hunt vetting claims`: decision 0042. A TOI or CTOI on a signal's own star that ExoFOP first listed after the
signal's public claim, with every disposition PC or empty, does not make the signal known. The stage takes those rows
out of the catalog snapshot the vetting run used and runs the unchanged novelty check again (M5 design, section
4.2)."""

import datetime as dt
import json
import re
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from tess_hunt.catalogs import snapshot_inputs
from tess_hunt.config import Criteria, catalogs_dir, load_criteria
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.novelty import check_novelty
from tess_hunt.provenance import repo_root, sha256_file, start_run
from tess_hunt.serialize import jsonable
from tess_hunt.threshold import load_v2_catalog

CLAIMS = "results/claims.toml"
# Where a literature record keeps ExoFOP's rows of each kind, and the field naming the listing in them.
ROWS = {"TOI": ("tois", "toi"), "CTOI": ("ctois", "ctoi")}
# The day ExoFOP first listed a row: the TOI catalog's alert date, the CTOI's creation day (pin P2).
FIRST_LISTED = {"TOI": "toidate1", "CTOI": "ctoi_created"}
# TESS's and TFOPWG's dispositions of a TOI; the uploader's and TFOPWG's of a CTOI.
DISPOSITIONS = {"TOI": ("disp_tess", "disp_tfop"), "CTOI": ("cdisp", "tdisp")}
# The snapshot writes TOI-1234.01 and CTOI-17361.01; ExoFOP writes TOI 1234.01, TIC 17361.01 and, for a CTOI the TOI
# team promoted, TIC 17361.01 (now TOI 3127.01).
LISTING = re.compile(r"(?:TOI[- ]|CTOI-|TIC )(\d+\.\d+)(?: \(now TOI \d+\.\d+\))?")


@dataclass(frozen=True)
class Claim:
    signal: str
    date: dt.date
    record: str


def load_claims(path: Path) -> dict[str, Claim]:
    """Each signal's claim: the day it was first public and the public record a reader can check that day against.
    The file changes only with a decision record (decision 0042)."""
    path = Path(path)
    out = {}
    for name, entry in tomllib.loads(path.read_text()).items():
        # A TOML datetime is a date too; a claim is a day.
        if (
            not isinstance(entry, dict)
            or set(entry) != {"date", "record"}
            or not isinstance(entry["date"], dt.date)
            or isinstance(entry["date"], dt.datetime)
            or not isinstance(entry["record"], str)
            or not entry["record"].startswith("https://")
        ):
            raise SystemExit(
                f"{path.name}: {name} needs exactly date (a TOML date) and record (an https URL)"
            )
        out[name] = Claim(name, entry["date"], entry["record"])
    return out


def listing_id(name: str) -> str | None:
    """The listing's number, the same in each form the snapshot and ExoFOP write it; None for any other name."""
    found = LISTING.fullmatch(name)
    return found.group(1) if found else None


def first_listed(row: dict, kind: str) -> dt.date | None:
    """The day ExoFOP first listed the row; None unless the field holds a plain date."""
    try:
        return dt.datetime.strptime(row.get(FIRST_LISTED[kind]), "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def dispositions(row: dict, kind: str) -> list[str]:
    """ExoFOP's dispositions of the row, without the empty ones."""
    return [row[field] for field in DISPOSITIONS[kind] if row[field] != ""]


def _why_kept(kind: str, found: list[dict], claim: Claim | None, status: str) -> str | None:
    """Why decision 0042 keeps a row of the signal's star that ExoFOP lists as `found`; None if it excepts the row.
    Any doubt keeps it."""
    if claim is None:
        return "the claims file gives the signal no claim"
    if status != "ok":
        return f"ExoFOP's record was not read (status {status})"
    if not found:
        return "ExoFOP's record for the star lacks it"
    if len(found) > 1:
        return "ExoFOP's record lists it more than once"
    [row] = found
    first = first_listed(row, kind)
    if first is None:
        return f"ExoFOP gives no first-listed date ({FIRST_LISTED[kind]})"
    if first <= claim.date:
        return f"first listed {first}, not after the claim date {claim.date}"
    unread = [field for field in DISPOSITIONS[kind] if not isinstance(row.get(field), str)]
    if unread:
        return f"ExoFOP's row gives no {' or '.join(unread)}"
    other = [d for d in dispositions(row, kind) if d != "PC"]
    if other:
        return f"disposition {', '.join(other)}, not PC"
    return None


def sort_rows(
    snapshot_rows: pd.DataFrame, exofop: dict, claim: Claim | None
) -> tuple[list[dict], list[dict]]:
    """The TOI and CTOI rows among `snapshot_rows`, the snapshot's rows on the signal's star, split into those decision
    0042 excepts, each with its first-listed date and dispositions, and those it keeps, each with the reason. A row is
    found among ExoFOP's rows of its own kind only."""
    listed: dict[tuple[str, str], list[dict]] = {}
    for kind, (rows, field) in ROWS.items():
        for row in exofop[rows]:
            number = listing_id(str(row.get(field)))
            if number is not None:
                listed.setdefault((kind, number), []).append(row)
    excepted, kept = [], []
    for row in snapshot_rows[snapshot_rows["source"].isin(list(ROWS))].to_dict("records"):
        kind = row["source"]
        found = listed.get((kind, listing_id(row["name"])), [])
        reason = _why_kept(kind, found, claim, exofop["status"])
        if reason is not None:
            kept.append({"source": kind, "name": row["name"], "reason": reason})
            continue
        excepted.append(
            {
                "source": kind,
                "name": row["name"],
                "tic": int(row["tic"]),
                "period": float(row["period"]),
                "first_listed": first_listed(found[0], kind).isoformat(),
                "dispositions": dispositions(found[0], kind),
            }
        )
    return excepted, kept


def rerun(checks: dict, known: pd.DataFrame, crit_search: Criteria, crit_vet: Criteria) -> dict:
    """The novelty check on `known`, for the star and ephemeris a vetting run's checks.json records, with the settings
    vet.vet_with_fits gives it."""
    star = checks["star"]
    return check_novelty(
        int(star["tic"]),
        float(star["ra"]),
        float(star["dec"]),
        Ephemeris(**checks["ephemeris"]),
        known,
        crit_vet["novelty"]["neighbour_arcmin"],
        tuple(crit_vet["novelty"]["harmonics"]),
        crit_search["match"]["sigma_p"],
        crit_search["match"]["sigma_t"],
        tuple(crit_vet["novelty"]["inconclusive_kinds"]),
    ).to_dict()


def sort_signal(
    checks: dict,
    known: pd.DataFrame,
    exofop: dict,
    claim: Claim | None,
    crit_search: Criteria,
    crit_vet: Criteria,
) -> dict:
    """What claims.json says of one signal: its claim, the rows of its star decision 0042 excepts and those it keeps,
    and novelty run again on the snapshot without the excepted rows, or None when it excepts none."""
    on_star = known["tic"] == int(checks["star"]["tic"])
    excepted, kept = sort_rows(known[on_star], exofop, claim)
    # TOI rows are named TOI-..., CTOI rows CTOI-..., so a name picks out one listing's rows.
    out = (
        on_star
        & known["source"].isin(list(ROWS))
        & known["name"].isin([r["name"] for r in excepted])
    )
    return {
        "claim": None
        if claim is None
        else {"date": claim.date.isoformat(), "record": claim.record},
        "exofop_status": exofop["status"],
        "excepted": excepted,
        "kept": kept,
        "novelty": rerun(checks, known[~out], crit_search, crit_vet) if excepted else None,
    }


def _snapshot(made: dict, run_id: str) -> Path:
    """The catalog snapshot a vetting run vetted with, under the data directory, each file the one the run read."""
    if made.get("catalogs") is None:
        raise SystemExit(f"{run_id} recorded no catalog snapshot")
    snapshot = catalogs_dir() / made["catalogs"]
    for name, path in snapshot_inputs(snapshot).items():
        if not path.is_file() or sha256_file(path) != made["inputs"].get(name, {}).get("sha256"):
            raise SystemExit(
                f"snapshot {snapshot.name} is not the one {run_id} vetted with ({path.name})"
            )
    return snapshot


def cmd_claims(args) -> int:
    # vetting imports this module for its parser, and prereg imports vetting.
    from tess_hunt import prereg, vetting

    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Every refusal comes before the run starts, so it leaves no unfinished run directory.
    made = vetting._vetting_run(args.run, crit_search, crit_vet, args.production)
    run_id = args.run.resolve().name
    records = vetting._literature_records(args.literature, args.production)
    literature_id = args.literature.resolve().name
    made_from = json.loads((args.literature / "provenance.json").read_text())["vetting_run"]
    if made_from != run_id:
        raise SystemExit(f"literature run {literature_id} was made from {made_from}, not {run_id}")
    names = args.signals or sorted(records)
    unsearched = [name for name in names if name not in records]
    if unsearched:
        raise SystemExit(f"literature run {literature_id} has no record of {', '.join(unsearched)}")
    vetted = vetting._vetted(args.run, names)
    snapshot = _snapshot(made, run_id)
    committed = repo_root() / CLAIMS
    claims_file = args.claims or committed
    # start_run's clean-tree check covers the code, not results/, so a production run could otherwise read claims from
    # another checkout or an edit no decision record made.
    if args.production and claims_file.resolve() != committed.resolve():
        raise SystemExit(f"a production run reads {CLAIMS} from this checkout, not {claims_file}")
    if args.production and prereg._uncommitted(committed):
        raise SystemExit(
            f"{CLAIMS} has changes that are not committed; a production run needs it committed"
        )
    claimed = load_claims(claims_file)
    known = load_v2_catalog(snapshot)
    run = start_run("vetting-claims", [crit_search, crit_vet], args.production, sys.argv)
    run.record("vetting_run", run_id)
    run.record("literature_run", literature_id)
    run.record("catalogs", snapshot.name)
    run.record_input("claims", claims_file)
    run.record_input("vetting_provenance", args.run / "provenance.json")
    run.record_input("literature_provenance", args.literature / "provenance.json")
    for name, path in snapshot_inputs(snapshot).items():
        run.record_input(name, path)
    for name in vetted:
        run.record_input(f"checks_{name}", args.run / "signals" / name / "checks.json")
        run.record_input(f"literature_{name}", records[name])
    done = {}
    for name, checks in vetted.items():
        tic = int(checks["star"]["tic"])
        exofop = json.loads(records[name].read_text())["search"]["exofop"]
        found = sort_signal(checks, known, exofop, claimed.get(name), crit_search, crit_vet)
        path = run.path / "signals" / name / "claims.json"
        path.parent.mkdir(parents=True)
        record = {
            "signal": {"name": name, "tic": tic},
            "vetting_run": run_id,
            "literature_run": literature_id,
            **found,
        }
        path.write_text(json.dumps(jsonable(record), indent=2, sort_keys=True) + "\n")
        novelty = found["novelty"]
        done[name] = {
            "tic": tic,
            "excepted": len(found["excepted"]),
            "novelty": None if novelty is None else novelty["outcome"],
            # Publish checks the record it copies against this.
            "sha256": sha256_file(path),
        }
        if novelty is None:
            print(f"{name}: nothing excepted, {len(found['kept'])} row(s) of the star kept")
        else:
            listed = ", ".join(r["name"] for r in found["excepted"])
            print(
                f"{name}: {listed} excepted; novelty without them {novelty['outcome']}, {novelty['reason']}"
            )
    run.finish(vetting_run=run_id, literature_run=literature_id, signals=done)
    excepting = sum(r["excepted"] > 0 for r in done.values())
    print(
        f"vetting claims: {len(done)} signal(s), {excepting} with a listing excepted -> {run.path}"
    )
    return 0


def add_parser(modes) -> None:
    c = modes.add_parser(
        "claims",
        help="novelty again without the TOIs and CTOIs on each signal's star listed after its claim (decision 0042)",
    )
    c.add_argument(
        "--run", type=Path, required=True, help="a finished vetting run, not evidence-only"
    )
    c.add_argument(
        "--literature", type=Path, required=True, help="a literature run made from --run"
    )
    c.add_argument(
        "--signals", nargs="+", help="signal names; by default every one --literature searched for"
    )
    c.add_argument(
        "--claims",
        type=Path,
        help=f"each signal's claim date and public record; by default, and in a production run, {CLAIMS}",
    )
    c.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    c.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    c.add_argument("--production", action="store_true")
    c.set_defaults(func=cmd_claims)
