"""The dossier's plots (docs/design.md and the M3 design, section 4.2). Each function writes one PNG
with matplotlib's Agg canvas, and a light curve with nothing to show gets a PNG that says so: a thin
signal's vet must not fail on its plots."""

from pathlib import Path

import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from scipy.stats import binned_statistic

from tess_hunt.checks.families import family_labels
from tess_hunt.checks.holdout import season_labels
from tess_hunt.ephemeris import Ephemeris, epoch_numbers, phase_days, transit_times_in_data
from tess_hunt.lightcurve import LightCurve

PPM = 1e6
HOURS_PER_DAY = 24.0
# Each zoom spans this many transit durations either side of mid-transit.
HALF_WINDOW_DURATIONS = 2.0
COLUMNS = 5


def _save(fig: Figure, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    FigureCanvasAgg(fig)
    fig.savefig(path, dpi=100)
    return path


def no_data(path: Path, title: str, why: str) -> Path:
    fig = Figure(figsize=(6, 2.5))
    ax = fig.subplots()
    ax.set_axis_off()
    ax.set_title(title)
    ax.text(0.5, 0.5, f"no data: {why}", ha="center", va="center", transform=ax.transAxes)
    return _save(fig, path)


def _finite(lc: LightCurve) -> LightCurve:
    return lc.select(np.isfinite(lc.time) & np.isfinite(lc.flux))


def _near(lc: LightCurve, eph: Ephemeris) -> LightCurve:
    return lc.select(np.abs(phase_days(lc.time, eph)) < HALF_WINDOW_DURATIONS * eph.duration)


def _ppm(flux: np.ndarray) -> np.ndarray:
    return (flux - 1.0) * PPM


def _ylim(ppm: np.ndarray) -> tuple[float, float]:
    # Percentiles, so one outlier cadence doesn't flatten every panel that shares the axis.
    lo, hi = np.percentile(ppm, [0.5, 99.5])
    pad = 0.1 * max(hi - lo, 1.0)
    return float(lo - pad), float(hi + pad)


def _binned(x: np.ndarray, y: np.ndarray, width: float) -> tuple[np.ndarray, np.ndarray]:
    if len(x) < 2 or not width > 0:
        return np.array([]), np.array([])
    edges = np.arange(x.min(), x.max() + width, width)
    if len(edges) < 2:
        return np.array([]), np.array([])
    medians, edges, _ = binned_statistic(x, y, "median", bins=edges)
    centres = 0.5 * (edges[1:] + edges[:-1])
    keep = np.isfinite(medians)
    return centres[keep], medians[keep]


def _fold_panel(ax, lc: LightCurve, eph: Ephemeris) -> None:
    hours = phase_days(lc.time, eph) * HOURS_PER_DAY
    ppm = _ppm(lc.flux)
    ax.plot(hours, ppm, ".", ms=1.5, color="0.65", rasterized=True)
    x, y = _binned(hours, ppm, eph.duration * HOURS_PER_DAY / 8.0)
    ax.plot(x, y, "o", ms=3, color="C0")
    half = 0.5 * eph.duration * HOURS_PER_DAY
    ax.axvspan(-half, half, color="C0", alpha=0.08)


def _sectors(lc: LightCurve) -> str:
    sectors = np.unique(lc.sector).astype(int)
    return f"S{sectors[0]}" if len(sectors) == 1 else f"S{sectors[0]}-{sectors[-1]}"


def transits(lc: LightCurve, eph: Ephemeris, path: Path) -> Path:
    """Each transit with cadences near it, against hours from its predicted mid-time."""
    title = f"TIC {lc.tic}: each transit"
    lc = _finite(lc)
    half = HALF_WINDOW_DURATIONS * eph.duration
    centres = transit_times_in_data(lc.time, eph, width=2.0 * HALF_WINDOW_DURATIONS)
    if len(centres) == 0:
        return no_data(path, title, "no cadences near a predicted transit")
    rows = int(np.ceil(len(centres) / COLUMNS))
    cols = min(COLUMNS, len(centres))
    fig = Figure(figsize=(3.2 * cols, 2.4 * rows + 0.6), layout="constrained")
    axes = fig.subplots(rows, cols, sharey=True, squeeze=False).ravel()
    near = _near(lc, eph)
    for ax, centre in zip(axes, centres, strict=False):
        part = lc.select(np.abs(lc.time - centre) < half)
        _fold_panel(ax, part, eph)
        epoch = int(np.round((centre - eph.t0) / eph.period))
        ax.set_title(f"epoch {epoch}, S{int(np.median(part.sector))}", fontsize=9)
    for ax in axes[len(centres) :]:
        ax.set_axis_off()
    axes[0].set_ylim(*_ylim(_ppm(near.flux)))
    fig.supxlabel("hours from predicted mid-transit")
    fig.supylabel("flux (ppm)")
    fig.suptitle(f"{title} (P = {eph.period:.5f} d)")
    return _save(fig, path)


def folds(
    lc: LightCurve, eph: Ephemeris, families: dict, path: Path, season_gap_days: float
) -> Path:
    """The fold in each season (as the held-out check splits them) and each product family (vet-v3's
    `[families]`): one row per family, one column per season."""
    title = f"TIC {lc.tic}: fold per family and season"
    lc = _finite(lc)
    if not len(lc.time):
        return no_data(path, title, "no finite cadences")
    # Seasons from every cadence: near-transit cadences alone would open gaps that aren't there.
    seasons = season_labels(lc.time, season_gap_days)
    labels = family_labels(lc, families)
    near = np.abs(phase_days(lc.time, eph)) < HALF_WINDOW_DURATIONS * eph.duration
    if not near.any():
        return no_data(path, title, "no cadences near a predicted transit")
    names, season_ids = np.unique(labels[near]), np.unique(seasons)
    fig = Figure(figsize=(3.2 * len(season_ids), 2.6 * len(names) + 0.6), layout="constrained")
    axes = fig.subplots(len(names), len(season_ids), sharex=True, sharey=True, squeeze=False)
    for i, name in enumerate(names):
        for j, season in enumerate(season_ids):
            ax = axes[i, j]
            part = lc.select(near & (labels == name) & (seasons == season))
            whole = lc.select(seasons == season)
            ax.set_title(f"{name}, season {season} ({_sectors(whole)})", fontsize=9)
            if not len(part.time):
                ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
                continue
            _fold_panel(ax, part, eph)
    axes[0, 0].set_ylim(*_ylim(_ppm(lc.flux[near])))
    fig.supxlabel("hours from mid-transit")
    fig.supylabel("flux (ppm)")
    fig.suptitle(title)
    return _save(fig, path)


def odd_even(lc: LightCurve, eph: Ephemeris, path: Path) -> Path:
    """Odd and even transits folded side by side, each with its median depth in the core."""
    title = f"TIC {lc.tic}: odd and even transits"
    near = _near(_finite(lc), eph)
    if not len(near.time):
        return no_data(path, title, "no cadences near a predicted transit")
    odd = epoch_numbers(near.time, eph) % 2 == 1
    fig = Figure(figsize=(9, 3.4), layout="constrained")
    axes = fig.subplots(1, 2, sharex=True, sharey=True)
    for ax, label, mask in ((axes[0], "odd", odd), (axes[1], "even", ~odd)):
        part = near.select(mask)
        ax.set_title(label, fontsize=10)
        if not len(part.time):
            ax.text(0.5, 0.5, "no data", ha="center", va="center", transform=ax.transAxes)
            continue
        _fold_panel(ax, part, eph)
        core = np.abs(phase_days(part.time, eph)) < 0.25 * eph.duration
        if core.any():
            level = float(np.median(_ppm(part.flux[core])))
            ax.axhline(level, color="C3", lw=1, label=f"core median {level:.0f} ppm")
            ax.legend(fontsize=8, loc="lower right")
    axes[0].set_ylim(*_ylim(_ppm(near.flux)))
    fig.supxlabel("hours from mid-transit")
    fig.supylabel("flux (ppm)")
    fig.suptitle(title)
    return _save(fig, path)


def phase(lc: LightCurve, eph: Ephemeris, modshift: dict | None, path: Path) -> Path:
    """The whole orbit, phase 0 to 1, with phase 0.5 and LEO-Vetter's ModShift secondary marked.
    ModShift's phases count from the same epoch (LEO-Vetter's modshift.uniqueness)."""
    title = f"TIC {lc.tic}: phase"
    lc = _finite(lc)
    if not len(lc.time):
        return no_data(path, title, "no finite cadences")
    orbit = ((lc.time - eph.t0) / eph.period) % 1.0
    ppm = _ppm(lc.flux)
    fig = Figure(figsize=(10, 3.6), layout="constrained")
    ax = fig.subplots()
    ax.plot(orbit, ppm, ",", color="0.65", rasterized=True)
    x, y = _binned(orbit, ppm, 0.5 * eph.duration / eph.period)
    ax.plot(x, y, "o", ms=2.5, color="C0")
    ax.axvline(0.5, color="0.3", ls="--", lw=1, label="phase 0.5")
    secondary = (modshift or {}).get("phs_sec")
    if secondary is not None and np.isfinite(secondary):
        label = f"ModShift secondary, phase {secondary:.3f}"
        sig = modshift.get("sig_sec")
        if sig is not None and np.isfinite(sig):
            label += f", {sig:.1f} sigma"
        ax.axvline(secondary, color="C3", lw=1.2, label=label)
    ax.set_xlim(0.0, 1.0)
    # Scaled to the binned flux: a secondary a fifth of the primary's depth would be lost in the
    # scatter's range.
    if len(y) > 1:
        pad = 0.3 * max(float(y.max() - y.min()), 1.0)
        ax.set_ylim(float(y.min()) - pad, float(y.max()) + pad)
    else:
        ax.set_ylim(*_ylim(ppm))
    ax.set_xlabel("phase")
    ax.set_ylabel("flux (ppm)")
    ax.legend(fontsize=8, loc="lower center")
    ax.set_title(title)
    return _save(fig, path)


def centroids(
    pixels_evidence: dict | None, neighbours: dict | None, path: Path, limit_arcsec: float | None
) -> Path:
    """The pixel check's centroid offset per sector (triage's evidence) with its limit, and the
    separation of each Gaia DR3 neighbour that could host the signal."""
    title = "centroid offsets and possible hosts"
    rows = sorted(
        (
            r
            for r in (pixels_evidence or {}).get("sectors", [])
            if r.get("offset_arcsec") is not None and np.isfinite(r["offset_arcsec"])
        ),
        key=lambda r: r["sector"],
    )
    hosts = [
        h
        for h in ((neighbours or {}).get("evidence") or {}).get("possible_hosts", [])
        if h.get("sep_arcsec") is not None and np.isfinite(h["sep_arcsec"])
    ]
    if not rows and not hosts:
        return no_data(path, title, "no centroid offsets and no possible hosts")
    fig = Figure(figsize=(8, 4), layout="constrained")
    ax = fig.subplots()
    if rows:
        x = np.arange(len(rows))
        ax.plot(x, [r["offset_arcsec"] for r in rows], "o", color="C0", zorder=3, label="offset")

        def tick(r: dict) -> str:
            quality = r.get("quality")
            known = quality is not None and np.isfinite(quality)
            return f"S{r['sector']}\nq {quality:.2f}" if known else f"S{r['sector']}\nq ?"

        ax.set_xticks(x, [tick(r) for r in rows])
    else:
        ax.set_xticks([])
        ax.text(0.02, 0.95, "no centroid offsets", transform=ax.transAxes, va="top", fontsize=8)
    if limit_arcsec is not None:
        ax.axhline(
            limit_arcsec, color="C3", ls="--", lw=1, label=f'pixel check limit {limit_arcsec:g}"'
        )
    for h in hosts:
        ax.axhline(h["sep_arcsec"], color="C1", lw=0.8, alpha=0.7)
        needs = h.get("required_depth")
        label = f'{h["sep_arcsec"]:.1f}"'
        if needs is not None and np.isfinite(needs):
            label += f", needs a {needs:.2%} eclipse"
        ax.annotate(
            label,
            (1.0, h["sep_arcsec"]),
            xycoords=("axes fraction", "data"),
            ha="right",
            va="bottom",
            fontsize=7,
            color="C1",
        )
    if hosts:
        ax.plot([], [], color="C1", lw=0.8, label="possible host separation")
    ax.set_ylim(bottom=0.0)
    ax.set_ylabel("arcsec from the target")
    ax.legend(fontsize=8, loc="upper left")
    ax.set_title(title)
    return _save(fig, path)
