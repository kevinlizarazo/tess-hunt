"""Predictions for the held signals (decision 0040): before TESS looks at a held signal's star again, the prediction
its held-out season test will judge, and the test. With the new season held out, every other season is the M3 light
curve, so the refit and the training depths `checks.holdout` computes for that season are fixed now. The package holds
them, the record's observer windows beside them, and a README and Zenodo text filled with `substitute` from the run,
the records and `facts.toml`: a value they lack, or hold as null or NaN, raises instead of rendering (docs/design.md,
section 5.5)."""

import datetime as dt
import json
import math
import shutil
import subprocess
import sys
import tomllib
from dataclasses import asdict
from pathlib import Path
from string import Template

import numpy as np
import pandas as pd
from astropy.time import Time

from tess_hunt import calls, predict, vetting
from tess_hunt.catalogs import load_known, snapshot_inputs
from tess_hunt.checks.families import family_labels
from tess_hunt.checks.holdout import reference, refit_ephemeris, season_labels
from tess_hunt.config import lc_dir, load_criteria
from tess_hunt.ddt import _number
from tess_hunt.dossier import _scrub, _table, _words
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import publish_run, repo_root, sha256_file, start_run
from tess_hunt.vet import prepare

# Decision 0040's rule: a new season not judged on its complete data by this date stays untested.
JUDGED_BY = dt.date(2027, 12, 31)
# fetch's products (mast.PROVENANCES), as the package names them.
PRODUCTS = {"SPOC": "SPOC 2-min", "TESS-SPOC": "TESS-SPOC", "QLP": "QLP"}
PACKAGE = (
    "README.md",
    "facts.toml",
    "predictions.csv",
    "provenance.json",
    "references.json",
    "windows.csv",
    "zenodo.md",
)
PREDICTION_COLUMNS = [
    "signal",
    "tic",
    "sector",
    "epoch",
    "mid_btjd",
    "mid_utc",
    "period",
    "t0",
    "core_half_width_days",
]
MINUTES_PER_DAY = 1440.0
FACTS = "results/predictions/facts.toml"

