"""When TESS looks at a star next, and where a signal's transits fall in those sectors."""

import numpy as np
import pandas as pd
from astropy.time import Time
from tess_stars2px import tess_stars2px_function_entry

from tess_hunt.fit import NAMES
from tess_hunt.provenance import repo_root

MINUTES_PER_DAY = 1440.0


def load_sectors(sectors_file: str) -> pd.DataFrame:
    """`[predict] sectors_file`, a path relative to the repo root, wherever the command runs from."""
    return pd.read_csv(repo_root() / sectors_file)


def btjd(utc: str) -> float:
    return float(Time(utc, scale="utc").tdb.jd - 2457000.0)


def upcoming_sectors(tic: int, ra: float, dec: float, first: int) -> list[int]:
    """Every sector from `first` on in which tess-point places the star on a camera."""
    # tess-point gives one row per camera hit, and -1 for a star it places nowhere.
    found = tess_stars2px_function_entry(tic, ra, dec)[3]
    return sorted({int(s) for s in found if s >= first})


def windows(
    samples: np.ndarray,
    sectors: pd.DataFrame,
    upcoming: list[int],
    duration: float,
    sigma: list[float],
) -> list[dict]:
    """Each transit predicted in an upcoming sector, with its uncertainty from the posterior's own
    t0 + n * period samples, so a correlation between t0 and period carries through. `epoch` n
    counts periods from the fit's t0."""
    t0, period = samples[:, NAMES.index("t0")], samples[:, NAMES.index("period")]
    t0_mid, period_mid = float(np.median(t0)), float(np.median(period))
    dated = sectors.dropna(subset=["start_utc", "end_utc"]).set_index("sector")
    out = []
    for sector in upcoming:
        if sector not in dated.index:
            out.append({"sector": int(sector), "dates": "unknown"})
            continue
        start, end = btjd(dated.at[sector, "start_utc"]), btjd(dated.at[sector, "end_utc"])
        # One epoch spare on each side: the median of t0 + n * period need not be t0's median plus n
        # times period's.
        first = int(np.floor((start - t0_mid) / period_mid)) - 1
        last = int(np.ceil((end - t0_mid) / period_mid)) + 1
        for n in range(first, last + 1):
            mids = t0 + n * period
            mid = float(np.median(mids))
            if not start <= mid < end:
                continue
            sd = float(np.std(mids)) * MINUTES_PER_DAY
            out.append(
                {
                    "sector": int(sector),
                    "epoch": n,
                    "mid_btjd": mid,
                    "sd_minutes": sd,
                    "half_width_minutes": {f"{s:g}": s * sd for s in sigma},
                    "duration_days": duration,
                }
            )
    return out
