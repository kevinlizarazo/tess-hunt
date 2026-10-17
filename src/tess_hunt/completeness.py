"""What triage passes: the injections the search recovered, replayed through novelty and LEO-Vetter's flux
tests as triage judged real signals, and the pixel check on the known planets at their catalog ephemerides."""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from tess_hunt.benchmark import (
    ENGINES,
    PERIOD_EDGES,
    RADIUS_EDGES,
    SNR_EDGES,
    _replayed,
    completeness,
    md_table,
    plant,
)
from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs
from tess_hunt.config import Criteria, data_dir, lc_dir, load_criteria, runs_dir
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pool import run_jobs
from tess_hunt.provenance import repo_root, scrub, sha256_file, start_run
from tess_hunt.recovery import classify
from tess_hunt.search import read_threshold, search_star, star_params, stellar_density
from tess_hunt.threshold import (
    check_leo_code,
    check_light_curves,
    check_mask_snapshot,
    check_reproducible,
    load_v2_catalog,
)
from tess_hunt.triage import (
    OUTCOMES,
    _eph,
    _pixel_job,
    _star,
    check_triage_criteria,
    judge_flux,
    judge_novelty,
)

KEYS = ["tic", "injection", "engine"]
# The judged signal's ephemeris keeps the names triage's signals table gives it.
REPLAY_COLUMNS = [
    "replay",
    "replay_reason",
    "period",
    "t0",
    "duration",
    "depth",
    "novelty",
    "novelty_category",
    "novelty_reason",
    "leo_flux",
    "leo_disposition",
    "leo_reason",
    "fa_failed",
    "fp_failed",
    "unknown",
]
LEO_LISTS = ("fa_failed", "fp_failed", "unknown")
TABLES = {
    "by_snr": ("expected_snr", SNR_EDGES),
    "by_period": ("inj_period", PERIOD_EDGES),
    "by_radius": ("inj_rp_rearth", RADIUS_EDGES),
}
# The same search of the same light curve repeats to rounding; a larger difference is another search.
SAME_SEARCH_RTOL = 1e-9


def _difference(found: dict, row: dict) -> str:
    """Why the replay's match is not the one the inject run recorded; empty when it is."""
    same = (
        found["recovered"]
        and found["rank"] == int(row["rank"])
        and np.isclose(found["found_period"], row["found_period"], rtol=SAME_SEARCH_RTOL, atol=0)
        and np.isclose(found["sde"], row["sde"], rtol=SAME_SEARCH_RTOL, atol=0)
    )
    if same:
        return ""
    return (
        f"the search matched rank {found['rank']} at {found['found_period']:.6f} d, SDE "
        f"{found['sde']:.3f}, recovered {found['recovered']}; the inject run recorded rank "
        f"{int(row['rank'])} at {row['found_period']:.6f} d, SDE {row['sde']:.3f}"
    )