README = Template("""\
# Predictions for $n_signals held tess-hunt signals in TESS Sectors $first_sector to $last_sector

tess-hunt is an independent search for transiting planets in public TESS light curves. Its vetting held these
$n_signals signals ($signals): not passed and not killed, because the public data can't decide them. Each is a
candidate signal, not a planet. TESS looks at their stars again from Sector $first_window on; this package predicts
their transits in the sectors from $first_sector to $last_sector, which start after its files lock (below).

This package fixes, before those sectors are observed, the prediction each signal's held-out season test will judge,
and the test itself. It was made on $made (UTC) by one run of `tess-hunt predictions run`, $run_id, from the signals'
published vetting records and the light curves their vetting run, $vetting_run, read. Every number in it comes from
those files, from that run, from the criteria file and the sector dates file that vetting run read, and from the
`facts.toml` beside this README; the text it quotes from a review says so where it begins.

## What is judged

vet-v3, tess-hunt's vetting criteria, has a held-out season check: it refits a signal's period and epoch on every
season but one, near the period and epoch tess-hunt's search found, and measures the left-out season's depth only in
the central $core_percent% of each transit the refit predicts (its core). Each signal's vetted light curve is the one
vetting run $vetting_run read for it, as its checks saw it: without the sectors flagged for suspect timestamps,
detrended around the same catalogued transits, with the same red-noise depth errors. The new season is the one TESS's
coming sectors make for its star. With it held out, the other seasons are exactly the vetted light curve's, so the
prediction is fixed now:

- `predictions.csv`: the refit's period, t0 and core half-width, and the mid-time of each transit it predicts in the
  sectors predicted. This is what the test judges.
- `references.json`: the training depths the new season is compared with, in the same cores: over every training
  cadence and for each product family, each with its error and cadence count; and what the check's two training gates
  read (the training seasons, which of them hold a transit in their data, and `min_training_seasons`).

Not judged: `windows.csv`, the transit windows of the density-prior fit in each record's `checks.json`, copied
unchanged with their standard deviations for anyone checking by eye. They come from another fit and can differ from
the refit; the test never reads them.

## The test

The new season is judged by vet-v3's `[holdout]` measurement and thresholds, read from `$criteria_vet` (sha256
$criteria_vet_sha256), with the published prediction and training depths in place of a fresh refit:

- Seasons are split at gaps of more than $season_gap_days days.
- A season is tested only if at least $min_training_seasons training seasons hold a transit in their data.
- Its depth is measured in the cores, and needs at least $min_points cadences there.
- It is untestable if a product family in its cores has fewer than $min_points training cadences in them. Otherwise
  its expected depth is each family's own training depth, weighted as its cadences weight the season's depth; if that
  is less than $min_expected_snr times the season's depth error, the season is underpowered.
- It is replicated when its depth is at least $min_sigma times its error and, in every family with $min_points
  cadences in the cores on both sides, within $max_depth_tension sigma of the same family's training depth. Otherwise
  it is missed.

The result for each signal is the new season's status: replicated (`predicted`), missed (`missed`), or untested
(`underpowered`, `untestable`, `no_predicted_transit_in_data`, or no light curve). On the unchanged vetted light curve
this is exactly what vet-v3's check computes for that season (tess-hunt's test `test_prediction_equals_holdout_refit`).
Judging with the published numbers keeps the result fixed if a later re-vet's training data change.

## Which data can test it

Depths are compared only within a product family (tess-hunt's decision 0023), so the new season is testable only if
every family in its cores is one with training data. tess-hunt takes one product per sector, so a season that mixes in
a sector of a family with no training data is untestable as a whole.

$routes

A family with no training cadences in the cores shows none for its depth and error in its signal's section, and can't
test the new season.

TESS-SPOC's full-frame light curves stop at Sector $fact_tess_spoc_last_sector, and MAST holds QLP's only through a
partial Sector $fact_qlp_last_sector (both as read on $facts_read). So for $n_need_2min of the $n_signals signals
($need_2min) only SPOC 2-min data can test the prediction. As read on $facts_read, none of the $n_signals stars is on
$fact_two_minute_lists, and a list can still change before its sector. $ddt_ask They are predicted anyway: anyone can
check a public prediction by eye. Any other product, the project's own full-frame photometry included, needs a decision record
saying how the test applies to it, made before it is run on these stars.

## When it is judged

Once for each signal, on the complete season: at the first re-vet whose light curve covers every predicted sector for
that star with data the test can use or, failing that, on $judged_by, when whatever is untested stays untested. A
re-vet before then may run, but reports the result as pending. A season runs from gap to gap, so a sector left out of
the prediction (below) can still fall in the new season; its cadences stay in it, as vet-v3 counts them, and each
signal's section says which.

## What a result means

A replicated season shows the dip is real, periodic and where it was predicted. It does not show that the dip is on
the target star: a signal held because another star's light could make the dip stays held until evidence on that
comes. A transit that arrives outside the predicted
cores because the refit's period has drifted counts as missed: the test is the prediction.

The held-out check as a whole fails when two or more seasons are tested and any is missed. That is a failed vet-v3
check, and a ground for a kill under tess-hunt's decision 0028. With fewer than two seasons tested the check stays
inconclusive, and a missed new season is then evidence against the signal that the maintainer weighs in its call
(passed, killed or held), not a failed check.

## The lock

Zenodo lets a record's owner edit its files for $fact_zenodo_edit_days days after publishing (as read on $facts_read).
Deposited by $deposit_by, this package's files are locked by $lock_start, so only sectors starting on or after
$lock_start are predicted. Each earlier sector in a record's windows is left out, and its signal's section names it.
Sector dates come from tess-hunt's `$sectors_file` (tess.mit.edu's sector pages, read $sectors_read).

$sections

## Provenance

- Code: tess-hunt commit $commit.
- Criteria: $criteria.
- The vetting run the records come from: $vetting_run. This package's run: $run_id; its `provenance.json` is here.
- The catalog snapshot that vetting run read, $catalogs: `known.parquet` sha256 $known_sha256, `manifest.json` sha256
  $manifest_sha256.
- Sector dates: `$sectors_file`, sha256 $sectors_sha256.
- Facts about archives and the DDT proposal: `facts.toml`, sha256 $facts_sha256.

Each signal's published record, `results/vetting/<signal>/` in the tess-hunt repository, and the light curve its
vetting run read:

$hashes

## Files

- `predictions.csv`: one row per predicted transit: $prediction_columns. `epoch` counts periods from the refit's t0;
  `mid_btjd` is BJD_TDB - 2457000; `mid_utc` is the mid-time as seen from Earth; `period` and `t0` are the refit's,
  in days and BTJD.
- `references.json`: for each signal, the refit (`predicted`, with BLS's duration and depth), the core half-width,
  the training depths (`reference`, as fractions of the flux, and by family), the training seasons and families, the
  products that can test it (`testable_with`) and the sectors left out; and the test's criteria values (`test`).
- `windows.csv`: the observers' windows: $window_columns. `epoch` counts periods from the density-prior fit's t0.
- `facts.toml`: the facts about archives and the DDT proposal this README states, each with its source and the date it
  was read.
- `provenance.json`: the run's commit, criteria, inputs with their sha256, and command line.
- `zenodo.md`: the deposit's title, description, keywords and licence.

## Licence and sources

CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The package holds no Gaia data. It is derived from TESS
light curves (SPOC, TESS-SPOC and QLP, from MAST) and the TESS Input Catalog. The facts in `facts.toml`, read
$facts_read, come from: $fact_sources.
""")

SIGNAL = Template("""\
## $signal (TIC $tic)

The search's ephemeris, which the refit starts from: period $search_period d, t0 BTJD $search_t0, duration
$search_duration_h h. Sectors left out of its vetted light curve for suspect timestamps: $suspect.

The $n_seasons seasons of its vetted light curve train the prediction, and $n_with_transits of them hold a transit in
their data, where the test needs $min_training_seasons:

$seasons

The refit: period $period d, t0 BTJD $t0, duration $duration_h h. Each predicted transit's core runs $core_minutes min
either side of its mid-time. The training depths in the cores:

$references

Predicted: $n_transits transits in $kept. Left out: $left_out.$in_season Data that can test the new season:
$testable.

Observers' windows: $n_windows in $kept, from the density-prior fit to the $fit_family family alone, with mid-time
sd $sd min. Each window's mid-time less the refit's nearest predicted mid-time: $offset min.
""")

# Each signal whose section says more than the others, from its record (design 4.3).
NOTES = {
    "399023421-1": Template("""\
tess-hunt's adversarial review of this signal found its timing-suspect QLP transits arriving later than the observers'
windows predict. The review's finding F9, quoted word for word: "$review_F9" The refit leaves those QLP sectors out,
as every check does. It stands as published: if the new season's transits arrive late against its cores, the season
can be missed, and a miss on drift counts as a miss.

RAVEN ($fact_raven) lists a dip on the star at $raven_period d. The review's
finding F4, quoted word for word: "$review_F4"
"""),
}

