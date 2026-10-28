"""`tess-hunt vetting`: vet-v3 on a list of signals, one directory each, with the evidence the
dossier reads beside the checks (M3 design, sections 4.2 to 4.7)."""

import contextlib
import datetime as dt
import json
import os
import re
import shutil
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt import (
    calls,
    dossier,
    gaia,
    literature,
    neighbours,
    plots,
    predict,
    secondlist,
    tricera,
)
from tess_hunt.catalogs import load_known, snapshot_inputs
from tess_hunt.checks import inconclusive
from tess_hunt.checks.families import split
from tess_hunt.config import Criteria, data_dir, lc_dir, load_criteria, runs_dir
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import (
    Ephemeris,
    ephemeris_match,
    epoch_numbers,
    phase_days,
    transit_times_in_data,
)
from tess_hunt.fit import FitResult
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pool import run_jobs
from tess_hunt.provenance import repo_root, scrub, sha256_file, start_run, unname
from tess_hunt.serialize import jsonable
from tess_hunt.threshold import _searched, check_leo_code, load_v2_catalog
from tess_hunt.transit import a_rs_from_density
from tess_hunt.triage import _pixel_job
from tess_hunt.vet import prepare, vet_with_fits

KINDS = ("candidate", "second", "control", "negative_control")
SIGNAL_COLUMNS = ["name", "tic", "period", "t0", "duration", "depth", "kind"]
# LEO-Vetter's ModShift fields in triage's evidence: the secondary at any phase (M3 design 4.2).
MODSHIFT = (
    "sig_pri",
    "sig_sec",
    "sig_ter",
    "sig_pos",
    "phs_pri",
    "phs_sec",
    "phs_ter",
    "phs_pos",
    "dep_sec",
    "err_sec",
    "Fred",
)
# A signal's name is its directory's name.
SAFE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
CONTRAST_COLUMNS = ["tic", "file", "filt", "source_url"]
DR3_VALUES = ("dr3_source_id", "ruwe")
# Our code around LEO-Vetter's pixel test: the second list runs it only as the triage run did.
PIXEL_WRAPPER = "src/tess_hunt/pixels.py"


def _number(value) -> float:
    # Targets rows carry pd.NA for a missing value, which float() refuses.
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _plain(row: dict) -> dict:
    """A targets row as JSON takes it: pd.NA as None."""
    return {k: None if v is pd.NA else v for k, v in row.items()}


def _source_id(star: dict) -> int | None:
    # None for a star neither its targets row nor the DR3 join gave one (`_join_dr3`).
    value = star.get("dr3_source_id")
    return None if value is None or pd.isna(value) else int(value)


def _known(value) -> bool:
    return value is not None and not pd.isna(value)


def fit_duration(fit: FitResult) -> float:
    """The posterior median of the full transit duration, first to fourth contact, for a circular
    orbit (Winn 2010, eq. 14)."""
    period, rp_rs, b = fit.column("period"), fit.column("rp_rs"), fit.column("b")
    a_rs = np.array(
        [
            a_rs_from_density(10.0**log_rho, p)
            for log_rho, p in zip(fit.column("log_rho"), period, strict=True)
        ]
    )
    sin_i = np.sqrt(1.0 - (b / a_rs) ** 2)
    chord = np.sqrt(np.clip((1.0 + rp_rs) ** 2 - b**2, 0.0, None))
    t14 = period / np.pi * np.arcsin(np.clip(chord / (a_rs * sin_i), 0.0, 1.0))
    return float(np.median(t14))


def _neighbours(star: dict, depth: float, cfg: dict) -> tuple[dict, pd.DataFrame | None]:
    tmag, source_id = _number(star.get("tmag")), _source_id(star)
    try:
        cone = neighbours.gaia_cone(
            float(star["ra"]), float(star["dec"]), cfg["radius_arcmin"], source_id=source_id
        )
        table = neighbours.required_depths(cone, depth, tmag, source_id, cfg)
        error = None
    except neighbours.NeighbourError as exc:
        table, error = None, str(exc)
    result = neighbours.neighbour_check(table, error).to_dict()
    # The required depths scale from this depth and the separations run from this centre (decision 0034), so the
    # dossier must say which they were.
    centre = "TIC position, J2000" if source_id is None else f"Gaia DR3 {source_id}, J2016.0"
    result["evidence"].update(
        depth=depth,
        depth_from="the signals file",
        tmag=tmag,
        target_source_id=source_id,
        centre=centre,
    )
    return result, table


def _windows(job: dict, report: dict, fit_prior: FitResult | None) -> dict:
    if job["include_suspect"]:
        return {
            "upcoming_sectors": None,
            "windows": None,
            "window_duration": None,
            "windows_reason": "evidence-only run: windows come from the main vet's density-prior fit",
        }
    cfg, star = job["crit_vet"]["predict"], job["star"]
    upcoming = predict.upcoming_sectors(
        int(star["tic"]), float(star["ra"]), float(star["dec"]), cfg["first_sector"]
    )
    if fit_prior is None:
        return {
            "upcoming_sectors": upcoming,
            "windows": None,
            "window_duration": None,
            "windows_reason": f"no density-prior fit: {report['fit_prior_reason']}",
        }
    days = fit_duration(fit_prior)
    duration = (
        {"days": days, "from": "fit_prior"}
        if np.isfinite(days) and days > 0
        else {"days": job["eph"].duration, "from": "signal"}
    )
    return {
        "upcoming_sectors": upcoming,
        # A dated sector with no transit in it gets no row, so upcoming_sectors stays beside them.
        "windows": predict.windows(
            fit_prior.samples, job["sectors"], upcoming, duration["days"], cfg["sigma"]
        ),
        "window_duration": duration,
        "windows_reason": None,
    }


def _catalogued(known: pd.DataFrame, lc: LightCurve, checks: dict, job: dict) -> dict:
    """Every catalogued row on the star, with the transits of ours inside its mask window: under vet-v3 only the
    search's kinds are masked, so the dossier shows what the rest would have cut (M3 design, section 4.2)."""
    eph, crit_search, crit_vet = job["eph"], job["crit_search"], job["crit_vet"]
    detrend_cfg, match = crit_search["detrend"], crit_search["match"]
    width, fallback = detrend_cfg["known_mask_width"], detrend_cfg["fallback_duration_days"]
    harmonics = tuple(crit_vet["novelty"]["harmonics"])
    seen = lc.select(~np.isin(lc.sector, checks["dropped_suspect"]))
    centres = transit_times_in_data(seen.time, eph)
    ours = epoch_numbers(centres, eph)
    rows = []
    for r in known[known["tic"] == int(job["star"]["tic"])].to_dict("records"):
        period, t0, duration = (_number(r[k]) for k in ("period", "t0", "duration"))
        has_period = np.isfinite(period) and period > 0
        duration = duration if np.isfinite(duration) and duration > 0 else fallback
        # Matched on period alone, as vet's masks match (vet.other_known_transits).
        matches = has_period and (
            ephemeris_match(
                eph,
                Ephemeris(period, float("nan"), duration),
                harmonics,
                match["sigma_p"],
                match["sigma_t"],
            )
            is not None
        )
        overlaps = None
        if has_period and np.isfinite(t0):
            gap = np.abs(phase_days(centres, Ephemeris(period, t0, duration)))
            overlaps = ours[gap < 0.5 * (width * duration + eph.duration)].tolist()
        rows.append(
            {
                **{k: r[k] for k in ("source", "kind", "name", "period", "t0", "duration")},
                "masked": bool(
                    overlaps is not None
                    and r["source"] in crit_vet["masks"]["sources"]
                    and not matches
                ),
                "matches_signal": bool(matches),
                "overlaps": overlaps,
            }
        )
    return {
        "transits": ours.tolist(),
        "mask_width_durations": width,
        "fallback_duration_days": fallback,
        "rows": rows,
    }


def _plots(lc: LightCurve, checks: dict, job: dict, path: Path) -> dict[str, str]:
    """Each plot drawn into `path`, and the error of each one that raised: a plot that fails leaves the vet standing,
    and the dossier names it where the plot would be."""
    crit_search, crit_vet, eph = job["crit_search"], job["crit_vet"], job["eph"]
    # The light curve the checks saw: without the sectors vet dropped, detrended around the rows it
    # masked.
    seen = lc.select(~np.isin(lc.sector, checks["dropped_suspect"]))
    flat = detrend(seen, crit_search["detrend"], [Ephemeris(**m) for m in checks["masked"]])
    pixels = checks["pixels"]["evidence"] if checks["pixels"] else None
    gap = crit_vet["holdout"]["season_gap_days"]
    draw = {
        "transits.png": lambda out: plots.transits(flat, eph, out),
        "folds.png": lambda out: plots.folds(flat, eph, crit_vet["families"], out, gap),
        "odd_even.png": lambda out: plots.odd_even(flat, eph, out),
        "phase.png": lambda out: plots.phase(flat, eph, checks["modshift"], out),
        "centroids.png": lambda out: plots.centroids(
            pixels, checks["neighbours"], out, job["pixel_limit"]
        ),
    }
    failed = {}
    for name, plot in draw.items():
        try:
            plot(path / name)
        except Exception as exc:
            failed[name] = scrub(f"raised {type(exc).__name__}: {exc}")
            # A file half written would read as the plot.
            (path / name).unlink(missing_ok=True)
    return failed


def _vet(job: dict) -> dict:
    crit_vet, eph, star, out = job["crit_vet"], job["eph"], job["star"], job["out"]
    lc = LightCurve.load(job["lc"])
    known = load_known(job["catalogs"])
    report, fit, fit_prior = vet_with_fits(
        lc,
        star,
        eph,
        known,
        job["crit_search"],
        crit_vet,
        crit_vet["fit"]["seed"],
        job["include_suspect"],
    )
    found, table = _neighbours(star, eph.depth, crit_vet["neighbours"])
    checks = {
        **report,
        "signal": {"name": job["name"], "kind": job["kind"]},
        "star": _plain(star),
        "sources": lc.sources,
        # Beside the checks, not among them: the neighbour table never fails (decision 0025).
        "neighbours": found,
        "catalogued": _catalogued(known, lc, report, job),
        **_windows(job, report, fit_prior),
        **job["triage"],
    }
    (out / "plots").mkdir(parents=True)
    if fit is not None:
        np.savez_compressed(out / "fit_samples.npz", samples=fit.samples)
    if fit_prior is not None:
        np.savez_compressed(out / "fit_prior_samples.npz", samples=fit_prior.samples)
    if table is not None:
        table.to_csv(out / "neighbours.csv", index=False)
    checks["plot_errors"] = _plots(lc, checks, job, out / "plots")
    # Written last: a directory with a checks.json holds everything the signal got.
    (out / "checks.json").write_text(json.dumps(jsonable(checks), indent=2, sort_keys=True) + "\n")
    windows = checks["windows"]
    return {
        "name": job["name"],
        "kind": job["kind"],
        "outcomes": {c["check"]: c["outcome"] for c in report["checks"]},
        "neighbours": found["outcome"],
        "windows": None if windows is None else sum("epoch" in w for w in windows),
        "plot_errors": checks["plot_errors"],
    }


