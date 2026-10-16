"""Benchmarks: recover known planets and injected transits, and compare search engines."""

import sys
import time
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs  # noqa: E402
from tess_hunt.config import lc_dir, load_criteria  # noqa: E402
from tess_hunt.detrend import detrend  # noqa: E402
from tess_hunt.ephemeris import Ephemeris  # noqa: E402
from tess_hunt.inject import Injection, draw, inject  # noqa: E402
from tess_hunt.lightcurve import LightCurve  # noqa: E402
from tess_hunt.pool import process_pool  # noqa: E402
from tess_hunt.provenance import publish_run, repo_root, sha256_file, start_run  # noqa: E402
from tess_hunt.recovery import classify  # noqa: E402
from tess_hunt.search import (  # noqa: E402
    # The production search's status gate; search.py is frozen, so it keeps its private name.
    _search_status,
    read_threshold,
    search_code_sha256,
    search_star,
    star_params,
    stellar_density,
)
from tess_hunt.targets import covered_sources  # noqa: E402
from tess_hunt.transit import light_curve  # noqa: E402

ENGINES = {
    "bls30": {"engine": "bls", "bin_minutes": 30.0},
    "bls10": {"engine": "bls", "bin_minutes": 10.0},
}
PERIOD_EDGES = [1, 2, 4, 8, 16, 40]
RADIUS_EDGES = [0.5, 1, 2, 4, 8, 16]
SNR_EDGES = [0, 5, 7, 10, 15, 20, 50, np.inf]
SEARCHED_COLUMNS = [
    "engine",
    "expected_snr",
    "inj_period",
    "inj_rp_rearth",
    "recovered",
    "alias",
    "runtime_s",
]


def _replayed(row: dict) -> Injection:
    return Injection(
        float(row["inj_period"]),
        float(row["inj_t0"]),
        float(row["inj_rp_rearth"]),
        float(row["inj_b"]),
        float(row["inj_rp_rs"]),
        float(row["inj_a_rs"]),
        float(row["inj_duration"]),
    )


def injection_job(job: tuple) -> list[dict]:
    star, lc_path, known_ephs, crit, engines, per_star, seed, replay, level = job
    # Seeded per star, so two runs inject the same planets into a star whatever its place in the list.
    rng = np.random.default_rng([seed, int(star["tic"])])
    bench, search = crit["benchmark"], crit["search"]
    u = (bench["inject_u1"], bench["inject_u2"])
    if replay:
        bases = [{"tic": int(star["tic"]), "injection": int(r["injection"])} for r in replay]
        draws = [_replayed(r) for r in replay]
    else:
        bases = [{"tic": int(star["tic"]), "injection": k} for k in range(per_star)]
        draws = None
    try:
        rstar, mstar, assumed = star_params(star)
        rho = stellar_density(star, rstar, mstar)
        bases = [{**base, "assumed_solar": assumed} for base in bases]
        # The cached light curve can be rewritten by a later fetch; the hash ties each row to its bytes.
        digest = sha256_file(lc_path)
        bases = [{**base, "lc_sha256": digest} for base in bases]
        lc = LightCurve.load(lc_path)
        # The search stage skips a star whose fetch kept too few sectors; injecting into it would
        # measure a different sample.
        if not covered_sources(lc.sources, crit["sample"]):
            return [{**base, "status": "not_covered_after_fetch"} for base in bases]
    except Exception as exc:  # one bad star must not stop the run; it is recorded, not hidden
        error = f"{type(exc).__name__}: {exc}"
        return [{**base, "status": "error", "error": error} for base in bases]
    rows = []
    for i, base in enumerate(bases):
        inj = (
            draws[i]
            if draws
            else draw(
                rng,
                lc.time,
                rstar,
                mstar,
                (search["period_min_days"], search["period_max_days"]),
                (bench["inject_rp_min_rearth"], bench["inject_rp_max_rearth"]),
                search["min_transits"],
            )
        )
        if inj is None:
            rows.append({**base, "status": "no_draw"})
            continue
        try:
            flat = detrend(inject(lc, inj, u), crit["detrend"], known_ephs)
            # The search stage skips these stars; scoring them would measure a different sample.
            if len(flat.time) < search["min_points"]:
                rows.append({**base, "status": "too_few_points", "n_points": len(flat.time)})
                continue
            # The signal the search sees, after limb darkening, impact parameter and exposure smearing.
            model = light_curve(
                flat.time, flat.exposure_days(), inj.t0, inj.period, inj.rp_rs, inj.a_rs, inj.b, *u
            )
            expected_snr = float(np.sqrt(np.sum(((1.0 - model) / flat.flux_err) ** 2)))
            # Engines are compared on the same injections, so a failure drops the injection for all.
            scored = []
            for name in engines:
                started = time.perf_counter()
                result = search_star(flat, rstar, mstar, {**search, **ENGINES[name]}, rho)
                scored.append(
                    {
                        **base,
                        # As in the search, too few bins or a non-finite top SDE take the
                        # injection out of the sample.
                        "status": _search_status(result, search["min_points"]),
                        "engine": name,
                        "runtime_s": time.perf_counter() - started,
                        **{f"inj_{key}": value for key, value in asdict(inj).items()},
                        "expected_snr": expected_snr,
                        **classify(inj.ephemeris(), result.signals, crit["match"], level),
                        **result.diagnostics(),
                    }
                )
            rows += scored
        except Exception as exc:  # one bad injection must not stop the run; it is recorded
            rows.append({**base, "status": "error", "error": f"{type(exc).__name__}: {exc}"})
    return rows


