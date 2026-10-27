"""TRICERATOPS (Giacalone et al. 2021): the probability that a signal is a false positive (FPP) and that it comes from
a nearby star (NFPP), with each way TRICERATOPS can go quietly wrong made inconclusive
(docs/decisions/0026-triceratops.md)."""

import hashlib
import os
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from astropy.io import fits

from tess_hunt import mast
from tess_hunt.checks import CheckResult, failed, inconclusive, passed
from tess_hunt.config import data_dir
from tess_hunt.ephemeris import Ephemeris, epoch_numbers, in_transit, phase_days
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import scrub, sha256_file

CHECK = "triceratops"
# calc_probs gets the fold within this many transit durations of mid-transit.
WINDOW_DURATIONS = 2.0
# The filters TRICERATOPS has contrast-curve relations for.
FILTERS = ("TESS", "Vis", "J", "H", "K")
SPOC, TESS_SPOC = "SPOC", "TESS-SPOC"
TWO_MINUTES_S = 120.0
STAR_COLUMNS = ("ID", "ra", "dec", "Tmag", "disposition", "tdepth")
# The TIC's flags for a row that is not a star of its own: DUPLICATE, a second entry for a star already in the TIC, and
# ARTIFACT, a spurious 2MASS source (Paegert et al. 2021, arXiv:2108.04778, section 3.1).
DROPPED_DISPOSITIONS = ("DUPLICATE", "ARTIFACT")
# TIC v8 gives each star's position at epoch J2000.0, moved there from its source catalogue's epoch (Stassun et al.
# 2019, AJ 158, 138); TRICERATOPS's star list takes the TIC's ra and dec.
TIC_EPOCH = 2000.0
# Gaia DR3's positions are at its reference epoch, J2016.0 (gaia_source's ref_epoch).
GAIA_DR3_EPOCH = 2016.0
MAS_PER_DEGREE = 3.6e6
# calc_probs needs these for the target; without one it stops at the target and reports probabilities from no
# scenario at all.
TARGET_PARAMETERS = ("mass", "rad", "Teff", "plx")
# Every field `run` records. `run` sets each one None (the runs' lists empty) before its first step and fills it on
# reaching it, in a dict `check` keeps when `run` raises: the record says how far TRICERATOPS got on every path, and
# None marks a step it never reached.
RUN_FIELDS = (
    "groups",
    "exposure_s",
    "sectors",
    "left_out",
    "points",
    "flux_err_0",
    "field_population",
    "field_population_file",
    "dropped_stars",
    "apertures",
    "stars",
    "fpp",
    "nfpp",
    "degenerate",
    "probs",
    "stopped",
)


class ContrastError(ValueError):
    pass


def _number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def _spread(name: str, values: list[float]) -> dict:
    array = np.asarray(values, dtype=float)
    finite = len(array) > 0 and bool(np.isfinite(array).all())
    return {
        f"{name}_mean": float(array.mean()) if finite else None,
        f"{name}_sd": float(array.std(ddof=1)) if finite and len(array) > 1 else None,
    }


def outcome(
    fpp: list[float], nfpp: list[float], cfg: dict, blockers: list[str], label_ok: bool
) -> CheckResult:
    """Pass on the paper's "likely planet" (mean FPP and NFPP both under their lines), fail on its "likely nearby
    false positive" (mean NFPP over `nfpp_fail`), otherwise inconclusive. Any blocker, or any run that is not
    finite, is inconclusive whatever the numbers say."""
    fpp, nfpp = [float(v) for v in fpp], [float(v) for v in nfpp]
    evidence = {
        "fpp": fpp,
        "nfpp": nfpp,
        **_spread("fpp", fpp),
        **_spread("nfpp", nfpp),
        "blockers": list(blockers),
        "validated_label": False,
    }
    if blockers:
        return inconclusive(CHECK, "; ".join(blockers), **evidence)
    if not fpp or len(fpp) != len(nfpp):
        return inconclusive(CHECK, "no TRICERATOPS run gave an FPP and an NFPP", **evidence)
    if not np.isfinite(fpp + nfpp).all():
        return inconclusive(CHECK, "a TRICERATOPS run gave a non-finite FPP or NFPP", **evidence)
    f, n = evidence["fpp_mean"], evidence["nfpp_mean"]
    # A label, never an outcome: the paper validates only with a contrast curve and 2-min data.
    evidence["validated_label"] = bool(
        label_ok and f < cfg["fpp_validated"] and n < cfg["nfpp_pass"]
    )
    runs = f"over {len(fpp)} run(s)"
    if n > cfg["nfpp_fail"]:
        return failed(
            CHECK,
            f"mean NFPP {n:.3g} > {cfg['nfpp_fail']:g} {runs}: likely a nearby false positive",
            **evidence,
        )
    if f < cfg["fpp_pass"] and n < cfg["nfpp_pass"]:
        return passed(
            CHECK,
            f"mean FPP {f:.3g} < {cfg['fpp_pass']:g} and mean NFPP {n:.3g} < {cfg['nfpp_pass']:g} {runs}: "
            "likely a planet",
            **evidence,
        )
    return inconclusive(
        CHECK,
        f"mean FPP {f:.3g}, mean NFPP {n:.3g} {runs}: neither likely a planet nor likely a nearby false positive",
        **evidence,
    )


