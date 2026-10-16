"""Find TESS light-curve files at MAST and download them from the public S3 bucket or MAST."""

import re
import sys
from functools import partial

import numpy as np
import pandas as pd
import requests
from astroquery.mast import Observations

from tess_hunt.retry import retry

PROVENANCES = ("SPOC", "TESS-SPOC", "QLP")
PREFERENCE = {"SPOC": 0, "TESS-SPOC": 1, "QLP": 2}
S3_BASE = "https://stpubdata.s3.amazonaws.com/"
MAST_API = "https://mast.stsci.edu/api/v0.1/Download/file?uri="
PRODUCT_COLUMNS = [
    "tic",
    "sector",
    "provenance",
    "cadence_s",
    "filename",
    "data_uri",
    "size",
    "s3_key",
]
_SPOC_NAME = re.compile(r"^tess\d{13}-s(\d{4})-(\d{16})-\d{4}-s_lc\.fits$")


class DownloadError(RuntimeError):
    pass


class MissingProduct(DownloadError):
    pass


class BadResponse(RuntimeError):
    """A reply worth retrying: a server error or a truncated body."""


class DiscoverError(RuntimeError):
    pass


def s3_key(data_uri: str) -> str:
    if data_uri.startswith("mast:HLSP/"):
        return "mast/hlsp/" + data_uri[len("mast:HLSP/") :]
    if data_uri.startswith("mast:TESS/product/"):
        name = data_uri[len("mast:TESS/product/") :]
        match = _SPOC_NAME.match(name)
        if not match:
            raise ValueError(f"unrecognised SPOC product name: {name}")
        sector, tic16 = match.groups()
        parts = "/".join(tic16[i : i + 4] for i in range(0, 16, 4))
        return f"tess/public/tid/s{sector}/{parts}/{name}"
    raise ValueError(f"unrecognised data URI: {data_uri}")


def is_light_curve(provenance: str, filename: str) -> bool:
    if provenance == "QLP":
        return filename.endswith("_llc.fits")
    return filename.endswith("_lc.fits") and not filename.endswith("fast-lc.fits")


def _batch_rows(names: list[str], observations) -> list[dict]:
    obs = observations.query_criteria(
        target_name=names, provenance_name=list(PROVENANCES), dataproduct_type="timeseries"
    )
    if len(obs) == 0:
        return []
    # 20-s targets also get their own 20-s observation; the 2-min one covers the same sector.
    fast = (obs["provenance_name"] == "SPOC") & (np.asarray(obs["t_exptime"], dtype=float) < 100)
    obs = obs[~fast]
    by_obs_id = {str(o["obs_id"]): o for o in obs}
    rows = []
    for product in observations.get_product_list(obs):
        o = by_obs_id.get(str(product["obs_id"]))
        name = str(product["productFilename"])
        if o is None or not is_light_curve(str(o["provenance_name"]), name):
            continue
        size = product["size"]
        rows.append(
            {
                "tic": int(o["target_name"]),
                "sector": int(o["sequence_number"]),
                "provenance": str(o["provenance_name"]),
                "cadence_s": float(o["t_exptime"]),
                "filename": name,
                "data_uri": str(product["dataURI"]),
                "size": 0 if np.ma.is_masked(size) else int(size),
                "s3_key": s3_key(str(product["dataURI"])),
            }
        )
    return rows


def discover(
    tics: list[int],
    batch: int = 50,
    attempts: int = 3,
    backoff: float = 10.0,
    failed: list | None = None,
    observations=None,
) -> pd.DataFrame:
    """Every SPOC 2-min, TESS-SPOC and QLP light-curve file for these stars. With `failed`, a batch that
    keeps failing adds its TICs there and the rest carry on; without it, the failure raises."""
    observations = observations or Observations
    rows = []
    for start in range(0, len(tics), batch):
        names = [str(t) for t in tics[start : start + batch]]
        try:
            rows += retry(
                partial(_batch_rows, names, observations),
                attempts=attempts,
                backoff=backoff,
                # MAST answers outages with assorted exception types.
                retry_on=Exception,
                error=DiscoverError,
                what=f"MAST discovery of {len(names)} TICs",
            )
        except DiscoverError as exc:
            if failed is None:
                raise
            # The cause tells an outage from a fault that retrying will never fix.
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            failed.extend(int(n) for n in names)
    frame = pd.DataFrame(rows, columns=PRODUCT_COLUMNS)
    return frame.drop_duplicates("data_uri").reset_index(drop=True)


def rank(products: pd.DataFrame) -> pd.DataFrame:
    """Products best-first within each star and sector: SPOC 2-min, then TESS-SPOC, then QLP."""
    order = products["provenance"].map(PREFERENCE)
    ranked = products.assign(_rank=order).sort_values(["tic", "sector", "_rank", "cadence_s"])
    return ranked.drop(columns="_rank").reset_index(drop=True)


def best(products: pd.DataFrame) -> pd.DataFrame:
    return rank(products).drop_duplicates(["tic", "sector"]).reset_index(drop=True)


def _get(url: str, expected_size: int, session) -> bytes:
    response = session.get(url, timeout=60)
    if response.status_code == 404:
        raise MissingProduct(f"not found: {url}")
    if response.status_code != 200:
        raise BadResponse(f"HTTP {response.status_code}")
    if expected_size and len(response.content) != expected_size:
        raise BadResponse(f"got {len(response.content)} bytes, expected {expected_size}")
    return response.content


def _fetch(url: str, expected_size: int, session, attempts: int, backoff: float) -> bytes:
    return retry(
        partial(_get, url, expected_size, session),
        attempts=attempts,
        backoff=backoff,
        retry_on=(requests.RequestException, BadResponse),
        error=DownloadError,
        what=url,
    )


def download(
    key: str,
    expected_size: int,
    session,
    attempts: int = 3,
    backoff: float = 2.0,
    data_uri: str | None = None,
) -> tuple[bytes, str]:
    """The file's bytes and the route that served them. Products listed at MAST can be missing from the
    bucket (QLP S99 to S104 in 2026-10), so a bucket 404 falls through to MAST's own download API."""
    try:
        return _fetch(S3_BASE + key, expected_size, session, attempts, backoff), "s3"
    except MissingProduct:
        if not data_uri:
            raise
    return _fetch(MAST_API + data_uri, expected_size, session, attempts, backoff), "mast_api"