ZENODO = Template("""\
# Zenodo metadata

The deposit's fields, to paste into Zenodo's form. Creators and the link to the code are filled in at deposit.

## Title

Preregistered transit predictions for $n_signals held tess-hunt planet-candidate signals in TESS Sectors $first_sector to $last_sector

## Resource type

Dataset

## Description

Predictions, fixed before TESS observes them, of where $n_signals held planet-candidate signals from tess-hunt's search
of public TESS light curves should transit in Sectors $first_sector to $last_sector, and the test that will judge each
one. Each prediction is the refit that tess-hunt's held-out season check (vet-v3) makes when the season these sectors
make is held out, on the light curve the signal was vetted on, with the training depths that season will be compared
with. The signals are $signals, on TIC $tics. Each is a candidate signal, not a planet.

The package was made by run $run_id at tess-hunt commit $commit, from the vetting records of run $vetting_run. Zenodo
lets a record's files be edited for $fact_zenodo_edit_days days after publication; deposited by $deposit_by, this
package's files lock by $lock_start, and no sector starting earlier is predicted. Each signal is judged once, on its
complete new season; one not judged by $judged_by stays untested. The README states the test, the data that can test
each signal, when it is judged and what a result means.

## Keywords

- TESS
- transiting exoplanets
- planet candidates
- preregistration
- transit timing prediction

## Licence

Creative Commons Attribution 4.0 International (CC BY 4.0)
""")

INDEX = Template("""\
# Predictions

Each directory here is one package of preregistered predictions for held signals, made by one run of `tess-hunt
predictions run` and copied unchanged from its run directory by `tess-hunt predictions publish`
([decision 0040](../../docs/decisions/0040-predictions-for-held-signals.md)). Its `README.md` says what is predicted,
the test that will judge it, and when. The maintainer deposits each package on Zenodo, which lets a record's files be
edited for $fact_zenodo_edit_days days after publishing; after that they are locked. Published packages are never
edited: a correction is a new package.

[facts.toml](facts.toml) holds the archive facts the packages state, each with its source and the date it was read.
`dois.toml`, once the maintainer writes it, holds the DOI and publication date Zenodo gave each package.

$packages
""")


def _sector(sectors: pd.DataFrame, sector: int) -> tuple[dt.date, float, float]:
    """A sector's start date (UTC) and its start and end in BTJD, from the sectors file."""
    dated = sectors.dropna(subset=["start_utc", "end_utc"]).set_index("sector")
    if sector not in dated.index:
        raise ValueError(f"the sectors file gives no dates for sector {sector}")
    start, end = dated.at[sector, "start_utc"], dated.at[sector, "end_utc"]
    return dt.datetime.fromisoformat(start).date(), predict.btjd(start), predict.btjd(end)


def _window_sectors(checks: dict) -> list[int]:
    if not checks["windows"]:
        raise ValueError(
            f"{checks['signal']['name']}'s record has no windows: {checks.get('windows_reason')}"
        )
    return sorted({int(w["sector"]) for w in checks["windows"]})


def _lock(checks: dict, lock_start: dt.date, sectors: pd.DataFrame) -> tuple[list[int], list[int]]:
    """The record's window sectors that start on or after `lock_start`, and the rest."""
    window = _window_sectors(checks)
    kept = [s for s in window if _sector(sectors, s)[0] >= lock_start]
    return kept, [s for s in window if s not in kept]


def _new_season(window: list[int], kept: list[int], sectors: pd.DataFrame, gap: float) -> set[int]:
    """The window sectors in a season with a predicted one, as vet-v3 splits seasons at gaps over `gap` days; each
    sector's dates stand in for its cadences."""
    groups, end = [], -math.inf
    for start, stop, sector in sorted((*_sector(sectors, s)[1:], s) for s in window):
        if start - end > gap:
            groups.append(set())
        groups[-1].add(sector)
        end = max(end, stop)
    return set().union(*(g for g in groups if g & set(kept)))


def _transits(
    predicted: Ephemeris, kept: list[int], sectors: pd.DataFrame, star: dict
) -> list[dict]:
    out = []
    for sector in kept:
        _, start, end = _sector(sectors, sector)
        first = math.floor((start - predicted.t0) / predicted.period)
        last = math.ceil((end - predicted.t0) / predicted.period)
        for n in range(first, last + 1):
            mid = predicted.t0 + n * predicted.period
            if start <= mid < end:
                out.append(
                    {
                        "sector": sector,
                        "epoch": n,
                        "mid_btjd": mid,
                        "mid_utc": predict.seen_utc(mid, star["ra"], star["dec"]),
                    }
                )
    return out


def testable_products(trained: dict, families_cfg: dict, min_points: int) -> list[str]:
    """The products whose data can test the new season: the members of each family with at least `min_points`
    training cadences in the predicted cores, as `family_expected_depth` asks of every family in a held-out season's
    cores (decision 0023)."""
    found = []
    for name, ref in trained["families"].items():
        if ref["ref_n"] >= min_points:
            members = families_cfg.get(name)
            # A provenance no family lists is a family of its own, named by it (families.family_of).
            found += members if isinstance(members, list) else [name]
    return [PRODUCTS[p] for p in sorted(found, key=list(PRODUCTS).index)]