def _vet_job(job: dict) -> dict:
    try:
        return _vet(job)
    except Exception as exc:
        # One signal's failure must not stop the others, nor leave a directory that reads as vetted.
        shutil.rmtree(job["out"], ignore_errors=True)
        return {"name": job["name"], "error": scrub(f"raised {type(exc).__name__}: {exc}")}


def _read_signals(path: Path) -> pd.DataFrame:
    table = pd.read_csv(path, dtype={"name": str, "kind": str})
    missing = [c for c in SIGNAL_COLUMNS if c not in table.columns]
    if missing:
        raise SystemExit(f"{path.name} has no column(s) {', '.join(missing)}")
    if table.empty:
        raise SystemExit(f"{path.name} lists no signals")
    table[["name", "kind"]] = table[["name", "kind"]].fillna("")
    unknown = sorted(set(table["kind"]) - set(KINDS))
    if unknown:
        raise SystemExit(f"{path.name}: unknown kind(s) {unknown}; kinds are {', '.join(KINDS)}")
    twice = sorted(set(table.loc[table["name"].duplicated(), "name"]))
    if twice:
        raise SystemExit(f"{path.name} lists signal names more than once: {', '.join(twice)}")
    unsafe = [n for n in table["name"] if not SAFE_NAME.fullmatch(n)]
    if unsafe:
        raise SystemExit(
            f"{path.name}: names are letters, digits, '.', '-' and '_', not {unsafe} "
            "(each is a directory)"
        )
    # A signal with no period or duration would reach vet and fail there, one job at a time.
    days = table[["period", "duration"]].apply(pd.to_numeric, errors="coerce")
    no_days = table.loc[~(np.isfinite(days) & (days > 0)).all(axis=1), "name"].tolist()
    if no_days:
        raise SystemExit(
            f"{path.name}: period and duration are positive numbers of days, not for {', '.join(no_days)}"
        )
    tic = pd.to_numeric(table["tic"], errors="coerce")
    no_tic = table.loc[~(np.isfinite(tic) & (tic == np.round(tic))), "name"].tolist()
    if no_tic:
        raise SystemExit(f"{path.name}: no TIC number for {', '.join(no_tic)}")
    # A BJD would fold the light curve at an epoch thousands of years away, and vet would run anyway.
    bjd = table.loc[~table["t0"].between(-20000, 10000, inclusive="neither"), "name"].tolist()
    if bjd:
        raise SystemExit(f"{path.name}: t0 is not a BTJD (BJD - 2457000) for {', '.join(bjd)}")
    return table


def _stars(signals: pd.DataFrame, targets: list[Path]) -> dict[int, dict]:
    """Each signal's targets row, from the first --targets file that lists its star."""
    tables = [pd.read_parquet(p) for p in targets]
    out = {}
    for tic in sorted({int(t) for t in signals["tic"]}):
        for table in tables:
            rows = table[table["tic"] == tic].to_dict("records")
            if rows:
                out[tic] = {**rows[0], "tic": tic}
                break
    missing = signals[~signals["tic"].isin(list(out))]
    if len(missing):
        listed = ", ".join(
            f"TIC {t} ({n})" for n, t in zip(missing["name"], missing["tic"], strict=True)
        )
        raise SystemExit(f"no targets file lists {listed}")
    return out


def _join_dr3(stars: dict[int, dict]) -> dict:
    """Ruling N: each star's Gaia DR3 source id and RUWE, from one `gaia.dr3_join` on the TIC's Gaia DR2 id for every
    star whose targets row lacks either (the control targets tables, made by `targets tics`, carry neither). Every
    row then holds both keys, None where nothing gave a value, and `dr3_from` says where they came from: `targets`;
    `dr3_join`, the join matched the star and both are its; or `missing`, the join failed or found no match and the
    row keeps what its targets row had. `dr3_reason` says why a value is None. A failed join is not fatal: those stars
    are judged without the values. Returns what the run's provenance records about the join."""
    need = sorted(t for t, s in stars.items() if not all(_known(s.get(k)) for k in DR3_VALUES))
    found, error = pd.DataFrame(columns=gaia.COLUMNS), None
    if need:
        try:
            found = gaia.dr3_join(
                pd.DataFrame([{"tic": t, "gaia": stars[t].get("gaia")} for t in need])
            )
        except gaia.GaiaError as exc:
            error = scrub(str(exc))
    found = found.set_index("tic")
    for tic, star in stars.items():
        star.update({k: star[k] if _known(star.get(k)) else None for k in DR3_VALUES})
        if tic not in need:
            star.update(dr3_from="targets", dr3_reason=None)
        elif tic in found.index:
            source_id, ruwe = int(found.loc[tic, "dr3_source_id"]), _number(found.loc[tic, "ruwe"])
            star.update(
                dr3_source_id=source_id,
                ruwe=ruwe if np.isfinite(ruwe) else None,
                dr3_from="dr3_join",
                dr3_reason=None if np.isfinite(ruwe) else f"Gaia DR3 {source_id} has no RUWE",
            )
        else:
            dr2 = str(star.get("gaia")).strip() if _known(star.get("gaia")) else ""
            if not dr2.isdigit():
                reason = "the TIC gives no Gaia DR2 id to join on"
            elif error is not None:
                reason = f"the Gaia DR3 join failed: {error}"
            else:
                reason = f"the Gaia DR3 join found no source for Gaia DR2 {dr2}"
            star.update(dr3_from="missing", dr3_reason=reason)
    return {"tics": need, "worked": error is None if need else None, "error": error}


def _no_triage(reason: str) -> dict:
    return {"modshift": None, "pixels": None, "other_signals": None, "triage_reason": reason}


def _triage(path: Path, signals: pd.DataFrame, crit_search: Criteria, production: bool) -> dict:
    """What a finished triage run holds for each signal in it, checked before the run starts."""
    provenance_file = path / "provenance.json"
    provenance = json.loads(provenance_file.read_text())
    run_id = path.resolve().name
    if provenance.get("stage") != "triage" or provenance.get("ended_at") is None:
        raise SystemExit(f"{run_id} is not a finished triage run")
    # The vetting run records the triage run by its directory's name.
    if provenance.get("run_id") != run_id:
        raise SystemExit(
            f"{run_id}'s provenance is run {provenance.get('run_id')}'s: a run directory keeps its run's name"
        )
    if production and not provenance.get("production"):
        raise SystemExit(
            f"{run_id} is not a production triage run; a production vetting run needs one"
        )
    ran_with = provenance.get("criteria")
    if not isinstance(ran_with, list) or len(ran_with) < 2:
        raise SystemExit(
            f"{run_id}'s provenance names no search and triage criteria; a triage run records both"
        )
    # Triage's ModShift and pixel evidence came from light curves detrended under its search
    # criteria; checks detrended otherwise would not sit beside them as one signal's evidence.
    searched = ran_with[0]
    if searched["sha256"] != crit_search.sha256:
        raise SystemExit(
            f"--criteria-search {crit_search.path.name} is not the {searched['file']} that "
            f"{run_id} ran with"
        )
    # Run directories sit side by side, so the search the triage run names is its sibling.
    search = provenance["search_run"]
    search_signals = path.resolve().parent / search / "signals.parquet"
    if not search_signals.is_file() or (
        sha256_file(search_signals) != provenance["inputs"]["search_signals"]["sha256"]
    ):
        raise SystemExit(f"{search}/signals.parquet is not the file {run_id} triaged")
    used = ran_with[1]
    criteria = repo_root() / used["file"]
    # The centroid plot draws the pixel check's limit as the triage run judged with it.
    if not criteria.is_file() or load_criteria(criteria).sha256 != used["sha256"]:
        raise SystemExit(f"{used['file']} changed since {run_id} ran; its pixel limit is unknown")
    limit = load_criteria(criteria)["pixels"]["max_offset_arcsec"]
    found = pd.read_parquet(search_signals)
    parts, files = {}, {}
    for s in signals.to_dict("records"):
        name, file = s["name"], path / "evidence" / f"{s['name']}.json"
        if not file.is_file():
            parts[name] = _no_triage(f"{name} is not in triage run {run_id}")
            continue
        item = json.loads(file.read_text())
        tic, rank = int(item["signal"]["tic"]), int(item["signal"]["rank"])
        if tic != int(s["tic"]):
            raise SystemExit(
                f"{run_id}'s evidence for {name} is for TIC {tic}, not TIC {int(s['tic'])}"
            )
        metrics = item["leo_flux"]["evidence"].get("metrics")
        pixels = item["pixels"]
        others = found[(found["tic"] == tic) & (found["rank"] != rank)]
        parts[name] = {
            "modshift": {k: metrics.get(k) for k in MODSHIFT} if metrics else None,
            "pixels": {
                "outcome": pixels["outcome"],
                "reason": pixels["reason"],
                "max_offset_arcsec": limit,
                "evidence": pixels.get("evidence"),
            },
            # The search's harmonic list can't show an eclipsing binary's pair at another ratio.
            "other_signals": [
                {
                    "rank": int(o["rank"]),
                    **{k: float(o[k]) for k in ("period", "t0", "duration", "depth", "sde")},
                    "period_ratio": float(o["period"]) / float(s["period"]),
                }
                for o in others.to_dict("records")
            ],
            "triage_reason": None if metrics else f"LEO-Vetter recorded no metrics in {run_id}",
        }
        files[name] = file
    return {
        "run_id": run_id,
        "search_run": search,
        "provenance": provenance_file,
        "search_signals": search_signals,
        "limit": limit,
        "parts": parts,
        "files": files,
    }


