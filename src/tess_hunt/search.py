"""Search: box least squares over every sector at once, up to three signals per star."""

import hashlib
import json
import math
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd
from astropy.timeseries import BoxLeastSquares
from scipy.ndimage import median_filter
from transitleastsquares import period_grid as tls_period_grid

from tess_hunt.catalogs import known_ephemerides, load_known, snapshot_inputs
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.detrend import detrend, known_mask
from tess_hunt.ephemeris import Ephemeris, in_transit, transit_times_in_data
from tess_hunt.lightcurve import LightCurve
from tess_hunt.pool import process_pool
from tess_hunt.provenance import repo_root, sha256_file, start_run
from tess_hunt.recovery import classify
from tess_hunt.scramble import scramble
from tess_hunt.targets import covered_sources

AU_PER_R_SUN = 215.032
BLS_FIELDS = ("period", "power", "transit_time", "duration", "depth", "depth_snr")
# The search's own modules. The null threshold is only valid for a search that ran the same code, so their
# hash travels with both runs (design 4.5). Some code that shapes the signals stays outside it: the
# known-planet masks come from catalogs.py and the criteria are read by config.py.
SEARCH_CODE = (
    "search.py",
    "detrend.py",
    "scramble.py",
    "lightcurve.py",
    "ephemeris.py",
    "recovery.py",
    "targets.py",
)


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


@dataclass
class SearchResult:
    """The emitted signals, and what the search did on the way (decision 0008)."""

    signals: list[Signal] = field(default_factory=list)
    n_bins: int = 0  # points the search started from, after binning
    few_transits: int = 0  # peaks rejected for too few transits on data
    budget_exhausted: bool = False
    n_bls: int = 0
    top_period: float = math.nan  # the first peak, before any rejection
    top_q: float = math.nan
    top_sde: float = math.nan
    masked_fraction: float = 0.0  # share of binned points masked when the search stopped

    def diagnostics(self) -> dict:
        return {k: v for k, v in asdict(self).items() if k != "signals"}


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


def stellar_density(star: Mapping, rstar: float, mstar: float) -> float:
    """Mean density in solar units: the TIC's own value, else from the radius and mass in use."""
    rho = star.get("rho")
    if rho is not None and np.isfinite(float(rho)) and float(rho) > 0:
        return float(rho)
    return mstar / rstar**3


def central_duration(periods: np.ndarray, rho: float) -> np.ndarray:
    """Duration of a central transit on a circular orbit around a star of density rho (solar)."""
    a_rs = AU_PER_R_SUN * rho ** (1 / 3) * (periods / 365.25) ** (2 / 3)
    return periods / np.pi * np.arcsin(np.minimum(1.0, 1.0 / a_rs))


def allowed_durations(
    periods: np.ndarray, durations: np.ndarray, rho: float, factor: float
) -> np.ndarray:
    """How many of the ascending durations each period may use: those up to factor x the central
    duration, and never fewer than the shortest."""
    bound = factor * central_duration(periods, rho)
    return np.maximum(np.searchsorted(durations, bound, side="right"), 1)


def repeat_periods(
    periods: np.ndarray, signals: list[Signal], harmonics, sigma_p: float
) -> np.ndarray:
    """Periods that ephemeris_match would call a harmonic of an emitted signal, on period alone."""
    tolerance = math.erfc(sigma_p / math.sqrt(2.0))
    out = np.zeros(len(periods), dtype=bool)
    for s in signals:
        for h in harmonics:
            out |= np.abs(periods - s.period * h) / periods < tolerance
    return out


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


def _bls_spectrum(
    lc: LightCurve, periods: np.ndarray, durations: np.ndarray, counts: np.ndarray
) -> dict:
    """BLS over the grid; each run of periods that share their allowed durations is one call."""
    bls = BoxLeastSquares(lc.time, lc.flux, dy=lc.flux_err)
    starts = np.r_[0, np.flatnonzero(np.diff(counts)) + 1]
    ends = np.r_[starts[1:], len(periods)]
    parts = [
        bls.power(periods[s:e], durations[: counts[s]], objective="likelihood")
        for s, e in zip(starts, ends, strict=True)
    ]
    return {f: np.concatenate([np.asarray(p[f], dtype=float) for p in parts]) for f in BLS_FIELDS}


