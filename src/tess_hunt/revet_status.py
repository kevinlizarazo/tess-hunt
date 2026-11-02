"""`tess-hunt revet status`: before a re-vet, what MAST lists today for each sector a deposited predictions package
predicts, which file fetch would take, and whether the package's test could use it (decision 0041, runbook step 0).
It fetches no light curve, records no run and writes nothing: the re-vet that follows records what it read."""

import json
from pathlib import Path

import pandas as pd

from tess_hunt import fetch, mast, prereg
from tess_hunt.config import load_criteria
from tess_hunt.dossier import _table
from tess_hunt.provenance import repo_root

COMPLETE = "complete: every predicted sector has data the test can use"
UNANSWERED = "MAST did not answer"


def predicted(package: Path) -> dict[str, dict]:
    """Each signal the package predicts: its star, the sectors its predicted transits fall in, and the products whose
    data can test it."""
    transits = pd.read_csv(package / "predictions.csv")
    signals = json.loads((package / "references.json").read_text())["signals"]
    out = {}
    for name, p in signals.items():
        sectors = sorted(
            int(s) for s in transits.loc[transits["signal"] == name, "sector"].unique()
        )
        # A signal with no predicted sector would get no row and so no verdict, which reads as nothing missing.
        if not sectors:
            raise ValueError(f"{package.name}'s predictions.csv predicts no transit of {name}")
        out[name] = {"tic": int(p["tic"]), "sectors": sectors, "testable_with": p["testable_with"]}
    return out


def _version(filename: str) -> str | None:
    match = fetch._VERSION.search(filename)
    return match.group(1) if match else None


def sector_rows(
    predicted: dict, products: pd.DataFrame, rules: list[dict], failed: list[int]
) -> list[dict]:
    """One row per signal and predicted sector: each file MAST lists for it, the one fetch would take (`mast.best`'s),
    and why the test could not use it, in `prereg.judge_signal`'s words. A star in `failed`, which MAST did not
    answer for, has `listed` None: what MAST holds for it is unknown, never nothing."""
    taken = {(int(r.tic), int(r.sector)): r for r in mast.best(products).itertuples()}
    rows = []
    for name, p in predicted.items():
        for sector in p["sectors"]:
            row = {
                "signal": name,
                "tic": p["tic"],
                "sector": sector,
                "listed": None,
                "taken": None,
                "taken_product": None,
                "usable": False,
                "why": UNANSWERED,
            }
            rows.append(row)
            if p["tic"] in failed:
                continue
            here = products[(products["tic"] == p["tic"]) & (products["sector"] == sector)]
            row["listed"] = [
                {
                    "provenance": f.provenance,
                    "cadence_s": float(f.cadence_s),
                    "filename": f.filename,
                    "version": _version(f.filename),
                    "suspect": fetch.timing_suspect(f.provenance, sector, f.filename, rules),
                }
                for f in here.itertuples()
            ]
            best = taken.get((p["tic"], sector))
            if best is None:
                row["why"] = "no data"
                continue
            row["taken"], row["taken_product"] = best.filename, prereg.PRODUCTS[best.provenance]
            # vet drops a timing-suspect sector, so the test finds no data in it.
            if fetch.timing_suspect(best.provenance, sector, best.filename, rules):
                row["why"] = "timing-suspect"
            elif row["taken_product"] not in p["testable_with"]:
                row["why"] = f"{row['taken_product']}, which can't test it"
            else:
                row["usable"], row["why"] = True, None
    return rows


def verdict(rows: list[dict]) -> dict[str, str]:
    """Per signal: complete when every predicted sector has data the test can use; unknown when MAST did not answer
    for its star; otherwise not yet, with each sector the test can't use and why."""
    by_signal: dict[str, list[dict]] = {}
    for row in rows:
        by_signal.setdefault(row["signal"], []).append(row)
    out = {}
    for name, own in by_signal.items():
        if any(r["listed"] is None for r in own):
            out[name] = f"unknown: {UNANSWERED} for TIC {own[0]['tic']}"
        elif all(r["usable"] for r in own):
            out[name] = COMPLETE
        else:
            out[name] = "not yet: " + ", ".join(
                f"S{r['sector']} {r['why']}" for r in own if not r["usable"]
            )
    return out