def predict_signal(
    record: Path,
    lc: LightCurve,
    known: pd.DataFrame,
    crit_search: dict,
    crit_vet: dict,
    sectors: pd.DataFrame,
    lock_start: dt.date,
) -> dict:
    """The prediction decision 0040 publishes for a held signal's new season: holdout's refit and training depths with
    every season of `lc`, the M3 light curve, as training, as `checks.holdout` computes them for a season it holds out;
    what its two training gates read; and each predicted transit in the record's window sectors that start on or after
    `lock_start`, the others left out with the reason."""
    checks = json.loads((record / "checks.json").read_text())
    star, eph = checks["star"], Ephemeris(**checks["ephemeris"])
    cfg, core = crit_vet["holdout"], crit_vet["depth"]["core_fraction"]
    kept, earlier = _lock(checks, lock_start, sectors)
    if not kept:
        raise ValueError(
            f"no sector in {checks['signal']['name']}'s windows starts on or after {lock_start}"
        )
    noisy = prepare(lc, star, eph, known, crit_search, crit_vet).noisy
    families = family_labels(noisy, crit_vet["families"])
    predicted = refit_ephemeris(noisy, eph, cfg)
    trained = reference(noisy, families, np.ones(len(noisy.time), dtype=bool), predicted, core)
    labels = season_labels(noisy.time, cfg["season_gap_days"])
    # Counted as holdout counts them for its gates: over the whole transit at the search's ephemeris (decision 0035).
    transit = in_transit(noisy.time, eph)
    seasons = []
    for label in np.unique(labels):
        held = labels == label
        n = int((transit & held).sum())
        seasons.append(
            {
                "season": int(label),
                "start": float(noisy.time[held].min()),
                "end": float(noisy.time[held].max()),
                "sectors": sorted(int(s) for s in np.unique(noisy.sector[held])),
                "transit_cadences": n,
                "holds_transits": n >= cfg["min_points"],
            }
        )
    in_season = _new_season(kept + earlier, kept, sectors, cfg["season_gap_days"])
    # holdout labels seasons over the whole light curve: a new season this close to the vetted cadences would merge
    # with their last season, and the prediction would not be the one it judges.
    gap = min(_sector(sectors, s)[1] for s in in_season) - float(noisy.time.max())
    if not gap > cfg["season_gap_days"]:
        raise ValueError(
            f"{checks['signal']['name']}'s new season starts {gap:.1f} days after its last vetted cadence, not more "
            f"than season_gap_days ({cfg['season_gap_days']:g}): the test would merge it with that season"
        )
    left_out = []
    for sector in earlier:
        start = _sector(sectors, sector)[0]
        left_out.append(
            {
                "sector": sector,
                "start_utc": start.isoformat(),
                "reason": f"starts {start}, before the lock on {lock_start}: the deposit's files can still be "
                "edited until then",
                "in_season": sector in in_season,
            }
        )
    return {
        "signal": checks["signal"]["name"],
        "tic": int(star["tic"]),
        "predicted": asdict(predicted),
        "core_half_width_days": 0.5 * core * predicted.duration,
        "reference": trained,
        "min_training_seasons": cfg["min_training_seasons"],
        "training_seasons": seasons,
        "training_families": {
            str(name): sorted(int(s) for s in np.unique(noisy.sector[families == name]))
            for name in np.unique(families)
        },
        "testable_with": testable_products(trained, crit_vet["families"], cfg["min_points"]),
        "transits": _transits(predicted, kept, sectors, star),
        "left_out": left_out,
    }


def observer_windows(checks: dict, lock_start: dt.date, sectors: pd.DataFrame) -> list[dict]:
    """The record's density-prior windows in the sectors the package predicts, unchanged. They are for observers; the
    test never reads them."""
    kept = _lock(checks, lock_start, sectors)[0]
    return [w for w in checks["windows"] if w["sector"] in kept]


def _filled(found: dict) -> dict[str, str]:
    """Without the values that are None, so their placeholders raise rather than render."""
    return {key: value for key, value in found.items() if value is not None}


def _sectors_words(sectors: list[int]) -> str:
    return f"Sector {sectors[0]}" if len(sectors) == 1 else f"Sectors {_words(sectors)}"


def _either(items: list[str]) -> str | None:
    if not items:
        return None
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + " or " + items[-1]


def _span(values: list[float], fmt: str) -> str | None:
    """The values' range as shown, or the one value when both ends show the same."""
    low, high = _number(min(values), fmt), _number(max(values), fmt)
    if low is None or high is None:
        return None
    return low if low == high else f"{low} to {high}"


def _hours(days) -> str | None:
    return None if days is None else _number(days * 24.0, ".2f")


def _ppm(fraction: float) -> str:
    if not math.isfinite(fraction):
        raise ValueError(f"{fraction} is not a depth")
    return f"{fraction * 1e6:.0f}"


def _year(btjd: float) -> int:
    return Time(btjd + 2457000.0, format="jd", scale="tdb").datetime.year


def record_values(record: Path) -> dict[str, str]:
    """The record's own values the package states: the search's ephemeris, the sectors left out for suspect
    timestamps, each review finding's claim quoted as the dossier quotes it (decision 0037), and RAVEN's period where
    the record lists one RAVEN row on the star."""
    checks = json.loads((record / "checks.json").read_text())
    eph = checks["ephemeris"]
    raven = [r for r in checks["catalogued"]["rows"] if r["source"] == "RAVEN"]
    found = {
        "signal": checks["signal"]["name"],
        "tic": str(checks["tic"]),
        "search_period": _number(eph["period"], ".6f"),
        "search_t0": _number(eph["t0"], ".4f"),
        "search_duration_h": _hours(eph["duration"]),
        "suspect": _words(checks["dropped_suspect"]) or "none",
        "raven_period": _number(raven[0]["period"], ".3f") if len(raven) == 1 else None,
    }
    review = record / "review.json"
    if review.is_file():
        found |= {
            f"review_{f['id']}": _scrub(f["claim"]) for f in calls.load_review(review)["findings"]
        }
    return _filled(found)


def fact_values(facts: dict) -> dict[str, str]:
    read = {str(fact["read"]) for fact in facts.values()}
    return _filled(
        {f"fact_{key}": str(fact["value"]) for key, fact in facts.items()}
        | {
            "fact_sources": "; ".join(dict.fromkeys(fact["source"] for fact in facts.values())),
            # One date stands for every fact only when all were read that day.
            "facts_read": read.pop() if len(read) == 1 else None,
        }
    )


def note(name: str, values: dict[str, str]) -> str:
    return NOTES[name].substitute(values) if name in NOTES else ""


