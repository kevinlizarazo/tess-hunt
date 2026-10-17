"""The second list (M3 design, section 4.10): the signals triage's novelty matched only to SPOC TCE or ExoMiner rows,
which decision 0013 leaves for the maintainer to promote by hand. Each gets SPOC's own DV statistics for the TCE at its
period and its ExoMiner score, read from the catalog snapshot's raw files, beside the vet, triage's pixel check run as
triage runs it, and the next TESS sectors, in one table."""

import fnmatch
import functools
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from tess_hunt.ephemeris import Ephemeris, ephemeris_match
from tess_hunt.provenance import sha256_file
from tess_hunt.serialize import jsonable

# The TCE's id and the sectors its run searched, then the DV statistics the M3 design names: MES, the odd/even
# statistic, the ghost diagnostic's core and halo statistics, the difference-image centroid offsets from the
# out-of-transit centroid and from the TIC position with their errors, and the weak secondary's depth.
DV_FIELDS = (
    "tceid",
    "sectors",
    "tce_max_mult_ev",
    "tce_bin_oedp_stat",
    "tce_cap_stat",
    "tce_hap_stat",
    "tce_dicco_msky",
    "tce_dicco_msky_err",
    "tce_ditco_msky",
    "tce_ditco_msky_err",
    "wst_depth",
)
# The files these tables read in each source's directory under the snapshot's raw/.
RAW = {"SPOC-TCE": "*_dvr-tcestats.csv", "ExoMiner-v2": "*.csv", "ExoMiner-v1": "*.csv"}
# Each ExoMiner release's columns for the names in EXOMINER_NAMES; v1 gives no label. v2 comes first: it is preferred.
EXOMINER = {
    "ExoMiner-v2": (
        "target_id",
        "uid",
        "sector_run",
        "tce_period",
        "mean_score",
        "std_score",
        "model_label",
    ),
    "ExoMiner-v1": (
        "TIC ID",
        "TCE ID",
        "Sector Run",
        "Orbital Period [day]",
        "ExoMiner Score",
        "ExoMiner Unc. Score",
        None,
    ),
}
EXOMINER_NAMES = ("tic", "id", "run", "period", "score", "score_sd", "label")
_TCE_RUN = re.compile(r"-s(\d{4})-s(\d{4})_dvr-tcestats\.csv$")
NAN = float("nan")


def _span(run: str) -> tuple[int, int]:
    """An ExoMiner sector run's first and last sector: "1-39" or "38"."""
    first, _, last = run.partition("-")
    return int(first), int(last or first)


@functools.cache
def _tces(snapshot: Path) -> pd.DataFrame:
    """Every SPOC TCE row in the snapshot's raw tables, each with the sector run of the file it came from."""
    parts = []
    for path in sorted((snapshot / "raw" / "SPOC-TCE").glob(RAW["SPOC-TCE"])):
        first, last = (int(s) for s in _TCE_RUN.search(path.name).groups())
        table = pd.read_csv(
            path,
            comment="#",
            usecols=["ticid", "tce_period", *DV_FIELDS],
            dtype={"tceid": str, "sectors": str},
        )
        parts.append(table.assign(run=f"s{first:04d}-s{last:04d}", first=first, last=last))
    if not parts:
        return pd.DataFrame(columns=["ticid", "tce_period", *DV_FIELDS, "run", "first", "last"])
    return pd.concat(parts, ignore_index=True)


@functools.cache
def _exominer(snapshot: Path) -> dict[str, pd.DataFrame]:
    """Each ExoMiner release's rows under EXOMINER_NAMES, v2's 2-min and FFI catalogs together, each row with its
    catalog and its run's first and last sector."""
    out = {}
    for release, columns in EXOMINER.items():
        parts = []
        for path in sorted((snapshot / "raw" / release).glob(RAW[release])):
            table = pd.read_csv(
                path,
                # v2's files open with comment lines; v1's have none, and a '#' in its URLs is text.
                comment="#" if release == "ExoMiner-v2" else None,
                usecols=[c for c in columns if c],
                dtype={columns[1]: str, columns[2]: str},
            ).rename(columns={c: n for c, n in zip(columns, EXOMINER_NAMES, strict=True) if c})
            if "label" not in table:
                table["label"] = None
            spans = [_span(run) for run in table["run"]]
            parts.append(
                table.assign(
                    catalog=f"{release} {path.stem}",
                    first=[s[0] for s in spans],
                    last=[s[1] for s in spans],
                )
            )
        empty = pd.DataFrame(columns=[*EXOMINER_NAMES, "catalog", "first", "last"])
        out[release] = pd.concat(parts, ignore_index=True) if parts else empty
    return out