def cmd_run(args) -> int:
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Checked before the run starts, so a refusal leaves no unfinished run directory.
    if "families" not in crit_vet.values:
        raise SystemExit(
            f"{args.criteria_vet.name} has no [families]: `vetting run` vets under vet-v3 only"
        )
    load_v2_catalog(args.catalogs)
    signals = _read_signals(args.signals)
    stars = _stars(signals, args.targets)
    lcs = args.lc_dir or lc_dir()
    no_lc = [str(t) for t in stars if not (lcs / f"{t}.npz").exists()]
    if no_lc:
        raise SystemExit(f"no light curve for TIC {', '.join(no_lc)}; fetch first")
    triage = (
        _triage(args.triage_run, signals, crit_search, args.production) if args.triage_run else None
    )
    sectors_file = crit_vet["predict"]["sectors_file"]
    sectors = predict.load_sectors(sectors_file)
    joined = _join_dr3(stars)
    if joined["error"] is not None:
        print(
            f"Gaia DR3 join failed for TIC {', '.join(map(str, joined['tics']))}: {joined['error']}"
        )
    # The later vetting stages read the vet criteria back from criteria[1] and refuse any other: one
    # run, one criteria file.
    run = start_run("vetting-run", [crit_search, crit_vet], args.production, sys.argv)
    run.record("dr3_join", joined)
    run.record("evidence_only", args.include_suspect)
    run.record("triage_run", triage["run_id"] if triage else None)
    run.record("search_run", triage["search_run"] if triage else None)
    run.record("catalogs", args.catalogs.resolve().name)
    # Later stages read the light curves from here (decision 0041); argv is scrubbed and names no run by its role.
    run.record("lc_dir", scrub(str(lcs.resolve())))
    run.record("revet_run", _revet_run(lcs))
    run.record_input("signals", args.signals)
    for i, path in enumerate(args.targets, 1):
        run.record_input(f"targets_{i}", path)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    for tic in sorted(stars):
        run.record_input(f"light_curve_{tic}", lcs / f"{tic}.npz")
    run.record_input("tess_sectors", repo_root() / sectors_file)
    if triage:
        run.record_input("triage_provenance", triage["provenance"])
        run.record_input("search_signals", triage["search_signals"])
        for name, file in triage["files"].items():
            run.record_input(f"triage_evidence_{name}", file)
    jobs = [
        {
            "name": s["name"],
            "kind": s["kind"],
            "eph": Ephemeris(
                float(s["period"]), float(s["t0"]), float(s["duration"]), float(s["depth"])
            ),
            "star": stars[int(s["tic"])],
            "lc": lcs / f"{int(s['tic'])}.npz",
            "catalogs": args.catalogs,
            "crit_search": crit_search.values,
            "crit_vet": crit_vet.values,
            "include_suspect": args.include_suspect,
            "sectors": sectors,
            "triage": triage["parts"][s["name"]] if triage else _no_triage("no --triage-run given"),
            "pixel_limit": triage["limit"] if triage else None,
            "out": run.path / "signals" / s["name"],
        }
        for s in signals.to_dict("records")
    ]
    results = run_jobs(_vet_job, jobs, args.workers)
    vetted = {
        r["name"]: {k: v for k, v in r.items() if k != "name"} for r in results if "error" not in r
    }
    errors = {r["name"]: r["error"] for r in results if "error" in r}
    for name, r in vetted.items():
        outcomes = ", ".join(f"{c} {o}" for c, o in r["outcomes"].items())
        print(
            f"{name} ({r['kind']}): {outcomes}; neighbours {r['neighbours']}; windows {r['windows']}"
        )
        for plot, error in r["plot_errors"].items():
            print(f"{name}: {plot} not drawn, {error}")
    for name, error in errors.items():
        print(f"{name}: {error}")
    run.finish(evidence_only=args.include_suspect, signals=vetted, errors=errors)
    label = " (evidence only)" if args.include_suspect else ""
    print(f"vetting run{label}: {len(vetted)} vetted, {len(errors)} failed -> {run.path}")
    return 1 if errors else 0


def _revet_run(lcs: Path) -> str | None:
    """The revet fetch run whose lc/ directory `lcs` is, or None."""
    made = lcs.resolve().parent / "provenance.json"
    if lcs.resolve().name != "lc" or not made.is_file():
        return None
    return (
        lcs.resolve().parent.name
        if json.loads(made.read_text()).get("stage") == "revet-fetch"
        else None
    )


def _light_curves(provenance: dict) -> Path:
    """Where a vetting run read its light curves. A run made before decision 0041 recorded none and read the shared
    cache."""
    recorded = provenance.get("lc_dir")
    if recorded is None:
        return lc_dir()
    return Path(recorded.replace("$TESS_HUNT_DATA", str(data_dir()), 1)).expanduser()


def _vetting_run(path: Path, crit_search: Criteria, crit_vet: Criteria, production: bool) -> dict:
    """A finished vetting run's provenance, checked against what this stage runs with: one run, one criteria file
    (Ruling C)."""
    provenance_file = path / "provenance.json"
    run_id = path.resolve().name
    if not provenance_file.is_file():
        raise SystemExit(f"{run_id} is not a run directory")
    provenance = json.loads(provenance_file.read_text())
    if provenance.get("stage") != "vetting-run" or provenance.get("ended_at") is None:
        raise SystemExit(f"{run_id} is not a finished vetting run")
    # It keeps the timing-suspect sectors in and never makes a call (decision 0022).
    if provenance.get("evidence_only"):
        raise SystemExit(
            f"{run_id} is an evidence-only vetting run; later stages read the main one"
        )
    if production and not provenance.get("production"):
        raise SystemExit(f"{run_id} is not a production vetting run; a production run needs one")
    _same_criteria(run_id, provenance, crit_search, crit_vet)
    return provenance


def _same_criteria(
    run_id: str, provenance: dict, crit_search: Criteria, crit_vet: Criteria
) -> None:
    for flag, given, used in (
        ("--criteria-search", crit_search, provenance["criteria"][0]),
        ("--criteria-vet", crit_vet, provenance["criteria"][1]),
    ):
        if given.sha256 != used["sha256"]:
            raise SystemExit(
                f"{flag} {given.path.name} is not the {used['file']} that {run_id} ran with"
            )


def _vetted(path: Path, names: list[str] | None) -> dict[str, dict]:
    """Each named signal's checks.json, or without names, those of every signal no check failed (M3 design,
    section 4.1)."""
    run_id = path.resolve().name
    signals = path / "signals"
    found = {
        p.name: json.loads((p / "checks.json").read_text())
        for p in (sorted(signals.iterdir()) if signals.is_dir() else [])
        if (p / "checks.json").is_file()
    }
    if names:
        unknown = [n for n in names if n not in found]
        if unknown:
            raise SystemExit(f"{run_id} vetted no {', '.join(unknown)}")
        return {n: found[n] for n in names}
    chosen = {n: c for n, c in found.items() if all(x["outcome"] != "fail" for x in c["checks"])}
    if not chosen:
        raise SystemExit(f"every signal {run_id} vetted failed a check; name one with --signals")
    return chosen


def _contrast(path: Path) -> list[dict]:
    """The contrast curves the CSV lists, each read and converted (Ruling K); any it can't read refuses the run."""
    table = pd.read_csv(path, dtype=str).fillna("")
    missing = [c for c in CONTRAST_COLUMNS if c not in table.columns]
    if missing:
        raise SystemExit(f"{path.name} has no column(s) {', '.join(missing)}")
    rows = []
    for i, r in enumerate(table.to_dict("records"), 1):
        if not r["tic"].isdigit():
            raise SystemExit(f"{path.name} row {i}: TIC {r['tic']!r} is not a number")
        if r["filt"] not in tricera.FILTERS:
            raise SystemExit(
                f"{path.name} row {i}: filter {r['filt']!r} is not one of {', '.join(tricera.FILTERS)}"
            )
        # Files sit beside the CSV unless it gives a full path.
        file = path.parent / r["file"]
        if not file.is_file():
            raise SystemExit(f"{path.name} row {i}: no file {r['file']}")
        try:
            curve, info = tricera.read_contrast(file)
        except tricera.ContrastError as exc:
            raise SystemExit(f"{path.name} row {i}: {exc}") from None
        rows.append(
            {**r, "row": i, "tic": int(r["tic"]), "file": file, "curve": curve, "info": info}
        )
    return rows


def _fold_ephemeris(checks: dict) -> tuple[Ephemeris, dict]:
    """The density-prior fit's ephemeris and duration (M3 design, section 4.5), or the signal's without that fit.
    The depth is the one the neighbour table scaled from, so its possible hosts and TRICERATOPS's tdepth compare."""
    depth = _number(checks["neighbours"]["evidence"].get("depth"))
    prior, duration = checks.get("fit_prior"), checks.get("window_duration")
    if prior is not None and duration is not None:
        e = prior["ephemeris"]
        return Ephemeris(e["period"]["median"], e["t0"]["median"], duration["days"], depth), {
            "ephemeris": "fit_prior",
            "duration": duration["from"],
        }
    signal = checks["ephemeris"]
    return Ephemeris(signal["period"], signal["t0"], signal["duration"], depth), {
        "ephemeris": "signal",
        "duration": "signal",
    }


def _triceratops(job: dict) -> dict:
    checks = json.loads(job["checks"].read_text())
    lc = LightCurve.load(job["lc"])
    # The light curve vet's checks saw, rebuilt from its record as the plots rebuild it, then the family both
    # fits use: QLP publishes no pixel aperture (pin P3).
    seen = lc.select(~np.isin(lc.sector, checks["dropped_suspect"]))
    flat = detrend(seen, job["detrend"], [Ephemeris(**m) for m in checks["masked"]])
    families = job["families"]
    none = flat.select(np.zeros(len(flat.time), dtype=bool))
    pdcsap = split(flat, families).get(families["fit"], none)
    eph, eph_from = _fold_ephemeris(checks)
    table = pd.DataFrame(checks["neighbours"]["evidence"].get("table") or [])
    possible = table[table["possible"].astype(bool)] if len(table) else table
    out = job["out"]
    out.mkdir(parents=True)
    curves = [(c["path"], c["filt"]) for c in job["contrast"]]
    # TRICERATOPS writes its Gaia field-star file to the working directory and reads it back in calc_probs.
    with contextlib.chdir(out):
        result = tricera.check(
            pdcsap, checks["star"], eph, checks, possible, job["cfg"], curves
        ).to_dict()
    probs = result["evidence"].pop("probs", None)
    if probs:
        pd.DataFrame(probs).to_csv(out / "probs.csv", index=False)
    record = {
        "signal": {"name": job["name"], "tic": job["tic"]},
        "vetting_run": job["vetting_run"],
        "ephemeris_from": eph_from,
        "contrast": [{k: v for k, v in c.items() if k != "path"} for c in job["contrast"]],
        **result,
    }
    # Written last: a directory with a triceratops.json holds everything the signal got.
    (out / "triceratops.json").write_text(
        json.dumps(jsonable(record), indent=2, sort_keys=True) + "\n"
    )
    evidence = result["evidence"]
    return {
        "name": job["name"],
        "outcome": result["outcome"],
        "reason": result["reason"],
        "fpp_mean": evidence["fpp_mean"],
        "nfpp_mean": evidence["nfpp_mean"],
    }


def _triceratops_job(job: dict) -> dict:
    try:
        return _triceratops(job)
    except Exception as exc:
        # One signal's failure must not stop the others, nor leave a directory that reads as judged.
        shutil.rmtree(job["out"], ignore_errors=True)
        return {"name": job["name"], "error": scrub(f"raised {type(exc).__name__}: {exc}")}