def _seasons_table(prediction: dict) -> str:
    rows = []
    for s in prediction["training_seasons"]:
        years = sorted({_year(s["start"]), _year(s["end"])})
        rows.append(
            [
                s["season"],
                _words(s["sectors"]),
                " to ".join(map(str, years)),
                s["transit_cadences"],
                "yes" if s["holds_transits"] else "no",
            ]
        )
    return _table(["Season", "Sectors", "Year", "Cadences in transit", "Holds a transit"], rows)


def _references_table(prediction: dict) -> str:
    def row(name: str, sectors: list[int], ref: dict, cadences: int) -> list:
        if ref["ref_n"] == 0:
            # No cadence in the cores: the README says a family showing none can't test the new season.
            return [name, _words(sectors), "none", "none", 0, cadences]
        return [
            name,
            _words(sectors),
            _ppm(ref["ref"]),
            _ppm(ref["ref_err"]),
            ref["ref_n"],
            cadences,
        ]

    trained = prediction["reference"]
    families = prediction["training_families"]
    rows = [
        row(name.upper(), families[name], ref, ref["training_cadences"])
        for name, ref in sorted(trained["families"].items())
    ]
    every = sorted(s for sectors in families.values() for s in sectors)
    total = sum(ref["training_cadences"] for ref in trained["families"].values())
    rows.append(row("All families", every, trained, total))
    header = [
        "Family",
        "Training sectors",
        "Depth (ppm)",
        "Error (ppm)",
        "Cadences in the cores",
        "Training cadences",
    ]
    return _table(header, rows)


def _left_out(prediction: dict, lock_start: dt.date) -> tuple[str, str]:
    left = prediction["left_out"]
    if not left:
        return "none", ""
    text = f"{_sectors_words([s['sector'] for s in left])}, which start before the lock on {lock_start}"
    inside = [s["sector"] for s in left if s["in_season"]]
    if not inside:
        return text, ""
    return text, (
        f" The new season still holds {_sectors_words(inside)}: the test counts their cadences as part of it, though "
        "this package lists no transit in them."
    )


def _offsets(windows: list[dict], transits: list[dict]) -> list[float]:
    mids = np.array([t["mid_btjd"] for t in transits])
    return [
        float((w["mid_btjd"] - mids[np.argmin(np.abs(mids - w["mid_btjd"]))]) * MINUTES_PER_DAY)
        for w in windows
    ]


def _section(
    prediction: dict,
    record: Path,
    crit_vet: dict,
    sectors: pd.DataFrame,
    lock_start: dt.date,
    facts: dict,
) -> str:
    checks = json.loads((record / "checks.json").read_text())
    windows = observer_windows(checks, lock_start, sectors)
    sd = [w["sd_minutes"] for w in windows]
    offsets = _offsets(windows, prediction["transits"])
    refit = prediction["predicted"]
    kept = sorted({t["sector"] for t in prediction["transits"]})
    left_out, in_season = _left_out(prediction, lock_start)
    found = record_values(record) | fact_values(facts)
    found |= _filled(
        {
            "n_seasons": str(len(prediction["training_seasons"])),
            "n_with_transits": str(
                sum(s["holds_transits"] for s in prediction["training_seasons"])
            ),
            "min_training_seasons": str(prediction["min_training_seasons"]),
            "seasons": _seasons_table(prediction),
            "period": _number(refit["period"], ".6f"),
            "t0": _number(refit["t0"], ".4f"),
            "duration_h": _hours(refit["duration"]),
            "core_minutes": _number(prediction["core_half_width_days"] * MINUTES_PER_DAY, ".0f"),
            "references": _references_table(prediction),
            "n_transits": str(len(prediction["transits"])),
            "kept": _sectors_words(kept),
            "left_out": left_out,
            "in_season": in_season,
            "testable": _either(prediction["testable_with"]) or "none",
            "n_windows": str(len(windows)),
            "fit_family": crit_vet["families"]["fit"].upper(),
            "sd": _span(sd, ".0f"),
            "offset": _span(offsets, "+.0f"),
        }
    )
    text = SIGNAL.substitute(found)
    extra = note(prediction["signal"], found)
    return (text + ("\n" + extra if extra else "")).rstrip("\n")


def _routes_table(predictions: dict[str, dict]) -> str:
    rows = [
        [
            name,
            "; ".join(
                f"{family.upper()}: {_words(sectors)}"
                for family, sectors in sorted(p["training_families"].items())
            ),
            _either(p["testable_with"]) or "none",
        ]
        for name, p in predictions.items()
    ]
    return _table(["Signal", "Training families", "Data that can test the new season"], rows)


def _hashes_table(provenance: dict, predictions: dict[str, dict]) -> str:
    inputs = provenance["inputs"]
    rows = []
    for name, p in predictions.items():
        checks, lc = inputs[f"checks_{name}"], inputs[f"light_curve_{p['tic']}"]
        rows.append([name, f"`checks.json` {checks['sha256']}", f"TIC {p['tic']}: {lc['sha256']}"])
    return _table(["Signal", "Record", "Light curve"], rows)


def _kept_sectors(predictions: dict[str, dict]) -> list[int]:
    return sorted({t["sector"] for p in predictions.values() for t in p["transits"]})