def _matching(
    rows: pd.DataFrame, period: str, eph: Ephemeris, match: dict, harmonics: tuple[float, ...]
) -> pd.DataFrame:
    """The `rows` whose period matches the signal's at one of `harmonics`, on period alone as novelty matches a row
    whose catalog epoch has gone stale (decision 0003), the latest sector run first: its last sector, then the longer
    run, then the earlier harmonic."""
    ratios = [
        ephemeris_match(eph, Ephemeris(p, NAN, NAN), harmonics, match["sigma_p"], match["sigma_t"])
        # ephemeris_match takes a NaN period for a match at any period.
        if np.isfinite(p) and p > 0
        else None
        for p in rows[period].astype(float)
    ]
    found = rows.assign(ratio=ratios).dropna(subset=["ratio"])
    found = found.assign(order=[harmonics.index(r) for r in found["ratio"]])
    return found.sort_values(
        ["last", "first", "order"], ascending=[False, True, True], kind="stable"
    )


def dv_fields(
    snapshot: Path, tic: int, eph: Ephemeris, match: dict, harmonics: tuple[float, ...] = (1.0,)
) -> dict | None:
    """SPOC's DV statistics for the TCE on `tic` whose period matches the signal's (search-v2's `[match]`, at
    `harmonics`), from the snapshot's raw `dvr-tcestats` tables, the latest sector run first; None when no SPOC row on
    the star matches (a match made only through ExoMiner or eumemic)."""
    tces = _tces(Path(snapshot))
    found = _matching(tces[tces["ticid"] == tic], "tce_period", eph, match, tuple(harmonics))
    if found.empty:
        return None
    best = found.iloc[0]
    return jsonable(
        {
            "tic": int(tic),
            "run": best["run"],
            "ratio": best["ratio"],
            "tce_period": best["tce_period"],
            **{k: best[k] for k in DV_FIELDS},
            # Every run whose TCE matched, latest first: how often SPOC found it.
            "runs": list(dict.fromkeys(found["run"])),
        }
    )


def exominer(
    snapshot: Path, tic: int, eph: Ephemeris, match: dict, harmonics: tuple[float, ...] = (1.0,)
) -> dict | None:
    """The ExoMiner score of the row on `tic` whose period matches the signal's, matched as `dv_fields` matches: from
    ExoMiner v2 (its 2-min and FFI catalogs) when a v2 row matches, else from v1; None when neither has one."""
    for table in _exominer(Path(snapshot)).values():
        found = _matching(table[table["tic"] == tic], "period", eph, match, tuple(harmonics))
        if found.empty:
            continue
        best = found.iloc[0]
        return jsonable(
            {
                "tic": int(tic),
                **{k: best[k] for k in ("catalog", "id", "run", "ratio", "period")},
                **{k: best[k] for k in ("score", "score_sd", "label")},
                "rows": len(found),
            }
        )
    return None


def check_raw(snapshot: Path) -> list[str]:
    """Why the raw files `dv_fields` and `exominer` read may not be the snapshot's; empty when each file is one the
    manifest lists, with the sha256 it recorded, and every one it lists is there."""
    manifest = json.loads((snapshot / "manifest.json").read_text())
    listed = {f["file"]: f["sha256"] for f in manifest.get("files", [])}
    problems = []
    for source, pattern in RAW.items():
        wanted = {f for f in listed if fnmatch.fnmatchcase(f, f"{source}/{pattern}")}
        found = {f"{source}/{p.name}" for p in (snapshot / "raw" / source).glob(pattern)}
        if not wanted:
            problems.append(f"the manifest lists no {source} file")
        problems += [f"raw/{f} is missing" for f in sorted(wanted - found)]
        problems += [f"raw/{f} is not in the manifest" for f in sorted(found - wanted)]
        problems += [
            f"raw/{f} is not the file the manifest lists"
            for f in sorted(wanted & found)
            if sha256_file(snapshot / "raw" / f) != listed[f]
        ]
    return problems


def stars(checks: dict) -> list[int]:
    """Where to look for the signal's TCE: its star, then each other star whose TCE or ExoMiner row novelty matched
    it to, since SPOC may have found the signal on a neighbour it comes from."""
    novelty = next(c for c in checks["checks"] if c["check"] == "novelty")["evidence"]
    matched = (novelty.get("tce_matches") or []) + (novelty.get("tce_period_matches") or [])
    tic = int(checks["star"]["tic"])
    return [tic, *sorted({int(m["tic"]) for m in matched} - {tic})]