def replay_job(job: dict) -> dict:
    """One recovered injection planted and searched again as the inject run did it, then judged by
    LEO-Vetter's flux tests as triage judges a signal: on the signal the search matched to the injection,
    with the star's other signals at or above the threshold dropped. A search that does not match the
    injection at the rank, period and SDE the inject run recorded is not judged. Novelty reads the whole
    v2 catalog, too big to hand every worker, so cmd_triage_completeness judges it."""
    row, star, crit, level = job["row"], job["star"], job["criteria"], job["level"]
    base = {k: row[k] for k in KEYS}
    try:
        rstar, mstar, _ = star_params(star)
        inj = _replayed(row)
        lc = LightCurve.load(lc_dir() / f"{int(row['tic'])}.npz")
        planted, flat = plant(lc, inj, crit, job["known"])
        search = {**crit["search"], **ENGINES[row["engine"]]}
        signals = search_star(
            flat, rstar, mstar, search, stellar_density(star, rstar, mstar)
        ).signals
        found = classify(inj.ephemeris(), signals, crit["match"], level)
        why = _difference(found, row)
        if why:
            return {**base, "replay": "not_reproduced", "replay_reason": why}
        signal = next(s for s in signals if s.rank == found["rank"])
        others = [s.ephemeris() for s in signals if s.rank != signal.rank and s.sde >= level]
        # LEO-Vetter detrends for itself, so it gets the planted light curve before detrending, as
        # triage hands it the fetched one.
        flux, outcome, _ = judge_flux(
            planted, star, signal.ephemeris(), others, job["known"], crit["detrend"], job["triage"]
        )
    except Exception as exc:  # one bad injection must not stop the run; it is recorded
        return {**base, "replay": "error", "replay_reason": scrub(f"{type(exc).__name__}: {exc}")}
    return {
        **base,
        "replay": "ok",
        "replay_reason": "",
        "period": signal.period,
        "t0": signal.t0,
        "duration": signal.duration,
        "depth": signal.depth,
        "leo_flux": str(flux.outcome),
        "leo_disposition": flux.evidence.get("disposition"),
        "leo_reason": scrub(flux.reason),
        **{k: ", ".join(getattr(outcome, k)) if outcome else "" for k in LEO_LISTS},
    }


def _aligned(table: pd.DataFrame, part: pd.DataFrame, column: str, missing) -> list:
    """`part`'s `column` at each of `table`'s engine and bin, `missing` where `part` has none. A merge
    would do it, but an empty `part` has untyped columns that pandas warns about casting."""
    values = dict(zip(zip(part["engine"], part["bin"], strict=True), part[column], strict=True))
    return [values.get(key, missing) for key in zip(table["engine"], table["bin"], strict=True)]


