"""Triage: a valid production search's signals through the threshold, novelty, LEO-Vetter, pixels and a
literature search, down to a shortlist (docs/design.md, section 4.1)."""

import json
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from leo_vetter.main import TCELightCurve

from tess_hunt import literature
from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs
from tess_hunt.checks import CheckResult, inconclusive
from tess_hunt.config import Criteria, data_dir, lc_dir, load_criteria, runs_dir
from tess_hunt.detrend import known_mask
from tess_hunt.ephemeris import Ephemeris, transit_times_in_data
from tess_hunt.leo import LeoOutcome, leo_flux
from tess_hunt.lightcurve import LightCurve
from tess_hunt.novelty import check_novelty
from tess_hunt.pixels import pixel_check
from tess_hunt.pool import run_jobs
from tess_hunt.provenance import publish_run, repo_root, scrub, sha256_file, start_run
from tess_hunt.search import read_threshold
from tess_hunt.threshold import (
    all_thresholds,
    check_leo_code,
    check_light_curves,
    check_mask_snapshot,
    check_null_light_curves,
    check_reproducible,
    check_search,
    cmd_threshold,
    load_v2_catalog,
)

STEPS = ("novelty", "leo_flux", "pixels")
OUTCOMES = ("pass", "fail", "inconclusive")
RESULT_COLUMNS = [
    "novelty",
    "novelty_category",
    "novelty_reason",
    "leo_flux",
    "leo_disposition",
    "leo_reason",
    "leo_unknown",
    "pixels",
    "pixels_reason",
    "timing_suspect_transits",
    "ruwe",
    "shortlisted",
]
# Copied by `triage publish` beside the threshold run's threshold.json.
PUBLISHED = ("summary.md", "shortlist.csv", "known_to_spoc.csv", "signals.csv", "provenance.json")


class _Metrics:
    """What pixel_vetting reads from a TCELightCurve: its metrics."""

    def __init__(self, metrics: dict):
        self.metrics = dict(metrics)


def _number(value) -> float:
    # Targets rows carry pd.NA for a missing value, which float() refuses.
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _eph(row: dict) -> Ephemeris:
    return Ephemeris(
        float(row["period"]), float(row["t0"]), float(row["duration"]), float(row["depth"])
    )


def _star(stars: pd.DataFrame, tic: int) -> dict:
    return {**stars.loc[tic].to_dict(), "tic": int(tic)}


def judge_novelty(
    star: dict, eph: Ephemeris, known: pd.DataFrame, novelty_cfg: dict, match: dict
) -> CheckResult:
    """Novelty as triage judges a signal: the star's position from the targets table, the triage
    criteria's radius, harmonics and soft kinds, and the search criteria's match tolerances."""
    return check_novelty(
        int(star["tic"]),
        _number(star.get("ra")),
        _number(star.get("dec")),
        eph,
        known,
        novelty_cfg["neighbour_arcmin"],
        tuple(novelty_cfg["harmonics"]),
        match["sigma_p"],
        match["sigma_t"],
        inconclusive_kinds=tuple(novelty_cfg["inconclusive_kinds"]),
    )


def judge_flux(
    lc: LightCurve,
    star: dict,
    eph: Ephemeris,
    others: list[Ephemeris],
    known: list[Ephemeris],
    crit_detrend: dict,
    crit_triage: dict,
) -> tuple[CheckResult, LeoOutcome | None, TCELightCurve | None]:
    """LEO-Vetter's flux tests on one signal as triage runs them: the known objects' transits excluded,
    the star's other signals dropped, and anything raised counted as inconclusive."""
    exclude = known_mask(lc.time, known, crit_detrend["known_mask_width"])
    try:
        return leo_flux(lc, star, eph, others, exclude, crit_detrend, crit_triage)
    except Exception as exc:
        # leo_flux catches LEO-Vetter's errors; anything else raised here is no pass either.
        return inconclusive("leo_flux", f"raised {type(exc).__name__}: {exc}"), None, None


