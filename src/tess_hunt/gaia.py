"""Gaia DR3 values for TIC stars, found through the TIC's Gaia DR2 ids."""

import sys
from functools import partial

import numpy as np
import pandas as pd
from astropy.table import Table

from tess_hunt.retry import retry

LOGG_SUN = 4.438  # cgs
QUERY = """
SELECT u.tic, n.dr3_source_id, n.angular_distance, g.ruwe, a.logg_gspphot, a.mass_flame, a.radius_flame,
       e.frequency AS eb_frequency, e.reference_time AS eb_reference_time
FROM tap_upload.ids AS u
JOIN gaiadr3.dr2_neighbourhood AS n ON n.dr2_source_id = u.dr2
JOIN gaiadr3.gaia_source AS g ON g.source_id = n.dr3_source_id
LEFT OUTER JOIN gaiadr3.astrophysical_parameters AS a ON a.source_id = n.dr3_source_id
LEFT OUTER JOIN gaiadr3.vari_eclipsing_binary AS e ON e.source_id = n.dr3_source_id
"""
COLUMNS = [
    "tic",
    "dr3_source_id",
    "angular_distance",
    "ruwe",
    "logg_gspphot",
    "mass_flame",
    "radius_flame",
    "logg_flame",
    "eb_frequency",
    "eb_reference_time",
]


class GaiaError(RuntimeError):
    pass


def launch_gaia(query: str, ids: Table, gaia=None) -> pd.DataFrame:
    if gaia is None:
        # Importing astroquery.gaia contacts the archive, so only a real query pays for it.
        from astroquery.gaia import Gaia

        gaia = Gaia
    job = gaia.launch_job_async(query, upload_resource=ids, upload_table_name="ids", verbose=False)
    try:
        return job.get_results().to_pandas()
    finally:
        # Anonymous jobs count against a quota on the archive, but a job left behind costs less than
        # discarding its result and spending a retry.
        try:
            gaia.remove_jobs([job.jobid])
        except Exception as exc:  # the archive answers outages with assorted exception types
            print(
                f"Gaia job {job.jobid} left on the archive: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )


def logg_flame(mass, radius) -> np.ndarray:
    m, r = np.asarray(mass, dtype=float), np.asarray(radius, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        return LOGG_SUN + np.log10(m) - 2.0 * np.log10(r)


def dr3_join(
    stars: pd.DataFrame,
    launch=launch_gaia,
    chunk: int = 50_000,
    attempts: int = 3,
    backoff: float = 30.0,
) -> pd.DataFrame:
    """One row per star with a DR2 id: its nearest DR3 neighbour's values. Stars without one are absent."""
    # DR2 ids run past 2**53, so a float parse (which one blank id forces) would round them.
    text = stars["gaia"].astype("string").str.strip()
    known = text.str.fullmatch(r"\d+").fillna(False).astype(bool)
    have = stars.loc[known].assign(dr2=text[known].astype("int64"))
    parts = []
    for start in range(0, len(have), chunk):
        part = have.iloc[start : start + chunk]
        ids = Table({"tic": part["tic"].astype("int64").to_numpy(), "dr2": part["dr2"].to_numpy()})
        parts.append(
            retry(
                partial(launch, QUERY, ids),
                attempts=attempts,
                backoff=backoff,
                # The archive answers outages with assorted exception types.
                retry_on=Exception,
                error=GaiaError,
                what="Gaia archive",
            )
        )
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    raw = pd.concat(parts, ignore_index=True)
    # A DR2 source can split into several DR3 sources; the nearest is the same star.
    raw = raw.sort_values(["tic", "angular_distance"]).drop_duplicates("tic")
    raw["logg_flame"] = logg_flame(raw["mass_flame"], raw["radius_flame"])
    return raw[COLUMNS].reset_index(drop=True)