def search_star(
    lc: LightCurve, rstar: float, mstar: float, cfg: Mapping, rho: float = 1.0
) -> SearchResult:
    """Up to max_signals signals, each with at least min_transits transits on data.

    Boxes are bounded by the star (C1): at most duration_factor x the central transit duration at
    each period. Harmonics of an emitted signal leave the argmax and the SDE statistics, so a
    variable star cannot fill every rank with itself. A peak with too few transits (C2) is masked
    and the search retried, at most max_retries times."""
    if cfg["engine"] != "bls":
        raise ValueError(f"unknown engine {cfg['engine']!r}")
    data = bin_lightcurve(lc, cfg["bin_minutes"]) if cfg["bin_minutes"] > 0 else lc
    n0 = len(data.time)
    result = SearchResult(n_bins=n0)
    if n0 < cfg["min_points"]:
        return result
    periods = period_grid(float(data.time.max() - data.time.min()), rstar, mstar, cfg)
    if len(periods) == 0:
        return result
    durations = np.sort(np.asarray(cfg["durations_hours"], dtype=float) / 24.0)
    counts = allowed_durations(periods, durations, rho, cfg["duration_factor"])
    retries = 0
    while len(result.signals) < cfg["max_signals"] and len(data.time) >= cfg["min_points"]:
        spectrum = _bls_spectrum(data, periods, durations, counts)
        result.n_bls += 1
        keep = ~repeat_periods(
            periods, result.signals, cfg["repeat_harmonics"], cfg["repeat_sigma_p"]
        )
        # BLS power drifts with period; judge each peak against its neighbours, as TLS does.
        power = spectrum["power"] - median_filter(
            spectrum["power"], size=cfg["sde_kernel"], mode="nearest"
        )
        sde = (power - power[keep].mean()) / power[keep].std()
        i = int(np.flatnonzero(keep)[np.argmax(sde[keep])])
        eph = Ephemeris(
            *(float(spectrum[f][i]) for f in ("period", "transit_time", "duration", "depth"))
        )
        if result.n_bls == 1:
            result.top_period, result.top_q = eph.period, eph.duration / eph.period
            result.top_sde = float(sde[i])
        # A NaN SDE compares False against any threshold; stop rather than emit a meaningless peak.
        if not np.isfinite(sde[i]):
            break
        n_transits = len(transit_times_in_data(data.time, eph, cfg["min_points_per_transit"]))
        if n_transits < cfg["min_transits"]:
            result.few_transits += 1
            if retries == cfg["max_retries"]:
                result.budget_exhausted = True
                break
            retries += 1
        else:
            result.signals.append(
                Signal(
                    lc.tic,
                    len(result.signals) + 1,
                    eph.period,
                    eph.t0,
                    eph.duration,
                    eph.depth,
                    float(spectrum["depth_snr"][i]),
                    float(sde[i]),
                    n_transits,
                )
            )
            if sde[i] < cfg["continue_sde"]:
                break
        data = data.select(~in_transit(data.time, eph, cfg["iter_mask_width"]))
    result.masked_fraction = 1.0 - len(data.time) / n0
    return result


def search_code_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name in SEARCH_CODE:
        digest.update(name.encode())
        digest.update((root / "src" / "tess_hunt" / name).read_bytes())
    return digest.hexdigest()


def read_threshold(path: Path) -> dict:
    data = json.loads(Path(path).read_text())
    for key in ("threshold", "search_criteria_sha256", "search_code_sha256"):
        if key not in data:
            raise SystemExit(f"{path} has no {key}; it is not a threshold.json")
    value = data["threshold"]
    # json reads NaN and Infinity as floats, and bool is an int; none of them is a threshold.
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value):
        raise SystemExit(f"{path} has threshold {value!r}; it must be a finite number")
    return data


def search_input(
    lc: LightCurve, known: list[Ephemeris], crit: Mapping, seed: int | None
) -> tuple[LightCurve, np.ndarray]:
    """The light curve a search detrends and the cadences it must exclude. Known planets are masked on the
    observed times; a null run (a seed) then scrambles the light curve, and the mask moves with its cadences."""
    exclude = known_mask(lc.time, known, crit["detrend"]["known_mask_width"])
    if seed is None:
        return lc, exclude
    scrambled, order = scramble(
        lc, crit["null"]["segment_gap_days"], crit["null"]["placement_gap_days"], seed
    )
    return scrambled, exclude[order]