def _separation_arcsec(ra1, dec1, ra2, dec2) -> np.ndarray:
    ra1, dec1, ra2, dec2 = (np.radians(np.asarray(v, dtype=float)) for v in (ra1, dec1, ra2, dec2))
    # Haversine: well conditioned at the arcsecond separations matched here.
    h = np.sin((dec2 - dec1) / 2) ** 2 + np.cos(dec1) * np.cos(dec2) * np.sin((ra2 - ra1) / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))) * 3600.0


def _motion(possible: pd.DataFrame, column: str) -> np.ndarray:
    values = pd.to_numeric(possible[column], errors="coerce").to_numpy(dtype=float)
    return np.where(np.isfinite(values), values, 0.0)


def at_tic_epoch(possible: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """Each possible host's Gaia DR3 position moved back to the TIC's epoch with its DR3 proper motion (Ruling S),
    where TRICERATOPS's stars sit. A host without one (a two-parameter solution) stays where DR3 puts it."""
    ra, dec = possible["ra"].to_numpy(dtype=float), possible["dec"].to_numpy(dtype=float)
    years = GAIA_DR3_EPOCH - TIC_EPOCH
    # DR3's pmra already carries the cos(dec) factor.
    ra_tic = ra - _motion(possible, "pmra") * years / (MAS_PER_DEGREE * np.cos(np.radians(dec)))
    # A host near RA 0 can move back across it; the evidence keeps RA in [0, 360) as the catalogues do.
    return ra_tic % 360.0, dec - _motion(possible, "pmdec") * years / MAS_PER_DEGREE


def _nearest(possible: pd.DataFrame, stars: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """For each possible host at the TIC's epoch (`at_tic_epoch`), the row in `stars` of the nearest TRICERATOPS star
    other than the target (the first row) and its distance in arcsec. The target is weighed as the target, so a
    companion the TIC merged into it, which sits closer to it than to any other star, must not count as weighed."""
    nearby = stars.iloc[1:]
    if len(possible) == 0 or len(nearby) == 0:
        return np.full(len(possible), -1), np.full(len(possible), np.inf)
    ra, dec = at_tic_epoch(possible)
    distance = _separation_arcsec(
        ra[:, None],
        dec[:, None],
        nearby["ra"].to_numpy()[None, :],
        nearby["dec"].to_numpy()[None, :],
    )
    # A star without a position matches nothing; argmin would otherwise pick its NaN.
    distance = np.where(np.isfinite(distance), distance, np.inf)
    rows = np.argmin(distance, axis=1)
    return rows + 1, distance[np.arange(len(possible)), rows]


def missing_hosts(possible: pd.DataFrame, stars: pd.DataFrame, match_arcsec: float) -> list[int]:
    """The possible hosts (the neighbour table's rows with `possible` true) with no TRICERATOPS star but the target
    (`stars`' first row) within `match_arcsec` at the TIC's epoch: stars TRICERATOPS did not weigh, so its NFPP leaves
    them out."""
    _, distance = _nearest(possible, stars)
    return [
        int(s)
        for s, d in zip(possible.get("source_id", []), distance, strict=True)
        if not d <= match_arcsec
    ]


def _hosts(possible: pd.DataFrame, stars: pd.DataFrame, match_arcsec: float) -> list[dict]:
    """Each possible host beside the TRICERATOPS star matched to it and that star's `tdepth`: the cross-check of the
    neighbour table (M3 design, section 4.4). Each keeps its proper motion and its position at the TIC's epoch, where
    the distance is measured."""
    rows, distance = _nearest(possible, stars)
    ra, dec = at_tic_epoch(possible) if len(possible) else ((), ())
    out = []
    for host, row, d, r, de in zip(
        possible.to_dict("records"), rows, distance, ra, dec, strict=True
    ):
        match = bool(d <= match_arcsec)
        pmra, pmdec = _number(host["pmra"]), _number(host["pmdec"])
        out.append(
            {
                "source_id": int(host["source_id"]),
                "sep_arcsec": host.get("sep_arcsec"),
                "required_depth": host.get("required_depth"),
                "pmra": pmra if np.isfinite(pmra) else None,
                "pmdec": pmdec if np.isfinite(pmdec) else None,
                "ra_2000": float(r),
                "dec_2000": float(de),
                "tic": str(stars["ID"].iloc[row]) if match else None,
                "distance_arcsec": float(d) if np.isfinite(d) else None,
                "tdepth": float(stars["tdepth"].iloc[row]) if match and "tdepth" in stars else None,
            }
        )
    return out


def to_exposure(lc: LightCurve, exposure: float) -> LightCurve:
    """Each sector faster than `exposure` (days) averaged in time to it, so one exposure models every cadence
    calc_probs sees: consecutive bins one exposure long from the sector's first cadence, each kept when it holds at
    least half the cadences it would hold full. A bin's time and flux are its cadences' means, its error their
    errors added in quadrature over their number."""
    exposure_s = exposure * 86400.0
    parts, sources = [], {}
    for sector in np.unique(lc.sector):
        key = str(int(sector))
        source = lc.sources[key]
        m = lc.sector == sector
        time, flux, err = lc.time[m], lc.flux[m], lc.flux_err[m]
        cadence = source["cadence_s"] / 86400.0
        if source["cadence_s"] < exposure_s - 1e-6:
            # Edges start half a cadence before the first, so a timestamp's jitter can't move it across one.
            index = np.floor((time - time[0] + 0.5 * cadence) / exposure).astype(int)
            _, inverse, counts = np.unique(index, return_inverse=True, return_counts=True)
            keep = counts >= 0.5 * exposure / cadence
            time = (np.bincount(inverse, weights=time) / counts)[keep]
            flux = (np.bincount(inverse, weights=flux) / counts)[keep]
            err = (np.sqrt(np.bincount(inverse, weights=err**2)) / counts)[keep]
            source = {**source, "cadence_s": exposure_s, "binned_from_s": source["cadence_s"]}
        parts.append((time, flux, err, np.full(len(time), sector, dtype=lc.sector.dtype)))
        sources[key] = source
    if not parts:
        return LightCurve(lc.tic, lc.time, lc.flux, lc.flux_err, lc.sector, dict(lc.sources))
    time, flux, err, sector = (np.concatenate(c) for c in zip(*parts, strict=True))
    order = np.argsort(time, kind="stable")
    return LightCurve(lc.tic, time[order], flux[order], err[order], sector[order], sources)


def cadence_group(
    lc: LightCurve, eph: Ephemeris, min_transits: int
) -> tuple[float | None, list[int], list[dict]]:
    """The exposure and sectors TRICERATOPS runs on (pin P3 for mixed cadences). `lc` holds the PDCSAP-family,
    good-timestamp sectors, each a product with an aperture. Each of their cadences is a candidate exposure E; its
    group is every sector at E or faster, the faster ones averaged to E (`to_exposure`). Among the groups with at
    least `min_transits` transits, the one with the most in-transit cadences wins, a tie going to the shorter E.
    Returns (E in days, the group's sectors with data within the fold's window, every candidate); E is None when no
    group has the transits."""
    cadences = {int(s): float(lc.sources[str(int(s))]["cadence_s"]) for s in np.unique(lc.sector)}
    candidates = []
    for exposure_s in sorted(set(cadences.values())):
        members = [s for s, c in cadences.items() if c <= exposure_s]
        group = to_exposure(lc.select(np.isin(lc.sector, members)), exposure_s / 86400.0)
        near = np.abs(phase_days(group.time, eph)) < WINDOW_DURATIONS * eph.duration
        inside = in_transit(group.time, eph)
        candidates.append(
            {
                "exposure_s": exposure_s,
                "sectors": sorted(int(s) for s in np.unique(group.sector[near])),
                "transits": len(np.unique(epoch_numbers(group.time[inside], eph))),
                "in_transit": int(inside.sum()),
            }
        )
    qualified = [c for c in candidates if c["transits"] >= min_transits]
    if not qualified:
        return None, [], candidates
    best = max(qualified, key=lambda c: (c["in_transit"], -c["exposure_s"]))
    return best["exposure_s"] / 86400.0, best["sectors"], candidates


def fold(
    lc: LightCurve, eph: Ephemeris, exposure: float, bin_phase: bool
) -> tuple[np.ndarray, np.ndarray, float]:
    """The light curve within `WINDOW_DURATIONS` durations of mid-transit, in days from it, and the one flux error
    calc_probs takes. With `bin_phase` (Ruling G, decision 0026) the fold is averaged into phase bins one exposure
    wide: the data's own time sampling with one point per bin instead of one per transit, which leaves the likelihood
    nearly unchanged and makes calc_probs much faster (pin P2). The error is then the median over bins of
    the median cadence error over the square root of the bin's count."""
    phase = phase_days(lc.time, eph)
    near = np.abs(phase) < WINDOW_DURATIONS * eph.duration
    time, flux, err = phase[near], lc.flux[near], lc.flux_err[near]
    if not bin_phase:
        return time, flux, float(np.median(err))
    index = np.floor(time / exposure).astype(int)
    keys, inverse, counts = np.unique(index, return_inverse=True, return_counts=True)
    binned = np.bincount(inverse, weights=flux) / counts
    return (keys + 0.5) * exposure, binned, float(np.median(np.median(err) / np.sqrt(counts)))


def light_curve_file(source: dict, session=None) -> Path:
    """The light-curve FITS fetch read for this sector, from the cache or fetched again by its S3 key, and checked
    against the sha256 fetch recorded: the aperture must be the one the photometry used."""
    expected = source.get("sha256")
    if not expected:
        raise ValueError("fetch recorded no sha256 for this product")
    path = data_dir() / "lc_fits" / Path(source["s3_key"]).name
    if path.is_file() and sha256_file(path) == expected:
        return path
    blob, _ = mast.download(source["s3_key"], 0, session or requests.Session())
    got = hashlib.sha256(blob).hexdigest()
    if got != expected:
        raise ValueError(
            f"{path.name} has sha256 {got[:12]} now, not the {expected[:12]} fetch read"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    # Two workers can fetch one file; each writes its own temporary name and the rename is atomic.
    part = path.with_name(f"{path.name}.{os.getpid()}.part")
    part.write_bytes(blob)
    part.replace(path)
    return path


def fits_aperture(path: Path) -> np.ndarray:
    """The optimal aperture (bit 2 of the APERTURE extension) as CCD (column, row) pixels, as TRICERATOPS's own
    get_aperture reads a SPOC file (pin P3)."""
    with fits.open(path) as hdul:
        hdu = hdul["APERTURE"]
        bits = np.asarray(hdu.data, dtype=int)
        col0, row0 = hdu.header["CRVAL1P"], hdu.header["CRVAL2P"]
    rows, cols = np.nonzero(bits & 2)
    if len(rows) == 0:
        raise ValueError(f"{path.name}'s aperture has no optimal-aperture pixels")
    return np.column_stack([cols + col0, rows + row0])


def apertures(
    tic: int, sectors: list[int], sources: dict, target
) -> tuple[dict[int, np.ndarray | None], dict[int, dict]]:
    """Each sector's photometric aperture in the form calc_depths takes, or None, and where each came from. SPOC
    2-min sectors take TRICERATOPS's get_spoc_apertures; TESS-SPOC sectors the APERTURE extension of the light-curve
    file the photometry came from (`light_curve_file`); any other product publishes none (QLP, pin P3)."""
    spoc = {}
    if any(sources[str(s)]["provenance"] == SPOC for s in sectors):
        spoc = {int(s): a for s, a in zip(target.sectors, target.get_spoc_apertures(), strict=True)}
    found, notes = {}, {}
    for sector in sectors:
        source = sources[str(sector)]
        note = {"provenance": source["provenance"]}
        aperture = None
        try:
            if source["provenance"] == SPOC:
                note["from"] = "TRICERATOPS get_spoc_apertures"
                aperture = spoc.get(sector)
                if aperture is None:
                    note["reason"] = "TRICERATOPS found no SPOC aperture"
            elif source["provenance"] == TESS_SPOC:
                path = light_curve_file(source)
                note.update(
                    {"from": "light-curve file", "file": path.name, "sha256": source["sha256"]}
                )
                aperture = fits_aperture(path)
            else:
                note["reason"] = f"{source['provenance']} publishes no pixel aperture"
        except Exception as exc:
            note["reason"] = scrub(f"{type(exc).__name__}: {exc}")
        if aperture is not None:
            # The pixels calc_depths gets, as (column, row): SPOC's come from the archive at run time, so the run
            # keeps them to be audited later (Ruling O).
            note["pixels"] = len(aperture)
            note["ccd_pixels"] = np.asarray(aperture).tolist()
        found[sector], notes[sector] = aperture, note
    return found, notes


def new_target(tic: int, sectors: list[int], search_radius: int):
    # Imported here: TRICERATOPS loads PyTransit, and only a real run should pay for it.
    from triceratops.triceratops import target

    return target(ID=tic, sectors=np.array(sectors), search_radius=search_radius)


def _drop_flagged(target) -> list[dict]:
    """Drops the rows after the target that the TIC flags DUPLICATE or ARTIFACT from TRICERATOPS's star list and its
    pixel positions, and returns them (ID, disposition, duplicate_id). The TIC flags them so that they are not taken
    into account (Paegert et al. 2021, arXiv:2108.04778), but TRICERATOPS selects the column and never reads it: it
    weighs a duplicate as a second star and an artifact as a star that does not exist (decision 0036). A SPLIT row and
    a row with only a duplicate_id are real stars and stay. The target's own row stays too; `_target_problems` stops
    on a flagged one."""
    stars = target.stars
    if "disposition" not in stars:
        return []
    drop = stars["disposition"].isin(DROPPED_DISPOSITIONS).to_numpy() & (np.arange(len(stars)) > 0)
    dropped = [
        {
            "ID": str(row["ID"]),
            "disposition": row["disposition"],
            "duplicate_id": None if pd.isna(row.get("duplicate_id")) else str(row["duplicate_id"]),
        }
        for row in stars[drop].to_dict("records")
    ]
    # One mask for both. calc_depths reads each star's pixel position by row, so a row dropped from the list alone, as
    # TRICERATOPS's own remove_star drops it, would give every star after it its neighbour's position.
    target.stars = stars[~drop].reset_index(drop=True)
    target.pix_coords = [p[~drop] for p in target.pix_coords]
    return dropped


def _stars(target) -> pd.DataFrame:
    return target.stars[[c for c in STAR_COLUMNS if c in target.stars]].reset_index(drop=True)


def _target_problems(target, tic: int, sectors: list[int]) -> list[str]:
    problems = []
    # TRICERATOPS skips a sector whose TESScut cutout fails and carries on, leaving its stars' pixel positions out
    # of step with the sectors and their apertures.
    if len(target.pix_coords) != len(sectors):
        problems.append(f"TESScut gave {len(target.pix_coords)} of {len(sectors)} sectors' cutouts")
    first = target.stars.iloc[0]
    if str(first["ID"]) != str(tic):
        problems.append(f"TRICERATOPS's first star is TIC {first['ID']}, not the target")
    flag = first.get("disposition")
    if flag in DROPPED_DISPOSITIONS:
        problems.append(f"the TIC flags the target {flag}, a row it says not to use")
    lacking = [p for p in TARGET_PARAMETERS if not np.isfinite(_number(first.get(p)))]
    if lacking:
        problems.append(f"the TIC gives the target no {', '.join(lacking)}")
    return problems


def run(
    lc: LightCurve,
    star: dict,
    eph: Ephemeris,
    depth: float,
    cfg: dict,
    contrast: list[tuple[Path, str]],
    out: dict | None = None,
) -> dict:
    """TRICERATOPS on the cadence group's sectors: the target, its apertures, `calc_depths`, then `cfg["runs"]`
    seeded `calc_probs` on the fold. `lc` is the vet's detrended light curve, PDCSAP family and good timestamps
    only. Stops before calc_probs, saying why in `stopped`, wherever calc_probs would give a number that means
    nothing. Fills `out` (a new dict when None) with each field as it gets there and returns it, so when a step
    raises, the caller's `out` still holds every field the steps before it recorded."""
    out = {} if out is None else out
    out.update(dict.fromkeys(RUN_FIELDS), fpp=[], nfpp=[], degenerate=[])
    tic = int(star["tic"])
    exposure, sectors, groups = cadence_group(lc, eph, cfg["min_transits"])
    cadences = {int(s): float(lc.sources[str(int(s))]["cadence_s"]) for s in np.unique(lc.sector)}
    out.update(
        groups=groups,
        exposure_s=None if exposure is None else round(exposure * 86400.0, 6),
        sectors=sectors,
        left_out=[
            {
                "sector": s,
                "cadence_s": c,
                "reason": (
                    "no exposure group"
                    if exposure is None
                    else "slower than the group's exposure"
                    if c > exposure * 86400.0 + 1e-6
                    else "no cadence within the fold's window"
                ),
            }
            for s, c in sorted(cadences.items())
            if s not in sectors
        ],
    )
    if exposure is None:
        counts = (
            ", ".join(f"{g['exposure_s']:g} s: {g['transits']}" for g in groups) or "no PDCSAP data"
        )
        out["stopped"] = f"no cadence group holds {cfg['min_transits']} transits ({counts})"
        return out
    # A depth that is not a fraction leaves calc_depths no star able to host the dip, the target included, and
    # calc_probs then weighs no scenario.
    if not (np.isfinite(depth) and 0.0 < depth <= 1.0):
        out["stopped"] = f"no usable transit depth ({depth})"
        return out
    group = to_exposure(lc.select(np.isin(lc.sector, sectors)), exposure)
    time, flux, err = fold(group, eph, exposure, cfg["bin_phase"])
    out.update(points=len(time), flux_err_0=err)
    target = new_target(tic, sectors, cfg["search_radius_pixels"])
    out["field_population"] = isinstance(target.trilegal_fname, str)
    if out["field_population"]:
        out["field_population_file"] = Path(target.trilegal_fname).name
    out["dropped_stars"] = _drop_flagged(target)
    out["stars"] = _stars(target)
    problems = _target_problems(target, tic, sectors)
    found, out["apertures"] = apertures(tic, sectors, lc.sources, target)
    missing = [s for s in sectors if found[s] is None]
    if missing:
        problems.append(f"no aperture for sector(s) {missing}")
    if problems:
        out["stopped"] = "; ".join(problems)
        return out
    # Evidence that each aperture sits on the target in TRICERATOPS's pixel frame (pin P3's conversion).
    for k, sector in enumerate(target.sectors):
        pixel = np.round(target.pix_coords[k][0])
        aperture = found[int(sector)]
        out["apertures"][int(sector)]["target_in_aperture"] = bool(
            ((aperture[:, 0] == pixel[0]) & (aperture[:, 1] == pixel[1])).any()
        )
    # PDCSAP is corrected for the crowding the apertures let in.
    target.calc_depths(
        tdepth=depth, all_ap_pixels=[found[int(s)] for s in target.sectors], dilution_corrected=True
    )
    out["stars"] = _stars(target)
    target_depth = _number(target.stars["tdepth"].iloc[0])
    # With no target light in the apertures (or a NaN magnitude among the stars), calc_depths leaves the target
    # out, and calc_probs takes the first star left as the target.
    if not target_depth > 0:
        out["stopped"] = (
            f"calc_depths left the target no light in the apertures (tdepth {target_depth})"
        )
        return out
    files = [str(path) for path, _ in contrast] or None
    filters = [f for _, f in contrast] or "TESS"
    for seed in range(cfg["runs"]):
        np.random.seed(seed)
        target.calc_probs(
            time=time,
            flux_0=flux,
            flux_err_0=float(err),
            # A numpy float is read as a period range and raises (pins: TRICERATOPS gotchas).
            P_orb=float(eph.period),
            contrast_curve_file=files,
            filt=filters,
            N=cfg["draws"],
            # PyTransit then evaluates every transiting draw at once, past the run's memory cap (pin P2).
            parallel=False,
            exptime=exposure,
            verbose=0,
            dilution_corrected=True,
        )
        # Read before any is kept, so the three lists count the same finished runs.
        fpp, nfpp = float(target.FPP), float(target.NFPP)
        degenerate = bool(getattr(target, "FPP_degenerate", False))
        out["fpp"].append(fpp)
        out["nfpp"].append(nfpp)
        out["degenerate"].append(degenerate)
    out["probs"] = target.probs
    return out


def check(
    lc: LightCurve,
    star: dict,
    eph: Ephemeris,
    report: dict,
    possible_hosts: pd.DataFrame,
    cfg: dict,
    contrast: list[tuple[Path, str]],
) -> CheckResult:
    """`run` on the signal at `eph` (its depth the one the neighbour table used), judged by `outcome`. Blockers,
    each named in the reason: RUWE over `max_ruwe` or missing, an inconclusive neighbour table (`report`'s), no
    cadence group, a missing aperture, a target TRICERATOPS can't weigh, no field-star population, any exception, a
    run TRICERATOPS flags degenerate, and a possible host it did not weigh. The label needs a contrast curve and a
    2-min group."""
    blockers = []
    ruwe = _number(star.get("ruwe"))
    if not np.isfinite(ruwe):
        blockers.append("no RUWE for the target: an unresolved companion can't be ruled out")
    elif ruwe > cfg["max_ruwe"]:
        blockers.append(
            f"RUWE {ruwe:.2f} > {cfg['max_ruwe']:g}: an unresolved companion the priors don't condition on"
        )
    table = report["neighbours"]
    if table["outcome"] != "pass":
        blockers.append(f"the neighbour table is {table['outcome']}: {table['reason']}")
    result, raised = {}, None
    try:
        run(lc, star, eph, _number(eph.depth), cfg, contrast, result)
    except Exception as exc:
        raised = scrub(f"{type(exc).__name__}: {exc}")
        blockers.append(f"TRICERATOPS raised {raised}")
    stars, probs = result.pop("stars"), result.pop("probs")
    evidence = {
        **result,
        "stars": None if stars is None else stars.to_dict("records"),
        "probs": None if probs is None else probs.to_dict("records"),
        "raised": raised,
        "ruwe": ruwe if np.isfinite(ruwe) else None,
        "ephemeris": asdict(eph),
        "runs": cfg["runs"],
        "draws": cfg["draws"],
        "bin_phase": cfg["bin_phase"],
        "contrast": [{"file": Path(path).name, "filt": f} for path, f in contrast],
        "hosts": None,
        "missing_hosts": None,
        "hosts_tdepth_zero": None,
    }
    if result["stopped"]:
        blockers.append(result["stopped"])
    if result["field_population"] is False:
        blockers.append(
            "no field-star population: TRICERATOPS skipped the DTP, DEB, DEBx2P, BTP, BEB and BEBx2P scenarios"
        )
    degenerate = [i for i, d in enumerate(result["degenerate"]) if d]
    if degenerate:
        blockers.append(
            f"TRICERATOPS flagged run(s) {degenerate} degenerate: NaN or infinite scenario evidence"
        )
    if stars is not None:
        evidence["hosts"] = _hosts(possible_hosts, stars, cfg["match_arcsec"])
        evidence["missing_hosts"] = missing_hosts(possible_hosts, stars, cfg["match_arcsec"])
        if evidence["missing_hosts"]:
            listed = ", ".join(str(s) for s in evidence["missing_hosts"])
            blockers.append(f"possible host(s) TRICERATOPS did not weigh: Gaia DR3 {listed}")
        # Ruling M: a matched star TRICERATOPS gave no depth is evidence for the review, not a blocker. The table
        # counts the star's whole light in the aperture; TRICERATOPS counts what its aperture takes. Before
        # calc_depths there is no depth to call zero.
        if "tdepth" in stars:
            evidence["hosts_tdepth_zero"] = [
                h["source_id"]
                for h in evidence["hosts"]
                if h["tic"] is not None and h["tdepth"] is not None and not h["tdepth"] > 0
            ]
    label_ok = bool(contrast) and result["exposure_s"] == TWO_MINUTES_S
    judged = outcome(result["fpp"], result["nfpp"], cfg, blockers, label_ok)
    return CheckResult(judged.check, judged.outcome, judged.reason, {**evidence, **judged.evidence})


def read_contrast(path: Path) -> tuple[np.ndarray, dict]:
    """An ExoFOP contrast curve as rows of (separation in arcsec, delta mag), the two columns TRICERATOPS reads
    (Ruling K, decision 0026). Two layouts: the Gemini and WIYN speckle `.dat` ('#' header, then four whitespace
    columns: annulus inner, outer and centre in arcsec, and delta mag, then the reduction's fitted curve in two
    columns, which is not read) and the PHARO `.tbl` ('key = value' lines, then an 'arcsec, dmag, dmrms' table).
    Rows at zero separation go. Raises `ContrastError` for anything else."""
    lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
    rows, skipped = [], 0
    if lines and lines[0].startswith("#"):
        layout = "speckle"
        for line in (x for x in lines if not x.startswith("#")):
            values = _numbers(line.split())
            if values is not None and len(values) == 4:
                rows.append((values[2], values[3]))
            elif values is not None and len(values) == 2:
                skipped += 1
            else:
                raise ContrastError(
                    f"{path.name}: a speckle row of four numbers expected, got {line!r}"
                )
    elif lines and " = " in lines[0]:
        layout = "pharo"
        header = [
            i
            for i, line in enumerate(lines)
            if [c.strip().lower() for c in line.split(",")] == ["arcsec", "dmag", "dmrms"]
        ]
        if len(header) != 1 or not all(" = " in line for line in lines[: header[0]]):
            raise ContrastError(
                f"{path.name}: a PHARO table needs 'key = value' lines, then 'arcsec, dmag, dmrms'"
            )
        for line in lines[header[0] + 1 :]:
            values = _numbers(line.split(","))
            if values is None or len(values) != 3:
                raise ContrastError(
                    f"{path.name}: a PHARO row of three numbers expected, got {line!r}"
                )
            rows.append((values[0], values[1]))
    else:
        raise ContrastError(
            f"{path.name} is in neither ExoFOP layout read here (Gemini or WIYN speckle .dat, PHARO .tbl)"
        )
    data = np.array(rows, dtype=float).reshape(-1, 2)
    data = data[data[:, 0] > 0]
    if len(data) < 2 or not np.isfinite(data).all() or not np.all(np.diff(data[:, 0]) > 0):
        raise ContrastError(f"{path.name}: needs two or more finite rows at increasing separations")
    # TRICERATOPS reads the separation at a companion's delta mag with np.interp over the curve, which needs delta
    # mag increasing, and a measured curve dips here and there. Lowered from outside in, each separation claims only
    # the depth reached there and at every wider one. Of a run of equal values the widest separation stays: keeping
    # the closest would interpolate from it to the next, deeper point and claim more than the run measured. So the
    # curve never rules out a companion the data don't.
    envelope = np.minimum.accumulate(data[::-1, 1])[::-1]
    keep = np.r_[np.diff(envelope) > 0, True]
    curve = np.column_stack([data[keep, 0], envelope[keep]])
    if len(curve) < 2:
        raise ContrastError(f"{path.name}: the curve never deepens")
    return curve, {
        "layout": layout,
        "rows": len(rows),
        "fit_rows_skipped": skipped,
        "used": len(curve),
        "lowered": int((envelope < data[:, 1]).sum()),
    }


def _numbers(fields: list[str]) -> list[float] | None:
    try:
        return [float(f) for f in fields]
    except ValueError:
        return None


def write_contrast(curve: np.ndarray, path: Path) -> None:
    np.savetxt(path, curve, delimiter=",", fmt="%.6f")
