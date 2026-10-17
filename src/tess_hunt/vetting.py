"""`tess-hunt vetting`: vet-v3 on a list of signals, one directory each, with the evidence the
dossier reads beside the checks (M3 design, sections 4.2 to 4.7)."""

import contextlib
import json
import os
import re
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import requests

from tess_hunt import literature, neighbours, plots, predict, tricera
from tess_hunt.catalogs import load_known, snapshot_inputs
from tess_hunt.checks.families import split
from tess_hunt.config import Criteria, lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris
from tess_hunt.fit import FitResult
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pool import run_jobs
from tess_hunt.provenance import repo_root, scrub, sha256_file, start_run
from tess_hunt.serialize import jsonable
from tess_hunt.threshold import load_v2_catalog
from tess_hunt.transit import a_rs_from_density
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
    report, fit, fit_prior = vet_with_fits(
        lc,
        star,
        eph,
        load_known(job["catalogs"]),
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
    """The searches an earlier run completed, each marked with the run that made it."""
    return {
        source: {
            name: {**r, "from_run": r.get("from_run", run_id)}
            for name, r in results.items()
            if r["status"] in literature.COMPLETE
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