def _search_status(result: SearchResult, min_points: int) -> str:
    if result.n_bins < min_points:
        return "too_few_points"
    # No finite peak was judged (a NaN spectrum, or no period to search), so the star was not searched.
    if not np.isfinite(result.top_sde):
        return "nonfinite_sde"
    return "ok"


def _search_job(job: dict) -> tuple[dict, list[dict]]:
    star, crit, cfg = job["star"], job["criteria"], job["search"]
    tic, control = int(star["tic"]), job["control"]
    base = {"tic": tic, "control": control}
    path = lc_dir() / f"{tic}.npz"
    if not path.exists():
        return {**base, "status": "no_light_curve"}, []
    try:
        rstar, mstar, assumed = star_params(star)
        rho = stellar_density(star, rstar, mstar)
        digest = sha256_file(path)
        lc = LightCurve.load(path)
        # Controls are the known set, chosen on their own rule; only sample stars must stay covered.
        if not control and not covered_sources(lc.sources, crit["sample"]):
            return {**base, "status": "not_covered_after_fetch", "n_sectors": len(lc.sources)}, []
        lc, exclude = search_input(lc, job["known"], crit, job["scramble"])
        flat = detrend(lc, crit["detrend"], exclude=exclude)
        if len(flat.time) < cfg["min_points"]:
            return {**base, "status": "too_few_points", "n_points": len(flat.time)}, []
        result = search_star(flat, rstar, mstar, cfg, rho)
    except Exception as exc:  # one bad star must not stop the run; it is recorded, not hidden
        return {**base, "status": "error", "error": f"{type(exc).__name__}: {exc}"}, []
    suspect = sum(bool(info.get("timing_suspect")) for info in lc.sources.values())
    status = {
        **base,
        "status": _search_status(result, cfg["min_points"]),
        "n_points": len(flat.time),
        "n_sectors": int(len(np.unique(flat.sector))),
        "timing_suspect_sectors": suspect,
        "assumed_solar": assumed,
        "rho": rho,
        "lc_sha256": digest,
        **result.diagnostics(),
    }
    rows = [{**asdict(s), "engine": cfg["engine"], "control": control} for s in result.signals]
    return status, rows


def evaluate_controls(
    known: pd.DataFrame, signals: pd.DataFrame, match: dict, threshold: float
) -> pd.DataFrame:
    rows = []
    for planet in known.to_dict("records"):
        found = signals[signals["tic"] == int(planet["tic"])]
        found = [
            Signal(**{k: r[k] for k in Signal.__dataclass_fields__})
            for r in found.to_dict("records")
        ]
        truth = Ephemeris(planet["period"], planet["t0"], planet["duration"])
        rows.append(
            {
                "toi": str(planet["toi"]),
                "tic": int(planet["tic"]),
                "period": planet["period"],
                "required": bool(planet["required"]),
                **classify(truth, found, match, threshold),
            }
        )
    return pd.DataFrame(rows)


def add_parser(sub) -> None:
    p = sub.add_parser("search", help="search fetched light curves for periodic transits")
    p.add_argument("--targets", type=Path, required=True)
    p.add_argument(
        "--catalogs", type=Path, required=True, help="snapshot dir for masking known planets"
    )
    p.add_argument("--criteria", type=Path, default=Path("criteria/search-v2.toml"))
    p.add_argument(
        "--scramble", type=int, help="null run: scramble each light curve with this seed"
    )
    p.add_argument("--threshold", type=Path, help="threshold.json from `triage threshold`")
    p.add_argument("--controls", type=Path, help="known planets searched with masks off")
    p.add_argument("--control-targets", type=Path, help="targets table for the control hosts")
    p.add_argument("--workers", type=int, default=8)
    p.add_argument("--production", action="store_true")
    p.set_defaults(func=cmd)


def _check_arguments(args) -> None:
    if args.scramble is not None and args.threshold is not None:
        raise SystemExit(
            "--scramble and --threshold exclude each other: the null runs at the provisional value"
        )
    if bool(args.controls) != bool(args.control_targets):
        raise SystemExit("--controls and --control-targets go together")
    if args.production and args.scramble is None and not (args.threshold and args.controls):
        # Spec 5.6: a production search carries its positive controls, and its threshold comes from the null.
        raise SystemExit("a production search needs --threshold, --controls and --control-targets")