def cmd_triceratops(args) -> int:
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Checked before the run starts, so a refusal leaves no unfinished run directory.
    if "triceratops" not in crit_vet.values:
        raise SystemExit(f"{args.criteria_vet.name} has no [triceratops]")
    provenance = _vetting_run(args.run, crit_search, crit_vet, args.production)
    run_id = args.run.resolve().name
    vetted = _vetted(args.run, args.signals)
    tics = sorted({int(c["star"]["tic"]) for c in vetted.values()})
    lcs = _light_curves(provenance)
    for tic in tics:
        path = lcs / f"{tic}.npz"
        recorded = provenance["inputs"].get(f"light_curve_{tic}", {}).get("sha256")
        if not path.is_file() or sha256_file(path) != recorded:
            raise SystemExit(f"the light curve for TIC {tic} changed since {run_id} vetted it")
    contrast = _contrast(args.contrast) if args.contrast else []
    run = start_run("vetting-triceratops", [crit_search, crit_vet], args.production, sys.argv)
    run.record("vetting_run", run_id)
    run.record_input("vetting_provenance", args.run / "provenance.json")
    for name in vetted:
        run.record_input(f"checks_{name}", args.run / "signals" / name / "checks.json")
    for tic in tics:
        run.record_input(f"light_curve_{tic}", lcs / f"{tic}.npz")
    curves = []
    if args.contrast:
        run.record_input("contrast", args.contrast)
        (run.path / "contrast").mkdir()
    for c in contrast:
        run.record_input(f"contrast_{c['row']}", c["file"])
        # TRICERATOPS reads it from the signal's directory, so the path must not depend on that.
        converted = (run.path / "contrast" / f"{c['row']}-{c['file'].stem}.csv").resolve()
        tricera.write_contrast(c["curve"], converted)
        curves.append(
            {
                "tic": c["tic"],
                "path": converted,
                "file": c["file"].name,
                "sha256": sha256_file(c["file"]),
                "converted": converted.name,
                "converted_sha256": sha256_file(converted),
                "filt": c["filt"],
                "source_url": c["source_url"],
                **c["info"],
            }
        )
    jobs = [
        {
            "name": name,
            "tic": int(checks["star"]["tic"]),
            "vetting_run": run_id,
            "checks": args.run / "signals" / name / "checks.json",
            "lc": lcs / f"{int(checks['star']['tic'])}.npz",
            "detrend": crit_search["detrend"],
            "families": crit_vet["families"],
            "cfg": crit_vet["triceratops"],
            "contrast": [c for c in curves if c["tic"] == int(checks["star"]["tic"])],
            "out": (run.path / "signals" / name).resolve(),
        }
        for name, checks in vetted.items()
    ]
    results = run_jobs(_triceratops_job, jobs, args.workers)
    judged = {
        r["name"]: {k: v for k, v in r.items() if k != "name"} for r in results if "error" not in r
    }
    errors = {r["name"]: r["error"] for r in results if "error" in r}
    for name, r in judged.items():
        print(f"{name}: {r['outcome']}, {r['reason']}")
    for name, error in errors.items():
        print(f"{name}: {error}")
    run.finish(vetting_run=run_id, signals=judged, errors=errors)
    print(f"vetting triceratops: {len(judged)} judged, {len(errors)} failed -> {run.path}")
    return 1 if errors else 0


def _earlier_literature(
    path: Path, crit_search: Criteria, crit_vet: Criteria, production: bool
) -> dict[int, tuple[str, Path]]:
    """A finished literature run's record for each star it searched, each checked against the sha256 the run
    recorded for it."""
    provenance_file = path / "provenance.json"
    run_id = path.resolve().name
    provenance = json.loads(provenance_file.read_text()) if provenance_file.is_file() else {}
    if provenance.get("stage") != "vetting-literature" or provenance.get("ended_at") is None:
        raise SystemExit(f"{run_id} is not a finished literature run")
    if production and not provenance.get("production"):
        raise SystemExit(
            f"{run_id} is not a production literature run; a production run resumes only from one"
        )
    _same_criteria(run_id, provenance, crit_search, crit_vet)
    out = {}
    for name, item in sorted(provenance["summary"]["signals"].items()):
        file = path / "signals" / name / "literature.json"
        if not file.is_file() or sha256_file(file) != item["sha256"]:
            raise SystemExit(f"{run_id}'s {name}/literature.json is not the file it wrote")
        out.setdefault(int(item["tic"]), (name, file))
    return out


def _kept(sources: dict, run_id: str) -> dict:
    """The searches an earlier run got an answer to, each marked with the run that made it."""
    return {
        source: {
            name: {**r, "from_run": r.get("from_run", run_id)}
            for name, r in results.items()
            if r["status"] in literature.ANSWERED
        }
        for source, results in sources.items()
    }


def cmd_literature(args) -> int:
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Checked before the run starts, so a refusal leaves no unfinished run directory.
    if "literature" not in crit_vet.values:
        raise SystemExit(f"{args.criteria_vet.name} has no [literature]")
    _vetting_run(args.run, crit_search, crit_vet, args.production)
    run_id = args.run.resolve().name
    vetted = _vetted(args.run, args.signals)
    earlier = (
        _earlier_literature(args.resume_from, crit_search, crit_vet, args.production)
        if args.resume_from
        else {}
    )
    # Read here and only passed down: the token never reaches a record, the provenance or a log line.
    token = os.environ.get("ADS_API_TOKEN") or None
    run = start_run("vetting-literature", [crit_search, crit_vet], args.production, sys.argv)
    run.record("vetting_run", run_id)
    run.record("ads_searched", token is not None)
    run.record("resumed_from", args.resume_from.resolve().name if args.resume_from else None)
    run.record_input("vetting_provenance", args.run / "provenance.json")
    for name in vetted:
        run.record_input(f"checks_{name}", args.run / "signals" / name / "checks.json")
    stars: dict[int, list[str]] = {}
    for name, checks in vetted.items():
        stars.setdefault(int(checks["star"]["tic"]), []).append(name)
    cfg = crit_vet["literature"]
    session = requests.Session()
    done = {}
    # One star at a time: arXiv's pace and OpenAlex's daily cap hold per client.
    for tic, names in sorted(stars.items()):
        kept = {}
        if tic in earlier:
            resumed, file = earlier[tic]
            run.record_input(f"resume_{resumed}", file)
            kept = _kept(
                json.loads(file.read_text())["search"]["sources"], args.resume_from.resolve().name
            )
        simbad = literature.simbad_record(tic, session)
        searched = literature.searchable(simbad["names"], vetted[names[0]]["star"], cfg["forms"])
        search = {
            "simbad": simbad,
            **literature.search_all(tic, searched, session, token, cfg, kept, simbad=simbad),
        }
        check = literature.literature_check(search).to_dict()
        for name in names:
            path = run.path / "signals" / name / "literature.json"
            path.parent.mkdir(parents=True)
            record = {"signal": {"name": name, "tic": tic}, "vetting_run": run_id, "search": search}
            path.write_text(
                json.dumps(jsonable({**record, **check}), indent=2, sort_keys=True) + "\n"
            )
            done[name] = {
                "tic": tic,
                "outcome": check["outcome"],
                "reason": check["reason"],
                # A later run that resumes from this one checks each record against it.
                "sha256": sha256_file(path),
            }
        print(f"TIC {tic} ({', '.join(searched)}): {check['outcome']}, {check['reason']}")
    run.finish(vetting_run=run_id, signals=done)
    passed = sum(r["outcome"] == "pass" for r in done.values())
    print(f"vetting literature: {passed} of {len(done)} searches complete -> {run.path}")
    return 0


def _literature_records(path: Path, production: bool) -> dict[str, Path]:
    """A finished literature run's record for each signal, each checked against the sha256 the run recorded."""
    made = _finished(path, "vetting-literature", "literature", production)
    run_id = path.resolve().name
    out = {}
    for name, item in sorted(made["summary"]["signals"].items()):
        file = path / "signals" / name / "literature.json"
        if not file.is_file() or sha256_file(file) != item["sha256"]:
            raise SystemExit(f"{run_id}'s {name}/literature.json is not the file it wrote")
        out[name] = file
    return out


def cmd_titles(args) -> int:
    """OpenAlex's title, by DOI, for each paper of a literature run that no open-source hit gives one (decision
    0038), so a published record's titles all come from open sources."""
    records = _literature_records(args.literature, args.production)
    dois = sorted(
        {d for f in records.values() for d in literature.to_look_up(json.loads(f.read_text()))}
    )
    run = start_run("vetting-titles", [], args.production, sys.argv)
    run.record("literature_run", args.literature.resolve().name)
    run.record_input("literature_provenance", args.literature / "provenance.json")
    for name, file in records.items():
        run.record_input(f"literature_{name}", file)
    session = requests.Session()
    titles = {}
    for doi in dois:
        titles[doi] = literature.openalex_title(session, doi)
        time.sleep(literature.LOOKUP_PAUSE_S)
    written = run.write_json(
        "titles.json", {"literature_run": run.provenance["literature_run"], "titles": titles}
    )
    counts = {
        s: sum(t["status"] == s for t in titles.values()) for s in ("ok", "not_found", "error")
    }
    with_title = sum(t["title"] is not None for t in titles.values())
    run.finish(
        literature_run=run.provenance["literature_run"],
        dois=len(titles),
        titled=with_title,
        # `vetting publish` checks the file it trims with against this.
        titles_sha256=sha256_file(written),
        **counts,
    )
    print(
        f"vetting titles: {with_title} of {len(titles)} DOIs titled, {counts['not_found']} not in OpenAlex, "
        f"{counts['error']} failed -> {run.path}"
    )
    return 1 if counts["error"] else 0


def _fetched(vetting: dict, package: dict, tic: int, run_id: str) -> dt.date | None:
    """When the light curve a vetting run read for `tic` was fetched, from the finished revet fetch run that wrote
    it; None for the light curve the package was made from. The code sees when data were fetched, not when they were
    public."""
    read = vetting["inputs"].get(f"light_curve_{tic}", {}).get("sha256")
    if read == package["inputs"].get(f"light_curve_{tic}", {}).get("sha256"):
        return None
    lc_run = runs_dir() / str(vetting.get("revet_run"))
    made = (
        json.loads((lc_run / "provenance.json").read_text())
        if vetting.get("revet_run") is not None and (lc_run / "provenance.json").is_file()
        else {}
    )
    if made.get("stage") != "revet-fetch" or made.get("ended_at") is None:
        raise SystemExit(
            f"{run_id} read a light curve for TIC {tic} that neither package {package['run_id']} read nor a finished "
            "revet fetch run made, so when it was fetched is unknown"
        )
    # The run's start dates only the bytes it wrote.
    star = json.loads((lc_run / "merge.json").read_text()).get(str(tic)) or {}
    if star.get("lc_sha256") != read:
        raise SystemExit(
            f"{run_id} read another light curve for TIC {tic} than revet fetch run {lc_run.name} made, so when it "
            "was fetched is unknown"
        )
    return dt.date.fromisoformat(made["started_at"][:10])