def redelivery_rows(products: pd.DataFrame, tics: list[int], rules: list[dict]) -> list[dict]:
    """Each file MAST serves for these stars in a provenance and sector a timing-suspect rule covers (QLP's S99 to
    S104), its version and whether it is still suspect. A re-vet takes such a sector again only when the same
    product comes back clean (decision 0041)."""
    covered = {(rule["provenance"], sector) for rule in rules for sector in rule["sectors"]}
    mine = products[products["tic"].isin(tics)].sort_values(["tic", "sector", "filename"])
    return [
        {
            "tic": int(f.tic),
            "sector": int(f.sector),
            "provenance": f.provenance,
            "filename": f.filename,
            "version": _version(f.filename),
            "suspect": fetch.timing_suspect(f.provenance, int(f.sector), f.filename, rules),
        }
        for f in mine.itertuples()
        if (f.provenance, int(f.sector)) in covered
    ]


def _latest(root: Path) -> str:
    packages = [p.name for p in root.iterdir() if (p / "provenance.json").is_file()]
    dois = prereg._dois(root, packages)
    if not dois:
        raise SystemExit("dois.toml lists no deposited package; name one with --package")
    # Run ids begin with the run's start, so of two deposited on one day the later made wins.
    return max(dois, key=lambda run_id: (dois[run_id]["published"], run_id))


def _listed(row: dict) -> str:
    if row["listed"] is None:
        return UNANSWERED
    files = [
        " ".join(filter(None, (f["provenance"], f["version"], f"{f['cadence_s']:g} s")))
        + (" (timing-suspect)" if f["suspect"] else "")
        for f in row["listed"]
    ]
    return ", ".join(files) or "nothing"


def cmd_status(args) -> int:
    root = repo_root() / "results" / "predictions"
    run_id = args.package or _latest(root)
    package = root / run_id
    if not (package / "references.json").is_file():
        raise SystemExit(f"no predictions package {run_id} under results/predictions/")
    rules = load_criteria(args.criteria).values.get("fetch", {}).get("timing_suspect")
    # Without them a suspect file would read as one the test can use.
    if not rules:
        raise SystemExit(f"{args.criteria.name} has no [[fetch.timing_suspect]] rules")
    signals = predicted(package)
    tics = sorted({p["tic"] for p in signals.values()})
    failed: list[int] = []
    products = mast.discover(tics, failed=failed)
    rows = sector_rows(signals, products, rules, failed)
    print(f"package {run_id}\n")
    table = [
        [
            r["signal"],
            f"S{r['sector']}",
            _listed(r),
            f"{r['taken_product']}: {r['taken']}" if r["taken"] else "nothing",
            "usable" if r["usable"] else r["why"],
        ]
        for r in rows
    ]
    print(_table(["Signal", "Sector", "Listed at MAST", "Fetch takes", "The test"], table))
    print()
    for name, text in verdict(rows).items():
        print(f"{name}: {text}")
    redelivered = [
        [r["tic"], f"S{r['sector']}", r["version"], r["filename"], "yes" if r["suspect"] else "no"]
        for r in redelivery_rows(products, tics, rules)
    ]
    print("\nFiles in the sectors a timing-suspect rule covers, as MAST serves them now:")
    print(
        _table(["TIC", "Sector", "Version", "File", "Timing-suspect"], redelivered)
        if redelivered
        else "none listed"
    )
    if failed:
        print(f"\n{UNANSWERED} for TIC {', '.join(str(t) for t in failed)}; run status again")
        return 1
    return 0


def add_parser(modes) -> None:
    s = modes.add_parser(
        "status",
        help="what MAST lists for each sector a predictions package predicts, and whether its test can use it; "
        "writes nothing",
    )
    s.add_argument(
        "--package",
        help="a package's run id under results/predictions/; by default the one dois.toml lists as published last",
    )
    s.add_argument("--criteria", type=Path, default=Path("criteria/search-v2.toml"))
    s.set_defaults(func=cmd_status)
