"""`tess-hunt revet`: the light curves a re-vet reads (decision 0041). Each keeps every sector as the earlier fetch
wrote it, adds the sectors only the new fetch has, and takes a changed old sector only when it replaces a
timing-suspect product. The earlier light curves are read, never written: every finished run keeps the file it
hashed."""

import hashlib
import io
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt import fetch
from tess_hunt.config import load_criteria
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file, start_run

# What merge.json says of each sector's product, enough to tell two products apart and find either again.
PRODUCT = ("provenance", "s3_key", "sha256", "timing_suspect")


def _product(info: dict | None) -> dict | None:
    return None if info is None else {k: info.get(k) for k in PRODUCT}


def _status(base: dict | None, fresh: dict | None) -> str:
    if base is None:
        return "added"
    if fresh is None or (base["s3_key"], base["sha256"]) == (fresh["s3_key"], fresh["sha256"]):
        return "kept"
    # A source written before fetch flagged timing can't show it was suspect, so a missing flag keeps the old file. Only
    # the same product delivered again replaces it: another product over a suspect sector (TESS-SPOC reaching past S85
    # over a QLP one) is a better product appearing later, which decision 0041 does not take.
    if (
        base.get("timing_suspect") is True
        and fresh.get("timing_suspect") is False
        and base.get("provenance") == fresh.get("provenance")
    ):
        return "redelivered"
    return "kept_m2"


def merge(base: LightCurve, fresh: LightCurve) -> tuple[LightCurve, dict]:
    """`base` with the sectors only `fresh` has added, and a sector of both taken from `fresh` only when it is the
    same product delivered again, replacing a timing-suspect file with one that is not. The record gives each
    sector's status (`kept`, `added`, `redelivered`, or `kept_m2` when `fresh` had another file and it was not taken)
    and both products."""
    parts, sources, record = [], {}, {}
    for key in sorted(base.sources.keys() | fresh.sources.keys(), key=int):
        old, new = base.sources.get(key), fresh.sources.get(key)
        status = _status(old, new)
        lc = fresh if status in ("added", "redelivered") else base
        parts.append(lc.select(lc.sector == int(key)))
        sources[key] = lc.sources[key]
        record[key] = {"status": status, "base": _product(old), "fresh": _product(new)}
    time, flux, err, sector = (
        np.concatenate([getattr(p, name) for p in parts])
        for name in ("time", "flux", "flux_err", "sector")
    )
    order = np.argsort(time, kind="stable")
    merged = LightCurve(base.tic, time[order], flux[order], err[order], sector[order], sources)
    return merged, record


def _revet_star(
    tic: int,
    products: pd.DataFrame,
    base: Path,
    recorded: str,
    out_dir: Path,
    cfg_fetch: dict,
    session,
) -> dict:
    # The merge reads the bytes the run recorded as its input, read once before the fetch: a base rewritten while
    # the run fetched would otherwise be merged unrecorded.
    blob = base.read_bytes()
    if hashlib.sha256(blob).hexdigest() != recorded:
        raise SystemExit(
            f"the light curve for TIC {tic} in --base-lc-dir changed after this run recorded it; a re-vet merges "
            "onto the file the run records"
        )
    old = LightCurve.load(io.BytesIO(blob))
    record = {"base_sha256": recorded, "lc_sha256": None, "sectors": None}
    with tempfile.TemporaryDirectory() as tmp:
        entry = fetch.fetch_star(tic, products, Path(tmp), cfg_fetch, session=session)
        fresh = LightCurve.load(Path(tmp) / f"{tic}.npz") if entry["status"] == "ok" else None
    got = fresh.sources if fresh is not None else {}
    record["fetch"] = {"status": entry["status"], "problems": entry["problems"]}
    record["unfetched"] = sorted((s for s in entry["problems"] if s not in got), key=int)
    # Nothing fetched is no re-vet: the old light curve alone would read as one with no new data.
    if fresh is None:
        return record
    merged, record["sectors"] = merge(old, fresh)
    # Nor is a fetch that brought no sector the merge takes: the merged file would be the old one again.
    if not any(s["status"] in ("added", "redelivered") for s in record["sectors"].values()):
        return record
    target = out_dir / f"{tic}.npz"
    merged.save(target)
    record["lc_sha256"] = sha256_file(target)
    return record


def cmd_fetch(args) -> int:
    if args.production:
        fetch._require_finished_targets(args.targets)
    criteria = load_criteria(args.criteria)
    # Without them every fresh product reads as clean, and a suspect product delivered again as a redelivery.
    if not criteria["fetch"].get("timing_suspect"):
        raise SystemExit(
            f"{args.criteria.name} has no [[fetch.timing_suspect]] rules: a re-vet takes an old sector only when a "
            "timing-suspect product is delivered again clean (decision 0041)"
        )
    tics = [int(t) for t in pd.read_parquet(args.targets)["tic"]]
    # Checked before the run starts, so a refusal leaves no unfinished run directory.
    no_base = [str(t) for t in tics if not (args.base_lc_dir / f"{t}.npz").is_file()]
    if no_base:
        raise SystemExit(
            f"no light curve for TIC {', '.join(no_base)} in --base-lc-dir; a re-vet keeps the earlier one"
        )
    products = pd.read_parquet(args.products)
    run = start_run("revet-fetch", [criteria], args.production, sys.argv)
    run.record_input("targets", args.targets)
    run.record_input("products", args.products)
    for tic in tics:
        run.record_input(f"base_light_curve_{tic}", args.base_lc_dir / f"{tic}.npz")
    session = requests.Session()
    stars = {
        str(tic): _revet_star(
            tic,
            products,
            args.base_lc_dir / f"{tic}.npz",
            run.provenance["inputs"][f"base_light_curve_{tic}"]["sha256"],
            run.path / "lc",
            criteria["fetch"],
            session,
        )
        for tic in tics
    }
    run.write_json("merge.json", stars)
    failed = [int(t) for t, r in stars.items() if r["lc_sha256"] is None]
    run.finish(stars=len(stars), failed=failed)
    for tic in failed:
        missed = ", ".join(f"S{s}" for s in stars[str(tic)]["unfetched"]) or "none"
        print(
            f"TIC {tic}: no sector added or redelivered, so no light curve; sectors fetched with problems and no "
            f"file: {missed}"
        )
    print(
        f"revet fetch: {len(stars) - len(failed)} merged, {len(failed)} with nothing new -> {run.path}"
    )
    return 1 if failed else 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "revet", help="light curves for a re-vet, keeping the earlier fetch's sectors"
    )
    modes = p.add_subparsers(dest="mode", required=True)
    f = modes.add_parser(
        "fetch",
        help="fetch each star again and merge it with its earlier light curve into this run's lc/",
    )
    f.add_argument("--targets", type=Path, required=True, help="a targets run's targets table")
    f.add_argument("--products", type=Path, required=True, help="products table from that run")
    f.add_argument(
        "--base-lc-dir",
        type=Path,
        required=True,
        help="the light curves the earlier runs read, <tic>.npz each; never written",
    )
    f.add_argument("--criteria", type=Path, default=Path("criteria/search-v2.toml"))
    f.add_argument("--production", action="store_true")
    f.set_defaults(func=cmd_fetch)
