"""Benchmarks: recover known planets and injected transits, and compare search engines."""

import shutil
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from tess_hunt.catalogs import FILES, known_ephemerides, load_known  # noqa: E402
from tess_hunt.config import lc_dir, load_criteria, runs_dir  # noqa: E402
from tess_hunt.detrend import detrend  # noqa: E402
from tess_hunt.ephemeris import Ephemeris, ephemeris_match, in_transit  # noqa: E402
from tess_hunt.inject import draw, inject  # noqa: E402
from tess_hunt.lightcurve import LightCurve  # noqa: E402
from tess_hunt.provenance import repo_root, start_run  # noqa: E402
from tess_hunt.search import search_star, star_params  # noqa: E402

ENGINES = {
    "bls30": {"engine": "bls", "bin_minutes": 30.0},
    "bls10": {"engine": "bls", "bin_minutes": 10.0},
    "tls": {"engine": "tls", "bin_minutes": 30.0},
}
ALIASES = (0.5, 2.0, 1 / 3, 3.0)
PERIOD_EDGES = [1, 2, 4, 8, 16, 40]
RADIUS_EDGES = [0.5, 1, 2, 4, 8, 16]
SNR_EDGES = [0, 5, 7, 10, 15, 20, 50, np.inf]


def classify(truth: Ephemeris, signals, match_cfg: dict, threshold: float) -> dict:
    """Recovered: a signal at the true ephemeris at or above the threshold. Alias: only a harmonic matches."""
    sp, st = match_cfg["sigma_p"], match_cfg["sigma_t"]
    for s in signals:
        if ephemeris_match(s.ephemeris(), truth, (1.0,), sp, st) is not None:
            return {
                "recovered": bool(s.sde >= threshold),
                "alias": False,
                "found_period": s.period,
                "sde": s.sde,
                "rank": s.rank,
            }
    for s in signals:
        if ephemeris_match(s.ephemeris(), truth, ALIASES, sp, st) is not None:
            return {
                "recovered": False,
                "alias": True,
                "found_period": s.period,
                "sde": s.sde,
                "rank": s.rank,
            }
    top = signals[0] if signals else None
    return {
        "recovered": False,
        "alias": False,
        "found_period": top.period if top else np.nan,
        "sde": top.sde if top else np.nan,
        "rank": 0,
    }


def injection_job(job: tuple) -> list[dict]:
    star, lc_path, known_ephs, crit, engines, per_star, seed = job
    rng = np.random.default_rng(seed)
    lc = LightCurve.load(lc_path)
    rstar, mstar, assumed = star_params(star)
    bench, search = crit["benchmark"], crit["search"]
    rows = []
    for k in range(per_star):
        base = {"tic": int(star["tic"]), "injection": k, "assumed_solar": assumed}
        inj = draw(
            rng,
            lc.time,
            rstar,
            mstar,
            (search["period_min_days"], search["period_max_days"]),
            (bench["inject_rp_min_rearth"], bench["inject_rp_max_rearth"]),
            search["min_transits"],
        )
        if inj is None:
            rows.append({**base, "status": "no_draw"})
            continue
        flat = detrend(
            inject(lc, inj, (bench["inject_u1"], bench["inject_u2"])), crit["detrend"], known_ephs
        )
        n_in = int(in_transit(flat.time, inj.ephemeris()).sum())
        expected_snr = (
            float(inj.rp_rs**2 / np.median(flat.flux_err) * np.sqrt(n_in)) if n_in else 0.0
        )
        for name in engines:
            started = time.perf_counter()
            signals = search_star(flat, rstar, mstar, {**search, **ENGINES[name]})
            rows.append(
                {
                    **base,
                    "status": "ok",
                    "engine": name,
                    "runtime_s": time.perf_counter() - started,
                    **{f"inj_{key}": value for key, value in asdict(inj).items()},
                    "expected_snr": expected_snr,
                    **classify(inj.ephemeris(), signals, crit["match"], bench["provisional_sde"]),
                }
            )
    return rows