def readme(
    provenance: dict,
    predictions: dict[str, dict],
    records: dict[str, Path],
    crit_vet: dict,
    facts: dict,
    sectors: pd.DataFrame,
) -> str:
    """The package's README, from the run's provenance, its predictions, the records and `facts`."""
    lock_start = dt.date.fromisoformat(provenance["lock_start"])
    cfg, inputs = crit_vet["holdout"], provenance["inputs"]
    kept = _kept_sectors(predictions)
    # TESS-SPOC stopped (facts.toml), so a signal that only SPOC and TESS-SPOC can test needs 2-min data.
    need = [
        n
        for n, p in predictions.items()
        if set(p["testable_with"]) - {"TESS-SPOC"} == {"SPOC 2-min"}
    ]
    read_on = list(sectors.set_index("sector").loc[kept, "read_on"])
    # A blank read date would render as "nan", so it raises instead.
    dated = all(isinstance(r, str) and r for r in read_on)
    unlisted = sorted(
        {p["tic"] for p in predictions.values()} - set(facts["off_two_minute_lists"]["value"])
    )
    if unlisted:
        raise ValueError(
            f"facts.toml does not give TIC {_words(unlisted)} as on none of the 2-min lists it read"
        )
    criteria_vet = provenance["criteria"][1]
    found = fact_values(facts) | _filled(
        {
            "n_signals": str(len(predictions)),
            "signals": _words(list(predictions)),
            "first_sector": str(kept[0]),
            "last_sector": str(kept[-1]),
            "first_window": str(
                min(
                    _window_sectors(json.loads((r / "checks.json").read_text()))[0]
                    for r in records.values()
                )
            ),
            "made": provenance["started_at"][:10],
            "run_id": provenance["run_id"],
            "commit": provenance["git"]["commit"],
            "vetting_run": provenance["vetting_run"],
            "core_percent": f"{crit_vet['depth']['core_fraction'] * 100:g}",
            "criteria_vet": criteria_vet["file"],
            "criteria_vet_sha256": criteria_vet["sha256"],
            "season_gap_days": f"{cfg['season_gap_days']:g}",
            "min_training_seasons": str(cfg["min_training_seasons"]),
            "min_points": str(cfg["min_points"]),
            "min_expected_snr": f"{cfg['min_expected_snr']:g}",
            "min_sigma": f"{cfg['min_sigma']:g}",
            "max_depth_tension": f"{cfg['max_depth_tension']:g}",
            "routes": _routes_table(predictions),
            "n_need_2min": str(len(need)),
            # The sentence assumes some signal needs 2-min data, as M4's do; with none its placeholder raises.
            "need_2min": _words(need) or None,
            "ddt_ask": _ddt_ask(need, predictions, facts),
            "judged_by": JUDGED_BY.isoformat(),
            "lock_start": lock_start.isoformat(),
            "deposit_by": _deposit_by(lock_start, facts),
            "sectors_file": crit_vet["predict"]["sectors_file"],
            "sectors_read": _words(sorted(set(read_on))) if dated else None,
            "sections": "\n\n".join(
                _section(p, records[name], crit_vet, sectors, lock_start, facts)
                for name, p in predictions.items()
            ),
            "criteria": "; ".join(
                f"`{c['file']}` sha256 {c['sha256']}" for c in provenance["criteria"]
            ),
            "catalogs": provenance["catalogs"],
            "known_sha256": inputs["known"]["sha256"],
            "manifest_sha256": inputs["catalog_manifest"]["sha256"],
            "sectors_sha256": inputs["tess_sectors"]["sha256"],
            "facts_sha256": inputs["facts"]["sha256"],
            "hashes": _hashes_table(provenance, predictions),
            "prediction_columns": ", ".join(f"`{c}`" for c in PREDICTION_COLUMNS),
            "window_columns": ", ".join(f"`{c}`" for c in _window_columns(crit_vet)),
        }
    )
    return README.substitute(found)


def zenodo(provenance: dict, predictions: dict[str, dict], facts: dict) -> str:
    kept = _kept_sectors(predictions)
    found = fact_values(facts) | {
        "n_signals": str(len(predictions)),
        "signals": _words(list(predictions)),
        "tics": _words(sorted(p["tic"] for p in predictions.values())),
        "first_sector": str(kept[0]),
        "last_sector": str(kept[-1]),
        "run_id": provenance["run_id"],
        "commit": provenance["git"]["commit"],
        "vetting_run": provenance["vetting_run"],
        "lock_start": provenance["lock_start"],
        "deposit_by": _deposit_by(dt.date.fromisoformat(provenance["lock_start"]), facts),
        "judged_by": JUDGED_BY.isoformat(),
    }
    return ZENODO.substitute(found)


def _deposit_by(lock_start: dt.date, facts: dict) -> str:
    """The last day a deposit locks its files by `lock_start`."""
    return (lock_start - dt.timedelta(days=facts["zenodo_edit_days"]["value"])).isoformat()


def _ddt_ask(need: list[str], predictions: dict[str, dict], facts: dict) -> str:
    """The DDT proposal (decision 0039) of each signal only 2-min data can test, in the state its `ddt_<tic>` fact
    gives, which the maintainer's decision sets; a sent proposal is a request, which the TESS office decides."""
    states = {
        n: facts[f"ddt_{predictions[n]['tic']}"]["value"]
        for n in need
        if f"ddt_{predictions[n]['tic']}" in facts
    }
    rest = [n for n in need if n not in states]
    if not states:
        return "No DDT proposal asks for 2-min data on any of them, so for these no 2-min data are in sight."
    texts = [
        f"For {n}, tess-hunt has a DDT proposal asking for 2-min data (`results/ddt/{n}/` in its repository); its "
        f"state, as `facts.toml` gives it: {state}."
        for n, state in states.items()
    ]
    texts.append("A sent proposal is a request, which the TESS office may or may not take.")
    if rest:
        texts.append(f"For {_words(rest)} no 2-min data are in sight.")
    return " ".join(texts)


def _window_columns(crit_vet: dict) -> list[str]:
    widths = [f"half_width_{s:g}sigma_minutes" for s in crit_vet["predict"]["sigma"]]
    return [
        "signal",
        "tic",
        "sector",
        "epoch",
        "mid_btjd",
        "mid_utc",
        "sd_minutes",
        *widths,
        "duration_days",
    ]


