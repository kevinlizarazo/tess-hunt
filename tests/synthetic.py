"""Synthetic light curves and catalog snapshots for tests."""

from pathlib import Path

import numpy as np
import pandas as pd

from tess_hunt.lightcurve import LightCurve


def sector_times(sector: int, cadence_min: float) -> np.ndarray:
    """27 days per sector with a one-day gap between the two orbits, like TESS."""
    start = 1325.0 + 27.4 * (sector - 1)
    t = np.arange(start, start + 27.0, cadence_min / 1440.0)
    return t[(t < start + 13.0) | (t > start + 14.0)]


def box(time, period, t0, duration, depth) -> np.ndarray:
    phase = (time - t0 + 0.5 * period) % period - 0.5 * period
    return np.where(np.abs(phase) < 0.5 * duration, -depth, 0.0)


def make_lc(
    sectors=(1, 2, 3),
    cadence_min=30.0,
    noise_ppm=200.0,
    signals=(),
    seed=0,
    tic=1,
    cadences=None,
) -> LightCurve:
    """Flat light curve plus box transits. signals: (period, t0, duration, depth) tuples.
    cadences and noise_ppm may be dicts keyed by sector."""
    rng = np.random.default_rng(seed)
    times, sectors_col, errs, sources = [], [], [], {}
    for s in sectors:
        cadence = (cadences or {}).get(s, cadence_min)
        noise = noise_ppm[s] if isinstance(noise_ppm, dict) else noise_ppm
        t = sector_times(s, cadence)
        times.append(t)
        sectors_col.append(np.full(len(t), s, dtype=np.int16))
        errs.append(np.full(len(t), noise * 1e-6))
        sources[str(s)] = {"provenance": "synthetic", "cadence_s": cadence * 60.0}
    time, sector, err = np.concatenate(times), np.concatenate(sectors_col), np.concatenate(errs)
    flux = 1.0 + rng.normal(0.0, 1.0, len(time)) * err
    for period, t0, duration, depth in signals:
        flux += box(time, period, t0, duration, depth)
    return LightCurve(tic, time, flux, err, sector, sources)


def with_products(lc: LightCurve, provenance: dict[int, str], suspect=()) -> LightCurve:
    """Each sector's product and fetch's timing flag, as a fetched light curve carries them."""
    for sector, name in provenance.items():
        lc.sources[str(sector)].update(provenance=name, timing_suspect=sector in suspect)
    return lc


def correlated_noise(lc: LightCurve, rms_ppm: float, smooth_hours: float, seed: int) -> np.ndarray:
    """White noise smoothed by a running mean of `smooth_hours` within each sector, scaled to
    `rms_ppm`. It stays correlated over a transit and survives a 1.2 d biweight, like the residuals
    of a bright star's 2-min light curve."""
    rng = np.random.default_rng(seed)
    out = np.zeros(len(lc.time))
    for sector in np.unique(lc.sector):
        m = lc.sector == sector
        k = max(1, round(smooth_hours * 3600.0 / lc.sources[str(int(sector))]["cadence_s"]))
        # "valid" over k - 1 extra draws, so the sector edges are as smooth as the middle.
        smooth = np.convolve(rng.normal(size=m.sum() + k - 1), np.ones(k) / k, mode="valid")
        out[m] = smooth * np.sqrt(k) * rms_ppm * 1e-6
    return out