def summarise(rows: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Per bin of expected SNR, injected period and radius: the inject run's search completeness over
    the injections it searched (`search`); over the judged injections, the share LEO-Vetter called a
    planet candidate, the share novelty passed and the share that passed both (`triage_pass`); and
    `product`, search times triage_pass. Then how many judged injections failed, or left unjudged, each
    LEO-Vetter test, and each step's outcomes."""
    judged = rows[rows["replay"].eq("ok")]
    leo, novelty = judged["leo_flux"].eq("pass"), judged["novelty"].eq("pass")
    shares = {"leo_pc": leo, "novelty_pass": novelty, "triage_pass": leo & novelty}
    out = {}
    for name, (column, edges) in TABLES.items():
        # completeness() bins as the inject run's own tables do; each share stands in for `recovered`.
        table = completeness(rows, column, edges).rename(
            columns={"count": "searched", "fraction": "search"}
        )
        table["judged"] = _aligned(table, completeness(judged, column, edges), "count", 0)
        for share, passed in shares.items():
            part = completeness(judged.assign(recovered=passed), column, edges)
            table[share] = _aligned(table, part, "fraction", np.nan)
        table["product"] = table["search"] * table["triage_pass"]
        out[name] = table
    tests = Counter(
        (kind, test.split(":")[0])
        for kind in LEO_LISTS
        for listed in judged[kind].fillna("")
        for test in str(listed).split(", ")
        if test
    )
    out["failed_tests"] = pd.DataFrame(
        [{"kind": k, "test": t, "injections": n} for (k, t), n in sorted(tests.items())],
        columns=["kind", "test", "injections"],
    )
    out["outcomes"] = pd.DataFrame(
        [
            {"step": step, **{o: int(judged[step].eq(o).sum()) for o in OUTCOMES}}
            for step in ("novelty", "leo_flux")
        ],
        columns=["step", *OUTCOMES],
    )
    return out


def _finished(path: Path, stage: str) -> dict:
    provenance = json.loads((path / "provenance.json").read_text())
    if provenance.get("stage") != stage:
        raise SystemExit(f"{path.name} is not a {stage} run")
    if provenance.get("ended_at") is None:
        raise SystemExit(f"{path.name} has not finished; only finished runs are evidence")
    return provenance


def _refuse(args, inject: dict, triaged: dict, crit_triage: Criteria) -> tuple[Criteria, float]:
    """Stops on any reason the replay would not plant and search as the inject run did or judge as the
    triage run did; otherwise returns the search criteria and the threshold."""
    injected, judged = args.inject_run.name, args.triage_run.name
    if args.production and not (inject.get("production") and triaged.get("production")):
        raise SystemExit(
            "production triage completeness needs a production inject run and triage run"
        )
    if inject.get("threshold") is None:
        raise SystemExit(f"{injected} ran without a threshold, so it did not recover at triage's")
    read = inject["inputs"]["threshold"]["sha256"]
    if triaged["inputs"]["threshold"]["sha256"] != read:
        raise SystemExit(f"{injected} and {judged} read different threshold files")
    threshold_file = runs_dir() / inject["threshold"]["run_id"] / "threshold.json"
    if not threshold_file.is_file() or sha256_file(threshold_file) != read:
        raise SystemExit(
            f"{threshold_file.parent.name}/threshold.json is not the threshold file {injected} read"
        )
    threshold = read_threshold(threshold_file)
    # The inject run refused a threshold made with other search code, so the threshold names its code.
    crit_search = check_reproducible(
        {**inject, "search_code_sha256": threshold["search_code_sha256"]},
        args.targets,
        "inject run",
    )
    if triaged["criteria"][0]["sha256"] != crit_search.sha256:
        raise SystemExit(f"{judged} ran other search criteria than {injected}")
    if triaged["inputs"].get("targets", {}).get("sha256") != sha256_file(args.targets):
        raise SystemExit(f"--targets differs from the targets {judged} judged")
    if sha256_file(repo_root() / "uv.lock") != inject["uv_lock_sha256"]:
        raise SystemExit(
            f"uv.lock differs from the one {injected} ran, so its search could find other signals"
        )
    check_mask_snapshot(inject, args.mask_catalogs, "inject run")
    # Triage records its mask snapshot's files under a mask_ prefix.
    masks = {
        k.removeprefix("mask_"): v for k, v in triaged["inputs"].items() if k.startswith("mask_")
    }
    check_mask_snapshot({"inputs": masks}, args.mask_catalogs, "triage run")
    for name, path in snapshot_inputs(args.catalogs).items():
        if triaged["inputs"].get(name, {}).get("sha256") != sha256_file(path):
            raise SystemExit(
                f"--catalogs differs from the snapshot {judged} judged novelty with ({name})"
            )
    check_triage_criteria(
        triaged["criteria"][1], crit_triage, ("leo", "leo_metrics", "novelty"), judged
    )
    problems = check_leo_code(triaged, repo_root())
    if problems:
        raise SystemExit(f"LEO-Vetter would not judge as in {judged}: " + "; ".join(problems))
    return crit_search, float(threshold["threshold"])


def cmd_triage_completeness(args) -> int:
    inject = _finished(args.inject_run, "benchmark-inject")
    triaged = _finished(args.triage_run, "triage")
    crit_triage = load_criteria(args.criteria_triage)
    crit_search, level = _refuse(args, inject, triaged, crit_triage)
    # The default parser is not correctly rounded; it would move the planets by a few ULP.
    injections = pd.read_csv(args.inject_run / "injections.csv", float_precision="round_trip")
    searched = injections[injections["status"] == "ok"]
    recovered = searched[searched["recovered"].astype(bool)]
    # A refetch since the inject run would plant its planets in other data.
    curves = recovered.drop_duplicates("tic").assign(control=False)
    check_light_curves(curves, sorted(int(t) for t in curves["tic"]), args.workers, "inject run")
    run = start_run(
        "benchmark-triage-completeness", [crit_search, crit_triage], args.production, sys.argv
    )
    run.record("inject_run", args.inject_run.resolve().name)
    run.record("triage_run", args.triage_run.resolve().name)
    threshold_run = inject["threshold"]["run_id"]
    run.record("threshold", {"value": level, "file": "threshold.json", "run_id": threshold_run})
    run.record_input("injections", args.inject_run / "injections.csv")
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    for name, path in snapshot_inputs(args.mask_catalogs).items():
        run.record_input(f"mask_{name}", path)
    stars = pd.read_parquet(args.targets).set_index("tic")
    masks = load_known(args.mask_catalogs)
    detrend_cfg = crit_search["detrend"]
    mask_sources = tuple(detrend_cfg["mask_sources"])
    fallback = detrend_cfg["fallback_duration_days"]
    crit = {**crit_search.values, "search": {**crit_search["search"], "continue_sde": level}}
    jobs = [
        {
            "row": row,
            "star": _star(stars, int(row["tic"])),
            # What the inject run masked in its search and triage excluded from LEO-Vetter's input.
            "known": known_ephemerides(masks, int(row["tic"]), fallback, mask_sources),
            "criteria": crit,
            "triage": crit_triage.values,
            "level": level,
        }
        for row in recovered.to_dict("records")
    ]
    replays = run_jobs(replay_job, jobs, args.workers)
    # Loaded only now: near a gigabyte at its peak, it would crowd the workers under a memory cap, and
    # its files are the ones triage loaded (checked above).
    catalog = load_v2_catalog(args.catalogs)
    for r in replays:
        if r["replay"] == "ok":
            result = judge_novelty(
                _star(stars, int(r["tic"])),
                _eph(r),
                catalog,
                crit_triage["novelty"],
                crit_search["match"],
            )
            r |= {
                "novelty": str(result.outcome),
                "novelty_category": result.evidence.get("category", ""),
                "novelty_reason": scrub(result.reason),
            }
    replayed = pd.DataFrame(replays, columns=[*KEYS, *REPLAY_COLUMNS])
    rows = searched.merge(replayed, on=KEYS, how="left")
    rows.to_csv(run.path / "rows.csv", index=False)
    tables = summarise(rows)
    for name, table in tables.items():
        table.to_csv(run.path / f"{name}.csv", index=False)
    statuses = rows["replay"].value_counts()
    counts = {s: int(statuses.get(s, 0)) for s in ("ok", "not_reproduced", "error")}
    steps = tables["outcomes"].set_index("step")
    lines = [
        f"# Triage completeness ({run.provenance['run_id']})",
        "",
        f"Inject run `{args.inject_run.resolve().name}`: {len(rows)} injections searched, "
        f"{len(recovered)} recovered at SDE {level:.2f} or above (the threshold from "
        f"`{threshold_run}`). Each recovered injection was planted and searched again as the inject "
        "run did it, then judged by novelty and LEO-Vetter's flux tests as triage run "
        f"`{args.triage_run.resolve().name}` judged its signals, on the signal the search matched to "
        "the injection, with the star's other signals at or above the threshold dropped.",
        "",
        f"Judged: {counts['ok']}. Not reproduced: {counts['not_reproduced']} (the search did not "
        "match the injection at the rank, period and SDE the inject run recorded). Errors: "
        f"{counts['error']}. Only judged injections enter the shares below.",
        "",
        md_table(tables["outcomes"]),
        "",
        "`search` is the inject run's search completeness over the injections it searched. "
        "`leo_pc`, `novelty_pass` and `triage_pass` (both passed) are shares of the judged "
        "injections; `product` is `search` times `triage_pass`. Pixels are not replayed: an "
        "injected transit is not in the pixels, so `benchmark pixel-completeness` measures that "
        "step on the known planets.",
        "",
        "## By expected SNR",
        "",
        md_table(tables["by_snr"]),
        "",
        "## By injected period (days)",
        "",
        md_table(tables["by_period"]),
        "",
        "## By injected radius (Earth radii)",
        "",
        md_table(tables["by_radius"]),
        "",
        "## LEO-Vetter tests failed or not judged",
        "",
        md_table(tables["failed_tests"]),
        "",
    ]
    (run.path / "summary.md").write_text("\n".join(lines))
    run.finish(
        searched=len(rows),
        recovered=len(recovered),
        judged=counts["ok"],
        not_reproduced=counts["not_reproduced"],
        error=counts["error"],
        **{step: steps.loc[step].to_dict() for step in steps.index},
    )
    print("\n".join(lines))
    return 0


def cmd_pixel_completeness(args) -> int:
    crit_triage = load_criteria(args.criteria_triage)
    planets = pd.read_csv(args.known, dtype={"toi": str}, float_precision="round_trip")
    stars = pd.read_parquet(args.targets).set_index("tic")
    missing = sorted(int(t) for t in set(planets["tic"]) - set(stars.index))
    if missing:
        raise SystemExit(f"--targets {args.targets.name} has no row for hosts {missing}")
    run = start_run("benchmark-pixel-completeness", [crit_triage], args.production, sys.argv)
    run.record_input("known", args.known)
    run.record_input("targets", args.targets)
    # transit-diffImage names its files by TIC, planet number and sector, so every planet gets a
    # directory of its own, and planet number 1 never meets another planet's images.
    tdi = data_dir() / "tdi" / run.provenance["run_id"]
    rows, jobs = [], []
    for p in planets.to_dict("records"):
        tic = int(p["tic"])
        path = lc_dir() / f"{tic}.npz"
        rows.append(
            {
                **{k: p[k] for k in ("toi", "tic", "period", "t0", "duration")},
                "lc_sha256": sha256_file(path) if path.exists() else None,
            }
        )
        jobs.append(
            {
                # The catalog ephemeris where triage hands over LEO-Vetter's fit.
                "metrics": {
                    "tic": tic,
                    "planetno": 1,
                    "per": p["period"],
                    "epo": p["t0"],
                    "dur": p["duration"],
                },
                "star": _star(stars, tic),
                # As triage: every sector the light curve holds, none without one.
                "sectors": sorted(int(s) for s in LightCurve.load(path).sources)
                if path.exists()
                else [],
                "cfg": crit_triage["pixels"],
                "tdi": tdi / f"{tic}-{p['toi']}",
            }
        )
    # TESScut allows 5 requests a second; as in triage, four planets at a time stays well inside it.
    results = run_jobs(_pixel_job, jobs, min(4, args.workers))
    (run.path / "evidence").mkdir()
    for row, result in zip(rows, results, strict=True):
        run.write_json(f"evidence/{row['tic']}-{row['toi']}.json", result)
        row |= {
            "pixels": result["outcome"],
            "pixels_reason": scrub(result["reason"]),
            "offset_qual_arcsec": result["evidence"].get("offset_qual_arcsec", np.nan),
            "good_sectors": len(result["evidence"].get("sectors", [])),
        }
    table = pd.DataFrame(rows)
    table.to_csv(run.path / "pixels.csv", index=False)
    counts = {o: int(table["pixels"].eq(o).sum()) for o in OUTCOMES}
    lines = [
        f"# Pixel completeness ({run.provenance['run_id']})",
        "",
        f"The pixel check, with `{args.criteria_triage.name}`'s `[pixels]`, on {len(table)} known "
        f"planets from `{args.known.name}` at their catalog ephemerides: pass {counts['pass']}, "
        f"fail {counts['fail']}, inconclusive {counts['inconclusive']}. `offset_qual_arcsec` is the "
        "best-quality sector's offset.",
        "",
        md_table(
            table[
                [
                    "toi",
                    "tic",
                    "period",
                    "pixels",
                    "offset_qual_arcsec",
                    "good_sectors",
                    "pixels_reason",
                ]
            ]
        ),
        "",
    ]
    (run.path / "summary.md").write_text("\n".join(lines))
    run.finish(planets=len(table), **counts)
    print("\n".join(lines))
    return 0
