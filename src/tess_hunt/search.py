"""Search: box least squares over every sector at once, up to three signals per star."""

import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.timeseries import BoxLeastSquares
from scipy.ndimage import median_filter
from transitleastsquares import period_grid as tls_period_grid
from transitleastsquares import transitleastsquares

from tess_hunt.catalogs import FILES, known_ephemerides, load_known
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend
from tess_hunt.ephemeris import Ephemeris, in_transit, transit_times_in_data
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pool import process_pool
from tess_hunt.provenance import sha256_file, start_run


@dataclass(frozen=True)
class Signal:
    tic: int
    rank: int
    period: float
    t0: float
    duration: float
    depth: float
    depth_snr: float
    sde: float
    n_transits: int

    def ephemeris(self) -> Ephemeris:
        return Ephemeris(self.period, self.t0, self.duration, self.depth)


def star_params(star: Mapping) -> tuple[float, float, bool]:
    """TIC radius and mass in solar units; solar values, flagged, when the TIC has none."""

    def usable(v) -> bool:
        # float() raises on text, so a corrupt TIC value is an error row, not a silent solar fallback.
        return v is not None and np.isfinite(float(v)) and float(v) > 0

    r, m = star.get("rad"), star.get("mass")
    return (
        float(r) if usable(r) else 1.0,
        float(m) if usable(m) else 1.0,
        not (usable(r) and usable(m)),
    )


def bin_lightcurve(lc: LightCurve, minutes: float) -> LightCurve:
    """Inverse-variance means in fixed time bins, never merging cadences from different sectors."""
    if len(lc.time) == 0:
        return lc
    width = minutes / 1440.0
    parts = []
    for sector in np.unique(lc.sector):
        m = lc.sector == sector
        t, f, e = lc.time[m], lc.flux[m], lc.flux_err[m]
        idx = np.floor((t - t[0]) / width).astype(int)
        n = np.bincount(idx)
        filled = n > 0
        w = np.bincount(idx, 1.0 / e**2)[filled]
        parts.append(
            (
                np.bincount(idx, t)[filled] / n[filled],
                np.bincount(idx, f / e**2)[filled] / w,
                1.0 / np.sqrt(w),
                np.full(int(filled.sum()), sector, dtype=np.int16),
            )
        )
    t, f, e, s = (np.concatenate(c) for c in zip(*parts, strict=True))
    return LightCurve(lc.tic, t, f, e, s, lc.sources)


def period_grid(span_days: float, rstar: float, mstar: float, cfg: Mapping) -> np.ndarray:
    # Ofir (2014) spacing: as fine as a transit's duration allows over the whole baseline.
    grid = tls_period_grid(
        R_star=rstar,
        M_star=mstar,
        time_span=span_days,
        period_min=cfg["period_min_days"],
        period_max=cfg["period_max_days"],
        oversampling_factor=cfg["oversampling"],
        n_transits_min=cfg["min_transits"],
    )
    return np.sort(np.asarray(grid, dtype=float))


def _bls_peak(lc: LightCurve, periods: np.ndarray, durations: np.ndarray, kernel: int) -> dict:
    result = BoxLeastSquares(lc.time, lc.flux, dy=lc.flux_err).power(
        periods, durations, objective="likelihood"
    )
    # BLS power drifts with period; judge each peak against its neighbours, as TLS does.
    power = result.power - median_filter(result.power, size=kernel, mode="nearest")
    sde = (power - power.mean()) / power.std()
    i = int(np.argmax(sde))
    return {
        "period": float(result.period[i]),
        "t0": float(result.transit_time[i]),
        "duration": float(result.duration[i]),
        "depth": float(result.depth[i]),
        "depth_snr": float(result.depth_snr[i]),
        "sde": float(sde[i]),
    }


def _tls_peak(lc: LightCurve, rstar: float, mstar: float, cfg: Mapping) -> dict:
    result = transitleastsquares(lc.time, lc.flux, lc.flux_err).power(
        period_min=cfg["period_min_days"],
        period_max=cfg["period_max_days"],
        n_transits_min=cfg["min_transits"],
        oversampling_factor=cfg["oversampling"],
        R_star=rstar,
        M_star=mstar,
        R_star_min=min(0.13, rstar),
        R_star_max=max(3.5, rstar),
        M_star_min=min(0.1, mstar),
        M_star_max=max(1.0, mstar),
        use_threads=1,
        show_progress_bar=False,
    )
    return {
        "period": float(result.period),
        "t0": float(result.T0),
        "duration": float(result.duration),
        "depth": float(1.0 - result.depth),
        "depth_snr": float(result.snr),
        "sde": float(result.SDE),
    }