def look_up(
    snapshot: Path, checks: dict, match: dict, harmonics: tuple[float, ...]
) -> dict[str, dict | None]:
    """The vetted signal's SPOC DV statistics and ExoMiner score, each from the first of `stars(checks)` with a row
    at its period."""
    eph = Ephemeris(**checks["ephemeris"])
    out = {}
    for key, look in (("dv", dv_fields), ("exominer", exominer)):
        rows = (look(snapshot, tic, eph, match, harmonics) for tic in stars(checks))
        out[key] = next((row for row in rows if row is not None), None)
    return out


def table(items: list[dict]) -> pd.DataFrame:
    """One row per signal: `items` are {name, checks, pixels, dv, exominer}, as `vetting second-list` builds them."""
    rows = []
    for item in items:
        c, pixels, dv, exo = item["checks"], item["pixels"], item["dv"], item["exominer"]
        evidence, upcoming = pixels["evidence"], c["upcoming_sectors"]
        rows.append(
            {
                "name": item["name"],
                "tic": int(c["star"]["tic"]),
                **{k: c["ephemeris"][k] for k in ("period", "t0", "duration", "depth")},
                **{x["check"]: x["outcome"] for x in c["checks"]},
                "neighbours": c["neighbours"]["outcome"],
                "pixels": pixels["outcome"],
                "pixels_reason": pixels["reason"],
                # A pixel check that never looked records no offsets.
                "offset_qual_arcsec": evidence.get("offset_qual_arcsec"),
                "offset_mean_arcsec": evidence.get("offset_mean_arcsec"),
                "pixel_sectors": " ".join(str(s["sector"]) for s in evidence.get("sectors", [])),
                "dv_tic": dv["tic"] if dv else None,
                "dv_run": dv["run"] if dv else None,
                "dv_ratio": dv["ratio"] if dv else None,
                "tce_period": dv["tce_period"] if dv else None,
                **{k: dv[k] if dv else None for k in DV_FIELDS},
                "dv_runs": " ".join(dv["runs"]) if dv else None,
                **{
                    f"exominer_{k}": exo[k] if exo else None
                    for k in ("tic", "catalog", "id", "run", "ratio", "period", "score", "score_sd")
                },
                "exominer_label": exo["label"] if exo else None,
                "upcoming_sectors": None if upcoming is None else " ".join(map(str, upcoming)),
            }
        )
    return pd.DataFrame(rows)


def _f(value, fmt: str) -> str:
    return "missing" if value is None else format(value, fmt)


