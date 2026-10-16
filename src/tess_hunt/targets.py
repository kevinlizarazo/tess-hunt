"""Targets: choose which stars to search."""

import json
import shutil
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from astroquery.mast import Catalogs

from tess_hunt import mast
from tess_hunt.catalogs import BJD_OFFSET, FILES
from tess_hunt.config import load_criteria
from tess_hunt.gaia import dr3_join
from tess_hunt.provenance import resume_run, start_run
from tess_hunt.retry import retry

TIC_FIELDS = {
    "ID": "tic",
    "ra": "ra",
    "dec": "dec",
    "Tmag": "tmag",
    "Teff": "teff",
    "e_Teff": "e_teff",
    "logg": "logg",
    "rad": "rad",
    "e_rad": "e_rad",
    "mass": "mass",
    "e_mass": "e_mass",
    "rho": "rho",
    "e_rho": "e_rho",
    "contratio": "contratio",
    "GAIA": "gaia",
    "disposition": "disposition",
}
TARGET_COLUMNS = list(TIC_FIELDS.values())
DEC_BANDS = [(float(lo), float(lo + 10)) for lo in range(-90, 90, 10)]
# MAST caps a query near 500,000 rows; a band this full may be truncated and must be split instead.
ROW_CAP = 400_000


class TicQueryError(RuntimeError):
    pass


def _tic_frame(table) -> pd.DataFrame:
    frame = table[list(TIC_FIELDS)].to_pandas().rename(columns=TIC_FIELDS)
    frame["tic"] = frame["tic"].astype(int)
    return frame


def _sample_criteria(sample: dict, ra: tuple[float, float], dec: tuple[float, float]) -> dict:
    """Sample A's TIC query over a sky box. MAST ranges are inclusive, so in_sample() finishes the cut."""
    return {
        "Tmag": [-5.0, sample["tmag_max"]],
        "Teff": [sample["teff_min"], sample["teff_max"]],
        "logg": [sample["logg_min"], sample["logg_max"]],
        "ra": list(ra),
        "dec": list(dec),
        "objType": "STAR",
    }


def _query_tic(**criteria):
    return Catalogs.query_criteria(catalog="Tic", **criteria)


def query_tic_region(
    sample: dict, ra: tuple[float, float], dec: tuple[float, float]
) -> pd.DataFrame:
    return _tic_frame(_query_tic(**_sample_criteria(sample, ra, dec)))


def query_tic_ids(tics: list[int]) -> pd.DataFrame:
    return _tic_frame(Catalogs.query_criteria(catalog="Tic", ID=list(tics)))


def query_tic_band(
    sample: dict,
    dec: tuple[float, float],
    query=None,
    attempts: int = 3,
    backoff: float = 10.0,
    row_cap: int = ROW_CAP,
) -> pd.DataFrame:
    query = query or _query_tic
    table = retry(
        lambda: query(**_sample_criteria(sample, (0.0, 360.0), dec)),
        attempts=attempts,
        backoff=backoff,
        # MAST answers outages with assorted exception types.
        retry_on=Exception,
        error=TicQueryError,
        what=f"dec {dec}: TIC query",
    )
    if len(table) >= row_cap:
        raise TicQueryError(f"dec {dec}: {len(table)} rows, at or above {row_cap}; split the band")
    return _tic_frame(table)


def flame_cut(stars: pd.DataFrame, logg_min: float) -> pd.Series:
    """True for stars to keep. A missing FLAME value keeps the star on its TIC log g (decision 0009)."""
    logg = pd.to_numeric(stars["logg_flame"], errors="coerce")
    return ~(logg < logg_min)


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


def covered_sources(sources: dict, sample: dict) -> bool:
    """Coverage on the sectors a fetch actually kept, not the ones MAST lists."""
    return covered(sorted(int(s) for s in sources), sample)


def build_sample(
    stars: pd.DataFrame, sectors: dict[int, list[int]], sample: dict, limit: int, seed: int
) -> pd.DataFrame:
    ok = stars.loc[in_sample(stars, sample)]
    ok = ok.loc[np.array([covered(sectors.get(int(t), []), sample) for t in ok["tic"]], dtype=bool)]
    ok = ok.sort_values("tic")
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


def _write_atomic(data: pd.DataFrame | list, path: Path) -> None:
    # A resumed run trusts any checkpoint it finds, so a crash must never leave a truncated one.
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_name(path.name + ".part")
    if isinstance(data, pd.DataFrame):
        data.to_parquet(part)
    else:
        part.write_text(json.dumps(data))
    part.replace(path)


def _concat_products(frames: list[pd.DataFrame]) -> pd.DataFrame:
    # A concat that includes an empty frame warns, and later pandas will make its columns object.
    full = [f for f in frames if len(f)]
    if not full:
        return pd.DataFrame(columns=mast.PRODUCT_COLUMNS)
    return pd.concat(full, ignore_index=True).drop_duplicates("data_uri")


