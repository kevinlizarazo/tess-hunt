"""Targets: choose which stars to search."""

import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from astroquery.mast import Catalogs

from tess_hunt import mast
from tess_hunt.catalogs import BJD_OFFSET, FILES
from tess_hunt.config import load_criteria
from tess_hunt.provenance import start_run

TIC_FIELDS = {
    "ID": "tic",
    "ra": "ra",
    "dec": "dec",
    "Tmag": "tmag",
    "Teff": "teff",
    "logg": "logg",
    "rad": "rad",
    "mass": "mass",
    "rho": "rho",
    "e_rho": "e_rho",
    "contratio": "contratio",
    "GAIA": "gaia",
    "disposition": "disposition",
}
TARGET_COLUMNS = list(TIC_FIELDS.values())


def _tic_frame(table) -> pd.DataFrame:
    frame = table[list(TIC_FIELDS)].to_pandas().rename(columns=TIC_FIELDS)
    frame["tic"] = frame["tic"].astype(int)
    return frame


def query_tic_region(
    sample: dict, ra: tuple[float, float], dec: tuple[float, float]
) -> pd.DataFrame:
    table = Catalogs.query_criteria(
        catalog="Tic",
        Tmag=[-5.0, sample["tmag_max"]],
        Teff=[sample["teff_min"], sample["teff_max"]],
        logg=[sample["logg_min"], sample["logg_max"]],
        ra=list(ra),
        dec=list(dec),
        objType="STAR",
    )
    return _tic_frame(table)


def query_tic_ids(tics: list[int]) -> pd.DataFrame:
    return _tic_frame(Catalogs.query_criteria(catalog="Tic", ID=list(tics)))


def in_sample(stars: pd.DataFrame, sample: dict) -> pd.Series:
    # The TIC marks split, duplicate and artifact entries in `disposition`; real stars leave it blank.
    clean = stars["disposition"].fillna("").astype(str).str.strip() == ""
    return (
        (stars["teff"] > sample["teff_min"])
        & (stars["teff"] <= sample["teff_max"])
        & (stars["tmag"] <= sample["tmag_max"])
        & (stars["logg"] >= sample["logg_min"])
        & (stars["logg"] <= sample["logg_max"])
        & clean
    )


def sectors_by_tic(products: pd.DataFrame) -> dict[int, list[int]]:
    return {int(t): sorted({int(s) for s in g}) for t, g in products.groupby("tic")["sector"]}


def covered(sectors: list[int], sample: dict) -> bool:
    recent = any(sample["recent_sector_min"] <= s <= sample["recent_sector_max"] for s in sectors)
    return len(sectors) >= sample["min_sectors"] and recent


def build_sample(
    stars: pd.DataFrame, sectors: dict[int, list[int]], sample: dict, limit: int, seed: int
) -> pd.DataFrame:
    ok = stars.loc[in_sample(stars, sample)]
    ok = ok.loc[np.array([covered(sectors.get(int(t), []), sample) for t in ok["tic"]], dtype=bool)]
    if limit and len(ok) > limit:
        ok = ok.sample(n=limit, random_state=seed)
    out = ok.sort_values("tic").reset_index(drop=True)
    out["sectors"] = [",".join(map(str, sectors[int(t)])) for t in out["tic"]]
    return out


def _exofop_cut(toi: pd.DataFrame, sample: dict, search: dict) -> pd.Series:
    num = {
        c: pd.to_numeric(toi[c], errors="coerce")
        for c in (
            "Stellar Eff Temp (K)",
            "TESS Mag",
            "Stellar log(g) (cm/s^2)",
            "Period (days)",
            "Depth (ppm)",
            "Epoch (BJD)",
            "Duration (hours)",
        )
    }
    return (
        toi["TFOPWG Disposition"].isin(["KP", "CP"])
        & (num["Stellar Eff Temp (K)"] > sample["teff_min"])
        & (num["Stellar Eff Temp (K)"] <= sample["teff_max"])
        & (num["TESS Mag"] <= sample["tmag_max"])
        & (num["Stellar log(g) (cm/s^2)"] >= sample["logg_min"])
        & num["Period (days)"].between(search["period_min_days"], search["period_max_days"])
        & num["Depth (ppm)"].notna()
        & num["Epoch (BJD)"].notna()
        & num["Duration (hours)"].notna()
    )


def sample_hosts(
    toi: pd.DataFrame, stars: pd.DataFrame, sample: dict, always: tuple[str, ...] = ("144.01",)
) -> pd.DataFrame:
    """TOI rows whose host passes the sample cut on its TIC values, plus the forced rows."""
    # Sample A is defined on TIC v8.2, and ExoFOP's stellar values can disagree with it
    # (TOI 194.01: ExoFOP log g 4.23, TIC log g blank).
    hosts = set(stars.loc[in_sample(stars, sample), "tic"].astype(int))
    names = toi["TOI"].map(lambda v: f"{v:.2f}")
    return toi[toi["TIC ID"].astype(int).isin(hosts) | names.isin(always)]