def search_star(lc: LightCurve, rstar: float, mstar: float, cfg: Mapping) -> list[Signal]:
    if cfg["engine"] not in ("bls", "tls"):
        raise ValueError(f"unknown engine {cfg['engine']!r}")
    data = bin_lightcurve(lc, cfg["bin_minutes"]) if cfg["bin_minutes"] > 0 else lc
    if len(data.time) < cfg["min_points"]:
        return []
    periods = period_grid(float(data.time.max() - data.time.min()), rstar, mstar, cfg)
    if len(periods) == 0:
        return []
    durations = np.asarray(cfg["durations_hours"], dtype=float) / 24.0
    signals: list[Signal] = []
    for rank in range(1, cfg["max_signals"] + 1):
        if len(data.time) < cfg["min_points"]:
            break
        if cfg["engine"] == "bls":
            peak = _bls_peak(data, periods, durations, cfg["sde_kernel"])
        else:
            peak = _tls_peak(data, rstar, mstar, cfg)
        eph = Ephemeris(peak["period"], peak["t0"], peak["duration"], peak["depth"])
        signals.append(
            Signal(
                lc.tic,
                rank,
                eph.period,
                eph.t0,
                eph.duration,
                eph.depth,
                peak["depth_snr"],
                peak["sde"],
                len(transit_times_in_data(data.time, eph)),
            )
        )
        # A NaN SDE compares False against any threshold; stop rather than mask around a meaningless peak.
        if not peak["sde"] >= cfg["continue_sde"]:
            break
        data = data.select(~in_transit(data.time, eph, cfg["iter_mask_width"]))
    return signals


def _search_job(job: tuple) -> tuple[dict, list[dict]]:
    star, known_ephs, cfg_detrend, cfg_search = job
    tic = int(star["tic"])
    path = lc_dir() / f"{tic}.npz"
    if not path.exists():
        return {"tic": tic, "status": "no_light_curve"}, []
    try:
        rstar, mstar, assumed = star_params(star)
        digest = sha256_file(path)
        flat = detrend(LightCurve.load(path), cfg_detrend, known_ephs)
        if len(flat.time) < cfg_search["min_points"]:
            return {"tic": tic, "status": "too_few_points", "n_points": len(flat.time)}, []
        signals = search_star(flat, rstar, mstar, cfg_search)
    except Exception as exc:  # one bad star must not stop the run; it is recorded, not hidden
        return {"tic": tic, "status": "error", "error": f"{type(exc).__name__}: {exc}"}, []
    status = {
        "tic": tic,
        "status": "ok",
        "n_points": len(flat.time),
        "n_sectors": int(len(np.unique(flat.sector))),
        "assumed_solar": assumed,
        "lc_sha256": digest,
    }
    return status, [{**asdict(s), "engine": cfg_search["engine"]} for s in signals]


def add_parser(sub) -> None:
    p = sub.add_parser("search", help="search fetched light curves for periodic transits")
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument(
        "--catalogs", type=Path, required=True, help="snapshot dir for masking known planets"
    )
    p.add_argument("--criteria", type=Path, default=Path("criteria/search-v1.toml"))
    p.add_argument(
        "--unmask", action="store_true", help="keep known planets in (positive controls)"
    )
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--production", action="store_true")
    p.set_defaults(func=cmd)


def cmd(args) -> int:
    criteria = load_criteria(args.criteria)
    run = start_run("search", [criteria], args.production, sys.argv)
    run.record_input("targets", args.targets)
    for name in FILES.values():
        run.record_input(name, args.catalogs / name)
    known = load_known(args.catalogs)
    fallback = criteria["detrend"]["fallback_duration_days"]
    stars = pd.read_parquet(args.targets).to_dict("records")
    jobs = [
        (
            s,
            [] if args.unmask else known_ephemerides(known, int(s["tic"]), fallback),
            criteria["detrend"],
            criteria["search"],
        )
        for s in stars
    ]
    with process_pool(args.workers) as pool:
        results = list(pool.map(_search_job, jobs, chunksize=2))
    star_rows = [r[0] for r in results]
    signal_rows = [row for r in results for row in r[1]]
    pd.DataFrame(star_rows).to_parquet(run.path / "stars.parquet")
    pd.DataFrame(signal_rows, columns=[*Signal.__dataclass_fields__, "engine"]).to_parquet(
        run.path / "signals.parquet"
    )
    counts = pd.Series([r["status"] for r in star_rows]).value_counts().to_dict()
    run.finish(
        stars=len(star_rows),
        signals=len(signal_rows),
        **{f"status_{k}": int(v) for k, v in counts.items()},
    )
    print(f"search: {counts}, {len(signal_rows)} signals -> {run.path}")
    return 0