def cmd_prereg(args) -> int:
    """Decision 0040's test for each signal of a predictions package that a re-vet's vetting run vetted: its new season
    judged against the package's prediction and training depths, on the light curve the vetting run read."""
    # prereg imports this module.
    from tess_hunt import prereg

    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Every refusal comes before the run starts, so it leaves no unfinished run directory.
    provenance = _vetting_run(args.run, crit_search, crit_vet, args.production)
    run_id = args.run.resolve().name
    package = _finished(args.package, "predictions", "predictions", args.production)
    package_id = package["run_id"]
    if [c["sha256"] for c in package["criteria"]] != [c["sha256"] for c in provenance["criteria"]]:
        raise SystemExit(f"package {package_id} was made on other criteria than {run_id}")
    today = dt.datetime.now(dt.UTC).date()
    if args.as_of > today:
        raise SystemExit(
            f"--as-of {args.as_of} is after today ({today}): a season is judged on the data there are"
        )
    # Backdated, a result could stay pending past the judging date on a light curve read after it.
    started = dt.date.fromisoformat(provenance["started_at"][:10])
    if args.as_of < started:
        raise SystemExit(
            f"--as-of {args.as_of} is before the day {run_id} started ({started}): a season is judged as of when "
            "its light curve was read"
        )
    read = provenance["inputs"]
    for name, path in snapshot_inputs(args.catalogs).items():
        if not path.is_file() or sha256_file(path) != read.get(name, {}).get("sha256"):
            raise SystemExit(
                f"--catalogs {args.catalogs.name} is not the snapshot {run_id} vetted with ({path.name})"
            )
    predicted = json.loads((args.package / "references.json").read_text())["signals"]
    signals = args.run / "signals"
    vetted = {
        name: json.loads((signals / name / "checks.json").read_text())
        for name in sorted(predicted)
        if (signals / name / "checks.json").is_file()
    }
    if not vetted:
        raise SystemExit(f"{run_id} vetted none of the signals package {package_id} predicts")
    lcs = _light_curves(provenance)
    records = repo_root() / "results" / "vetting"
    # Decision 0040 judges a signal once and each later version carries that result, so a re-vet that vets a judged
    # signal beside others judges only the others.
    skipped = {}
    for name in list(vetted):
        judged = _judged(records / name)
        if judged is not None:
            result = json.loads((judged / "prereg.json").read_text())["result"]
            skipped[name] = f"judged in {judged.relative_to(records.parent.parent)} ({result})"
            del vetted[name]
    if not vetted:
        listed = "; ".join(f"{name} was {why}" for name, why in skipped.items())
        raise SystemExit(
            f"{run_id} leaves no signal to judge ({listed}): decision 0040 judges a signal once, and each later "
            "version carries that result"
        )
    fetched = {}
    for name, checks in vetted.items():
        tic = int(checks["tic"])
        if tic != predicted[name]["tic"]:
            raise SystemExit(
                f"{run_id} vetted {name} on TIC {tic}; package {package_id} predicts it on TIC {predicted[name]['tic']}"
            )
        path = lcs / f"{tic}.npz"
        recorded = read.get(f"light_curve_{tic}", {}).get("sha256")
        if not path.is_file() or sha256_file(path) != recorded:
            raise SystemExit(f"the light curve for TIC {tic} changed since {run_id} vetted it")
        fetched[name] = _fetched(provenance, package, tic, run_id)
    run = start_run("vetting-prereg", [crit_search, crit_vet], args.production, sys.argv)
    run.record("vetting_run", run_id)
    run.record("package", package_id)
    run.record("as_of", args.as_of.isoformat())
    run.record("skipped", skipped)
    run.record_input("vetting_provenance", args.run / "provenance.json")
    for file in ("provenance.json", "references.json", "predictions.csv"):
        run.record_input(f"package_{Path(file).stem}", args.package / file)
    for name, checks in vetted.items():
        run.record_input(f"checks_{name}", signals / name / "checks.json")
        run.record_input(f"light_curve_{checks['tic']}", lcs / f"{checks['tic']}.npz")
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    known = load_known(args.catalogs)
    done = {}
    for name, checks in vetted.items():
        tic = int(checks["tic"])
        # The light curve the vetting run's checks saw, prepared as vet prepared it.
        prepared = prepare(
            LightCurve.load(lcs / f"{tic}.npz"),
            checks["star"],
            Ephemeris(**checks["ephemeris"]),
            known,
            crit_search.values,
            crit_vet.values,
        )
        result = prereg.judge_signal(
            args.package, name, prepared, crit_vet.values, args.as_of, fetched=fetched[name]
        )
        path = run.path / "signals" / name / "prereg.json"
        path.parent.mkdir(parents=True)
        record = {
            "signal": {"name": name, "tic": tic},
            "vetting_run": run_id,
            "package": package_id,
            **result,
        }
        path.write_text(json.dumps(jsonable(record), indent=2, sort_keys=True) + "\n")
        done[name] = {
            "tic": tic,
            "result": result["result"],
            "status": result["status"],
            "sha256": sha256_file(path),
        }
        print(f"{name}: {result['result']} ({result['status']})")
    for name, why in skipped.items():
        print(f"{name}: skipped, {why}")
    run.finish(
        vetting_run=run_id,
        package=package_id,
        as_of=args.as_of.isoformat(),
        signals=done,
        skipped=skipped,
    )
    print(f"vetting prereg: {len(done)} signal(s), {len(skipped)} skipped -> {run.path}")
    return 0


def _second_triage(
    path: Path, provenance: dict, run_id: str, names: list[str], production: bool
) -> dict:
    """The triage run whose pixel check the second list runs as triage would have (M3 design, section 4.10): the one
    the vetting run read, unchanged, with the `[pixels]` criteria, pixel code and lock it ran with, and the targets and
    light curves it judged."""
    triage_id = path.resolve().name
    provenance_file = path / "provenance.json"
    made = json.loads(provenance_file.read_text()) if provenance_file.is_file() else {}
    if made.get("stage") != "triage" or made.get("ended_at") is None:
        raise SystemExit(f"{triage_id} is not a finished triage run")
    if production and not made.get("production"):
        raise SystemExit(
            f"{triage_id} is not a production triage run; a production second list needs one"
        )
    inputs = provenance["inputs"]
    if provenance.get("triage_run") != triage_id:
        raise SystemExit(
            f"{run_id} read triage run {provenance.get('triage_run')}, not {triage_id}"
        )
    if sha256_file(provenance_file) != inputs["triage_provenance"]["sha256"]:
        raise SystemExit(f"{triage_id}/provenance.json is not the file {run_id} read")
    used = made["criteria"][1]
    criteria = repo_root() / used["file"]
    if not criteria.is_file() or load_criteria(criteria).sha256 != used["sha256"]:
        raise SystemExit(f"{used['file']} changed since {triage_id} ran; its [pixels] are unknown")
    problems = check_leo_code(made, repo_root(), PIXEL_WRAPPER)
    if problems:
        raise SystemExit(f"the pixel check would not run as in {triage_id}: " + "; ".join(problems))
    # The pixel check takes the star's position from the targets row in checks.json. The vetting run must have read
    # the targets file triage judged with; it records no file per star, so a star an earlier --targets file also
    # lists would still take that file's row.
    read = {v["sha256"] for k, v in inputs.items() if k.startswith("targets_")}
    if made["inputs"]["targets"]["sha256"] not in read:
        raise SystemExit(f"{run_id} read none of the targets files {triage_id} judged with")
    evidence = {}
    for name in names:
        file = path / "evidence" / f"{name}.json"
        recorded = inputs.get(f"triage_evidence_{name}", {}).get("sha256")
        if recorded is None:
            raise SystemExit(
                f"{name} is not in triage run {triage_id}, so its LEO-Vetter metrics are unknown"
            )
        if not file.is_file() or sha256_file(file) != recorded:
            raise SystemExit(f"{triage_id}'s evidence for {name} is not the file {run_id} read")
        evidence[name] = file
    # Run directories sit side by side, so the search the triage run names is its sibling.
    stars = path.resolve().parent / made["search_run"] / "stars.parquet"
    if not stars.is_file() or sha256_file(stars) != made["inputs"]["search_stars"]["sha256"]:
        raise SystemExit(f"{made['search_run']}/stars.parquet is not the file {triage_id} read")
    return {
        "run_id": triage_id,
        "provenance": provenance_file,
        "criteria": criteria,
        "criteria_file": used["file"],
        "pixels": load_criteria(criteria)["pixels"],
        "evidence": evidence,
        "search_stars": stars,
    }


def cmd_second_list(args) -> int:
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Everything is checked before the run starts, so a refusal leaves no unfinished run directory.
    provenance = _vetting_run(args.run, crit_search, crit_vet, args.production)
    run_id = args.run.resolve().name
    signals = args.run / "signals"
    vetted = {
        p.name: json.loads((p / "checks.json").read_text())
        for p in (sorted(signals.iterdir()) if signals.is_dir() else [])
        if (p / "checks.json").is_file()
    }
    second = {name: c for name, c in vetted.items() if c["signal"]["kind"] == "second"}
    if not second:
        raise SystemExit(f"{run_id} vetted no second-list signal (kind second)")
    triage = _second_triage(args.triage_run, provenance, run_id, list(second), args.production)
    tics = sorted({int(c["star"]["tic"]) for c in second.values()})
    lcs = _light_curves(provenance)
    searched = _searched(pd.read_parquet(triage["search_stars"]))
    for tic in tics:
        path = lcs / f"{tic}.npz"
        recorded = provenance["inputs"].get(f"light_curve_{tic}", {}).get("sha256")
        if not path.is_file() or sha256_file(path) != recorded:
            raise SystemExit(f"the light curve for TIC {tic} changed since {run_id} vetted it")
        # Triage handed the pixel check every sector of the light curve its search searched; a re-vet's light curve
        # holds others, and its record carries the second list's pixel check instead.
        if recorded != searched.get(tic):
            raise SystemExit(
                f"{run_id} vetted another light curve for TIC {tic} than the search searched; the second list runs "
                "the pixel check only on the search's, and a re-vet's record carries it (decision 0041)"
            )
    for name, path in snapshot_inputs(args.catalogs).items():
        recorded = provenance["inputs"].get(name, {}).get("sha256")
        if not path.is_file() or sha256_file(path) != recorded:
            raise SystemExit(
                f"--catalogs {args.catalogs.name} is not the snapshot {run_id} vetted with ({path.name})"
            )
    problems = secondlist.check_raw(args.catalogs)
    if problems:
        raise SystemExit(f"--catalogs {args.catalogs.name}: " + "; ".join(problems))
    match, harmonics = crit_search["match"], tuple(crit_vet["novelty"]["harmonics"])
    found = {
        name: secondlist.look_up(args.catalogs, checks, match, harmonics)
        for name, checks in second.items()
    }
    run = start_run("vetting-second-list", [crit_search, crit_vet], args.production, sys.argv)
    run.record("vetting_run", run_id)
    run.record("triage_run", triage["run_id"])
    run.record_input("vetting_provenance", args.run / "provenance.json")
    for name in second:
        run.record_input(f"checks_{name}", signals / name / "checks.json")
    run.record_input("triage_provenance", triage["provenance"])
    run.record_input("triage_criteria", triage["criteria"])
    run.record_input("search_stars", triage["search_stars"])
    for name, file in triage["evidence"].items():
        run.record_input(f"triage_evidence_{name}", file)
    for tic in tics:
        run.record_input(f"light_curve_{tic}", lcs / f"{tic}.npz")
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    results, jobs = {}, []
    for name, checks in second.items():
        metrics = json.loads(triage["evidence"][name].read_text())["leo_flux"]["evidence"].get(
            "metrics"
        )
        if not metrics:
            results[name] = inconclusive(
                "pixels",
                f"triage run {triage['run_id']} recorded no metrics from LEO-Vetter for {name}, so the "
                "pixel check can't run as triage runs it",
            ).to_dict()
            continue
        tic = int(checks["star"]["tic"])
        jobs.append(
            {
                "name": name,
                # The evidence file holds a NaN as null; triage handed the pixel check the NaN, and which fit's
                # ephemeris it asks for turns on it (pixels.asked_ephemeris).
                "metrics": {k: float("nan") if v is None else v for k, v in metrics.items()},
                "star": checks["star"],
                "sectors": sorted(int(s) for s in LightCurve.load(lcs / f"{tic}.npz").sources),
                "cfg": triage["pixels"],
                # transit-diffImage names its files by TIC, planet number and sector: one directory per signal.
                "tdi": run.path / "tdi" / name,
            }
        )
    # TESScut allows 5 requests a second; as in triage, four signals at a time stays well inside it.
    done = run_jobs(_pixel_job, jobs, min(4, args.workers))
    results |= {job["name"]: result for job, result in zip(jobs, done, strict=True)}
    limit = triage["pixels"]["max_offset_arcsec"]
    items, summary = [], {}
    for name, checks in second.items():
        tic = int(checks["star"]["tic"])
        record = {
            "signal": {"name": name, "tic": tic},
            "vetting_run": run_id,
            "triage_run": triage["run_id"],
            "max_offset_arcsec": limit,
            **results[name],
            # The record is published with the signal's.
            "reason": scrub(results[name]["reason"]),
        }
        path = run.path / "signals" / name / "pixels.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps(jsonable(record), indent=2, sort_keys=True) + "\n")
        # The vetting run's centroid plot drew triage's record, which holds no offsets for this row.
        plots.centroids(record["evidence"], checks["neighbours"], path.parent / "pixels.png", limit)
        items.append({"name": name, "checks": checks, "pixels": record, **found[name]})
        summary[name] = {"tic": tic, "pixels": record["outcome"], "sha256": sha256_file(path)}
        print(f"{name}: pixels {record['outcome']}, {record['reason']}")
    secondlist.table(items).to_csv(run.path / "second-list.csv", index=False)
    about = {
        "run_id": run.provenance["run_id"],
        "vetting_run": run_id,
        "triage_run": triage["run_id"],
        "triage_criteria": triage["criteria_file"],
        "criteria": [Path(c["file"]).stem for c in provenance["criteria"]],
        "limit": limit,
    }
    (run.path / "second-list.md").write_text(secondlist.markdown(items, about))
    run.finish(
        vetting_run=run_id, triage_run=triage["run_id"], max_offset_arcsec=limit, signals=summary
    )
    print(f"vetting second-list: {len(items)} row(s) -> {run.path}")
    return 0