def known_job(job: tuple) -> dict:
    planet, star, lc_path, crit = job
    base = {k: planet[k] for k in ("toi", "tic", "period", "depth_ppm", "planet_snr", "required")}
    missed = {"recovered": False, "alias": False}
    try:
        rstar, mstar, base["assumed_solar"] = star_params(star)
        rho = stellar_density(star, rstar, mstar)
        if not Path(lc_path).exists():
            return {**base, "status": "no_light_curve", **missed}
        base["lc_sha256"] = sha256_file(lc_path)
        # Masks off: these planets are the positive controls.
        flat = detrend(LightCurve.load(lc_path), crit["detrend"])
        if len(flat.time) < crit["search"]["min_points"]:
            return {**base, "status": "too_few_points", "n_points": len(flat.time), **missed}
        result = search_star(flat, rstar, mstar, crit["search"], rho)
    except Exception as exc:  # one bad star must not stop the run; it is recorded, not hidden
        return {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}", **missed}
    truth = Ephemeris(planet["period"], planet["t0"], planet["duration"])
    return {
        **base,
        "status": "ok",
        **classify(truth, result.signals, crit["match"], crit["benchmark"]["provisional_sde"]),
        **result.diagnostics(),
    }


def searched(rows: pd.DataFrame) -> pd.DataFrame:
    """The rows that reached the search. Only they carry an engine and its scores, so a run where none
    did gets an empty frame with those columns: empty tables and maps, not a KeyError."""
    ok = rows[rows["status"] == "ok"]
    return ok if len(ok) else pd.DataFrame(columns=SEARCHED_COLUMNS, dtype=float)


def completeness(rows: pd.DataFrame, column: str, edges) -> pd.DataFrame:
    ok = searched(rows)
    out = []
    for engine, g in ok.groupby("engine"):
        bins = pd.cut(g[column], edges, right=False)
        stats = g.groupby(bins, observed=False)["recovered"].agg(["sum", "count"])
        for interval, row in stats.iterrows():
            out.append(
                {
                    "engine": engine,
                    "bin": str(interval),
                    "count": int(row["count"]),
                    "fraction": float(row["sum"] / row["count"]) if row["count"] else np.nan,
                }
            )
    return pd.DataFrame(out, columns=["engine", "bin", "count", "fraction"])


