"""Fetch: download each star's best light curve per sector and keep only what the search needs."""

import hashlib
import json
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

import lightkurve as lk
import numpy as np
import pandas as pd
import requests

from tess_hunt import mast
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import sha256_file, start_run


def _plain(column) -> np.ndarray:
    if hasattr(column, "filled"):
        column = column.filled(np.nan)
    return np.asarray(getattr(column, "value", column), dtype=float)


def read_product(path: Path, provenance: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Good cadences of one file as (time BTJD, flux, flux_err), normalised to median 1."""
    if provenance == "QLP":
        # lightkurve's default bitmask is SPOC's; QLP marks every bad cadence with a non-zero flag.
        lc = lk.read(path, quality_bitmask="none")
        good = _plain(lc["quality"]) == 0
    else:
        lc = lk.read(path, quality_bitmask="default")
        good = np.ones(len(lc), dtype=bool)
    time, flux, err = _plain(lc.time.value), _plain(lc.flux), _plain(lc.flux_err)
    good &= np.isfinite(time) & np.isfinite(flux) & np.isfinite(err) & (err > 0)
    time, flux, err = time[good], flux[good], err[good]
    facts = {
        k.lower(): float(lc.meta[k]) for k in ("CROWDSAP", "FLFRCSAP") if lc.meta.get(k) is not None
    }
    if len(flux) == 0:
        return time, flux, err, facts
    scale = np.median(flux)
    return time, flux / scale, err / scale, facts


def _manifest_sources(sources: dict) -> dict:
    # lc/<tic>.npz is overwritten by --refresh or a newly ranked product, so the run keeps its own copy.
    keys = ("provenance", "cadence_s", "s3_key", "sha256")
    return {sector: {k: info[k] for k in keys} for sector, info in sources.items()}


def fetch_star(
    tic: int,
    products: pd.DataFrame,
    out_dir: Path,
    min_good: int,
    session=None,
    refresh: bool = False,
) -> dict[str, Any]:
    """Write out_dir/<tic>.npz from the best usable product per sector. Failures are recorded per sector."""
    session = session or requests.Session()
    ranked = mast.rank(products[products["tic"] == tic])
    target = out_dir / f"{tic}.npz"
    if target.exists() and not refresh:
        existing = LightCurve.load(target)
        best_keys = set(ranked.drop_duplicates("sector")["s3_key"])
        if {v["s3_key"] for v in existing.sources.values()} == best_keys:
            return {
                "tic": tic,
                "status": "cached",
                "sectors": sorted(int(s) for s in existing.sources),
                "sources": _manifest_sources(existing.sources),
                "problems": {},
                "lc_sha256": sha256_file(target),
            }
    parts, sources, problems = [], {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        for sector, options in ranked.groupby("sector", sort=True):
            for row in options.itertuples():
                try:
                    blob = mast.download(row.s3_key, int(row.size), session)
                except mast.DownloadError as exc:
                    problems.setdefault(str(sector), []).append(f"{row.provenance}: {exc}")
                    continue
                path = Path(tmp) / row.filename
                path.write_bytes(blob)
                try:
                    time, flux, err, facts = read_product(path, row.provenance)
                except Exception as exc:
                    # Only the type: reader messages can carry the temp path into the manifest.
                    problems.setdefault(str(sector), []).append(
                        f"{row.provenance}: unreadable ({type(exc).__name__})"
                    )
                    continue
                if len(time) < min_good:
                    problems.setdefault(str(sector), []).append(
                        f"{row.provenance}: {len(time)} good cadences"
                    )
                    continue
                parts.append((time, flux, err, np.full(len(time), sector, dtype=np.int16)))
                sources[str(sector)] = {
                    "provenance": row.provenance,
                    "cadence_s": float(row.cadence_s),
                    "s3_key": row.s3_key,
                    "sha256": hashlib.sha256(blob).hexdigest(),
                    "n_good": int(len(time)),
                    **facts,
                }
                break
    if not parts:
        return {"tic": tic, "status": "empty", "sectors": [], "problems": problems}
    time, flux, err, sector = (np.concatenate(cols) for cols in zip(*parts, strict=True))
    order = np.argsort(time, kind="stable")
    LightCurve(tic, time[order], flux[order], err[order], sector[order], sources).save(target)
    return {
        "tic": tic,
        "status": "ok",
        "sectors": sorted(int(s) for s in sources),
        "sources": _manifest_sources(sources),
        "problems": problems,
        "lc_sha256": sha256_file(target),
    }


def _fetch_job(job: tuple) -> dict[str, Any]:
    tic, products, out_dir, min_good, refresh = job
    return fetch_star(tic, products, out_dir, min_good, refresh=refresh)


def add_parser(sub) -> None:
    p = sub.add_parser("fetch", help="download light curves for a targets table")
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument("--products", type=Path, help="products table from the targets run")
    p.add_argument("--criteria", type=Path, default=Path("criteria/search-v1.toml"))
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--refresh", action="store_true")
    p.add_argument("--production", action="store_true")
    p.set_defaults(func=cmd)


def cmd(args) -> int:
    criteria = load_criteria(args.criteria)
    run = start_run("fetch", [criteria], args.production, sys.argv)
    run.record_input("targets", args.targets)
    tics = [int(t) for t in pd.read_parquet(args.targets)["tic"]]
    if args.products:
        run.record_input("products", args.products)
        products = pd.read_parquet(args.products)
    else:
        products = mast.discover(tics)
        products.to_parquet(run.path / "products.parquet")
    out_dir = lc_dir()
    out_dir.mkdir(parents=True, exist_ok=True)
    min_good = criteria["fetch"]["min_good_cadences"]
    jobs = [(t, products[products["tic"] == t], out_dir, min_good, args.refresh) for t in tics]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        entries = list(pool.map(_fetch_job, jobs, chunksize=4))
    with open(run.path / "fetch_manifest.jsonl", "w") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    counts = pd.Series([e["status"] for e in entries]).value_counts().to_dict()
    run.finish(stars=len(entries), **{f"status_{k}": int(v) for k, v in counts.items()})
    print(f"fetch: {counts} -> {run.path}")
    return 0
