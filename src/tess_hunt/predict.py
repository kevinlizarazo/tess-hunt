"""When TESS looks at a star next, and where a signal's transits fall in those sectors."""

import astropy.units as u
import numpy as np
import pandas as pd
from astropy.constants import c
from astropy.coordinates import get_body_barycentric
from astropy.time import Time, TimeDelta
from astropy.utils import iers
from tess_stars2px import tess_stars2px_function_entry

from tess_hunt.fit import NAMES
from tess_hunt.provenance import repo_root

MINUTES_PER_DAY = 1440.0


def load_sectors(sectors_file: str) -> pd.DataFrame:
    """`[predict] sectors_file`, a path relative to the repo root, wherever the command runs from."""
    return pd.read_csv(repo_root() / sectors_file)


def btjd(utc: str) -> float:
    # astropy's bundled leap-second table expires 2027-06-28 and uv.lock fixes astropy; from 150 days before then
    # a UTC conversion would try to download a newer table. These conversions keep to the bundled one, and warn once
    # it has expired (decision 0024). The setting is scoped to these two calls, never global: frozen modules use
    # astropy too, directly or through the libraries they call, and their behaviour must not change. astropy checks
    # once per process, so when one of these is a process's first UTC conversion it settles the check for that whole
    # process.
    with iers.conf.set_temp("auto_download", False):
        return float(Time(utc, scale="utc").tdb.jd - 2457000.0)


def seen_utc(btjd: float, ra: float, dec: float) -> str:
    """The mid-time as seen from Earth, in UTC: BJD_TDB less the light's travel time between the geocentre and the
    barycentre toward the star, which runs to about 8 minutes either way. The travel time is taken at the geocentric
    time, found by one iteration from the barycentric one. Earth's position comes from ERFA's built-in ephemeris and
    the leap seconds from astropy's bundled table, as in `btjd`, so nothing here needs IERS tables or the network."""
    ra, dec = np.radians(ra), np.radians(dec)
    toward = np.array([np.cos(dec) * np.cos(ra), np.cos(dec) * np.sin(ra), np.sin(dec)])

    def delay(t: Time) -> TimeDelta:
        earth = get_body_barycentric("earth", t, ephemeris="builtin").xyz.to_value(u.m)
        return TimeDelta(earth @ toward / c.value, format="sec")

    with iers.conf.set_temp("auto_download", False):
        bjd = Time(btjd + 2457000.0, format="jd", scale="tdb")
        seen = bjd - delay(bjd - delay(bjd))
        return seen.utc.strftime("%Y-%m-%d %H:%M")


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
