"""vet-v3's controls (M3 design, sections 1 and 4.3): each check's outcome on the known planets and the negative
controls, read from a finished vetting run, the TRICERATOPS runs on it and the pixel check on the known planets."""

import json
import sys
from pathlib import Path

import pandas as pd

from tess_hunt.benchmark import md_table
from tess_hunt.completeness import _finished
from tess_hunt.provenance import scrub, start_run
from tess_hunt.triage import OUTCOMES

KINDS = ("control", "negative_control")
# Outcomes outside checks.json's `checks` list, so the rates and the fails table add them after it: the neighbour
# table and TRICERATOPS, judged under vet-v3's [neighbours] and [triceratops], and triage's pixel check.
BESIDE = ("neighbours", "pixels", "triceratops")
TRICERATOPS_VALUES = ("fpp_mean", "fpp_sd", "nfpp_mean", "nfpp_sd")


def _controls(path: Path) -> dict[str, dict]:
    """Each control's and negative control's checks.json, controls first, then by name."""
    vetted = {
        p.name: json.loads((p / "checks.json").read_text()) for p in (path / "signals").iterdir()
    }
    chosen = {n: c for n, c in vetted.items() if c["signal"]["kind"] in KINDS}
    return {
        n: chosen[n]
        for n in sorted(chosen, key=lambda n: (KINDS.index(chosen[n]["signal"]["kind"]), n))
    }


def _records(runs: list[Path], names: list[str]) -> dict[str, list[dict]]:
    """Each signal's TRICERATOPS records, in the order the runs were given."""
    found = {n: [] for n in names}
    for i, path in enumerate(runs, 1):
        for name in names:
            file = path / "signals" / name / "triceratops.json"
            if file.is_file():
                found[name].append(
                    {
                        "index": i,
                        "run_id": path.resolve().name,
                        "file": file,
                        **json.loads(file.read_text()),
                    }
                )
    return found


def _row(name: str, checks: dict, order: list[str], pixel: dict | None, judged: list[dict]) -> dict:
    outcomes = {c["check"]: c["outcome"] for c in checks["checks"]}
    neighbours = checks["neighbours"]
    table = neighbours["evidence"].get("table")
    *earlier, used = judged
    e = used["evidence"]
    return {
        "name": name,
        "kind": checks["signal"]["kind"],
        "tic": int(checks["star"]["tic"]),
        **{c: outcomes[c] for c in order},
        "neighbours": neighbours["outcome"],
        # None where the table was never built: no count, rather than none counted.
        "possible_hosts": None if table is None else sum(bool(r["possible"]) for r in table),
        "pixels": None if pixel is None else pixel["pixels"],
        "offset_qual_arcsec": None if pixel is None else pixel["offset_qual_arcsec"],
        "triceratops": used["outcome"],
        **{k: e[k] for k in TRICERATOPS_VALUES},
        "blockers": scrub("; ".join(e["blockers"])),
        "triceratops_run": used["run_id"],
        "superseded": "; ".join(
            f"{s['run_id']}: {s['outcome']}, {scrub(s['reason'])}" for s in earlier
        ),
    }


def pass_rates(table: pd.DataFrame, checks: list[str], left_out: list[str]) -> pd.DataFrame:
    """Each check's outcomes over the `control` rows, all of them and without `left_out`."""
    controls = table[table["kind"].eq("control")]
    out = []
    for label, part in (
        ("all", controls),
        ("without_left_out", controls[~controls["name"].isin(left_out)]),
    ):
        for check in checks:
            counts = {o: int(part[check].eq(o).sum()) for o in OUTCOMES}
            rate = counts["pass"] / len(part) if len(part) else float("nan")
            out.append(
                {
                    "controls": label,
                    "check": check,
                    "signals": len(part),
                    **counts,
                    "pass_rate": rate,
                }
            )
    return pd.DataFrame(out)


def _reasons(checks: dict, pixel: dict | None, judged: list[dict]) -> dict[str, str | None]:
    return {
        **{c["check"]: c["reason"] for c in checks["checks"]},
        "neighbours": checks["neighbours"]["reason"],
        "pixels": None if pixel is None else pixel["pixels_reason"],
        "triceratops": judged[-1]["reason"],
    }


