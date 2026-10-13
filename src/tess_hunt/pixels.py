"""Pixel vetting: LEO-Vetter's difference-image centroid test through transit-diffImage, with every way it
can fail to look counted as inconclusive."""

import shutil
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from tess_stars2px import tess_stars2px_function_entry

from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.provenance import sha256_file
from tess_hunt.retry import retry


class PixelError(RuntimeError):
    pass


class NoDifferenceImage(Exception):
    """No sector gave a difference image. transit-diffImage runs curl through os.system, so a failed TESScut
    download raises nothing and looks like this."""

    def __init__(self, good: list, centroids: list):
        super().__init__("no sector gave a difference image")
        self.good, self.centroids = good, centroids


def pixel_vetting(tlc, star: Mapping, sectors: list[int], **kwargs):
    # leo_vetter.pixel imports transit-diffImage, which imports astroquery.gaia, and that import contacts
    # the Gaia archive; only a real pixel check pays for it.
    from leo_vetter.pixel import pixel_vetting as run

    return run(tlc, star, sectors, **kwargs)


def observable_sectors(tic: int, ra: float, dec: float, sectors: list[int]) -> list[int]:
    """pixel_vetting looks the star's camera up by sector and raises on a sector tess-point doesn't list."""
    on = {int(s) for s in tess_stars2px_function_entry(tic, ra, dec)[3]}
    return [s for s in sectors if s in on]


def pixel_check(
    tlc,
    star: Mapping,
    sectors: list[int],
    cfg: dict,
    tdi_dir: Path,
    attempts: int = 3,
    backoff: float = 30.0,
) -> CheckResult:
    missing = [tool for tool in ("curl", "unzip") if shutil.which(tool) is None]
    if missing:
        # transit-diffImage shells out to them, and without them every cutout fails quietly.
        return inconclusive("pixels", f"transit-diffImage needs {', '.join(missing)} on PATH")
    tic, ra, dec = int(star["tic"]), float(star["ra"]), float(star["dec"])
    usable = observable_sectors(tic, ra, dec, sorted(set(sectors), reverse=True))
    if not usable:
        return inconclusive(
            "pixels",
            "no sector with data that tess-point places the star in",
            sectors=sorted(sectors),
        )
    # transit-diffImage makes its per-star directory with a plain mkdir, which fails without the parent.
    Path(tdi_dir).mkdir(parents=True, exist_ok=True)

    def look() -> tuple[list, list]:
        _, good, _, centroids = pixel_vetting(
            tlc,
            {"tic": tic, "ra": ra, "dec": dec},
            usable,
            tdi_dir=str(tdi_dir),
            n_bad=cfg["n_bad"],
            max_sectors=cfg["max_sectors"],
        )
        if not np.isfinite(float(tlc.metrics.get("offset_qual", np.nan))):
            raise NoDifferenceImage(good, centroids)
        return good, centroids

    try:
        # TESScut, MAST's TIC query and the PRF files fail with assorted exception types. A retry redoes
        # only the sectors that left no difference image: transit-diffImage reuses the ones it saved.
        good, centroids = retry(
            look,
            attempts=attempts,
            backoff=backoff,
            retry_on=Exception,
            error=PixelError,
            what=f"pixel vetting of TIC {tic}",
        )
    except PixelError as exc:
        if not isinstance(exc.__cause__, NoDifferenceImage):
            return inconclusive("pixels", str(exc), asked=usable)
        good, centroids = exc.__cause__.good, exc.__cause__.centroids
    star_dir = Path(tdi_dir) / f"tic{tic}"
    files = {
        str(p.relative_to(tdi_dir)): sha256_file(p)
        for p in sorted(star_dir.rglob("*"))
        if p.is_file()
    }
    offset = float(tlc.metrics.get("offset_qual", np.nan))
    evidence = {
        "offset_qual_arcsec": offset,
        "offset_mean_arcsec": float(tlc.metrics.get("offset_mean", np.nan)),
        "sectors": [
            {
                "sector": int(s),
                "offset_arcsec": float(c["offset_arc"]),
                "quality": float(c["quality"]),
            }
            for s, c in zip(good, centroids, strict=True)
        ],
        "asked": usable,
        "files": files,
    }
    # The published comparison passes a NaN offset; here no difference image is no evidence.
    if not np.isfinite(offset):
        return inconclusive("pixels", "no usable difference image", **evidence)
    if offset > cfg["max_offset_arcsec"]:
        return failed(
            "pixels",
            f'centroid offset {offset:.1f}" exceeds {cfg["max_offset_arcsec"]:g}"',
            **evidence,
        )
    return passed(
        "pixels", f'centroid offset {offset:.1f}" within {cfg["max_offset_arcsec"]:g}"', **evidence
    )