def _band_name(band: tuple[float, float]) -> str:
    return f"dec{band[0]:+03.0f}_{band[1]:+03.0f}"


def _in_band(dec: pd.Series, band: tuple[float, float]) -> pd.Series:
    lo, hi = band
    return (dec >= lo) & ((dec < hi) | (hi == 90.0))


def _discover_band(run, band, tics: list[int]) -> tuple[pd.DataFrame, list[int]]:
    products_file = run.path / "products" / f"{_band_name(band)}.parquet"
    # Written after the products, so a band that has it has products for every TIC it doesn't list.
    failed_file = run.path / "products" / f"{_band_name(band)}.failed.json"
    if failed_file.exists():
        products = pd.read_parquet(products_file)
        todo = json.loads(failed_file.read_text())
    else:
        products, todo = pd.DataFrame(columns=mast.PRODUCT_COLUMNS), tics
    failed: list[int] = []
    if todo:
        products = _concat_products([products, mast.discover(todo, failed=failed)])
    _write_atomic(products, products_file)
    _write_atomic(failed, failed_file)
    return products, failed


def _all_sky(run, sample: dict, seed: int) -> int:
    frames = []
    for band in DEC_BANDS:
        path = run.path / "bands" / f"{_band_name(band)}.parquet"
        if not path.exists():
            _write_atomic(query_tic_band(sample, band), path)
        frames.append(pd.read_parquet(path))
    # MAST ranges are inclusive, so a star on a band edge comes back twice.
    stars = pd.concat(frames, ignore_index=True).drop_duplicates("tic")
    candidates = stars.loc[in_sample(stars, sample)]
    gaia_path = run.path / "gaia_dr3.parquet"
    if not gaia_path.exists():
        _write_atomic(dr3_join(candidates), gaia_path)
    # DR3 ids pass 2**53, and the left merge below would make them float for any star without a match.
    gaia = pd.read_parquet(gaia_path).astype({"dr3_source_id": "Int64"})
    eb = gaia.loc[np.isfinite(pd.to_numeric(gaia["eb_frequency"], errors="coerce"))]
    candidates = candidates.merge(
        gaia.drop(columns=["eb_frequency", "eb_reference_time"]), on="tic", how="left"
    )
    kept = candidates.loc[flame_cut(candidates, sample["flame_logg_min"])]
    parts, failed = [], []
    for band in DEC_BANDS:
        tics = [int(t) for t in kept.loc[_in_band(kept["dec"], band), "tic"]]
        products, band_failed = _discover_band(run, band, tics)
        parts.append(products)
        failed += band_failed
    if failed:
        # An unfinished run is the record of an incomplete one: fetch refuses it and --resume retries the rest.
        print(
            f"targets all-sky: {len(failed)} TICs failed discovery; resume with --resume {run.path.name}"
        )
        return 1
    products = _concat_products(parts)
    chosen = build_sample(kept, sectors_by_tic(products), sample, 0, seed)
    _write_targets(run, chosen, products)
    eb[["tic", "eb_frequency", "eb_reference_time"]].to_parquet(run.path / "dr3_eb.parquet")
    flame_logg = pd.to_numeric(candidates["logg_flame"], errors="coerce")
    run.finish(
        queried=len(stars),
        in_sample=len(candidates),
        # With these, a cut that matched nothing or found no FLAME values shows in the summary.
        gaia_matched=int(candidates["dr3_source_id"].notna().sum()),
        with_flame_logg=int(np.isfinite(flame_logg).sum()),
        after_flame_cut=len(kept),
        covered=len(chosen),
        complete=True,
    )
    print(f"targets all-sky: {len(chosen)} covered of {len(stars)} -> {run.path}")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser("targets", help="choose stars to search")
    modes = p.add_subparsers(dest="mode", required=True)
    s = modes.add_parser("sample", help="sample-A stars in a sky box, or the whole sky")
    s.add_argument("--ra", type=float, nargs=2)
    s.add_argument("--dec", type=float, nargs=2)
    s.add_argument(
        "--all-sky",
        action="store_true",
        help="18 declination bands, Gaia DR3 cut, all covered stars",
    )
    s.add_argument("--resume", help="continue an unfinished --all-sky run by its id")
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
        mode.add_argument("--criteria", type=Path, default=Path("criteria/search-v2.toml"))
        mode.add_argument("--production", action="store_true")


def cmd_sample(args) -> int:
    criteria = load_criteria(args.criteria)
    if args.all_sky:
        run = (
            resume_run(args.resume, [criteria])
            if args.resume
            else start_run("targets", [criteria], args.production, sys.argv)
        )
        return _all_sky(run, criteria["sample"], args.seed)
    if not (args.ra and args.dec):
        raise SystemExit("targets sample needs --ra and --dec, or --all-sky")
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