def _leo_star_job(job: dict) -> list[dict]:
    """Every above-threshold signal on one star, each with the star's other signals dropped."""
    star, rows = job["star"], job["rows"]
    lc = LightCurve.load(lc_dir() / f"{int(star['tic'])}.npz")
    suspect = np.isin(
        lc.sector, [int(s) for s, info in lc.sources.items() if info.get("timing_suspect")]
    )
    out = []
    for row in rows:
        eph = _eph(row)
        others = [_eph(o) for o in rows if o["rank"] != row["rank"]]
        result, outcome, tlc = judge_flux(
            lc, star, eph, others, job["known"], job["detrend"], job["triage"]
        )
        out.append(
            {
                "tic": int(row["tic"]),
                "rank": int(row["rank"]),
                "leo": result.to_dict(),
                "unknown": list(outcome.unknown) if outcome is not None else [],
                "metrics": dict(tlc.metrics) if tlc is not None else None,
                "timing_suspect_transits": int(len(transit_times_in_data(lc.time[suspect], eph))),
                "sectors": sorted(int(s) for s in lc.sources),
            }
        )
    return out


def _pixel_job(job: dict) -> dict:
    # TESScut waits dominate (minutes per sector), so a few signals run at once.
    try:
        return pixel_check(
            _Metrics(job["metrics"]), job["star"], job["sectors"], job["cfg"], job["tdi"]
        ).to_dict()
    except Exception as exc:
        # pixel_check counts its own failures to look; anything else raised here is no pass either.
        return inconclusive("pixels", f"raised {type(exc).__name__}: {exc}").to_dict()