def completeness_map(rows: pd.DataFrame, engine: str) -> pd.DataFrame:
    ok = searched(rows)
    g = ok[ok["engine"] == engine]
    p = pd.cut(g["inj_period"], PERIOD_EDGES, right=False)
    r = pd.cut(g["inj_rp_rearth"], RADIUS_EDGES, right=False)
    stats = g.groupby([r, p], observed=False)["recovered"].agg(["sum", "count"]).reset_index()
    stats.columns = ["radius_bin", "period_bin", "recovered", "count"]
    stats["fraction"] = stats["recovered"] / stats["count"].where(stats["count"] > 0)
    stats["radius_bin"] = stats["radius_bin"].astype(str)
    stats["period_bin"] = stats["period_bin"].astype(str)
    return stats


def plot_map(table: pd.DataFrame, engine: str, path: Path) -> None:
    frac = table.pivot(index="radius_bin", columns="period_bin", values="fraction")
    count = table.pivot(index="radius_bin", columns="period_bin", values="count")
    # pd.cut writes every bin in the edges' common dtype ("[0.5, 1.0)", not "[0.5, 1)"), so the
    # labels must come from the same constructor or the reindex below finds no rows.
    rows = [str(i) for i in pd.IntervalIndex.from_breaks(RADIUS_EDGES, closed="left")]
    cols = [str(i) for i in pd.IntervalIndex.from_breaks(PERIOD_EDGES, closed="left")]
    frac, count = frac.reindex(index=rows, columns=cols), count.reindex(index=rows, columns=cols)
    fig, ax = plt.subplots(figsize=(7, 5))
    # Fraction is a magnitude: one hue, light to dark. Every cell is labelled so colour is never the only cue.
    image = ax.imshow(
        frac.to_numpy(float), origin="lower", vmin=0, vmax=1, cmap="Blues", aspect="auto"
    )
    for i in range(len(rows)):
        for j in range(len(cols)):
            f, n = frac.iat[i, j], count.iat[i, j]
            label = "no data" if not n or np.isnan(n) else f"{f:.2f}\nn={int(n)}"
            ax.text(
                j,
                i,
                label,
                ha="center",
                va="center",
                fontsize=8,
                color="white" if (n and not np.isnan(f) and f > 0.6) else "#222222",
            )
    ax.set_xticks(
        range(len(cols)),
        [f"{a:g}-{b:g}" for a, b in zip(PERIOD_EDGES, PERIOD_EDGES[1:], strict=False)],
    )
    ax.set_yticks(
        range(len(rows)),
        [f"{a:g}-{b:g}" for a, b in zip(RADIUS_EDGES, RADIUS_EDGES[1:], strict=False)],
    )
    ax.set_xlabel("orbital period (days)")
    ax.set_ylabel("planet radius (Earth radii)")
    ax.set_title(f"Injection recovery, {engine}")
    fig.colorbar(image, ax=ax, label="fraction recovered")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)