def _finished(path: Path, stage: str, what: str, production: bool) -> dict:
    provenance_file = path / "provenance.json"
    run_id = path.resolve().name
    provenance = json.loads(provenance_file.read_text()) if provenance_file.is_file() else {}
    if provenance.get("stage") != stage or provenance.get("ended_at") is None:
        raise SystemExit(f"{run_id} is not a finished {what} run")
    if production and not provenance.get("production"):
        raise SystemExit(f"{run_id} is not a production {what} run; the published record needs one")
    return provenance


def _published(record: Path) -> bool:
    """A record `publish` finished: it writes dossier.md last."""
    return (record / "checks.json").is_file() and (record / "dossier.md").is_file()


def _signal_dir(record: Path) -> Path:
    return record.parent if calls.version(record) else record


def _label(record: Path) -> str:
    version = calls.version(record)
    return f"r{version}" if version else "the M3 record"


def _records(signal: Path) -> list[Path]:
    """A signal's published records in order: the M3 record, then each version."""
    versions = sorted((p for p in signal.glob("r*") if calls.version(p)), key=calls.version)
    return [record for record in (signal, *versions) if _published(record)]


def _judged(signal: Path) -> Path | None:
    """The earliest published record whose preregistered test is not pending: decision 0040 judges a signal once, so
    its result stands."""
    for record in _records(signal):
        result = record / "prereg.json"
        if result.is_file() and json.loads(result.read_text())["result"] != "pending":
            return record
    return None


def _carries(previous: Path | None) -> dict[str, Path]:
    """The runs a version takes from an earlier record instead of running them again, by role, each with the record
    that holds it: the previous record's second-list run, since a re-vet carries the pixel check, and the
    preregistered test of the earliest version that judged the signal (decisions 0040 and 0041)."""
    if previous is None:
        return {}
    held = {"second-list": previous, "prereg": _judged(_signal_dir(previous))}
    return {
        role: record
        for role, record in held.items()
        if record is not None and (record / f"provenance-{role}.json").is_file()
    }


def _carried(run: Path, role: str, carries: dict[str, Path]) -> bool:
    """Whether `run` is the `role` run that the record `carries` names for it holds, its provenance byte for byte."""
    record = carries.get(role)
    return record is not None and sha256_file(record / f"provenance-{role}.json") == sha256_file(
        run / "provenance.json"
    )


def _origin(record: Path, vetting_run: str) -> Path | None:
    """The published record, of the signal `record` is a record of, that `vetting_run` vetted."""
    return next(
        (
            r
            for r in _records(_signal_dir(record))
            if json.loads((r / "provenance-checks.json").read_text())["run_id"] == vetting_run
        ),
        None,
    )


def _record_runs(args, production: bool, previous: Path | None = None) -> dict[str, Path]:
    """The runs a signal's record is made from, by the role their files play in it, checked to belong together
    before anything is copied: one vetting run, the TRICERATOPS, literature, second-list and preregistered-test runs
    made from it, and an evidence-only run, all on the same criteria (Ruling C). A version may carry the previous
    record's second-list run and must carry the preregistered test of the version that judged the signal, both made
    from another vetting run (decision 0041)."""
    main = _finished(args.run, "vetting-run", "vetting", production)
    run_id = args.run.resolve().name
    # It keeps the timing-suspect sectors in and never makes a call (decision 0022).
    if main.get("evidence_only"):
        raise SystemExit(f"{run_id} is an evidence-only vetting run; give it as --evidence-only")
    criteria = [c["sha256"] for c in main["criteria"]]
    carries = _carries(previous)
    runs = {"checks": args.run}
    given = (
        ("triceratops", args.triceratops, "vetting-triceratops", "TRICERATOPS"),
        ("literature", args.literature, "vetting-literature", "literature"),
        ("checks-with-suspect", args.evidence_only, "vetting-run", "evidence-only vetting"),
        ("second-list", args.second_list, "vetting-second-list", "second-list"),
        ("prereg", args.prereg, "vetting-prereg", "preregistered test"),
    )
    for role, path, stage, what in given:
        if path is None:
            continue
        made = _finished(path, stage, what, production)
        name = path.resolve().name
        if role == "checks-with-suspect":
            if not made.get("evidence_only"):
                raise SystemExit(f"{name} is not an evidence-only vetting run")
        elif made["vetting_run"] != run_id and not _carried(path, role, carries):
            raise SystemExit(f"{what} run {name} was made from {made['vetting_run']}, not {run_id}")
        elif role == "prereg" and "prereg" in carries and not _carried(path, role, carries):
            judged = carries["prereg"]
            raise SystemExit(
                f"{what} run {name} judges the signal again; {_label(judged)} judged it, and decision 0040 judges a "
                "signal once: give --prereg the run that version holds"
            )
        if [c["sha256"] for c in made["criteria"]] != criteria:
            raise SystemExit(f"{what} run {name} ran on other criteria than {run_id}")
        runs[role] = path
    return runs


def _signal_files(
    runs: dict[str, Path], name: str, previous: Path | None = None
) -> dict[str, Path]:
    """A signal's record: each run's files for it under the name the record gives them, and beside each run's files
    that run's provenance, unchanged (M3 design, section 4.9)."""
    vetted = runs["checks"] / "signals" / name
    if not SAFE_NAME.fullmatch(name) or not (vetted / "checks.json").is_file():
        raise SystemExit(f"{runs['checks'].resolve().name} vetted no {name}")
    checks = vetted / "checks.json"
    kind = json.loads(checks.read_text())["signal"]["kind"]
    carries = _carries(previous)
    files = {"checks.json": checks, "provenance-checks.json": runs["checks"] / "provenance.json"}
    if (vetted / "neighbours.csv").is_file():
        files["neighbours.csv"] = vetted / "neighbours.csv"
    for plot in sorted((vetted / "plots").glob("*.png")):
        files[f"plots/{plot.name}"] = plot
    for role, outputs, what in (
        ("triceratops", ("triceratops.json", "probs.csv"), "TRICERATOPS"),
        ("literature", ("literature.json",), "literature"),
        # Only a second-list row has them: the pixel check triage never ran on it (Ruling U), and its centroid plot,
        # named apart from the vetting run's plots/ so every file there keeps its source.
        ("second-list", ("pixels.json", "pixels.png"), "second-list"),
        ("prereg", ("prereg.json",), "preregistered test"),
    ):
        path = runs.get(role)
        # The second list judges only second-list rows; any other signal's pixel check is triage's, and its record
        # names no second-list run.
        if path is None or (role == "second-list" and kind != "second"):
            continue
        files[f"provenance-{role}.json"] = path / "provenance.json"
        made = path / "signals" / name
        # A signal a check killed gets no TRICERATOPS; the dossier says the run did not judge it.
        if not (made / outputs[0]).is_file():
            continue
        made_from = json.loads((path / "provenance.json").read_text())
        inputs = made_from["inputs"]
        carried = _carried(path, role, carries)
        # A carried run read the checks.json of the record its own vetting run made, and the record it is carried
        # from holds its files.
        origin = _origin(previous, made_from["vetting_run"]) if carried else None
        if carried and origin is None:
            raise SystemExit(
                f"{what} run {path.resolve().name} was made from {made_from['vetting_run']}, which no published "
                f"record of {name} holds"
            )
        read = origin / "checks.json" if carried else checks
        if inputs.get(f"checks_{name}", {}).get("sha256") != sha256_file(read):
            raise SystemExit(
                f"{what} run {path.resolve().name} read another checks.json for {name} than "
                f"{(origin or runs['checks']).resolve().name} holds"
            )
        found = {out: made / out for out in outputs if (made / out).is_file()}
        kept = carries.get(role)
        if carried and any(
            not (kept / out).is_file() or sha256_file(kept / out) != sha256_file(file)
            for out, file in found.items()
        ):
            raise SystemExit(
                f"{what} run {path.resolve().name}'s files for {name} are not the ones {_label(kept)} holds"
            )
        files.update(found)
    suspect = runs.get("checks-with-suspect")
    if suspect is not None:
        file = suspect / "signals" / name / "checks.json"
        if not file.is_file():
            raise SystemExit(f"{suspect.resolve().name} vetted no {name}")
        if json.loads(file.read_text())["ephemeris"] != json.loads(checks.read_text())["ephemeris"]:
            raise SystemExit(f"{suspect.resolve().name} vetted {name} at another ephemeris")
        files["checks-with-suspect.json"] = file
        files["provenance-checks-with-suspect.json"] = suspect / "provenance.json"
    return files


def _previous(args, root: Path, name: str) -> Path | None:
    """With `--version N`, the published record the version follows: the M3 record for N = 2, r<N-1> after it
    (decision 0041). None without `--version`."""
    if args.version is None:
        for flag, value in (("--lc-run", args.lc_run), ("--prereg", args.prereg)):
            if value is not None:
                raise SystemExit(f"{flag} is for a version of a record: give --version N")
        return None
    if args.version < 2:
        raise SystemExit("--version counts from 2: the M3 record is the first")
    if args.lc_run is None:
        raise SystemExit(
            "a version is a re-vet: give --lc-run, the revet fetch run whose light curves --run vetted"
        )
    previous = root / name if args.version == 2 else root / name / f"r{args.version - 1}"
    if not _published(previous):
        label = "M3 record" if args.version == 2 else f"r{args.version - 1}"
        raise SystemExit(
            f"no {label} published in results/vetting/{name}: a version follows the one before it"
        )
    return previous