def _sample_signals(search: Path, value: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """A search's sample signals, and those at or above the threshold, which triage judges."""
    signals = pd.read_parquet(search / "signals.parquet")
    # With no signals at all the column is empty object dtype, which `~` cannot negate.
    sample = signals[~signals["control"].astype(bool)]
    return sample, sample[sample["sde"] >= value].reset_index(drop=True)


def check_triage_criteria(
    used: dict, crit_triage: Criteria, sections: tuple[str, ...], run: str
) -> None:
    """Refuse a --criteria-triage that sets any of `sections` otherwise than the criteria file `used` (a
    provenance criteria entry) did when `run` ran; other sections may differ."""
    if used["sha256"] == crit_triage.sha256:
        return
    listed = [f"[{s}]" for s in sections]
    names = f"{', '.join(listed[:-1])} and {listed[-1]}" if len(listed) > 1 else listed[0]
    path = Path(used["file"])
    before = load_criteria(path) if path.exists() else None
    if before is None or before.sha256 != used["sha256"]:
        raise SystemExit(
            f"{used['file']} changed since {run} ran, so --criteria-triage's {names} cannot be "
            "checked against it"
        )
    if any(before[s] != crit_triage[s] for s in sections):
        raise SystemExit(f"--criteria-triage must set {names} as {used['file']} did when {run} ran")


def _refuse(args, search_prov: dict, threshold: dict, crit_triage: Criteria) -> Criteria:
    """Stops on any reason not to triage the search; otherwise returns its criteria."""
    if search_prov.get("ended_at") is None:
        raise SystemExit(f"{args.search.name} has not finished")
    if not (search_prov.get("summary") or {}).get("controls_valid"):
        # Spec 5.6: a run that misses its positive controls is invalid and its signals are not triaged.
        raise SystemExit(
            f"{args.search.name} is invalid: its positive controls failed or did not run"
        )
    if args.production and not search_prov.get("production"):
        raise SystemExit(
            f"{args.search.name} is not a production search; production triage needs one"
        )
    threshold_prov = json.loads((args.threshold / "provenance.json").read_text())
    if threshold_prov["ended_at"] is None:
        raise SystemExit(f"{args.threshold.name} has not finished; only finished runs are evidence")
    # Triage records the directory's name as the threshold's run id, and publishing looks it up by that.
    if threshold_prov["run_id"] != args.threshold.resolve().name:
        raise SystemExit(
            f"{args.threshold.name} is not the run its provenance names ({threshold_prov['run_id']})"
        )
    if args.production and not threshold_prov.get("production"):
        raise SystemExit(
            f"{args.threshold.name} is not a production threshold run; production triage needs one"
        )
    # The threshold counts null signals that pass LEO-Vetter's false-alarm tests, so triage must run
    # those tests as the threshold run did.
    check_triage_criteria(
        threshold_prov["criteria"][1], crit_triage, ("leo", "leo_metrics"), args.threshold.name
    )
    problems = check_leo_code(threshold_prov, repo_root())
    if problems:
        raise SystemExit(
            f"LEO-Vetter would not judge as in {args.threshold.name}: " + "; ".join(problems)
        )
    crit_search = check_reproducible(search_prov, args.targets, "search")
    thresholds = all_thresholds(runs_dir())
    problems = check_search(search_prov, threshold, thresholds)
    if problems:
        raise SystemExit("; ".join(problems))
    hashes = (threshold["search_criteria_sha256"], threshold["search_code_sha256"])
    same = [
        t["threshold"]
        for t in thresholds
        if (t["search_criteria_sha256"], t["search_code_sha256"]) == hashes
    ]
    # check_search holds the search to the current threshold; the cut below must use it too.
    if same and threshold["threshold"] < max(same):
        raise SystemExit(
            f"{args.threshold.name} sets {threshold['threshold']}, below the current null "
            f"threshold {max(same)}"
        )
    check_mask_snapshot(search_prov, args.mask_catalogs, "search")
    # The threshold measured false alarms on the null's light curves; a refetch between the null and the
    # search would cut the search's signals at a rate measured on other data.
    null = threshold.get("null_run")
    null_stars = runs_dir() / str(null) / "stars.parquet"
    if not null_stars.is_file():
        raise SystemExit(f"{args.threshold.name} names a null run with no stars.parquet: {null}")
    _, triaged = _sample_signals(args.search, float(threshold["threshold"]))
    changed = check_null_light_curves(
        pd.read_parquet(null_stars),
        pd.read_parquet(args.search / "stars.parquet"),
        sorted({int(t) for t in triaged["tic"]}),
    )
    if changed:
        noun = "star" if len(changed) == 1 else "stars"
        raise SystemExit(
            f"the light curves of {len(changed)} triaged {noun} differ from the ones the null {null} "
            f"searched for {args.threshold.name}: {changed[:10]}"
        )
    return crit_search


def _counts(table: pd.DataFrame, leo_unknown: Counter) -> dict:
    reached = table["novelty"].eq("pass") & table["leo_flux"].eq("pass")

    def outcomes(column: pd.Series) -> dict:
        return {o: int(column.eq(o).sum()) for o in OUTCOMES}

    unsure = table.loc[table["novelty"].eq("inconclusive"), "novelty_category"]
    return {
        "signals": len(table),
        "novelty": outcomes(table["novelty"]),
        "novelty_inconclusive": {str(k): int(n) for k, n in unsure.value_counts().items()},
        "leo_flux": outcomes(table["leo_flux"]),
        # Per LEO-Vetter test, the signals it could not judge.
        "leo_unknown": dict(sorted(leo_unknown.items())),
        "pixels_ran": int(reached.sum()),
        "pixels": outcomes(table.loc[reached, "pixels"]),
        "known_to_spoc": int(table["novelty_category"].eq("known_to_spoc").sum()),
        "timing_suspect_signals": int((table["timing_suspect_transits"] > 0).sum()),
        "shortlisted": int(table["shortlisted"].astype(bool).sum()),
    }


def _listing(counts: dict) -> str:
    return ", ".join(f"{k} {n}" for k, n in counts.items()) or "none"


def _md_rows(frame: pd.DataFrame, cols: list[str]) -> list[str]:
    def cell(v) -> str:
        return f"{v:.6g}" if isinstance(v, float) else str(v)

    head = "| " + " | ".join(cols) + " |"
    rule = "|" + "|".join("---" for _ in cols) + "|"
    body = ["| " + " | ".join(cell(r[c]) for c in cols) + " |" for r in frame.to_dict("records")]
    return [head, rule, *body, ""]


def _summary(
    table: pd.DataFrame, counts: dict, provenance: dict, n_sample: int, incomplete: dict
) -> str:
    threshold = provenance["threshold"]
    ran = {
        "novelty": counts["signals"],
        "leo_flux": counts["signals"],
        "pixels": counts["pixels_ran"],
    }
    lines = [
        f"# Triage ({provenance['run_id']})",
        "",
        f"Search `{provenance['search_run']}`: {n_sample} sample signals. Threshold: SDE "
        f"{threshold['value']:.2f} from `{threshold['run_id']}`. Signals at or above it: "
        f"{counts['signals']}.",
        "",
        "| step | ran | pass | fail | inconclusive |",
        "|---|---|---|---|---|",
        *(
            f"| {step} | {ran[step]} | " + " | ".join(str(counts[step][o]) for o in OUTCOMES) + " |"
            for step in STEPS
        ),
        "",
        "Pixels ran on the signals that passed novelty and the flux tests.",
        f"Novelty inconclusive by category: {_listing(counts['novelty_inconclusive'])}.",
        f"LEO-Vetter tests left unknown, in signals: {_listing(counts['leo_unknown'])}.",
        f"Signals with transits in timing-suspect sectors: {counts['timing_suspect_signals']}.",
        f"Known to SPOC only: {counts['known_to_spoc']}. Shortlisted: {counts['shortlisted']}.",
        "",
    ]
    short = table[table["shortlisted"].astype(bool)]
    if len(short):
        cols = ["tic", "rank", "period", "t0", "duration", "depth", "sde"]
        down = "; ".join(f"TIC {tic} ({', '.join(names)})" for tic, names in incomplete.items())
        lines += ["## Shortlist", ""]
        lines += _md_rows(short, [*cols, "timing_suspect_transits", "ruwe"])
        lines += [
            f"Literature searched for {len(set(short['tic']))} shortlisted stars (`literature/`); "
            f"incomplete for: {down or 'none'}.",
            "",
        ]
    held = table[
        table["novelty"].eq("pass") & table["leo_flux"].eq("pass") & table["pixels"].ne("pass")
    ]
    if len(held):
        lines += ["## Passed novelty and the flux tests, not pixels", ""]
        lines += _md_rows(held, ["tic", "rank", "sde", "ruwe", "pixels", "pixels_reason"])
    lines.append("Every row is a candidate signal, not a confirmed planet.")
    return "\n".join(lines) + "\n"


def cmd_run(args) -> int:
    search_prov = json.loads((args.search / "provenance.json").read_text())
    threshold = read_threshold(args.threshold / "threshold.json")
    crit_triage = load_criteria(args.criteria_triage)
    crit_search = _refuse(args, search_prov, threshold, crit_triage)
    known = load_v2_catalog(args.catalogs)
    value = float(threshold["threshold"])
    sample, signals = _sample_signals(args.search, value)
    # LEO-Vetter and the transit counts must see the light curves the search found the signals in.
    tics = sorted({int(t) for t in signals["tic"]})
    check_light_curves(pd.read_parquet(args.search / "stars.parquet"), tics, args.workers, "search")
    run = start_run("triage", [crit_search, crit_triage], args.production, sys.argv)
    run.record("search_run", args.search.resolve().name)
    run.record(
        "threshold",
        {"value": value, "file": "threshold.json", "run_id": args.threshold.resolve().name},
    )
    for name in ("signals", "stars"):
        run.record_input(f"search_{name}", args.search / f"{name}.parquet")
    run.record_input("threshold", args.threshold / "threshold.json")
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    for name, path in snapshot_inputs(args.mask_catalogs).items():
        run.record_input(f"mask_{name}", path)
    stars = pd.read_parquet(args.targets).set_index("tic")
    novelty_cfg, match = crit_triage["novelty"], crit_search["match"]
    evidence: dict[tuple[int, int], dict] = {}
    rows = []
    for s in signals.to_dict("records"):
        key = (int(s["tic"]), int(s["rank"]))
        result = judge_novelty(_star(stars, key[0]), _eph(s), known, novelty_cfg, match)
        evidence[key] = {"signal": s, "novelty": result.to_dict()}
        rows.append(
            {
                **s,
                "novelty": str(result.outcome),
                "novelty_category": result.evidence.get("category", ""),
                "novelty_reason": scrub(result.reason),
            }
        )
    masks = load_known(args.mask_catalogs)
    detrend_cfg = crit_search["detrend"]
    # As the search masked them: known planets and candidates, not the TCE or binary rows.
    mask_sources = tuple(detrend_cfg["mask_sources"])
    fallback = detrend_cfg["fallback_duration_days"]
    jobs = [
        {
            "star": _star(stars, int(tic)),
            "rows": group.to_dict("records"),
            "known": known_ephemerides(masks, int(tic), fallback, mask_sources),
            "detrend": detrend_cfg,
            "triage": crit_triage.values,
        }
        for tic, group in signals.groupby("tic")
    ]
    leo = {
        (r["tic"], r["rank"]): r
        for batch in run_jobs(_leo_star_job, jobs, args.workers)
        for r in batch
    }
    ready = [
        (int(r["tic"]), int(r["rank"]))
        for r in rows
        if r["novelty"] == "pass"
        and leo[(int(r["tic"]), int(r["rank"]))]["leo"]["outcome"] == "pass"
    ]
    # transit-diffImage names its files by TIC, planet number and sector, so every signal of every run
    # gets a directory of its own.
    tdi = data_dir() / "tdi" / run.provenance["run_id"]
    pixel_jobs = [
        {
            "metrics": leo[key]["metrics"],
            "star": _star(stars, key[0]),
            "sectors": leo[key]["sectors"],
            "cfg": crit_triage["pixels"],
            "tdi": tdi / f"{key[0]}-{key[1]}",
        }
        for key in ready
    ]
    # TESScut allows 5 requests a second; four signals at a time stays well inside it.
    pixels = dict(zip(ready, run_jobs(_pixel_job, pixel_jobs, min(4, args.workers)), strict=True))
    not_run = inconclusive("pixels", "not run: novelty or the flux tests did not pass").to_dict()
    out = []
    for row in rows:
        key = (int(row["tic"]), int(row["rank"]))
        flux, pix = leo[key], pixels.get(key, not_run)
        evidence[key] |= {
            "leo_flux": flux["leo"],
            "pixels": pix,
            "timing_suspect_transits": flux["timing_suspect_transits"],
        }
        out.append(
            {
                **row,
                "leo_flux": flux["leo"]["outcome"],
                "leo_disposition": flux["leo"]["evidence"].get("disposition"),
                "leo_reason": scrub(flux["leo"]["reason"]),
                "leo_unknown": scrub(", ".join(flux["unknown"])),
                "pixels": pix["outcome"],
                "pixels_reason": scrub(pix["reason"]),
                "timing_suspect_transits": flux["timing_suspect_transits"],
                "ruwe": _number(stars.loc[key[0]].get("ruwe")),
                # Rule 5.1: only explicit passes; a check that could not judge keeps the signal off.
                "shortlisted": row["novelty"] == "pass"
                and flux["leo"]["outcome"] == "pass"
                and pix["outcome"] == "pass",
            }
        )
    table = pd.DataFrame(out, columns=[*signals.columns, *RESULT_COLUMNS])
    short = table["shortlisted"].astype(bool)
    (run.path / "evidence").mkdir()
    for (tic, rank), item in evidence.items():
        run.write_json(f"evidence/{tic}-{rank}.json", item)
    (run.path / "literature").mkdir()
    session = requests.Session()
    incomplete = {}
    for tic in sorted({int(t) for t in table.loc[short, "tic"]}):
        found = literature.search(tic, session)
        run.write_json(f"literature/{tic}.json", found)
        down = [name for name, r in found.items() if r["status"] != "ok"]
        if down:
            incomplete[tic] = down
    table.to_parquet(run.path / "signals.parquet")
    table.to_csv(run.path / "signals.csv", index=False)
    table[short].to_csv(run.path / "shortlist.csv", index=False)
    table[table["novelty_category"].eq("known_to_spoc")].to_csv(
        run.path / "known_to_spoc.csv", index=False
    )
    counts = _counts(table, Counter(u.split(":")[0] for r in leo.values() for u in r["unknown"]))
    summary = _summary(table, counts, run.provenance, len(sample), incomplete)
    (run.path / "summary.md").write_text(summary)
    run.finish(
        threshold=value,
        sample_signals=len(sample),
        **counts,
        literature_incomplete=sorted(incomplete),
    )
    print(f"triage: {counts['shortlisted']} shortlisted of {counts['signals']} -> {run.path}")
    return 0


def _published_files(source: Path) -> list[Path]:
    provenance = json.loads((source / "provenance.json").read_text())
    if provenance.get("stage") != "triage":
        raise SystemExit(f"run {source.name} is not a triage run")
    threshold = runs_dir() / provenance["threshold"]["run_id"] / "threshold.json"
    # The shortlist goes out with the threshold it was cut at, exactly as triage read it.
    if not threshold.is_file() or (
        sha256_file(threshold) != provenance["inputs"]["threshold"]["sha256"]
    ):
        raise SystemExit(
            f"{threshold.parent.name}/threshold.json is not the threshold file this triage read"
        )
    return [*(source / name for name in PUBLISHED), threshold]


def cmd_publish(args) -> int:
    publish_run(args.run, repo_root(), "triage", _published_files)
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "triage", help="the null threshold, triage of a search's signals, and publishing"
    )
    modes = p.add_subparsers(dest="mode", required=True)
    t = modes.add_parser("threshold", help="the detection threshold from a null (scrambled) search")
    t.add_argument("--null", type=Path, required=True, help="the null search's run directory")
    t.add_argument("--targets", type=Path, required=True)
    t.add_argument("--catalogs", type=Path, required=True, help="a v2 snapshot (kinds, TCEs, EBs)")
    t.add_argument(
        "--mask-catalogs", type=Path, required=True, help="the snapshot the null masked with"
    )
    t.set_defaults(func=cmd_threshold)
    r = modes.add_parser("run", help="triage a production search's signals")
    r.add_argument("--search", type=Path, required=True, help="the search's run directory")
    r.add_argument("--threshold", type=Path, required=True, help="the threshold run's directory")
    r.add_argument("--catalogs", type=Path, required=True, help="a v2 snapshot (kinds, TCEs, EBs)")
    r.add_argument(
        "--mask-catalogs", type=Path, required=True, help="the snapshot the search masked with"
    )
    r.add_argument("--targets", type=Path, required=True)
    r.set_defaults(func=cmd_run)
    for mode in (t, r):
        mode.add_argument("--criteria-triage", type=Path, default=Path("criteria/triage-v1.toml"))
        mode.add_argument("--workers", type=int, default=8)
        mode.add_argument("--production", action="store_true")
    pub = modes.add_parser("publish", help="copy a triage run's results into results/triage/")
    pub.add_argument("--run", required=True)
    pub.set_defaults(func=cmd_publish)