def known_job(job: tuple) -> dict:
    planet, star, lc_path, crit = job
    base = {k: planet[k] for k in ("toi", "tic", "period", "depth_ppm", "planet_snr", "required")}
    if not Path(lc_path).exists():
        return {**base, "status": "no_light_curve", "recovered": False, "alias": False}
    # Masks off: these planets are the positive controls.
    flat = detrend(LightCurve.load(lc_path), crit["detrend"])
    rstar, mstar, _ = star_params(star)
    signals = search_star(flat, rstar, mstar, crit["search"])
    truth = Ephemeris(planet["period"], planet["t0"], planet["duration"])
    return {
        **base,
        "status": "ok",
        **classify(truth, signals, crit["match"], crit["benchmark"]["provisional_sde"]),
    }


def completeness(rows: pd.DataFrame, column: str, edges) -> pd.DataFrame:
    ok = rows[rows["status"] == "ok"]
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
    g = rows[(rows["status"] == "ok") & (rows["engine"] == engine)]
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
    i.set_defaults(func=cmd_inject)
    for mode in (k, i):
        mode.add_argument("--criteria", type=Path, default=Path("criteria/search-v1.toml"))
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
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        table = pd.DataFrame(list(pool.map(known_job, jobs)))
    table.to_csv(run.path / "known.csv", index=False)
    missed = table[table["required"] & ~table["recovered"]]
    summary = [
        f"# Known-planet recovery ({run.provenance['run_id']})",
        "",
        f"Required planets recovered: {int((table['required'] & table['recovered']).sum())} of {int(table['required'].sum())}.",
        f"All planets recovered: {int(table['recovered'].sum())} of {len(table)}.",
        "",
        md_table(
            table[
                [
                    "toi",
                    "tic",
                    "period",
                    "depth_ppm",
                    "planet_snr",
                    "required",
                    "recovered",
                    "alias",
                    "found_period",
                    "sde",
                    "rank",
                ]
            ]
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
    run = start_run("benchmark-inject", [criteria], args.production, sys.argv)
    run.record_input("targets", args.targets)
    for name in FILES.values():
        run.record_input(name, args.catalogs / name)
    known = load_known(args.catalogs)
    fallback = criteria["detrend"]["fallback_duration_days"]
    stars = [
        s
        for s in pd.read_parquet(args.targets).to_dict("records")
        if (lc_dir() / f"{int(s['tic'])}.npz").exists()
    ]
    if args.limit:
        stars = stars[: args.limit]
    jobs = [
        (
            s,
            lc_dir() / f"{int(s['tic'])}.npz",
            known_ephemerides(known, int(s["tic"]), fallback),
            criteria.values,
            engines,
            args.per_star,
            args.seed + n,
        )
        for n, s in enumerate(stars)
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        rows = pd.DataFrame([row for batch in pool.map(injection_job, jobs) for row in batch])
    rows.to_csv(run.path / "injections.csv", index=False)
    by_snr = completeness(rows, "expected_snr", SNR_EDGES)
    by_snr.to_csv(run.path / "completeness_snr.csv", index=False)
    ok = rows[rows["status"] == "ok"]
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
    lines = [
        f"# Injection recovery ({run.provenance['run_id']})",
        "",
        md_table(overview),
        "",
        "## By expected SNR",
        "",
        md_table(by_snr),
        "",
    ]
    for engine in engines:
        table = completeness_map(rows, engine)
        table.to_csv(run.path / f"completeness_{engine}.csv", index=False)
        plot_map(table, engine, run.path / f"completeness_{engine}.png")
        lines += [f"![{engine}](completeness_{engine}.png)", ""]
    (run.path / "summary.md").write_text("\n".join(lines))
    run.finish(
        stars=len(stars), injections=int(len(ok)), no_draw=int((rows["status"] == "no_draw").sum())
    )
    print("\n".join(lines))
    return 0


def cmd_publish(args) -> int:
    source = runs_dir() / args.run
    dest = repo_root() / "results" / "benchmarks" / args.run
    dest.mkdir(parents=True, exist_ok=True)
    for path in source.iterdir():
        if path.suffix in (".md", ".csv", ".png", ".json"):
            shutil.copy(path, dest / path.name)
            (dest / path.name).chmod(0o644)
    print(f"published {args.run} -> {dest.relative_to(repo_root())}")
    return 0