def _revet_files(
    lc_run: Path, vetting: Path, previous: Path, tic: int, production: bool
) -> dict[str, Path]:
    """The revet fetch run a version's light curve came from: the vetting run read its file for the star, and it
    merged its sectors onto the light curve the previous record's vetting run read. Its merge record goes into the
    version with its provenance."""
    made = _finished(lc_run, "revet-fetch", "revet fetch", production)
    run_id, vetted = lc_run.resolve().name, vetting.resolve().name
    star = json.loads((lc_run / "merge.json").read_text()).get(str(tic))
    if star is None or star["lc_sha256"] is None:
        raise SystemExit(f"revet fetch run {run_id} made no light curve for TIC {tic}")
    file = lc_run / "lc" / f"{tic}.npz"
    vetted_from = json.loads((vetting / "provenance.json").read_text())
    read = vetted_from["inputs"].get(f"light_curve_{tic}", {}).get("sha256")
    if not file.is_file() or read != star["lc_sha256"] or sha256_file(file) != read:
        raise SystemExit(
            f"{vetted} did not vet the light curve revet fetch run {run_id} made for TIC {tic}"
        )
    # `vetting prereg` dated the light curve by the run the vetting run read it from, so the version's merge record
    # is that run's, even where another run holds the same bytes.
    if vetted_from.get("revet_run") != run_id:
        raise SystemExit(
            f"{vetted} read its light curves from {vetted_from.get('revet_run') or 'no revet fetch run'}, not revet "
            f"fetch run {run_id}"
        )
    before = json.loads((previous / "provenance-checks.json").read_text())["inputs"]
    base = before.get(f"light_curve_{tic}", {}).get("sha256")
    merged_onto = made["inputs"].get(f"base_light_curve_{tic}", {}).get("sha256")
    if base is None or star["base_sha256"] != base or merged_onto != base:
        raise SystemExit(
            f"revet fetch run {run_id} merged TIC {tic}'s sectors onto another light curve than the one the previous "
            "record's vetting run read"
        )
    return {
        "merge.json": lc_run / "merge.json",
        "provenance-merge.json": lc_run / "provenance.json",
    }


def _same_signal(files: dict[str, Path], previous: Path, predictions: Path) -> None:
    """A version vets the previous record's signal at the same ephemeris on the same criteria with the same triage
    run, its evidence-only twin on the same light curve and snapshot, keeps a second-list row's pixel check, and for a
    signal a published predictions package holds, carries the preregistered test (decisions 0040 and 0041)."""
    now, before = (
        json.loads(p.read_text()) for p in (files["checks.json"], previous / "checks.json")
    )
    name = before["signal"]["name"]
    for key in ("tic", "signal", "ephemeris"):
        if now[key] != before[key]:
            raise SystemExit(
                f"the vetting run vetted {name} with another {key} than the previous record: a re-vet vets the same "
                "signal"
            )
    made, was = (
        json.loads(p.read_text())
        for p in (files["provenance-checks.json"], previous / "provenance-checks.json")
    )
    if [c["sha256"] for c in made["criteria"]] != [c["sha256"] for c in was["criteria"]]:
        raise SystemExit(
            f"the vetting run ran on other criteria than the previous record of {name}"
        )
    # Triage's pixel and ModShift evidence stay the earlier record's.
    if made.get("triage_run") != was.get("triage_run"):
        raise SystemExit(
            f"the vetting run read another triage run than the previous record of {name} ({made.get('triage_run')}, "
            f"not {was.get('triage_run')})"
        )
    twin = files.get("provenance-checks-with-suspect.json")
    if twin is not None:
        read = json.loads(twin.read_text())["inputs"]
        same = (f"light_curve_{now['tic']}", "known", "catalog_manifest")
        if any(
            read.get(k, {}).get("sha256") != made["inputs"].get(k, {}).get("sha256") for k in same
        ):
            raise SystemExit(
                f"the evidence-only run read another light curve or catalog snapshot for {name} than the version's "
                "vetting run"
            )
    if (previous / "pixels.json").is_file() and "pixels.json" not in files:
        raise SystemExit(
            f"a version of {name} carries the second list's pixel check: give --second-list, the run the previous "
            "record holds"
        )
    # A judged result stands whatever results/predictions/ holds now.
    judged = _carries(previous).get("prereg")
    if judged is not None and "prereg.json" not in files:
        run = json.loads((judged / "provenance-prereg.json").read_text())["run_id"]
        raise SystemExit(
            f"a version of {name} carries {_label(judged)}'s preregistered test, which judged it once (decision "
            f"0040): give --prereg {run}"
        )
    held = [
        p.parent
        for p in sorted(predictions.glob("*/references.json"))
        if name in json.loads(p.read_text())["signals"]
    ]
    if not held:
        if "provenance-prereg.json" in files and judged is None:
            raise SystemExit(
                f"--prereg: no package under results/predictions/ predicts {name}, so its version has no "
                "preregistered test to report"
            )
        return
    listed = ", ".join(p.name for p in held)
    if "prereg.json" not in files:
        raise SystemExit(
            f"{name} is in the predictions package {listed}: a version carries the preregistered test (--prereg, a "
            "vetting prereg run)"
        )
    tested = json.loads(files["provenance-prereg.json"].read_text())
    package = predictions / tested["package"]
    if package not in held or tested["inputs"]["package_references"]["sha256"] != sha256_file(
        package / "references.json"
    ):
        raise SystemExit(f"the preregistered test ran on another package than {listed}")


def _tic(files: dict[str, Path]) -> int:
    return int(json.loads(files["checks.json"].read_text())["tic"])


def _copy(files: dict[str, Path], dest: Path) -> None:
    for name, source in files.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # Run files are read-only; the copies are not.
        shutil.copyfile(source, target)
        target.chmod(0o644)


def _clear(draft: Path) -> None:
    """A draft's earlier record, so files from other runs never sit beside the new ones; the review, the
    notes on it and the call stay."""
    if not draft.is_dir():
        return
    for path in draft.iterdir():
        if path.name == "plots":
            shutil.rmtree(path)
        elif calls.version(path) is not None:
            # A version's draft beside it is a record of its own.
            continue
        elif path.name not in ("review.json", "review-notes.toml", "call.toml"):
            path.unlink()


def cmd_dossier(args) -> int:
    repo = repo_root().resolve()
    results = repo / "results"
    out = args.out.resolve()
    # A draft anywhere in the checkout could be committed beside the published records.
    if out == repo or repo in out.parents:
        raise SystemExit(
            "drafts go outside the repository; `vetting publish` is the only way into its results/"
        )
    if args.version is not None and len(args.signals or []) != 1:
        raise SystemExit("a version's draft is one signal's: give --signals NAME")
    names = args.signals or sorted(
        p.name for p in (args.run / "signals").iterdir() if (p / "checks.json").is_file()
    )
    previous = _previous(args, results / "vetting", args.signals[0] if args.signals else "")
    runs = _record_runs(args, production=False, previous=previous)
    for name in names:
        files = _signal_files(runs, name, previous)
        draft = out / name
        if previous is not None:
            files |= _revet_files(args.lc_run, args.run, previous, _tic(files), production=False)
            _same_signal(files, previous, results / "predictions")
            # The version's dossier compares its checks with the previous record's, and names the version that
            # judged a carried result by the vetting runs of the records before it, all read from beside it.
            for record in _records(_signal_dir(previous)):
                if (calls.version(record) or 1) >= args.version:
                    continue
                kept = (
                    ("checks.json", "provenance-checks.json", "dossier.md")
                    if record == previous
                    else ("provenance-checks.json",)
                )
                beside = draft / record.name if calls.version(record) else draft
                _copy({f: record / f for f in kept}, beside)
            draft = draft / f"r{args.version}"
        _clear(draft)
        _copy(files, draft)
        (draft / "dossier.md").write_text(dossier.render(draft))
        print(f"{name}: {draft / 'dossier.md'}")
    return 0


def _trimmed(
    source: Path,
    titles: Path | None,
    literature_run: Path,
    name: str,
    tmp: Path,
    replaced: str | None = None,
) -> dict[str, Path]:
    """The literature record as `source` is published (decision 0038): cut by `literature.trim` with the titles
    run's lookups and written into `tmp`, with that run's provenance beside it. `replaced` names the titles run an
    earlier trim of the record used, which this one replaces."""
    if titles is None:
        raise SystemExit(
            "a literature record is published trimmed: give --titles, a titles run made from --literature "
            "(decision 0038)"
        )
    made = _finished(titles, "vetting-titles", "titles", production=True)
    run_id = titles.resolve().name
    if made["literature_run"] != literature_run.resolve().name:
        raise SystemExit(
            f"titles run {run_id} was made from {made['literature_run']}, not {literature_run.resolve().name}"
        )
    if made["inputs"].get(f"literature_{name}", {}).get("sha256") != sha256_file(source):
        raise SystemExit(f"titles run {run_id} read another literature.json for {name}")
    lookups = titles / "titles.json"
    if not lookups.is_file() or sha256_file(lookups) != made["summary"]["titles_sha256"]:
        raise SystemExit(f"{run_id}/titles.json is not the file it wrote")
    try:
        record = literature.trim(
            json.loads(source.read_text()),
            sha256_file(source),
            json.loads(lookups.read_text())["titles"],
            run_id,
        )
    except literature.TrimError as exc:
        raise SystemExit(str(exc)) from None
    if replaced is not None:
        record["trim"]["replaced_titles_run"] = replaced
    out = tmp / "literature.json"
    out.write_text(json.dumps(jsonable(record), indent=2, sort_keys=True) + "\n")
    return {"literature.json": out, "provenance-titles.json": titles / "provenance.json"}


def cmd_publish(args) -> int:
    root = repo_root() / "results" / "vetting"
    previous = _previous(args, root, args.name)
    runs = _record_runs(args, production=True, previous=previous)
    files = _signal_files(runs, args.name, previous)
    dest = root / args.name
    where = f"results/vetting/{args.name}"
    if previous is not None:
        dest, where = dest / f"r{args.version}", f"{where}/r{args.version}"
        # A version is published once, when its dossier.md, written last, is there; nothing in it changes after,
        # not even from the same runs. Until then the same runs finish an interrupted publish.
        if (dest / "dossier.md").is_file():
            raise SystemExit(f"{where} is already published; a published record never changes")
        files |= _revet_files(args.lc_run, args.run, previous, _tic(files), production=True)
        _same_signal(files, previous, root.parent / "predictions")
    # Judged and rendered, the README included, from a staged copy before anything is copied: a refusal or a render
    # that raises at any point leaves results/ as it was.
    with tempfile.TemporaryDirectory() as tmp:
        if "literature.json" in files:
            # A record trimmed again with another titles run names the run it replaced; publishing it with the new
            # run keeps that name, so the same runs again change nothing.
            trim = {}
            if (dest / "literature.json").is_file():
                trim = json.loads((dest / "literature.json").read_text()).get("trim", {})
            replaced = None
            if args.titles is not None and trim.get("titles_run") == args.titles.resolve().name:
                replaced = trim.get("replaced_titles_run")
            files |= _trimmed(
                files["literature.json"],
                args.titles,
                runs["literature"],
                args.name,
                Path(tmp),
                replaced=replaced,
            )
        # The same run's file again changes nothing; any other would overwrite the record.
        changed = sorted(
            name
            for name, source in files.items()
            if (dest / name).exists() and sha256_file(dest / name) != sha256_file(source)
        )
        if changed:
            raise SystemExit(
                f"{where} already holds another {', '.join(changed)}; published files are never overwritten"
            )
        if not (dest / "call.toml").is_file():
            raise SystemExit(
                f"no call.toml in {where}: the maintainer's call comes before publishing"
            )
        # Text quoted from a machine is published as tess-hunt's scrub writes it (decision 0038).
        review = dest / "review.json"
        if review.is_file() and unname(scrub(review.read_text())) != review.read_text():
            raise SystemExit(
                f"{where}/review.json names the home or data directory or the maintainer; write it as "
                "provenance.scrub and provenance.unname would (decision 0038)"
            )
        # The whole signal's directory: a version's dossier reads the record before it.
        staged = Path(tmp) / "staged" / args.name
        shutil.copytree(root / args.name, staged)
        if previous is not None:
            staged = staged / f"r{args.version}"
        _copy(files, staged)
        found = calls.problems(staged)
        if found:
            raise SystemExit(
                f"refused: the call on {args.name} does not stand on its record:\n"
                + "\n".join(f"- {p}" for p in found)
            )
        text = dossier.render(staged)
        (staged / "dossier.md").write_text(text)
        readme = dossier.readme(root, staged)
        left = dossier.listed(root, staged)[1]
        new = {name: source for name, source in files.items() if not (dest / name).exists()}
        try:
            _copy(new, dest)
        except BaseException:
            # Files copied before the failure would sit in the record with no dossier beside them; the same runs
            # copy them again.
            for name in new:
                (dest / name).unlink(missing_ok=True)
            raise
    # Last of the record: the README lists only a directory that holds it.
    (dest / "dossier.md").write_text(text)
    (root / "README.md").write_text(readme)
    print(f"published {args.name} -> {where} ({len(new)} new file(s), dossier.md, README.md)")
    for name, why in left.items():
        print(f"README leaves out {name}: {'; '.join(why)}")
    return 0