def _window_rows(name: str, checks: dict, lock_start, sectors) -> list[dict]:
    star = checks["star"]
    return [
        {
            "signal": name,
            "tic": int(checks["tic"]),
            "sector": w["sector"],
            "epoch": w["epoch"],
            "mid_btjd": w["mid_btjd"],
            "mid_utc": predict.seen_utc(w["mid_btjd"], star["ra"], star["dec"]),
            "sd_minutes": w["sd_minutes"],
            **{f"half_width_{k}sigma_minutes": v for k, v in w["half_width_minutes"].items()},
            "duration_days": w["duration_days"],
        }
        for w in observer_windows(checks, lock_start, sectors)
    ]


def _records() -> Path:
    return repo_root() / "results" / "vetting"


def _uncommitted(path: Path) -> bool:
    """Whether git sees `path` changed, staged or untracked in the checkout it sits in."""
    out = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", path.name],
        cwd=path.parent,
        capture_output=True,
        text=True,
        check=True,
    )
    return bool(out.stdout.strip())


def cmd_run(args) -> int:
    crit_search, crit_vet = load_criteria(args.criteria_search), load_criteria(args.criteria_vet)
    # Every refusal comes before the run starts, so it leaves no unfinished run directory.
    made = vetting._vetting_run(args.vetting_run, crit_search, crit_vet, args.production)
    run_id = args.vetting_run.resolve().name
    read = {name: item["sha256"] for name, item in made["inputs"].items()}
    snapshot = snapshot_inputs(args.catalogs)
    if any(not p.is_file() or sha256_file(p) != read.get(n) for n, p in snapshot.items()):
        raise SystemExit(f"{args.catalogs.name} is not the catalog snapshot {run_id} read")
    sectors_file = crit_vet["predict"]["sectors_file"]
    if sha256_file(repo_root() / sectors_file) != read.get("tess_sectors"):
        # The records' windows were placed in sectors by the dates that run read.
        raise SystemExit(f"{sectors_file} is not the file {run_id} read for the sector dates")
    sectors = predict.load_sectors(sectors_file)
    records, light_curves = {}, {}
    for name in args.records:
        record, where = _records() / name, f"results/vetting/{name}"
        if not (record / "call.toml").is_file():
            raise SystemExit(f"no call in {where}: only a published record is predicted")
        try:
            call = calls.load(record / "call.toml")
        except calls.CallError as exc:
            raise SystemExit(f"{where}: {exc}") from None
        if call["outcome"] != "held":
            raise SystemExit(
                f"{name} is {call['outcome']}, not held: decision 0040 predicts held signals only"
            )
        vetted = args.vetting_run / "signals" / name / "checks.json"
        if not vetted.is_file() or sha256_file(vetted) != sha256_file(record / "checks.json"):
            raise SystemExit(f"{where}/checks.json is not {run_id}'s checks.json for {name}")
        checks = json.loads((record / "checks.json").read_text())
        tic = int(checks["tic"])
        lc = lc_dir() / f"{tic}.npz"
        if not lc.is_file() or sha256_file(lc) != read.get(f"light_curve_{tic}"):
            raise SystemExit(f"the light curve on disk for TIC {tic} is not the one {run_id} read")
        if not _lock(checks, args.lock_start, sectors)[0]:
            raise SystemExit(f"no sector in {name}'s windows starts on or after {args.lock_start}")
        records[name], light_curves[name] = record, (tic, lc)
    committed = repo_root() / FACTS
    facts_file = args.facts or committed
    # start_run's clean-tree check covers the code, not results/, so a production package could otherwise state facts
    # from another checkout or an edit nobody committed.
    if args.production and facts_file.resolve() != committed.resolve():
        raise SystemExit(f"a production run states {FACTS} from this checkout, not {facts_file}")
    if args.production and _uncommitted(committed):
        raise SystemExit(
            f"{FACTS} has changes that are not committed; a production run needs it committed"
        )
    facts = tomllib.loads(facts_file.read_text())
    run = start_run("predictions", [crit_search, crit_vet], args.production, sys.argv)
    run.record("vetting_run", run_id)
    run.record("catalogs", args.catalogs.resolve().name)
    run.record("lock_start", args.lock_start.isoformat())
    run.record("judged_by", JUDGED_BY.isoformat())
    run.record_input("vetting_provenance", args.vetting_run / "provenance.json")
    for name, record in records.items():
        for file in ("checks.json", "call.toml", "review.json"):
            if (record / file).is_file():
                run.record_input(f"{Path(file).stem}_{name}", record / file)
        proposal = record.parent.parent / "ddt" / name / "proposal.md"
        if proposal.is_file():
            run.record_input(f"ddt_proposal_{name}", proposal)
        tic, lc = light_curves[name]
        run.record_input(f"light_curve_{tic}", lc)
    for name, path in snapshot.items():
        run.record_input(name, path)
    run.record_input("tess_sectors", repo_root() / sectors_file)
    run.record_input("facts", facts_file)
    known = load_known(args.catalogs)
    predictions = {
        name: predict_signal(
            record,
            LightCurve.load(light_curves[name][1]),
            known,
            crit_search.values,
            crit_vet.values,
            sectors,
            args.lock_start,
        )
        for name, record in records.items()
    }
    # Rendered before anything is written beside the provenance: a missing value leaves no partial package.
    text = readme(run.provenance, predictions, records, crit_vet.values, facts, sectors)
    metadata = zenodo(run.provenance, predictions, facts)
    rows = [
        {
            "signal": name,
            "tic": p["tic"],
            **t,
            "period": p["predicted"]["period"],
            "t0": p["predicted"]["t0"],
            "core_half_width_days": p["core_half_width_days"],
        }
        for name, p in predictions.items()
        for t in p["transits"]
    ]
    windows = [
        row
        for name, record in records.items()
        for row in _window_rows(
            name, json.loads((record / "checks.json").read_text()), args.lock_start, sectors
        )
    ]
    columns = _window_columns(crit_vet.values)
    # A window with other half-widths than [predict] sigma gives would lose them, or gain empty ones, in the CSV.
    if any(list(row) != columns for row in windows):
        raise ValueError("a record's windows carry other fields than [predict] gives them")
    pd.DataFrame(rows, columns=PREDICTION_COLUMNS).to_csv(run.path / "predictions.csv", index=False)
    pd.DataFrame(windows, columns=columns).to_csv(run.path / "windows.csv", index=False)
    run.write_json(
        "references.json",
        {
            "lock_start": args.lock_start.isoformat(),
            "judged_by": JUDGED_BY.isoformat(),
            "test": {
                "holdout": crit_vet["holdout"],
                "core_fraction": crit_vet["depth"]["core_fraction"],
                "families": crit_vet["families"],
            },
            "signals": {
                name: {k: v for k, v in p.items() if k != "transits"}
                for name, p in predictions.items()
            },
        },
    )
    shutil.copyfile(facts_file, run.path / "facts.toml")
    (run.path / "README.md").write_text(text)
    (run.path / "zenodo.md").write_text(metadata)
    summary = {
        name: {
            "sectors": sorted({t["sector"] for t in p["transits"]}),
            "transits": len(p["transits"]),
        }
        for name, p in predictions.items()
    }
    for name, s in summary.items():
        print(f"{name}: {s['transits']} transits in sectors {s['sectors']}")
    run.finish(signals=summary, lock_start=args.lock_start.isoformat())
    print(f"predictions: {len(predictions)} signals -> {run.path}")
    return 0


