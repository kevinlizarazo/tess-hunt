"""The null threshold (decision 0019): the highest SDE among scrambled signals that pass LEO-Vetter's
false-alarm tests, and the guards that tie a production search to it."""

import json
import math
import sys
from collections.abc import Callable, Mapping
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, ephemeris_match, in_transit
from tess_hunt.leo import leo_flux
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pool import run_jobs
from tess_hunt.provenance import repo_root, scrub, sha256_file, start_run
from tess_hunt.search import (
    search_code_sha256,
    search_input,
    search_star,
    star_params,
    stellar_density,
)

# The share of a null signal's in-transit cadences that must lie in one real signal's transits for the
# trace-back to call it made of them. The trace-back is evidence for the maintainer's review and decides
# nothing, so this is not a criterion.
OWN_TRANSITS_SHARE = 0.5

# The trace-back's fields when it cannot say either way.
UNTRACED = {
    "built": None,
    "overlap": None,
    "period": None,
    "sde": None,
    "n_cadences": 0,
    "reason": "",
}


def exclude_known(
    signals: pd.DataFrame, known: pd.DataFrame, harmonics, sigma_p: float
) -> pd.Series:
    """For each null signal, the name of a known object on its own star that it matches on period, or ''.
    Real binaries and planets survive scrambling; they are not false alarms (Kunimoto et al. 2025, 5.5)."""
    by_tic = {int(t): g for t, g in known.groupby("tic")}
    names = []
    for s in signals.itertuples():
        found = ""
        for row in by_tic.get(int(s.tic), pd.DataFrame()).itertuples():
            if not (np.isfinite(row.period) and row.period > 0):
                continue
            ref = Ephemeris(float(row.period), float("nan"), 0.1)
            if (
                ephemeris_match(Ephemeris(s.period, s.t0, s.duration), ref, harmonics, sigma_p)
                is not None
            ):
                found = str(row.name)
                break
        names.append(found)
    return pd.Series(names, index=signals.index)


def compute_threshold(
    candidates: pd.DataFrame, evaluate: Callable[[list[dict]], list[dict]], batch: int
) -> tuple[float | None, pd.DataFrame]:
    rows = candidates.sort_values("sde", ascending=False).to_dict("records")
    evaluated: list[dict] = []
    for start in range(0, len(rows), batch):
        results = evaluate(rows[start : start + batch])
        evaluated += results
        # Every higher SDE has been judged by now, so the first batch with a pass holds the threshold. A
        # signal LEO-Vetter could not judge counts as a pass, so evaluation goes on until a batch holds a
        # judged one: the threshold as it would be if unjudged signals did not count.
        if any(r["passes_fa"] and r["judged"] for r in results):
            break
    passing = [r["sde"] for r in evaluated if r["passes_fa"]]
    return (max(passing) if passing else None), pd.DataFrame(evaluated)