def cmd(args) -> int:
    _check_arguments(args)
    criteria = load_criteria(args.criteria)
    cfg = dict(criteria["search"])
    threshold = None
    if args.threshold:
        threshold = read_threshold(args.threshold)
        code = search_code_sha256(repo_root())
        if threshold["search_criteria_sha256"] != criteria.sha256:
            raise SystemExit(f"{args.threshold} came from other search criteria; rerun the null")
        if threshold["search_code_sha256"] != code:
            raise SystemExit(f"{args.threshold} came from other search code; rerun the null")
        cfg["continue_sde"] = float(threshold["threshold"])
    planets = hosts = None
    if args.controls:
        planets = pd.read_csv(args.controls, dtype={"toi": str})
        hosts = pd.read_parquet(args.control_targets).set_index("tic")
        missing = sorted(int(t) for t in set(planets["tic"]) - set(hosts.index))
        if missing:
            raise SystemExit(f"{args.control_targets} has no row for control hosts {missing}")
    run = start_run("search", [criteria], args.production, sys.argv)
    run.record("search_code_sha256", search_code_sha256(repo_root()))
    run.record("scramble", args.scramble)
    if threshold is None:
        run.record("threshold", None)
    else:
        run.record_input("threshold", args.threshold)
        run.record(
            "threshold",
            {
                "value": cfg["continue_sde"],
                "file": args.threshold.name,
                # threshold.json sits in the run directory that computed it.
                "run_id": args.threshold.resolve().parent.name,
            },
        )
    run.record_input("targets", args.targets)
    for name, path in snapshot_inputs(args.catalogs).items():
        run.record_input(name, path)
    known = load_known(args.catalogs)
    mask_sources = tuple(criteria["detrend"]["mask_sources"])
    fallback = criteria["detrend"]["fallback_duration_days"]

    def job(star, control):
        ephs = [] if control else known_ephemerides(known, int(star["tic"]), fallback, mask_sources)
        return {
            "star": star,
            "control": control,
            "known": ephs,
            "criteria": criteria.values,
            "search": cfg,
            "scramble": args.scramble,
        }

    jobs = [job(s, False) for s in pd.read_parquet(args.targets).to_dict("records")]
    if planets is not None:
        run.record_input("controls", args.controls)
        run.record_input("control_targets", args.control_targets)
        jobs += [
            job({**hosts.loc[t].to_dict(), "tic": int(t)}, True)
            for t in sorted(set(planets["tic"]))
        ]
    with process_pool(args.workers) as pool:
        results = list(pool.map(_search_job, jobs, chunksize=2))
    star_rows = [r[0] for r in results]
    signal_rows = [row for r in results for row in r[1]]
    pd.DataFrame(star_rows).to_parquet(run.path / "stars.parquet")
    signals = pd.DataFrame(signal_rows, columns=[*Signal.__dataclass_fields__, "engine", "control"])
    signals.to_parquet(run.path / "signals.parquet")
    # The sample's counts; control hosts are searched again on purpose and counted apart.
    sample = [r for r in star_rows if not r["control"]]
    counts = pd.Series([r["status"] for r in sample]).value_counts().to_dict()
    summary = {
        "stars": len(sample),
        "signals": sum(not r["control"] for r in signal_rows),
        **{f"status_{k}": int(v) for k, v in counts.items()},
        "control_rows": len(star_rows) - len(sample),
        "control_signals": sum(bool(r["control"]) for r in signal_rows),
    }
    code = 0
    if planets is not None:
        level = cfg["continue_sde"] if threshold else criteria["benchmark"]["provisional_sde"]
        # With no signals at all the column is empty object dtype, which pandas would read as a
        # column list, not a mask.
        controls = signals[signals["control"].astype(bool)]
        table = evaluate_controls(planets, controls, criteria["match"], level)
        table.to_csv(run.path / "controls.csv", index=False)
        required_missed = sorted(table.loc[table["required"] & ~table["recovered"], "toi"])
        summary |= {
            "controls_valid": not required_missed,
            "controls_required_missed": required_missed,
            "controls_missed": sorted(table.loc[~table["required"] & ~table["recovered"], "toi"]),
        }
        # Spec 5.6: a run that misses a required control is invalid, and triage refuses it.
        code = 1 if required_missed else 0
    run.finish(**summary)
    print(f"search: {counts}, {summary['signals']} signals -> {run.path}")
    return code