def _package(source: Path) -> list[Path]:
    made = json.loads((source / "provenance.json").read_text())
    if made.get("stage") != "predictions":
        raise SystemExit(f"run {source.name} is not a predictions run")
    if not made.get("production"):
        raise SystemExit(
            f"run {source.name} is not a production run; only a production package is published"
        )
    return [source / name for name in PACKAGE]


def _dois(root: Path, packages: list[str]) -> dict[str, dict]:
    """`dois.toml`: the DOI and publication date Zenodo gave each package, by its run id."""
    path = root / "dois.toml"
    if not path.is_file():
        return {}
    dois = tomllib.loads(path.read_text())
    for run_id, entry in dois.items():
        if run_id not in packages:
            raise SystemExit(f"dois.toml names {run_id}, which is not a published package")
        if not isinstance(entry.get("doi"), str) or not isinstance(entry.get("published"), dt.date):
            raise SystemExit(
                f"dois.toml: {run_id} needs doi (a string) and published (a TOML date)"
            )
    return dois


def index(repo: Path) -> str:
    """results/predictions/README.md: each published package, the day its run was made, its signals and, once
    `dois.toml` records it, its DOI."""
    root = repo / "results" / "predictions"
    packages = sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "provenance.json").is_file()
    )
    dois = _dois(root, packages)
    rows = []
    for run_id in packages:
        made = json.loads((root / run_id / "provenance.json").read_text())
        signals = json.loads((root / run_id / "references.json").read_text())["signals"]
        entry = dois.get(run_id)
        doi = (
            f"[{entry['doi']}](https://doi.org/{entry['doi']}), published {entry['published']}"
            if entry
            else "DOI pending"
        )
        rows.append(
            [
                f"[`{run_id}`]({run_id}/README.md)",
                made["started_at"][:10],
                _words(list(signals)),
                doi,
            ]
        )
    table = (
        _table(["Package", "Made", "Signals", "DOI"], rows)
        if rows
        else "No package is published yet."
    )
    facts = tomllib.loads((root / "facts.toml").read_text())
    return INDEX.substitute(fact_values(facts) | {"packages": table})


def _write_index(repo: Path) -> None:
    (repo / "results" / "predictions" / "README.md").write_text(index(repo))


def cmd_publish(args) -> int:
    root = repo_root()
    publish_run(args.run, root, "predictions", _package)
    _write_index(root)
    return 0


def cmd_index(args) -> int:
    _write_index(repo_root())
    print("rendered results/predictions/README.md")
    return 0


def add_parser(sub) -> None:
    p = sub.add_parser(
        "predictions", help="preregistered predictions for held signals (decision 0040)"
    )
    modes = p.add_subparsers(dest="mode", required=True)
    r = modes.add_parser(
        "run", help="the prediction each held signal's next season is judged against"
    )
    r.add_argument(
        "--vetting-run", type=Path, required=True, help="the vetting run the records came from"
    )
    r.add_argument(
        "--records", nargs="+", required=True, help="held signals' names under results/vetting/"
    )
    r.add_argument(
        "--catalogs", type=Path, required=True, help="the catalog snapshot the vetting run read"
    )
    r.add_argument(
        "--lock-start",
        type=dt.date.fromisoformat,
        required=True,
        help="the date the deposit's files lock; sectors starting earlier are left out",
    )
    r.add_argument(
        "--facts",
        type=Path,
        help=f"archive facts, with sources; by default {FACTS} in this checkout, the only file a production run takes",
    )
    r.add_argument("--criteria-search", type=Path, default=Path("criteria/search-v2.toml"))
    r.add_argument("--criteria-vet", type=Path, default=Path("criteria/vet-v3.toml"))
    r.add_argument("--production", action="store_true")
    r.set_defaults(func=cmd_run)
    pub = modes.add_parser(
        "publish", help="copy a production predictions run into results/predictions/"
    )
    pub.add_argument("--run", required=True, help="the run id")
    pub.set_defaults(func=cmd_publish)
    i = modes.add_parser(
        "index", help="render results/predictions/README.md again, with dois.toml's DOIs"
    )
    i.set_defaults(func=cmd_index)