def _cell(text) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _table(header: list[str], rows: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    return "\n".join(lines + ["| " + " | ".join(_cell(c) for c in row) + " |" for row in rows])


def _sectors(sectors: list[int] | None) -> str:
    if sectors is None:
        return "missing"
    return ", ".join(map(str, sectors)) or "none"


def _exominer_cell(exo: dict | None, tic: int) -> str:
    if exo is None:
        return "no row at the period"
    where = [exo["catalog"], f"run {exo['run']}"]
    if exo["tic"] != tic:
        where.append(f"on TIC {exo['tic']}")
    if exo["ratio"] != 1.0:
        where.append(f"ratio {exo['ratio']:g}")
    label = f"{exo['label']}; " if exo["label"] else ""
    return f"{exo['score']:.3f} ({label}{', '.join(where)})"


def _offset(dv: dict, name: str) -> str:
    # SPOC's own values, as given, an error of -1 included.
    return f"{_f(dv[name], '.2f')} (err {_f(dv[f'{name}_err'], '.2f')})"


def markdown(items: list[dict], about: dict) -> str:
    """second-list.md: the table the maintainer reads to promote a row or leave a note. `about` names the run, the
    vetting and triage runs, the criteria files and the pixel limit."""
    summary, outcomes, pixel_rows, dv_rows = [], [], [], []
    names = list(dict.fromkeys(x["check"] for item in items for x in item["checks"]["checks"]))
    for item in items:
        name, c, pixels, dv = item["name"], item["checks"], item["pixels"], item["dv"]
        tic, evidence = int(c["star"]["tic"]), pixels["evidence"]
        found = {x["check"]: x["outcome"] for x in c["checks"]}
        found["neighbours"] = c["neighbours"]["outcome"]
        unpassed = "; ".join(f"{k} {v}" for k, v in found.items() if v != "pass") or "none"
        summary.append(
            [
                name,
                tic,
                f"{c['ephemeris']['period']:.6f}",
                f"{c['ephemeris']['depth'] * 1e6:.0f}",
                unpassed,
                pixels["outcome"],
                _f(evidence.get("offset_qual_arcsec"), ".1f"),
                _exominer_cell(item["exominer"], tic),
                _sectors(c["upcoming_sectors"]),
            ]
        )
        outcomes.append([name, *(found[n] for n in names), found["neighbours"]])
        measured = "; ".join(
            f"S{s['sector']} {_f(s['offset_arcsec'], '.1f')} ({_f(s['quality'], '.2f')})"
            for s in evidence.get("sectors", [])
        )
        pixel_rows.append([name, pixels["outcome"], pixels["reason"], measured or "none measured"])
        if dv is None:
            none = "no SPOC TCE at the period on this star or a star novelty matched it to"
            dv_rows.append([name, none, *[""] * 9])
            continue
        tce = f"{dv['tceid']}, run {dv['run']}" + (
            f", on TIC {dv['tic']}" if dv["tic"] != tic else ""
        )
        dv_rows.append(
            [
                name,
                tce,
                f"{dv['ratio']:g}",
                _f(dv["tce_max_mult_ev"], ".2f"),
                _f(dv["tce_bin_oedp_stat"], ".3g"),
                _f(dv["tce_cap_stat"], ".3g"),
                _f(dv["tce_hap_stat"], ".3g"),
                _offset(dv, "tce_dicco_msky"),
                _offset(dv, "tce_ditco_msky"),
                _f(dv["wst_depth"], ".1f"),
                ", ".join(dv["runs"]),
            ]
        )
    search, vet = about["criteria"]
    lines = [
        f"# Second list ({about['run_id']})",
        "",
        f"The second-list signals of vetting run `{about['vetting_run']}`: signals triage's novelty matched only "
        "to SPOC TCE or ExoMiner rows, which decision 0013 leaves for the maintainer to promote by hand (M3 design, "
        f"section 4.10). Each row has the vet under {vet}; triage's pixel check, which triage runs only on novelty "
        f"passes, run on it as triage runs it (the `[pixels]` of `{about['triage_criteria']}` as triage run "
        f"`{about['triage_run']}` read it, an offset limit of {about['limit']:g}\"); SPOC's DV statistics for the TCE "
        "at the signal's period; the ExoMiner score; and the next TESS sectors. Every row is a candidate signal, not "
        "a planet.",
        "",
        f"SPOC and ExoMiner rows match the signal on period alone, within {search}'s `[match]` tolerance at {vet}'s "
        "novelty harmonics; ratio k means the row's period times k is the signal's. A row is taken from the signal's "
        "star when it has one there, else from a star novelty matched the signal to; of several, from the latest "
        "sector run (its last sector, then the longer run). ExoMiner v2's 2-min and FFI catalogs come before v1.",
        "",
        _table(
            [
                "Signal",
                "TIC",
                "Period (d)",
                "Depth (ppm)",
                "Not passed",
                "Pixels",
                "Offset (arcsec)",
                "ExoMiner",
                "Next sectors",
            ],
            summary,
        ),
        "",
        "## Checks",
        "",
        _table(["Signal", *names, "neighbours"], outcomes),
        "",
        "## Pixel check",
        "",
        "The best-quality sector's centroid offset decides it; each measured sector's offset follows, with its "
        "quality.",
        "",
        _table(["Signal", "Outcome", "Reason", "Offset (arcsec) per sector (quality)"], pixel_rows),
        "",
        "## SPOC DV statistics",
        "",
        "MES is `tce_max_mult_ev`; odd/even is `tce_bin_oedp_stat`; the ghost diagnostic's core and halo statistics "
        "are `tce_cap_stat` and `tce_hap_stat`; the difference-image centroid offsets are `tce_dicco_msky` (from the "
        "out-of-transit centroid) and `tce_ditco_msky` (from the TIC position), each with its `_err`; the weak "
        "secondary's depth is `wst_depth`. Each is SPOC's value as the snapshot's raw table gives it.",
        "",
        _table(
            [
                "Signal",
                "TCE",
                "Ratio",
                "MES",
                "Odd/even",
                "Ghost core",
                "Ghost halo",
                "Offset from OOT centroid (arcsec)",
                "Offset from TIC position (arcsec)",
                "Weak secondary (ppm)",
                "Runs that matched",
            ],
            dv_rows,
        ),
        "",
    ]
    return "\n".join(lines)