def _flagged(table: pd.DataFrame, checks: list[str], reasons: dict[str, dict]) -> pd.DataFrame:
    """Each fail and inconclusive among the `control` rows, by check, with its reason."""
    controls = table[table["kind"].eq("control")]
    return pd.DataFrame(
        [
            {"check": check, "signal": name, "outcome": o, "reason": scrub(reasons[name][check])}
            for check in checks
            for o in ("fail", "inconclusive")
            for name in controls.loc[controls[check].eq(o), "name"]
        ],
        columns=["check", "signal", "outcome", "reason"],
    )


def _errors(provenance: dict) -> str:
    """A TRICERATOPS run's errors: a rerun that raised writes no record, so the summary would not show it was tried."""
    errors = provenance["summary"]["errors"]
    if not errors:
        return "none"
    return "; ".join(f"{name} ({scrub(error)})" for name, error in sorted(errors.items()))


def _negatives(table: pd.DataFrame) -> str:
    rows = table[table["kind"].eq("negative_control")]
    if rows.empty:
        return "None."
    # One column per negative control: their rows are too wide to read side by side.
    shown = rows.drop(columns="kind").set_index("name").T.astype(object)
    return md_table(shown.where(shown.notna(), "").reset_index(names=""))


def cmd_controls(args) -> int:
    vetted = _finished(args.vet_run, "vetting-run")
    vet_id = args.vet_run.resolve().name
    # It keeps the timing-suspect sectors in and never makes a call (decision 0022).
    if vetted.get("evidence_only"):
        raise SystemExit(
            f"{vet_id} is an evidence-only vetting run; the controls are judged on the main one"
        )
    if vetted["summary"]["errors"]:
        raise SystemExit(
            f"{vet_id} failed to vet {', '.join(sorted(vetted['summary']['errors']))}; a control without its "
            "checks can't be counted"
        )
    tric_ids = [path.resolve().name for path in args.triceratops]
    # A run given twice would list its own outcome as superseded.
    if len(set(tric_ids)) < len(tric_ids):
        raise SystemExit("a TRICERATOPS run is given more than once")
    tric_runs = {
        run_id: _finished(path, "vetting-triceratops")
        for run_id, path in zip(tric_ids, args.triceratops, strict=True)
    }
    for run_id, provenance in tric_runs.items():
        if provenance.get("vetting_run") != vet_id:
            raise SystemExit(
                f"{run_id} ran TRICERATOPS on vetting run {provenance.get('vetting_run')}, not {vet_id}"
            )
    pixel_run = _finished(args.pixels, "benchmark-pixel-completeness")
    pixel_id = args.pixels.resolve().name
    if args.production:
        given = {vet_id: vetted, **tric_runs, pixel_id: pixel_run}
        lacking = [run_id for run_id, p in given.items() if not p.get("production")]
        if lacking:
            raise SystemExit(
                f"production benchmark controls needs production runs, not {', '.join(lacking)}"
            )
    vet_criteria, pixel_criteria = vetted["criteria"][1]["file"], pixel_run["criteria"][0]["file"]
    controls = _controls(args.vet_run)
    names = list(controls)
    if not names:
        raise SystemExit(f"{vet_id} vetted no control or negative control")
    # A check missing from one signal would sit in a rate's count of signals but in none of its outcomes.
    order = [c["check"] for c in controls[names[0]]["checks"]]
    for name in names[1:]:
        theirs = [c["check"] for c in controls[name]["checks"]]
        if theirs != order:
            raise SystemExit(
                f"{name}'s checks ({', '.join(theirs)}) differ from {names[0]}'s ({', '.join(order)})"
            )
    records = _records(args.triceratops, names)
    unjudged = [n for n in names if not records[n]]
    if unjudged:
        raise SystemExit(f"no TRICERATOPS run given judged {', '.join(unjudged)}")
    # The default parser is not correctly rounded; it would move the offsets by a few ULP.
    pixels = pd.read_csv(
        args.pixels / "pixels.csv", dtype={"toi": str}, float_precision="round_trip"
    )
    by_name = {f"TOI-{p['toi']}": p for p in pixels.to_dict("records")}
    planets = {(n, int(p["tic"])) for n, p in by_name.items()}
    known = {
        (n, int(c["star"]["tic"])) for n, c in controls.items() if c["signal"]["kind"] == "control"
    }
    if planets != known:

        def listed(pairs: set) -> str:
            return ", ".join(f"{n} (TIC {t})" for n, t in sorted(pairs)) or "none"

        raise SystemExit(
            f"{pixel_id}'s planets are not {vet_id}'s controls: only in the pixel run {listed(planets - known)}; "
            f"only in the vetting run {listed(known - planets)}"
        )
    left_out = list(dict.fromkeys(args.leave_out))
    wrong = [n for n in left_out if n not in controls or controls[n]["signal"]["kind"] != "control"]
    if wrong:
        raise SystemExit(f"--leave-out takes a control {vet_id} vetted, not {', '.join(wrong)}")

    run = start_run("benchmark-controls", [], args.production, sys.argv)
    run.record("vetting_run", vet_id)
    run.record("triceratops_runs", tric_ids)
    run.record("pixel_run", pixel_id)
    run.record("left_out", left_out)
    run.record_input("vetting_provenance", args.vet_run / "provenance.json")
    for name in names:
        run.record_input(f"checks_{name}", args.vet_run / "signals" / name / "checks.json")
    for i, path in enumerate(args.triceratops, 1):
        run.record_input(f"triceratops_provenance_{i}", path / "provenance.json")
    for name in names:
        for r in records[name]:
            run.record_input(f"triceratops_{r['index']}_{name}", r["file"])
    run.record_input("pixel_provenance", args.pixels / "provenance.json")
    run.record_input("pixels", args.pixels / "pixels.csv")

    table = pd.DataFrame(
        [_row(n, controls[n], order, by_name.get(n), records[n]) for n in names]
    ).astype({"possible_hosts": "Int64"})
    table.to_csv(run.path / "controls.csv", index=False)
    checks = [*order, *BESIDE]
    rates = pass_rates(table, checks, left_out)
    rates.to_csv(run.path / "pass_rates.csv", index=False)
    superseded = pd.DataFrame(
        [
            {
                "signal": name,
                "run": s["run_id"],
                "outcome": s["outcome"],
                "reason": scrub(s["reason"]),
                "replaced_by": records[name][-1]["run_id"],
            }
            for name in names
            for s in records[name][:-1]
        ]
    )
    reasons = {n: _reasons(controls[n], by_name.get(n), records[n]) for n in names}
    flagged = _flagged(table, checks, reasons)
    n_controls = int(table["kind"].eq("control").sum())
    kept = n_controls - len(left_out)

    def rate_table(label: str) -> str:
        return md_table(rates[rates["controls"].eq(label)].drop(columns="controls"))

    lines = [
        f"# {Path(vet_criteria).stem} controls ({run.provenance['run_id']})",
        "",
        f"Vetting run `{vet_id}` judged {n_controls} controls (known planets, kind `control`) and "
        f"{len(table) - n_controls} negative controls under `{vet_criteria}`. Each row of `controls.csv` holds a "
        "signal's checks and neighbour-table outcome from that run, and its TRICERATOPS outcome from the last run "
        f"given that judged it. A known planet's pixel check comes from pixel-completeness run `{pixel_id}`: "
        f"`{pixel_criteria}`'s `[pixels]` at the catalog ephemeris. `vetting run` takes pixels from triage, and the "
        "controls never went through triage. `possible_hosts` counts the neighbour table's possible hosts; "
        "`offset_qual_arcsec` is the best-quality sector's centroid offset. `pass_rate` is pass over all the "
        "`signals` counted, inconclusives in the denominator. Novelty fails every known planet by design, since each "
        "is in the catalogs it checks against.",
        "",
        "## Inputs",
        "",
        f"- Vetting run: `{vet_id}`",
        "- TRICERATOPS runs, in the order given, with the signals each failed to judge:",
        *(f"  - `{run_id}`: {_errors(p)}" for run_id, p in tric_runs.items()),
        f"- Pixel-completeness run: `{pixel_id}`",
        "",
        f"## Pass rates over all {n_controls} controls",
        "",
        rate_table("all"),
        "",
        f"## Pass rates without the left-out controls ({kept} controls)",
        "",
        rate_table("without_left_out"),
        "",
        "## Left out",
        "",
        ", ".join(left_out) or "None.",
        "",
        "## Failed and inconclusive controls, by check",
        "",
        md_table(flagged) if len(flagged) else "None.",
        "",
        "## Negative controls",
        "",
        _negatives(table),
        "",
        "## Superseded TRICERATOPS outcomes",
        "",
        md_table(superseded) if len(superseded) else "None.",
        "",
    ]
    (run.path / "summary.md").write_text("\n".join(lines))
    run.finish(
        controls=n_controls,
        negative_controls=len(table) - n_controls,
        left_out=left_out,
        superseded=len(superseded),
    )
    print("\n".join(lines))
    return 0