def select_known(
    toi: pd.DataFrame,
    sectors: dict[int, list[int]],
    sample: dict,
    search: dict,
    count: int,
    required_snr: float,
    always: tuple[str, ...] = ("144.01",),
) -> pd.DataFrame:
    """Confirmed and known planets like sample A's targets, spread across depth."""
    ok = _exofop_cut(toi, sample, search)
    names = toi["TOI"].map(lambda v: f"{v:.2f}")
    forced = toi[names.isin(always)]
    cand = toi[ok & ~names.isin(always)]
    has_cover = [covered(sectors.get(int(t), []), sample) for t in cand["TIC ID"]]
    cand = (
        cand.loc[np.array(has_cover, dtype=bool)].sort_values("Depth (ppm)").reset_index(drop=True)
    )
    picks = max(count - len(forced), 0)
    index = (
        np.unique(np.round(np.linspace(0, len(cand) - 1, picks)).astype(int))
        if len(cand) and picks
        else []
    )
    chosen = pd.concat([cand.iloc[list(index)], forced])
    snr = pd.to_numeric(chosen["Planet SNR"], errors="coerce")
    out = pd.DataFrame(
        {
            "toi": [f"{v:.2f}" for v in chosen["TOI"]],
            "tic": chosen["TIC ID"].astype(int).to_numpy(),
            "period": pd.to_numeric(chosen["Period (days)"]).to_numpy(float),
            "t0": pd.to_numeric(chosen["Epoch (BJD)"]).to_numpy(float) - BJD_OFFSET,
            "duration": pd.to_numeric(chosen["Duration (hours)"]).to_numpy(float) / 24.0,
            "depth_ppm": pd.to_numeric(chosen["Depth (ppm)"]).to_numpy(float),
            "planet_snr": snr.to_numpy(float),
            "tmag": pd.to_numeric(chosen["TESS Mag"]).to_numpy(float),
            "teff": pd.to_numeric(chosen["Stellar Eff Temp (K)"]).to_numpy(float),
            "required": (snr >= required_snr).to_numpy(),
        }
    )
    return out.sort_values("depth_ppm").reset_index(drop=True)


def _write_targets(run, stars: pd.DataFrame, products: pd.DataFrame) -> None:
    stars.to_parquet(run.path / "targets.parquet")
    products[products["tic"].isin(stars["tic"])].to_parquet(run.path / "products.parquet")


def add_parser(sub) -> None:
    p = sub.add_parser("targets", help="choose stars to search")
    modes = p.add_subparsers(dest="mode", required=True)
    s = modes.add_parser("sample", help="sample-A stars in a sky box")
    s.add_argument("--ra", type=float, nargs=2, required=True)
    s.add_argument("--dec", type=float, nargs=2, required=True)
    s.add_argument("--limit", type=int, default=0)
    s.add_argument("--seed", type=int, default=1)
    s.set_defaults(func=cmd_sample)
    k = modes.add_parser("known", help="select the known-planet benchmark set")
    k.add_argument("--catalogs", type=Path, required=True)
    k.add_argument("--out", type=Path, default=Path("benchmarks/known_planets.csv"))
    k.set_defaults(func=cmd_known)
    t = modes.add_parser("tics", help="targets for the TICs listed in a CSV with a 'tic' column")
    t.add_argument("--from", dest="source", type=Path, required=True)
    t.set_defaults(func=cmd_tics)
    for mode in (s, k, t):
        mode.add_argument("--criteria", type=Path, default=Path("criteria/search-v1.toml"))
        mode.add_argument("--production", action="store_true")


def cmd_sample(args) -> int:
    criteria = load_criteria(args.criteria)
    run = start_run("targets", [criteria], args.production, sys.argv)
    stars = query_tic_region(criteria["sample"], tuple(args.ra), tuple(args.dec))
    candidates = stars.loc[in_sample(stars, criteria["sample"])]
    products = mast.discover([int(t) for t in candidates["tic"]])
    chosen = build_sample(
        candidates, sectors_by_tic(products), criteria["sample"], args.limit, args.seed
    )
    _write_targets(run, chosen, products)
    run.finish(queried=len(stars), in_sample=len(candidates), chosen=len(chosen))
    print(f"targets: {len(chosen)} of {len(stars)} -> {run.path}")
    return 0


def cmd_known(args) -> int:
    criteria = load_criteria(args.criteria)
    run = start_run("targets", [criteria], args.production, sys.argv)
    toi_path = args.catalogs / FILES["TOI"]
    run.record_input("toi", toi_path)
    toi = pd.read_csv(toi_path)
    # The ExoFOP cut costs nothing and shrinks the TIC and MAST queries to the hosts that could pass.
    plausible = toi[
        _exofop_cut(toi, criteria["sample"], criteria["search"])
        | toi["TOI"].map(lambda v: f"{v:.2f}").eq("144.01")
    ]
    stars = query_tic_ids(sorted({int(t) for t in plausible["TIC ID"]}))
    hosts = sample_hosts(plausible, stars, criteria["sample"])
    products = mast.discover(sorted({int(t) for t in hosts["TIC ID"]}))
    bench = criteria["benchmark"]
    known = select_known(
        hosts,
        sectors_by_tic(products),
        criteria["sample"],
        criteria["search"],
        bench["known_count"],
        bench["required_recovery_snr"],
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    known.to_csv(args.out, index=False)
    shutil.copy(args.out, run.path / args.out.name)
    run.finish(selected=len(known), required=int(known["required"].sum()))
    print(f"targets known: {len(known)} planets -> {args.out}")
    return 0


def cmd_tics(args) -> int:
    criteria = load_criteria(args.criteria)
    run = start_run("targets", [criteria], args.production, sys.argv)
    run.record_input("source", args.source)
    tics = sorted({int(t) for t in pd.read_csv(args.source)["tic"]})
    stars = query_tic_ids(tics)
    products = mast.discover(tics)
    sectors = sectors_by_tic(products)
    stars["sectors"] = [",".join(map(str, sectors.get(int(t), []))) for t in stars["tic"]]
    _write_targets(run, stars.sort_values("tic").reset_index(drop=True), products)
    run.finish(stars=len(stars))
    print(f"targets tics: {len(stars)} -> {run.path}")
    return 0