TOI_COLUMNS = [
    "TIC ID",
    "TOI",
    "TFOPWG Disposition",
    "TESS Mag",
    "Stellar Eff Temp (K)",
    "Stellar log(g) (cm/s^2)",
    "RA",
    "Dec",
    "Period (days)",
    "Epoch (BJD)",
    "Duration (hours)",
    "Depth (ppm)",
    "Planet SNR",
    "Comments",
]
CTOI_COLUMNS = [
    "TIC ID",
    "CTOI",
    "RA",
    "Dec",
    "Period (days)",
    "Transit Epoch (BJD)",
    "Duration (hrs)",
    "Depth ppm",
]
ARCHIVE_COLUMNS = [
    "pl_name",
    "tic_id",
    "pl_orbper",
    "pl_tranmid",
    "pl_trandep",
    "pl_trandur",
    "ra",
    "dec",
]
FAR_TOI = {
    "TIC ID": 999001,
    "TOI": 9001.01,
    "TFOPWG Disposition": "PC",
    "TESS Mag": 9.0,
    "Stellar Eff Temp (K)": 5800.0,
    "Stellar log(g) (cm/s^2)": 4.4,
    "RA": "00:00:00.0",
    "Dec": "+80:00:00.0",
    "Period (days)": 2.5,
    "Epoch (BJD)": 2459000.0,
    "Duration (hours)": 2.0,
    "Depth (ppm)": 1000.0,
    "Planet SNR": 20.0,
    "Comments": "",
}
FAR_CTOI = {
    "TIC ID": 999002,
    "CTOI": 999002.01,
    "RA": 1.0,
    "Dec": 80.0,
    "Period (days)": 3.5,
    "Transit Epoch (BJD)": 2459001.0,
    "Duration (hrs)": 2.0,
    "Depth ppm": 900.0,
}
FAR_ARCHIVE = {
    "pl_name": "Far b",
    "tic_id": "TIC 999003",
    "pl_orbper": 4.5,
    "pl_tranmid": 2459002.0,
    "pl_trandep": 0.1,
    "pl_trandur": 2.0,
    "ra": 2.0,
    "dec": 80.0,
}


def write_catalog_snapshot(path: Path, toi_rows=(), ctoi_rows=(), archive_rows=()) -> Path:
    """A snapshot directory with one far-away object per catalog plus the given rows."""
    path.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([FAR_TOI, *toi_rows], columns=TOI_COLUMNS).to_csv(path / "toi.csv", index=False)
    pd.DataFrame([FAR_CTOI, *ctoi_rows], columns=CTOI_COLUMNS).to_csv(
        path / "ctoi.csv", index=False
    )
    pd.DataFrame([FAR_ARCHIVE, *archive_rows], columns=ARCHIVE_COLUMNS).to_csv(
        path / "pscomppars.csv", index=False
    )
    return path


from tess_hunt.transit import a_rs_from_density, light_curve  # noqa: E402


def make_transit_lc(
    rho_gcc=1.41,
    rp_rs=0.03,
    b=0.3,
    period=5.0,
    t0=1326.1,
    sectors=(1, 2, 64),
    cadences=None,
    noise_ppm=None,
    seed=3,
) -> LightCurve:
    """Limb-darkened transit; by default two 2-min sectors and one 30-min sector, as in the 2026-10-08 probe."""
    cadences = cadences or {1: 2.0, 2: 2.0, 64: 30.0}
    noise_ppm = noise_ppm or {1: 600.0, 2: 600.0, 64: 150.0}
    lc = make_lc(sectors=sectors, cadences=cadences, noise_ppm=noise_ppm, seed=seed)
    model = light_curve(
        lc.time,
        lc.exposure_days(),
        t0,
        period,
        rp_rs,
        a_rs_from_density(rho_gcc, period),
        b,
        0.36,
        0.24,
    )
    lc.flux = lc.flux * model
    return lc


ROOT = Path(__file__).resolve().parents[1]


def relaxed_criteria(tmp_path: Path) -> Path:
    """search-v2.toml with sample A's coverage rule relaxed so a three-sector synthetic star counts."""
    text = (ROOT / "criteria" / "search-v2.toml").read_text()
    for old, new in (
        ("min_sectors = 4", "min_sectors = 3"),
        ("recent_sector_min = 97", "recent_sector_min = 1"),
        ("recent_sector_max = 107", "recent_sector_max = 3"),
    ):
        assert old in text
        text = text.replace(old, new)
    path = tmp_path / "search.toml"
    path.write_text(text)
    return path
