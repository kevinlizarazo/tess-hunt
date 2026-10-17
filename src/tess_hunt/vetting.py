"""`tess-hunt vetting`: vet-v3 on a list of signals, one directory each, with the evidence the
dossier reads beside the checks (M3 design, sections 4.2 to 4.7)."""

import contextlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt import calls, dossier, literature, neighbours, plots, predict, secondlist, tricera
from tess_hunt.catalogs import load_known, snapshot_inputs
from tess_hunt.checks import inconclusive
from tess_hunt.checks.families import split
from tess_hunt.config import Criteria, lc_dir, load_criteria
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
from tess_hunt.provenance import repo_root, scrub, sha256_file, start_run
from tess_hunt.serialize import jsonable
from tess_hunt.threshold import check_leo_code, check_light_curves, load_v2_catalog
from tess_hunt.transit import a_rs_from_density
from tess_hunt.triage import _pixel_job
from tess_hunt.vet import vet_with_fits

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
    # pd.NA for a star without one; the control targets tables have no such column at all.
    value = star.get("dr3_source_id")
    return None if value is None or pd.isna(value) else int(value)


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
        cone = neighbours.gaia_cone(float(star["ra"]), float(star["dec"]), cfg["radius_arcmin"])
        table = neighbours.required_depths(cone, depth, tmag, source_id, cfg)
        error = None
    except neighbours.NeighbourError as exc:
        table, error = None, str(exc)
    result = neighbours.neighbour_check(table, error).to_dict()
    # The required depths scale from this depth, so the dossier must say which it was.
    result["evidence"].update(
        depth=depth, depth_from="the signals file", tmag=tmag, target_source_id=source_id
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


def _plots(lc: LightCurve, checks: dict, job: dict, path: Path) -> None:
    crit_search, crit_vet, eph = job["crit_search"], job["crit_vet"], job["eph"]
    # The light curve the checks saw: without the sectors vet dropped, detrended around the rows it
    # masked.
    seen = lc.select(~np.isin(lc.sector, checks["dropped_suspect"]))
    flat = detrend(seen, crit_search["detrend"], [Ephemeris(**m) for m in checks["masked"]])
    plots.transits(flat, eph, path / "transits.png")
    plots.folds(
        flat,
        eph,
        crit_vet["families"],
        path / "folds.png",
        crit_vet["holdout"]["season_gap_days"],
    )
    plots.odd_even(flat, eph, path / "odd_even.png")
    plots.phase(flat, eph, checks["modshift"], path / "phase.png")
    pixels = checks["pixels"]["evidence"] if checks["pixels"] else None
    plots.centroids(pixels, checks["neighbours"], path / "centroids.png", job["pixel_limit"])


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
    _plots(lc, checks, job, out / "plots")
    # Written last: a directory with a checks.json holds everything the signal got.
    (out / "checks.json").write_text(json.dumps(jsonable(checks), indent=2, sort_keys=True) + "\n")
    windows = checks["windows"]
    return {
        "name": job["name"],
        "kind": job["kind"],
        "outcomes": {c["check"]: c["outcome"] for c in report["checks"]},
        "neighbours": found["outcome"],
        "windows": None if windows is None else sum("epoch" in w for w in windows),
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


def _no_triage(reason: str) -> dict:
    return {"modshift": None, "pixels": None, "other_signals": None, "triage_reason": reason}


def _triage(path: Path, signals: pd.DataFrame, crit_search: Criteria, production: bool) -> dict:
    """What a finished triage run holds for each signal in it, checked before the run starts."""
    provenance_file = path / "provenance.json"
    provenance = json.loads(provenance_file.read_text())
    run_id = path.resolve().name
    if provenance.get("stage") != "triage" or provenance.get("ended_at") is None:
        raise SystemExit(f"{run_id} is not a finished triage run")
    if production and not provenance.get("production"):
        raise SystemExit(
            f"{run_id} is not a production triage run; a production vetting run needs one"
        )
    # Triage's ModShift and pixel evidence came from light curves detrended under its search
    # criteria; checks detrended otherwise would not sit beside them as one signal's evidence.
    searched = provenance["criteria"][0]
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
    used = provenance["criteria"][1]
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
    no_lc = [str(t) for t in stars if not (lc_dir() / f"{t}.npz").exists()]
    if no_lc:
        raise SystemExit(f"no light curve for TIC {', '.join(no_lc)}; fetch first")
    triage = (
        _triage(args.triage_run, signals, crit_search, args.production) if args.triage_run else None
    )
    sectors_file = crit_vet["predict"]["sectors_file"]
    sectors = predict.load_sectors(sectors_file)
    # The later vetting stages read the vet criteria back from criteria[1] and refuse any other: one
    # run, one criteria file.
    run = start_run("vetting-run", [crit_search, crit_vet], args.production, sys.argv)
    run.record("evidence_only", args.include_suspect)
    run.record("triage_run", triage["run_id"] if triage else None)
    run.record("search_run", triage["search_run"] if triage else None)
    run.record_input("signals", args.signals)
    for i, path in enumerate(args.targets, 1):
        run.record_input(f"targets_{i}", path)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    for tic in sorted(stars):
        run.record_input(f"light_curve_{tic}", lc_dir() / f"{tic}.npz")
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
            "lc": lc_dir() / f"{int(s['tic'])}.npz",
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
    for name, error in errors.items():
        print(f"{name}: {error}")
    run.finish(evidence_only=args.include_suspect, signals=vetted, errors=errors)
    label = " (evidence only)" if args.include_suspect else ""
    print(f"vetting run{label}: {len(vetted)} vetted, {len(errors)} failed -> {run.path}")
    return 1 if errors else 0


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
    for tic in tics:
        path = lc_dir() / f"{tic}.npz"
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
        run.record_input(f"light_curve_{tic}", lc_dir() / f"{tic}.npz")
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
            "lc": lc_dir() / f"{int(checks['star']['tic'])}.npz",
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
            **literature.search_all(tic, searched, session, token, cfg, kept),
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
    for tic in tics:
        path = lc_dir() / f"{tic}.npz"
        recorded = provenance["inputs"].get(f"light_curve_{tic}", {}).get("sha256")
        if not path.is_file() or sha256_file(path) != recorded:
            raise SystemExit(f"the light curve for TIC {tic} changed since {run_id} vetted it")
    # Triage handed the pixel check every sector of the light curve its search searched.
    check_light_curves(pd.read_parquet(triage["search_stars"]), tics, 1, "search")
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
        run.record_input(f"light_curve_{tic}", lc_dir() / f"{tic}.npz")
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
                "sectors": sorted(int(s) for s in LightCurve.load(lc_dir() / f"{tic}.npz").sources),
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


def _record_runs(args, production: bool) -> dict[str, Path]:
    """The runs a signal's record is made from, by the role their files play in it, checked to belong together
    before anything is copied: one vetting run, the TRICERATOPS, literature and second-list runs made from it, and
    an evidence-only run, all on the same criteria (Ruling C)."""
    main = _finished(args.run, "vetting-run", "vetting", production)
    run_id = args.run.resolve().name
    # It keeps the timing-suspect sectors in and never makes a call (decision 0022).
    if main.get("evidence_only"):
        raise SystemExit(f"{run_id} is an evidence-only vetting run; give it as --evidence-only")
    criteria = [c["sha256"] for c in main["criteria"]]
    runs = {"checks": args.run}
    given = (
        ("triceratops", args.triceratops, "vetting-triceratops", "TRICERATOPS"),
        ("literature", args.literature, "vetting-literature", "literature"),
        ("checks-with-suspect", args.evidence_only, "vetting-run", "evidence-only vetting"),
        ("second-list", args.second_list, "vetting-second-list", "second-list"),
    )
    for role, path, stage, what in given:
        if path is None:
            continue
        made = _finished(path, stage, what, production)
        name = path.resolve().name
        if role == "checks-with-suspect":
            if not made.get("evidence_only"):
                raise SystemExit(f"{name} is not an evidence-only vetting run")
        elif made["vetting_run"] != run_id:
            raise SystemExit(f"{what} run {name} was made from {made['vetting_run']}, not {run_id}")
        if [c["sha256"] for c in made["criteria"]] != criteria:
            raise SystemExit(f"{what} run {name} ran on other criteria than {run_id}")
        runs[role] = path
    return runs


def _signal_files(runs: dict[str, Path], name: str) -> dict[str, Path]:
    """A signal's record: each run's files for it under the name the record gives them, and beside each run's files
    that run's provenance, unchanged (M3 design, section 4.9)."""
    vetted = runs["checks"] / "signals" / name
    if not SAFE_NAME.fullmatch(name) or not (vetted / "checks.json").is_file():
        raise SystemExit(f"{runs['checks'].resolve().name} vetted no {name}")
    checks = vetted / "checks.json"
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
    ):
        path = runs.get(role)
        if path is None:
            continue
        files[f"provenance-{role}.json"] = path / "provenance.json"
        made = path / "signals" / name
        # A signal a check killed gets no TRICERATOPS; the dossier says the run did not judge it.
        if not (made / outputs[0]).is_file():
            continue
        inputs = json.loads((path / "provenance.json").read_text())["inputs"]
        if inputs.get(f"checks_{name}", {}).get("sha256") != sha256_file(checks):
            raise SystemExit(
                f"{what} run {path.resolve().name} read another checks.json for {name} than "
                f"{runs['checks'].resolve().name} holds"
            )
        files.update({out: made / out for out in outputs if (made / out).is_file()})
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


def _copy(files: dict[str, Path], dest: Path) -> None:
    for name, source in files.items():
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        # Run files are read-only; the copies are not.
        shutil.copyfile(source, target)
        target.chmod(0o644)


def _clear(draft: Path) -> None:
    """A draft's earlier record, so files from other runs never sit beside the new ones; the review and the call
    stay."""
    if not draft.is_dir():
        return
    for path in draft.iterdir():
        if path.name == "plots":
            shutil.rmtree(path)
        elif path.name not in ("review.json", "call.toml"):
            path.unlink()


def cmd_dossier(args) -> int:
    results = (repo_root() / "results").resolve()
    out = args.out.resolve()
    if out == results or results in out.parents:
        raise SystemExit(
            "drafts go outside the repo's results/; `vetting publish` is the only way in"
        )
    runs = _record_runs(args, production=False)
    names = args.signals or sorted(
        p.name for p in (args.run / "signals").iterdir() if (p / "checks.json").is_file()
    )
    for name in names:
        files = _signal_files(runs, name)
        draft = out / name
        _clear(draft)
        _copy(files, draft)
        (draft / "dossier.md").write_text(dossier.render(draft))
        print(f"{name}: {draft / 'dossier.md'}")
    return 0


def cmd_publish(args) -> int:
    runs = _record_runs(args, production=True)
    files = _signal_files(runs, args.name)
    root = repo_root() / "results" / "vetting"
    dest = root / args.name
    where = f"results/vetting/{args.name}"
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
        raise SystemExit(f"no call.toml in {where}: the maintainer's call comes before publishing")
    # Judged and rendered, the README included, from a staged copy before anything is copied: a refusal or a render
    # that raises at any point leaves results/ as it was.
    with tempfile.TemporaryDirectory() as tmp:
        staged = Path(tmp) / args.name
        shutil.copytree(dest, staged)
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
    _copy(new, dest)
    # Last of the record: the README lists only a directory that holds it.
    (dest / "dossier.md").write_text(text)
    (root / "README.md").write_text(readme)
    print(f"published {args.name} -> {where} ({len(new)} new file(s), dossier.md, README.md)")
    for name, why in left.items():
        print(f"README leaves out {name}: {'; '.join(why)}")
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
    d = modes.add_parser(
        "dossier", help="render draft dossiers for the maintainer, outside the repo's results/"
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
    pub.set_defaults(func=cmd_publish)


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
        help="a second-list run made from --run, whose pixel check a second-list row's record needs",
    )