def cmd_trim(args) -> int:
    """Decision 0038 on a record published before it: its literature record trimmed as `publish` now trims it, the
    titles run's provenance beside it, and review.json with the home and data directories scrubbed and the
    maintainer's name written as "the maintainer"; then the dossier and the README rendered again. Nothing else in
    the record changes. The published literature.json must be the literature run's file for the signal, or already
    its trim."""
    root = repo_root() / "results" / "vetting"
    dest = root / args.name
    where = f"results/vetting/{args.name}"
    run_id = args.literature.resolve().name
    _finished(args.literature, "vetting-literature", "literature", production=True)
    published = dest / "literature.json"
    if not published.is_file():
        raise SystemExit(f"no literature.json in {where}")
    provenance = dest / "provenance-literature.json"
    if not provenance.is_file() or sha256_file(provenance) != sha256_file(
        args.literature / "provenance.json"
    ):
        raise SystemExit(f"{where} was not published from literature run {run_id}")
    source = args.literature / "signals" / args.name / "literature.json"
    trimmed = json.loads(published.read_text()).get("trim", {})
    origin = trimmed.get("source_sha256")
    if not source.is_file() or sha256_file(source) != (origin or sha256_file(published)):
        raise SystemExit(f"{where}/literature.json is neither {run_id}'s file nor its trim")
    # A record keeps naming the titles run it replaced, so trimming it again with the new run changes nothing.
    replaced = trimmed.get("replaced_titles_run")
    kept = dest / "provenance-titles.json"
    if kept.is_file() and sha256_file(kept) != sha256_file(args.titles / "provenance.json"):
        if not args.replace_titles_run:
            raise SystemExit(
                f"{where} was trimmed with another titles run; published files are never overwritten "
                "(--replace-titles-run replaces it, and the record names the run it replaced)"
            )
        replaced = trimmed["titles_run"]
    with tempfile.TemporaryDirectory() as tmp:
        files = _trimmed(
            source, args.titles, args.literature, args.name, Path(tmp), replaced=replaced
        )
        staged = Path(tmp) / "staged" / args.name
        shutil.copytree(dest, staged)
        _copy(files, staged)
        review = staged / "review.json"
        if review.is_file():
            review.write_text(unname(scrub(review.read_text())))
        text = dossier.render(staged)
        readme = dossier.readme(root, staged)
        changed = [
            name
            for name in (*files, "review.json")
            if (staged / name).is_file()
            and not (
                (dest / name).is_file() and sha256_file(dest / name) == sha256_file(staged / name)
            )
        ]
        _copy({name: staged / name for name in changed}, dest)
    (dest / "dossier.md").write_text(text)
    (root / "README.md").write_text(readme)
    print(
        f"trimmed {args.name} -> {where} ({', '.join(changed) or 'no file changed'}; dossier.md, README.md)"
    )
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("vetting", help="vet-v3 on a list of signals, and the dossier's evidence")
    modes = p.add_subparsers(dest="mode", required=True)
    r = modes.add_parser("run", help="vet each signal in a list, one directory per signal")
    r.add_argument("--signals", type=Path, required=True, help="CSV: " + ", ".join(SIGNAL_COLUMNS))
    r.add_argument(
        "--targets",
        type=Path,
        action="append",
        required=True,
        help="repeatable; the first file that lists a star gives its row",
    )
    r.add_argument("--catalogs", type=Path, required=True, help="a v2 snapshot")
    r.add_argument(
        "--triage-run",
        type=Path,
        help="the triage run whose LEO-Vetter ModShift and pixel evidence the dossier shows",
    )
    r.add_argument(
        "--include-suspect",
        action="store_true",
        help="evidence only: keep timing-suspect sectors in; no windows, never used for a call",
    )
    r.add_argument(
        "--lc-dir",
        type=Path,
        help="the light curves to vet, <tic>.npz each (a re-vet's: a revet fetch run's lc/); "
        "by default the shared cache",
    )
    r.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    r.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    r.add_argument("--workers", type=int, default=4)
    r.add_argument("--production", action="store_true")
    r.set_defaults(func=cmd_run)
    t = modes.add_parser(
        "triceratops", help="TRICERATOPS's FPP and NFPP for the signals of a vetting run"
    )
    t.add_argument(
        "--run", type=Path, required=True, help="a finished vetting run, not evidence-only"
    )
    t.add_argument(
        "--signals", nargs="+", help="signal names; by default every one no check failed"
    )
    t.add_argument(
        "--contrast",
        type=Path,
        help="CSV: " + ", ".join(CONTRAST_COLUMNS) + "; ExoFOP's machine-readable contrast curves",
    )
    t.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    t.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    t.add_argument("--workers", type=int, default=4)
    t.add_argument("--production", action="store_true")
    t.set_defaults(func=cmd_triceratops)
    lit = modes.add_parser(
        "literature",
        help="literature by every name, NASA ADS (with ADS_API_TOKEN set) and ExoFOP, per star",
    )
    lit.add_argument(
        "--run", type=Path, required=True, help="a finished vetting run, not evidence-only"
    )
    lit.add_argument(
        "--signals", nargs="+", help="signal names; by default every one no check failed"
    )
    lit.add_argument(
        "--resume-from",
        type=Path,
        help="an earlier literature run: its complete searches are kept, the rest made again",
    )
    lit.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    lit.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    lit.add_argument("--production", action="store_true")
    lit.set_defaults(func=cmd_literature)
    s = modes.add_parser(
        "second-list",
        help="the second-list rows' SPOC DV statistics, ExoMiner scores and triage's pixel check",
    )
    s.add_argument(
        "--run", type=Path, required=True, help="a finished vetting run, not evidence-only"
    )
    s.add_argument(
        "--catalogs",
        type=Path,
        required=True,
        help="the v2 snapshot --run vetted with, its raw files kept",
    )
    s.add_argument("--triage-run", type=Path, required=True, help="the triage run --run read")
    s.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    s.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    s.add_argument("--workers", type=int, default=4)
    s.add_argument("--production", action="store_true")
    s.set_defaults(func=cmd_second_list)
    pr = modes.add_parser(
        "prereg",
        help="the preregistered test of each held signal of a predictions package that a re-vet vetted "
        "(decision 0040)",
    )
    pr.add_argument(
        "--run", type=Path, required=True, help="a re-vet's finished vetting run, not evidence-only"
    )
    pr.add_argument(
        "--package",
        type=Path,
        required=True,
        help="a predictions package: its run directory or its copy under results/predictions/",
    )
    pr.add_argument(
        "--catalogs", type=Path, required=True, help="the catalog snapshot --run vetted with"
    )
    pr.add_argument(
        "--as-of",
        type=dt.date.fromisoformat,
        required=True,
        help="the day judged on; before the package's judging date a predicted sector without data the test can "
        "use leaves the result pending",
    )
    pr.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    pr.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    pr.add_argument("--production", action="store_true")
    pr.set_defaults(func=cmd_prereg)
    d = modes.add_parser(
        "dossier", help="render draft dossiers for the maintainer, outside the repository"
    )
    _record_arguments(d, required=False)
    d.add_argument(
        "--signals", nargs="+", help="signal names; by default every signal --run vetted"
    )
    d.add_argument(
        "--out",
        type=Path,
        required=True,
        help="one directory per signal; a review.json or call.toml already in it is rendered too",
    )
    d.set_defaults(func=cmd_dossier)
    pub = modes.add_parser(
        "publish",
        help="copy a called signal's record into results/vetting/<name>/ and render its dossier",
    )
    pub.add_argument("--name", required=True, help="the signal's name in --run")
    _record_arguments(pub, required=True)
    pub.add_argument(
        "--titles",
        type=Path,
        help="a titles run made from --literature; needed when the record has a literature.json",
    )
    pub.set_defaults(func=cmd_publish)
    ti = modes.add_parser(
        "titles",
        help="OpenAlex's title, by DOI, for each paper a literature run found no open-source title for",
    )
    ti.add_argument("--literature", type=Path, required=True, help="a finished literature run")
    ti.add_argument("--production", action="store_true")
    ti.set_defaults(func=cmd_titles)
    tr = modes.add_parser(
        "trim",
        help="apply decision 0038 to a record published before it: trim its literature.json, scrub "
        "review.json, render its dossier again",
    )
    tr.add_argument("--name", required=True, help="the published signal's name")
    tr.add_argument(
        "--literature", type=Path, required=True, help="the literature run the record came from"
    )
    tr.add_argument(
        "--titles", type=Path, required=True, help="a titles run made from --literature"
    )
    tr.add_argument(
        "--replace-titles-run",
        action="store_true",
        help="replace the titles run the record was trimmed with; the record names the run it replaced",
    )
    tr.set_defaults(func=cmd_trim)


def _record_arguments(p, required: bool) -> None:
    p.add_argument(
        "--run", type=Path, required=True, help="a finished vetting run, not evidence-only"
    )
    p.add_argument(
        "--triceratops", type=Path, required=required, help="a TRICERATOPS run made from --run"
    )
    p.add_argument(
        "--literature", type=Path, required=required, help="a literature run made from --run"
    )
    p.add_argument(
        "--evidence-only",
        type=Path,
        help="the evidence-only vetting run (timing-suspect sectors kept in), shown beside --run",
    )
    p.add_argument(
        "--second-list",
        type=Path,
        help="a second-list run made from --run, whose pixel check a second-list row's record needs; for a version, "
        "the previous record's",
    )
    p.add_argument(
        "--version",
        type=int,
        help="a re-vet's record, version N (from 2), beside the record in results/vetting/<name>/r<N>/ "
        "(decision 0041)",
    )
    p.add_argument(
        "--lc-run",
        type=Path,
        help="with --version: the revet fetch run whose light curves --run vetted",
    )
    p.add_argument(
        "--prereg", type=Path, help="with --version: a vetting prereg run made from --run"
    )