def md_table(df: pd.DataFrame) -> str:
    def cell(v) -> str:
        return f"{v:.3g}" if isinstance(v, float) else str(v)

    head = "| " + " | ".join(map(str, df.columns)) + " |"
    rule = "|" + "|".join("---" for _ in df.columns) + "|"
    body = ["| " + " | ".join(cell(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join([head, rule, *body])


def _star_index(targets: Path) -> dict[int, dict]:
    return {int(r["tic"]): r for r in pd.read_parquet(targets).to_dict("records")}


def add_parser(sub) -> None:
    p = sub.add_parser("benchmark", help="known-planet and injection-recovery benchmarks")
    modes = p.add_subparsers(dest="mode", required=True)
    k = modes.add_parser("known", help="recover the known-planet set with masks off")
    k.add_argument("--known", type=Path, default=Path("benchmarks/known_planets.csv"))
    k.add_argument("--targets", type=Path, required=True)
    k.set_defaults(func=cmd_known)
    i = modes.add_parser("inject", help="injection-recovery per engine")
    i.add_argument("--targets", type=Path, required=True)
    i.add_argument("--catalogs", type=Path, required=True)
    i.add_argument("--engines", default="bls30,bls10")
    i.add_argument("--per-star", type=int, default=2)
    i.add_argument("--seed", type=int, default=7)
    i.add_argument("--limit", type=int, default=0)
    i.add_argument(
        "--replay", type=Path, help="injections.csv of an earlier run: inject exactly its planets"
    )
    i.add_argument("--replay-engine", default="bls30")
    i.add_argument(
        "--threshold",
        type=Path,
        help="threshold.json: classify and stop at the production threshold",
    )
    i.add_argument("--sample", type=int, default=0, help="draw this many stars at random")
    i.set_defaults(func=cmd_inject)
    for mode in (k, i):
        mode.add_argument("--criteria", type=Path, default=Path("criteria/search-v2.toml"))
        mode.add_argument(
            "--manifest", type=Path, help="the fetch run's fetch_manifest.jsonl, to record"
        )
        mode.add_argument("--workers", type=int, default=8)
        mode.add_argument("--production", action="store_true")
    pub = modes.add_parser("publish", help="copy a benchmark run's summary into results/")
    pub.add_argument("--run", required=True)
    pub.set_defaults(func=cmd_publish)


def cmd_known(args) -> int:
    criteria = load_criteria(args.criteria)
    run = start_run("benchmark-known", [criteria], args.production, sys.argv)
    run.record_input("known", args.known)
    run.record_input("targets", args.targets)
    if args.manifest:
        run.record_input("fetch_manifest", args.manifest)
    known = pd.read_csv(args.known, dtype={"toi": str})
    stars = _star_index(args.targets)
    jobs = [
        (
            p,
            stars.get(int(p["tic"]), {"tic": p["tic"]}),
            lc_dir() / f"{int(p['tic'])}.npz",
            criteria.values,
        )
        for p in known.to_dict("records")
    ]
    with process_pool(args.workers) as pool:
        table = pd.DataFrame(list(pool.map(known_job, jobs)))
    table.to_csv(run.path / "known.csv", index=False)
    missed = table[table["required"] & ~table["recovered"]]
    summary = [
        f"# Known-planet recovery ({run.provenance['run_id']})",
        "",
        f"Required planets recovered: {int((table['required'] & table['recovered']).sum())} of {int(table['required'].sum())}.",
        f"All planets recovered: {int(table['recovered'].sum())} of {len(table)}.",
        "",
        # Rows that never reached the search carry no classify columns; reindex fills them with NaN.
        md_table(
            table.reindex(
                columns=[
                    "toi",
                    "tic",
                    "period",
                    "depth_ppm",
                    "planet_snr",
                    "required",
                    "assumed_solar",
                    "status",
                    "recovered",
                    "alias",
                    "found_period",
                    "sde",
                    "rank",
                ]
            )
        ),
        "",
    ]
    (run.path / "summary.md").write_text("\n".join(summary))
    run.finish(
        planets=len(table), recovered=int(table["recovered"].sum()), required_missed=len(missed)
    )
    print("\n".join(summary))
    return 1 if len(missed) else 0


def cmd_inject(args) -> int:
    criteria = load_criteria(args.criteria)
    engines = [e.strip() for e in args.engines.split(",")]
    unknown = set(engines) - set(ENGINES)
    if unknown:
        raise SystemExit(f"unknown engines: {sorted(unknown)}")
    if args.production and not args.threshold:
        # As the production search does (spec 5.6): production is judged at the null's threshold.
        raise SystemExit("a production injection run needs --threshold")
    search = dict(criteria["search"])
    level = criteria["benchmark"]["provisional_sde"]
    if args.threshold:
        threshold = read_threshold(args.threshold)
        hashes = (threshold["search_criteria_sha256"], threshold["search_code_sha256"])
        if hashes != (criteria.sha256, search_code_sha256(repo_root())):
            raise SystemExit(f"{args.threshold} belongs to other search criteria or code")
        search["continue_sde"] = level = float(threshold["threshold"])
    run = start_run("benchmark-inject", [criteria], args.production, sys.argv)
    if args.threshold:
        run.record_input("threshold", args.threshold)
        run.record(
            "threshold",
            {
                "value": level,
                "file": args.threshold.name,
                # threshold.json sits in the run directory that computed it.
                "run_id": args.threshold.resolve().parent.name,
            },
        )
    else:
        run.record("threshold", None)
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    if args.manifest:
        run.record_input("fetch_manifest", args.manifest)
    known = load_known(args.catalogs)
    fallback = criteria["detrend"]["fallback_duration_days"]
    mask_sources = tuple(criteria["detrend"]["mask_sources"])
    stars = [
        s
        for s in pd.read_parquet(args.targets).to_dict("records")
        if (lc_dir() / f"{int(s['tic'])}.npz").exists()
    ]
    replays: dict[int, list[dict]] = {}
    if args.replay:
        run.record_input("replay", args.replay)
        # The default parser is not correctly rounded; it would move M1's planets by a few ULP.
        published = pd.read_csv(args.replay, float_precision="round_trip")
        published = published[
            (published["engine"] == args.replay_engine) & (published["status"] == "ok")
        ]
        replays = {int(tic): rows.to_dict("records") for tic, rows in published.groupby("tic")}
        stars = sorted((s for s in stars if int(s["tic"]) in replays), key=lambda s: int(s["tic"]))
    if args.limit:
        stars = stars[: args.limit]
    if args.sample and len(stars) > args.sample:
        picks = np.random.default_rng(args.seed).choice(len(stars), size=args.sample, replace=False)
        stars = [stars[i] for i in sorted(picks)]
    crit = {**criteria.values, "search": search}
    jobs = [
        (
            s,
            lc_dir() / f"{int(s['tic'])}.npz",
            known_ephemerides(known, int(s["tic"]), fallback, mask_sources),
            crit,
            engines,
            args.per_star,
            args.seed,
            replays.get(int(s["tic"])),
            level,
        )
        for s in stars
    ]
    with process_pool(args.workers) as pool:
        rows = pd.DataFrame([row for batch in pool.map(injection_job, jobs) for row in batch])
    rows.to_csv(run.path / "injections.csv", index=False)
    by_snr = completeness(rows, "expected_snr", SNR_EDGES)
    by_snr.to_csv(run.path / "completeness_snr.csv", index=False)
    ok = searched(rows)
    statuses = rows["status"].value_counts()
    source = f"the threshold in `{args.threshold.name}`" if args.threshold else "`provisional_sde`"
    lines = [
        f"# Injection recovery ({run.provenance['run_id']})",
        "",
        f"Recovered: a signal at the injected ephemeris with SDE {level:g} or above ({source}).",
        "",
    ]
    if args.replay:
        replayed = sum(len(replays[int(s["tic"])]) for s in stars)
        lines += [
            f"Replay of an earlier run's `{args.replay.name}` (sha256 in provenance.json): {replayed} "
            f"of its {len(published)} `{args.replay_engine}` injections with status ok. "
            "`--per-star` is ignored, and `--seed` only chooses the stars for `--sample`.",
            "",
        ]
    if ok.empty:
        counts = ", ".join(f"{status} {n}" for status, n in statuses.items())
        lines += [
            f"No injection reached the search ({counts}); the tables and maps below are empty.",
            "",
        ]
    else:
        overview = (
            ok.groupby("engine")
            .agg(
                injections=("recovered", "size"),
                recovered=("recovered", "mean"),
                alias=("alias", "mean"),
                median_runtime_s=("runtime_s", "median"),
            )
            .reset_index()
        )
        lines += [md_table(overview), ""]
    lines += ["## By expected SNR", "", md_table(by_snr), ""]
    for engine in engines:
        table = completeness_map(rows, engine)
        table.to_csv(run.path / f"completeness_{engine}.csv", index=False)
        plot_map(table, engine, run.path / f"completeness_{engine}.png")
        lines += [f"![{engine}](completeness_{engine}.png)", ""]
    (run.path / "summary.md").write_text("\n".join(lines))
    run.finish(
        stars=len(stars),
        injections=int(len(ok)),
        **{
            s: int(statuses.get(s, 0))
            for s in (
                "no_draw",
                "too_few_points",
                "nonfinite_sde",
                "not_covered_after_fetch",
                "error",
            )
        },
    )
    print("\n".join(lines))
    return 0


def cmd_publish(args) -> int:
    def files(source: Path) -> list[Path]:
        return [p for p in source.iterdir() if p.suffix in (".md", ".csv", ".png", ".json")]

    publish_run(args.run, repo_root(), "benchmarks", files)
    return 0
