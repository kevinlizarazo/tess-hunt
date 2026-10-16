"""Pixel vetting: LEO-Vetter's difference-image centroid test through transit-diffImage, with every way it
can fail to look counted as inconclusive."""

import pickle
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


class MissingImages(Exception):
    """Sectors LEO-Vetter tried left no difference image. transit-diffImage fetches TESScut cutouts with curl
    through os.system, so a failed download raises nothing and shows only as a missing image file."""

    def __init__(self, good: list, centroids: list, missing: list[int]):
        super().__init__(f"no difference image for sectors {missing}")
        self.good, self.centroids, self.missing = good, centroids, missing


def pixel_vetting(tlc, star: Mapping, sectors: list[int], **kwargs):
    # leo_vetter.pixel imports transit-diffImage, which imports astroquery.gaia, and that import contacts
    # the Gaia archive; only a real pixel check pays for it.
    from leo_vetter.pixel import pixel_vetting as run

    return run(tlc, star, sectors, **kwargs)


def observable_sectors(tic: int, ra: float, dec: float, sectors: list[int]) -> list[int]:
    """pixel_vetting looks the star's camera up by sector and raises on a sector tess-point doesn't list."""
    on = {int(s) for s in tess_stars2px_function_entry(tic, ra, dec)[3]}
    return [s for s in sectors if s in on]


def asked_ephemeris(metrics: Mapping) -> tuple:
    """Period, epoch and duration in hours as leo-vetter 1.2.0's planet_dict_from_metrics hands them to
    transit-diffImage: the transit fit's, else the trapezoid fit's, else the search's. Copied, not
    imported, because importing leo_vetter.pixel contacts the Gaia archive."""
    for fit in ("transit", "trap"):
        if f"{fit}_aic" in metrics and not np.isnan(metrics[f"{fit}_aic"]):
            return metrics[f"{fit}_per"], metrics[f"{fit}_epo"], metrics[f"{fit}_dur"] * 24
    return metrics["per"], metrics["epo"], metrics["dur"] * 24


def drop_stale_images(star_dir: Path, planet_id: str, asked: tuple) -> list[str]:
    """transit-diffImage reuses any difference image saved under the planet's name without checking its
    ephemeris, so one made for another ephemeris, or one that cannot be read, is removed first."""
    removed = []
    for path in sorted(star_dir.glob(f"imageData_{planet_id}_sector*.pickle")):
        try:
            with open(path, "rb") as fh:
                planet = pickle.load(fh)[6]
            stored = (planet["period"], planet["epoch"], planet["durationHours"])
        except Exception:  # a truncated or foreign file is made again
            stored = None
        if stored != asked:
            path.unlink()
            removed.append(path.name)
    return removed


def pixel_check(
    tlc,
    star: Mapping,
    sectors: list[int],
    cfg: dict,
    tdi_dir: Path,
    attempts: int = 3,
    backoff: float = 30.0,
) -> CheckResult:
    """LEO-Vetter's pixel test on the latest sectors the star has data in. `tdi_dir` must be unique to
    the signal: transit-diffImage names its difference images by TIC, planet number (always 1 here) and
    sector, so a second signal on the star would find the first one's."""
    limit, n_bad, max_sectors = cfg["max_offset_arcsec"], cfg["n_bad"], cfg["max_sectors"]
    missing_tools = [tool for tool in ("curl", "unzip") if shutil.which(tool) is None]
    if missing_tools:
        # transit-diffImage shells out to them, and without them every cutout fails quietly.
        return inconclusive("pixels", f"transit-diffImage needs {', '.join(missing_tools)} on PATH")
    tic, ra, dec = int(star["tic"]), float(star["ra"]), float(star["dec"])
    usable = observable_sectors(tic, ra, dec, sorted(set(sectors), reverse=True))
    if not usable:
        return inconclusive(
            "pixels",
            "no sector with data that tess-point places the star in",
            sectors=sorted(sectors),
        )
    star_dir = Path(tdi_dir) / f"tic{tic}"
    planet_id = f"{int(tlc.metrics['tic'])}.{int(tlc.metrics['planetno'])}"
    # transit-diffImage makes its per-star directory with a plain mkdir, which fails without the parent.
    Path(tdi_dir).mkdir(parents=True, exist_ok=True)
    stale = drop_stale_images(star_dir, planet_id, asked_ephemeris(tlc.metrics))

    def look() -> tuple[list, list, list[int]]:
        _, good, _, centroids = pixel_vetting(
            tlc,
            {"tic": tic, "ra": ra, "dec": dec},
            usable,
            tdi_dir=str(tdi_dir),
            n_bad=n_bad,
            max_sectors=max_sectors,
        )
        # LEO-Vetter stops at max_sectors good ones, so sectors after the last good one were not tried.
        tried = usable[: usable.index(good[-1]) + 1] if len(good) >= max_sectors else usable
        no_image = [
            s for s in tried if not (star_dir / f"imageData_{planet_id}_sector{s}.pickle").exists()
        ]
        if no_image:
            raise MissingImages(good, centroids, no_image)
        return good, centroids, []

    try:
        # TESScut, MAST's TIC query and the PRF files fail with assorted exception types. A retry redoes
        # only the sectors that left no difference image: transit-diffImage reuses the ones it saved.
        good, centroids, no_image = retry(
            look,
            attempts=attempts,
            backoff=backoff,
            retry_on=Exception,
            error=PixelError,
            what=f"pixel vetting of TIC {tic}",
        )
    except PixelError as exc:
        cause = exc.__cause__
        if not isinstance(cause, MissingImages):
            return inconclusive("pixels", str(exc), asked=usable, stale_removed=stale)
        # The sectors that did give an image are evidence; the missing ones are recorded beside them.
        good, centroids, no_image = cause.good, cause.centroids, cause.missing
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
        "no_image": no_image,
        "stale_removed": stale,
        "files": files,
    }
    # The published comparison passes a NaN offset; here no difference image is no evidence.
    if not good:
        return inconclusive("pixels", "no sector gave a usable difference image", **evidence)
    if not np.isfinite(offset):
        return inconclusive("pixels", "the best-quality sector's offset is NaN", **evidence)
    if offset > limit:
        return failed("pixels", f'centroid offset {offset:.1f}" exceeds {limit:g}"', **evidence)
    return passed("pixels", f'centroid offset {offset:.1f}" within {limit:g}"', **evidence)