def _finite_number(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def check_search(search_provenance: dict, threshold: dict, thresholds: list[dict]) -> list[str]:
    """Why triage must refuse a search; empty when it may go ahead."""
    problems = []
    criteria = search_provenance["criteria"][0]["sha256"]
    code = search_provenance.get("search_code_sha256")
    if criteria != threshold["search_criteria_sha256"]:
        problems.append("the search ran other criteria than the null behind its threshold")
    if code != threshold["search_code_sha256"]:
        problems.append("the search ran other code than the null behind its threshold")
    ran = search_provenance.get("threshold")
    if ran is None:
        problems.append("the search ran without a threshold")
        return problems
    # Provenance writes a NaN as null, so the value is checked before any comparison.
    value = ran.get("value")
    if not _finite_number(value):
        problems.append(f"the search's continue_sde {value!r} is not a finite number")
        return problems
    if not value >= threshold["threshold"]:
        problems.append(
            f"the search's continue_sde {value} is below its threshold {threshold['threshold']}"
        )
    same = [
        t["threshold"]
        for t in thresholds
        if t["search_criteria_sha256"] == criteria and t["search_code_sha256"] == code
    ]
    # Spec 5.4: the threshold is recomputed as the null grows, and a run below the current value fails.
    if same and not value >= max(same):
        problems.append(
            f"the search's continue_sde {value} is below the current null threshold {max(same)}"
        )
    return problems


def all_thresholds(runs: Path) -> list[dict]:
    out = []
    for path in sorted(runs.glob("*-threshold-*/threshold.json")):
        if json.loads((path.parent / "provenance.json").read_text())["ended_at"] is not None:
            out.append(json.loads(path.read_text()))
    return out


def _leo_job(job: dict) -> dict:
    row = job["row"]
    # A null signal counts toward the threshold unless a false-alarm test definitely rejects it: a signal
    # LEO-Vetter could not judge is not cleared as a false alarm, so it can raise the threshold, never lower it.
    out = {
        **row,
        "passes_fa": True,
        "judged": False,
        "why_unjudged": "",
        "disposition": None,
        "fa_failed": [],
        "unknown": [],
    }
    try:
        lc = LightCurve.load(lc_dir() / f"{int(row['tic'])}.npz")
        lc, exclude = search_input(lc, job["known"], job["search"], job["seed"])
        others = [Ephemeris(o["period"], o["t0"], o["duration"]) for o in job["others"]]
        eph = Ephemeris(row["period"], row["t0"], row["duration"], row["depth"])
        result, outcome, _ = leo_flux(
            lc,
            job["star"],
            eph,
            others,
            exclude,
            job["search"]["detrend"],
            job["triage"],
            fa_only=True,
        )
    except Exception as exc:  # a crash is no evidence that LEO-Vetter would reject the signal
        return {**out, "why_unjudged": scrub(f"{type(exc).__name__}: {exc}")}
    if outcome is None:
        # LEO-Vetter did not run: a stellar value is missing, nothing was left after detrending, or it raised.
        return {**out, "why_unjudged": scrub(result.reason)}
    judged = outcome.disposition == "PC" or bool(outcome.fa_failed)
    return {
        **out,
        "passes_fa": outcome.passes_fa,
        "judged": judged,
        "why_unjudged": "" if judged else scrub(result.reason),
        "disposition": outcome.disposition,
        "fa_failed": outcome.fa_failed,
        "unknown": outcome.unknown,
    }


def own_transits(
    lc: LightCurve, star: Mapping, known: list[Ephemeris], crit: Mapping, seed: int, eph: Ephemeris
) -> dict:
    """Whether a null signal is made of a real signal's own transits. The scramble can leave three or four
    of a planet's or binary's transits evenly spaced by chance, at a period that is no harmonic of the real
    one; the events agree with each other, so LEO-Vetter's false-alarm tests cannot reject the peak. The
    star is searched unscrambled as the production search searches it, and the null signal's in-transit
    cadences are traced back through the scramble: built when at least OWN_TRANSITS_SHARE of them fall
    inside the transits of one signal found there. Evidence for the maintainer's review; it changes no rule.

    The cadences are every unmasked one inside the null signal's transits on the scrambled light curve. For
    a signal of rank 2 or lower they include cadences the null search had already masked for the star's
    higher-ranked signals, which that search never saw."""
    rstar, mstar, _ = star_params(star)
    plain, exclude = search_input(lc, known, crit, None)
    flat = detrend(plain, crit["detrend"], exclude=exclude)
    found = search_star(
        flat, rstar, mstar, crit["search"], stellar_density(star, rstar, mstar)
    ).signals
    # search_input keeps the scramble's order to itself; a light curve whose flux is each cadence's index
    # comes out of the same steps carrying it.
    index = replace(lc, flux=np.arange(len(lc.time), dtype=float))
    scrambled, dropped = search_input(index, known, crit, seed)
    cadences = scrambled.flux[in_transit(scrambled.time, eph) & ~dropped].astype(int)
    out = {**UNTRACED, "n_cadences": len(cadences)}
    if len(cadences) == 0:
        return {**out, "reason": "no cadence of the null signal is in transit"}
    if not found:
        return {
            **out,
            "built": False,
            "overlap": 0.0,
            "reason": "the unscrambled search found no signal",
        }
    overlaps = [float(in_transit(lc.time[cadences], s.ephemeris()).mean()) for s in found]
    best = int(np.argmax(overlaps))
    return {
        **out,
        "built": overlaps[best] >= OWN_TRANSITS_SHARE,
        "overlap": overlaps[best],
        "period": found[best].period,
        "sde": found[best].sde,
    }


def _own_transits_job(job: dict) -> dict:
    row = job["row"]
    try:
        lc = LightCurve.load(lc_dir() / f"{int(row['tic'])}.npz")
        eph = Ephemeris(row["period"], row["t0"], row["duration"])
        return own_transits(lc, job["star"], job["known"], job["search"], job["seed"], eph)
    except Exception as exc:  # a failed trace-back says nothing either way
        return {**UNTRACED, "reason": scrub(f"{type(exc).__name__}: {exc}")}


def _lc_sha256(tic: int) -> str | None:
    path = lc_dir() / f"{tic}.npz"
    return sha256_file(path) if path.exists() else None


def check_mask_snapshot(provenance: dict, snapshot: Path, masked_by: str) -> None:
    """Refuse a --mask-catalogs other than the snapshot the run behind `provenance` masked with: LEO-Vetter
    must see the light curve with the same known objects masked."""
    for name, path in snapshot_inputs(snapshot).items():
        if provenance["inputs"].get(name, {}).get("sha256") != sha256_file(path):
            raise SystemExit(
                f"--mask-catalogs differs from the snapshot the {masked_by} masked with ({name})"
            )


def cmd_threshold(args) -> int:
    null_prov = json.loads((args.null / "provenance.json").read_text())
    if null_prov["ended_at"] is None or null_prov.get("scramble") is None:
        raise SystemExit(f"{args.null.name} is not a finished null (scrambled) search")
    check_mask_snapshot(null_prov, args.mask_catalogs, "null")
    if null_prov["inputs"].get("targets", {}).get("sha256") != sha256_file(args.targets):
        raise SystemExit("--targets differs from the targets the null searched")
    crit_search = load_criteria(Path(null_prov["criteria"][0]["file"]))
    if crit_search.sha256 != null_prov["criteria"][0]["sha256"]:
        raise SystemExit("the search criteria file changed since the null ran")
    # The null's light curves are scrambled again here, so this checkout must scramble as the null did.
    if search_code_sha256(repo_root()) != null_prov["search_code_sha256"]:
        raise SystemExit("the search code changed since the null ran")
    crit_triage = load_criteria(args.criteria_triage)
    cfg = crit_triage["threshold"]
    signals = pd.read_parquet(args.null / "signals.parquet")
    # With no signals at all the column is empty object dtype, which `~` cannot negate.
    signals = signals[~signals["control"].astype(bool)].reset_index(drop=True)
    known = load_known(args.catalogs)
    signals["excluded_by"] = exclude_known(
        signals, known, tuple(cfg["exclude_harmonics"]), crit_search["match"]["sigma_p"]
    )
    candidates = signals[signals["excluded_by"] == ""]
    if candidates.empty:
        raise SystemExit(f"{args.null.name} leaves no null signal to judge")
    # A refetch since the null changes the scramble's order and times, so LEO-Vetter would judge another
    # light curve than the one the null searched.
    null_stars = pd.read_parquet(args.null / "stars.parquet")
    sample = null_stars[~null_stars["control"].astype(bool)]
    searched = dict(zip(sample["tic"].astype(int), sample["lc_sha256"], strict=True))
    tics = sorted({int(t) for t in candidates["tic"]})
    now = run_jobs(_lc_sha256, tics, args.workers)
    changed = [t for t, sha in zip(tics, now, strict=True) if sha is None or sha != searched.get(t)]
    if changed:
        raise SystemExit(
            f"the light curves of {len(changed)} null stars differ from the ones the null searched: "
            f"{changed[:10]}"
        )
    stars = pd.read_parquet(args.targets).set_index("tic")
    run = start_run("threshold", [crit_search, crit_triage], args.production, sys.argv)
    run.record_input("null_signals", args.null / "signals.parquet")
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    masks = load_known(args.mask_catalogs)
    mask_sources = tuple(crit_search["detrend"]["mask_sources"])
    fallback = crit_search["detrend"]["fallback_duration_days"]

    def job(row: dict) -> dict:
        tic = int(row["tic"])
        return {
            "row": row,
            "star": {**stars.loc[tic].to_dict(), "tic": tic},
            "known": known_ephemerides(masks, tic, fallback, mask_sources),
            "seed": null_prov["scramble"],
            "search": crit_search.values,
        }

    def evaluate(rows: list[dict]) -> list[dict]:
        jobs = [
            {
                **job(row),
                "others": signals[
                    (signals["tic"] == row["tic"]) & (signals["rank"] != row["rank"])
                ].to_dict("records"),
                "triage": crit_triage.values,
            }
            for row in rows
        ]
        return run_jobs(_leo_job, jobs, args.workers)

    value, evaluated = compute_threshold(candidates, evaluate, cfg["batch"])
    evaluated.to_parquet(run.path / "null_leo.parquet")
    passing = evaluated[evaluated["passes_fa"]]
    # The highest surviving null signal; it sets the threshold unless the floor is higher.
    threshold_row = passing.loc[passing["sde"].idxmax()].to_dict() if len(passing) else None
    top = evaluated.head(cfg["report_top"]).to_dict("records")
    traced = {
        (int(r["tic"]), int(r["rank"])): r
        for r in [*top, *([threshold_row] if threshold_row else [])]
    }
    own = dict(
        zip(
            traced,
            run_jobs(_own_transits_job, [job(r) for r in traced.values()], args.workers),
            strict=True,
        )
    )

    def with_trace(row: dict) -> dict:
        return {**row, "own_transits": own[(int(row["tic"]), int(row["rank"]))]}

    top = [with_trace(r) for r in top]
    threshold_row = with_trace(threshold_row) if threshold_row else None
    unjudged = ~evaluated["judged"].astype(bool)
    judged_passes = evaluated.loc[evaluated["passes_fa"] & ~unjudged, "sde"]
    highest_judged = float(judged_passes.max()) if len(judged_passes) else None
    above = evaluated["sde"] > (highest_judged if highest_judged is not None else -math.inf)
    floor = crit_search["search"]["continue_sde"]
    n_null = int((sample["status"] == "ok").sum())
    n_sample = len(stars)
    result = {
        "threshold": float(max(value, floor)) if value is not None else float(floor),
        "rule": cfg["rule"],
        "floor_used": value is None or value < floor,
        "null_run": args.null.name,
        "n_null_stars": n_null,
        "n_sample": n_sample,
        "expected_false_alarms": n_sample / n_null if n_null else None,
        "excluded": int((signals["excluded_by"] != "").sum()),
        "evaluated": len(evaluated),
        "top": top,
        "threshold_row": threshold_row,
        "threshold_row_unjudged": None if threshold_row is None else not threshold_row["judged"],
        "threshold_row_own_transits": None
        if threshold_row is None
        else threshold_row["own_transits"]["built"],
        "unjudged": int(unjudged.sum()),
        # The threshold as it would be if unjudged signals did not count, and how many sit above it.
        "highest_judged_pass_sde": highest_judged,
        "why_no_judged_pass": ""
        if highest_judged is not None
        else f"no judged pass among {len(evaluated)} evaluated",
        "unjudged_above_judged_pass": int((unjudged & above).sum()),
        "search_criteria_sha256": null_prov["criteria"][0]["sha256"],
        "search_code_sha256": null_prov["search_code_sha256"],
        "snapshot": args.catalogs.name,
    }
    run.write_json("threshold.json", result)
    run.finish(
        **{
            k: result[k]
            for k in (
                "threshold",
                "floor_used",
                "n_null_stars",
                "expected_false_alarms",
                "excluded",
                "evaluated",
            )
        }
    )
    print(
        f"threshold {result['threshold']:.2f} from {result['evaluated']} null signals -> {run.path}"
    )
    if threshold_row is not None:
        # Under the floor that signal does not set the threshold.
        label = "the highest surviving null signal" if result["floor_used"] else "the threshold row"
        where = f"{label} (TIC {int(threshold_row['tic'])} rank {int(threshold_row['rank'])})"
        if result["threshold_row_unjudged"]:
            print(f"{where} was not judged: {threshold_row['why_unjudged']}")
        if result["threshold_row_own_transits"]:
            period = threshold_row["own_transits"]["period"]
            print(f"{where} is made of the star's own {period:.4f} d transits")
    return 0
