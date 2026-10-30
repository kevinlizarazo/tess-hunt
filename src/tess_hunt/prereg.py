"""Predictions for the held signals (decision 0040): before TESS looks at a held signal's star again, the prediction
its held-out season test will judge, and the test. With the new season held out, every other season is the M3 light
curve, so the refit and the training depths `checks.holdout` computes for that season are fixed now. The package holds
them, the record's observer windows beside them, and a README filled with `substitute` from the run, the records and
`facts.toml`; the Zenodo deposit form's text is rendered the same way from a finished run's files. A value they lack,
or hold as null or NaN, raises instead of rendering (docs/design.md, section 5.5)."""

import datetime as dt
import json
import math
import shutil
import subprocess
import sys
import textwrap
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
from tess_hunt.checks.holdout import judge, reference, refit_ephemeris, season_labels
from tess_hunt.config import lc_dir, load_criteria, runs_dir
from tess_hunt.ddt import _number
from tess_hunt.dossier import _scrub, _table, _words
from tess_hunt.ephemeris import Ephemeris, in_transit
from tess_hunt.lightcurve import LightCurve
from tess_hunt.provenance import publish_run, repo_root, sha256_file, start_run
from tess_hunt.vet import Prepared, prepare

# Decision 0040's judging date, applied to the fetch (decision 0041): a light curve fetched on or after it completes no
# season, and a season still missing a predicted sector as of it stays untested.
JUDGED_BY = dt.date(2027, 12, 31)
# The new season's status as decision 0040 names it; every other status is untested.
RESULTS = {"predicted": "replicated", "missed": "missed"}
# fetch's products (mast.PROVENANCES), as the package names them.
PRODUCTS = {"SPOC": "SPOC 2-min", "TESS-SPOC": "TESS-SPOC", "QLP": "QLP"}
PACKAGE = (
    "README.md",
    "facts.toml",
    "predictions.csv",
    "provenance.json",
    "references.json",
    "windows.csv",
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
# Zenodo's two limits on editing a record's files; a sentence that states them names both read dates.
ZENODO_FACTS = ("zenodo_edit_days", "zenodo_edit_publish_days")

README = Template("""\
# Transit predictions for $n_signals held tess-hunt signals in TESS Sectors $first_sector to $last_sector

tess-hunt is an independent search for transiting planets in public TESS light curves. Each signal is named by its
star's TIC number and its rank on that star. tess-hunt's vetting neither passed nor rejected these $n_signals
signals, because the public data cannot decide them, and holds them for new data:
$signals.
Each is a candidate signal, not a planet. TESS observes their stars again from Sector $first_window on. This package
predicts their transits in Sectors $first_sector to $last_sector, which start after its files are fixed (see The lock).

The package fixes the prediction for each signal's new season, and the test that will judge it, before TESS observes
those sectors. It was made on $made (UTC). tess-hunt's code computed every number in it from the signals'
published vetting records, the light curves they were vetted on and the other files listed under Provenance.
tess-hunt's code and this text were written with LLM assistance.

## What is judged

tess-hunt's vetting criteria, vet-v3, include a held-out season check. It refits a signal's period and epoch on every
season but one, searching periods near the one tess-hunt's search found, and measures the left-out season's depth
only in the central $core_percent% of each transit the refit predicts (the transit's core).

Here the left-out season is the new one, made by the sectors TESS is about to observe for each star. The other seasons
are the light curve the signal was vetted on, as the vetting run's checks saw it: without the sectors flagged for
suspect timestamps, detrended with the star's other catalogued transits masked, as before, and with the same
red-noise depth errors. Those seasons are fixed already, so the refit and the training depths are published now:

- `predictions.csv`: the refit's period, t0 and core half-width, and the mid-time of each transit it predicts in the
  predicted sectors. This is what the test judges.
- `references.json`: the training depths the new season is compared with, measured in the same cores over all
  training cadences and for each product family, each with its error and cadence count. It also holds what the
  check's two training gates read: the training seasons, which of them hold a transit in their data, and
  `min_training_seasons`.

`windows.csv` is not judged. It holds the transit windows of the transit-model fit with the TIC stellar density as a
prior (the density-prior fit) in each signal's vetting record, copied unchanged with their standard deviations, for
observers checking by eye. They come from a different fit and can differ from the refit. The test never reads them.

## The test

The new season is judged with the held-out check's measurement and thresholds, read from `$criteria_vet` (listed
with its sha256 under Provenance), using the published prediction and training depths in place of a fresh refit:

- Seasons are split at gaps of more than $season_gap_days days.
- The new season is tested only if at least $min_training_seasons training seasons hold a transit in their data.
- Its depth is measured in the predicted cores. With fewer than $min_points cadences there, it is untested.
- If a product family present in its cores has fewer than $min_points training cadences in the cores, it is untested.
- Its expected depth is each family's training depth, weighted as that family's cadences weight the season's depth. If
  the expected depth is less than $min_expected_snr times the season's depth error, the season's data are too noisy
  to show the dip, and it is untested.
- Otherwise the season is replicated when its depth is at least $min_sigma times its error and, in every family with
  at least $min_points cadences in the cores both in the season and in training, within $max_depth_tension sigma of
  that family's training depth. If not, it is missed.

The result for each signal is replicated, missed or untested. The new season is also untested if no light curve the
test can use covers it, or if the one that does was downloaded on or after the judging date (see When it is
judged).

Applied to any season of the vetted light curve, with that season held out, this test gives exactly the held-out
check's result for it. tess-hunt's test suite checks this on a synthetic three-season light curve, holding out each
season in turn: the package's refit, training depths and result equal what the check computes. Judging with the
published numbers, not a fresh refit, keeps the result fixed if the training data later change, for example when a
sector is redelivered.

## Which data can test it

Depths are compared only within a product family.
$families
The new season can therefore be tested only if every family in its cores also has training data. tess-hunt takes one
product per sector, so a season that includes a sector from a family without training data is untested as a whole.

$routes
$no_cadences
TESS-SPOC's full-frame light curves stop at Sector $fact_tess_spoc_last_sector, and MAST holds QLP's only through a
partial Sector $fact_qlp_last_sector (as read on $archives_read). For $n_need_2min of the $n_signals signals
($need_2min) the table allows only SPOC 2-min or TESS-SPOC data,
so only SPOC 2-min data can test their predictions.

As read on $lists_read, none of the $n_signals stars is on
$fact_two_minute_lists.
A list can still change before its sector.

$ddt_ask

All $n_need_2min are predicted anyway, since anyone can check a public prediction by eye. No other product, tess-hunt's
own full-frame photometry included, can test a prediction unless a decision record in tess-hunt's repository says how
the test applies to it, made before that product is run on these stars.

## When it is judged

tess-hunt vets a held signal again when new data arrive (a re-vet). Each signal is judged once, at the first re-vet
whose light curve covers every predicted sector with data the test can use. Until then, and only before the judging
date, a re-vet reports the result as pending.

The judging date is $judged_by. It applies to the date a re-vet's light curve was downloaded, which tess-hunt
records, not to when the data became public or when the re-vet runs. A complete light curve downloaded before that
date is judged whenever the re-vet runs. One downloaded on or after it does not count, and a season still incomplete
on the judging date stays untested. A judged result stands for every later re-vet.

A season runs from gap to gap, so a sector left out of the prediction (see The lock) can still fall in the new season.
The test then counts that sector's cadences as part of the season, and the signal's section says so.

## What a result means

A replicated season shows the dip is real, periodic and where it was predicted. It does not show that the dip is on
the target star: a signal held because light from another star could cause the dip stays held until there is evidence
on that. A transit that arrives outside the predicted cores because the refit's period has drifted counts as missed:
the test judges the prediction as published.

In vetting, the held-out check holds out each season in turn. It fails when two or more seasons are tested and any of
them is missed, and under tess-hunt's rules for its vetting calls (decision record 0028 in its repository) a failed
check is grounds to reject the signal. With fewer than two seasons tested the check stays inconclusive. A missed new
season is then not a failed check but evidence against the signal, which the maintainer weighs in deciding whether
to pass, reject or keep holding it.

## The lock

Zenodo lets a record's owner open an edit of its files within $fact_zenodo_edit_days days of publishing, and the edit
must be published within $fact_zenodo_edit_publish_days days of publishing (as read on $zenodo_read). A record's files
are therefore fixed $fact_zenodo_edit_publish_days days after it is published. This package was deposited by
$deposit_by, so its files are fixed by $lock_start, and it predicts only sectors that start on or after that date. A
sector in a signal's windows that starts earlier is left out, and the signal's section names it.

Sector dates are from tess.mit.edu's sector pages (read $sectors_read), as tess-hunt's
`$sectors_file` holds them.

$sections

## Provenance

- Code: tess-hunt commit $commit.
- This package: run $run_id.
  Its `provenance.json` lists the run's inputs with their sha256 and its command line.
- Vetting records: from vetting run $vetting_run.
- Criteria:
$criteria
- Catalog snapshot read by the vetting run, $catalogs:
  - `known.parquet`, sha256 $known_sha256
  - `manifest.json`, sha256 $manifest_sha256
- Sector dates: `$sectors_file`, sha256
  $sectors_sha256.
- Facts about archives, target lists, RAVEN's citation and the DDT proposal: `facts.toml`, sha256
  $facts_sha256.

Each signal's published record, `results/vetting/<signal>/` in tess-hunt's repository, and the light curve its vetting
run read:

$hashes

## Files

- `predictions.csv`: one row per predicted transit, with columns
$prediction_columns.
  `epoch` counts periods from the refit's t0, `mid_btjd` is BJD_TDB - 2457000, `mid_utc` is the mid-time in UTC as
  seen from Earth, and `period` and `t0` are the refit's, in days and BTJD.
- `references.json`: for each signal, the refit (`predicted`, with BLS's duration and depth), the core half-width, the
  training depths (`reference`, as fractions of the flux, pooled and by family), the training seasons and families,
  the products that can test it (`testable_with`) and the sectors left out; and the test's criteria values (`test`).
- `windows.csv`: the observers' windows, with columns
$window_columns.
  `epoch` counts periods from the density-prior fit's t0.
- `facts.toml`: the facts this README states about archives, target lists, RAVEN's citation and the DDT proposal,
  each with its source and the date it was read.
- `provenance.json`: the run's commit, criteria, inputs with their sha256, and command line.

## Licence and sources

CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). It contains no Gaia data, so CC BY 4.0 covers all of it.
It is derived from TESS light curves (SPOC, TESS-SPOC and QLP, from MAST) and the TESS Input Catalog. The facts in
`facts.toml` come from:

$fact_sources

## Acknowledgements

$credits
""")

NO_CADENCES = """
Where a family has no training cadences in the cores, its signal's section shows "none" for that family's depth and
error, and that family cannot test the new season.
"""

SIGNAL = Template("""\
## $signal (TIC $tic)

The search found the signal at period $search_period d, t0 BTJD $search_t0 and duration $search_duration_h h.
The refit starts from this ephemeris.
$suspect

$training

$seasons

The refit gives period $period d, t0 BTJD $t0 and duration $duration_h h. Each predicted transit's core runs
$core_minutes min either side of its mid-time. The training depths in the cores are:

$references

The package predicts $n_transits transits in $kept.$left_out
$testable

For observers, the vetting record gives $n_windows transit windows in $kept, from the density-prior fit
to the $fit_family family alone. Their mid-times have standard deviations of $sd min
and run $offset the refit's nearest predicted mid-times.$wide
""")

# A signal's section adds it when its observers' windows reach half its refit period either side.
WIDE = Template("""
These windows are too wide to place a transit: at $sigma sigma they reach up to $widest min either side of their
mid-times, against a refit period of $orbit min. Use the refit's times in `predictions.csv` instead.""")

# What a data release built on the project's results must carry (ACKNOWLEDGEMENTS.md, which test_prereg checks these
# against): MAST's acknowledgement for TESS data, QLP's own, and each light-curve product's DOI and papers, in the
# order the deposited package's Zenodo description lists them, and the TIC's papers.
TESS_CREDIT = (
    "includes data collected with the TESS mission, obtained from the MAST data archive at the Space Telescope "
    "Science Institute (STScI). Funding for US Institutions for the TESS mission is provided by the NASA Explorer "
    "Program. STScI is operated by the Association of Universities for Research in Astronomy, Inc., under NASA "
    "contract NAS5\u201326555."
)
QLP_CREDIT = (
    "We acknowledge the use of TESS High Level Science Products (HLSP) produced by the Quick-Look Pipeline (QLP) at "
    "the TESS Science Office at MIT, which are publicly available from the Mikulski Archive for Space Telescopes "
    "(MAST). Funding for the TESS mission is provided by NASA's Science Mission directorate."
)
CREDITED = {
    "TESS-SPOC": (
        "TESS-SPOC full-frame-image light curves",
        "10.17909/t9-wpz1-8s54",
        (("Caldwell et al. 2020", "RNAAS 4, 201"),),
    ),
    "QLP": (
        "QLP light curves",
        "10.17909/t9-r086-e880",
        (
            ("Huang et al. 2020a", "RNAAS 4, 204"),
            ("Huang et al. 2020b", "RNAAS 4, 206"),
            ("Kunimoto et al. 2021", "RNAAS 5, 234"),
            ("Kunimoto et al. 2022", "RNAAS 6, 236"),
        ),
    ),
    "SPOC 2-min": (
        "SPOC 2-minute light curves",
        "10.17909/t9-nmc8-f686",
        (("Jenkins et al. 2016", "Proc. SPIE 9913, 99133E"),),
    ),
}
TIC_PAPERS = (("Stassun et al. 2019", "AJ 158, 138"), ("Paegert et al. 2021", "arXiv:2108.04778"))

# Each signal whose section says more than the others, from its record (design 4.3).
NOTES = {
    "399023421-1": Template("""\
tess-hunt's adversarial review of this signal was written by an AI model,
$review_model, on $review_date. Its finding F9, quoted word for word:

> $review_F9

The refit leaves those QLP sectors out, as every check does, and is published as it stands. If the new season's
transits arrive late against its cores, the season can be missed, and a miss caused by drift counts as a miss.

RAVEN ($fact_raven)
lists a dip on the star at $raven_period d. The review's finding F4, quoted word for word:

> $review_F4
"""),
}

ZENODO = Template("""\
# Zenodo deposit form for $run_id

Creators and the link to tess-hunt's code are added in the form at deposit.

## Title

Preregistered transit predictions for $n_signals tess-hunt planet-candidate signals in TESS Sectors $first_sector to $last_sector

## Resource type

Dataset

## Description

$description

## Keywords

- TESS
- transiting exoplanets
- planet candidates
- preregistration
- transit timing prediction

## Licence

Creative Commons Attribution 4.0 International (CC BY 4.0)
""")

# Each paragraph is pasted as one line, so the line breaks here do not reach the form.
DESCRIPTION = Template("""\
Transit predictions for $n_signals planet-candidate signals in TESS Sectors $first_sector to $last_sector, published
before TESS observes those sectors. The signals come from tess-hunt, an independent search for transiting planets in
public TESS light curves, whose vetting neither passed nor rejected them because the public data cannot decide them.
They are on TIC $tics
(tess-hunt's signals $signals). Each is a candidate signal, not a planet.

For each signal the dataset gives a period and epoch refitted on the light curve the signal was vetted on, the transit
times they predict in the new sectors, and the transit depths of the earlier seasons. The test measures the depth in
the central $core_percent% of each predicted transit in the new sectors and compares it with those depths, using the
thresholds of tess-hunt's held-out season check.

Zenodo lets a record's owner open an edit of its files within $fact_zenodo_edit_days days of publication and publish
it within $fact_zenodo_edit_publish_days days (as read on $zenodo_read). This dataset was deposited by $deposit_by,
so its files are fixed by $lock_start, and no sector that starts earlier is predicted. Each signal is judged once, on
the first light curve that covers all its predicted sectors with data the test can use. Light curves downloaded on or
after
$judged_by do not count. The README gives the test in full, the data that can test each signal and what a result
means.

tess-hunt's code and this dataset's text were written with LLM assistance$reviewed.

Made by tess-hunt commit $commit in run $run_id, from the vetting records of run $vetting_run.

Acknowledgements. $credits
""")

INDEX = Template("""\
# Predictions

Each directory here is one package of preregistered transit predictions for held signals
([decision 0040](../../docs/decisions/0040-predictions-for-held-signals.md)). A package is made by one production
run of `tess-hunt predictions run` and copied unchanged from its run directory by `tess-hunt predictions publish`.
Its `README.md` says what is predicted, the test that will judge it, and when.

The maintainer deposits each package directory as one Zenodo record, with the form text that
`tess-hunt predictions zenodo --run RUN_ID` prints. Zenodo lets a record's owner open an edit of its files within
$fact_zenodo_edit_days days of publishing and publish it within $fact_zenodo_edit_publish_days days
(as read on $zenodo_read); after that the files are fixed. Published packages are never edited: a correction is a
new package.

[facts.toml](facts.toml) holds the facts the packages state, each with its source and the date it was read.
`dois.toml` holds the DOI and publication date Zenodo gave each deposited package.

$packages

## Credits

The packages are derived from TESS light curves from MAST and from stellar parameters in the TESS Input Catalog.
Reuse of a package must carry the TESS acknowledgement, and QLP's for a package trained on QLP light curves, and cite
the light-curve products it used, with their sectors, and the TIC's papers, all as
[ACKNOWLEDGEMENTS.md](../../ACKNOWLEDGEMENTS.md) gives them. Each deposited package's Zenodo record carries them in
its description.
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
    # holdout labels seasons over the whole light curve: a window sector this close to the vetted cadences, predicted or
    # left out, would merge with their last season at a re-vet, and the prediction would not be the one it judges.
    last = float(noisy.time.max())
    gap, first = min((_sector(sectors, s)[1] - last, s) for s in kept + earlier)
    if not gap > cfg["season_gap_days"]:
        raise ValueError(
            f"{checks['signal']['name']}'s window sector {first} starts {gap:.1f} days after its last vetted cadence, "
            f"not more than season_gap_days ({cfg['season_gap_days']:g}): the test would merge it with that season"
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


def _unusable(prepared: Prepared, sector: int, testable_with: list[str]) -> str | None:
    """Why a predicted sector holds no data the test can use, or None when it does."""
    if sector in prepared.dropped:
        return "timing-suspect"
    if sector not in prepared.noisy.sector:
        return "no data"
    product = PRODUCTS.get(prepared.good.sources[str(sector)]["provenance"])
    return None if product in testable_with else f"{product}, which can't test it"


def _trained(found: dict) -> dict:
    """The package's training depths as `holdout.judge` reads them: a depth no cadence gave is NaN, which the
    package's JSON holds as null."""

    def nan(values: dict) -> dict:
        return {k: float("nan") if v is None else v for k, v in values.items()}

    return {
        **nan({k: found[k] for k in ("ref", "ref_err", "ref_n")}),
        "families": {name: nan(ref) for name, ref in found["families"].items()},
    }


def judge_signal(
    package: Path,
    signal: str,
    prepared: Prepared,
    crit_vet: dict,
    as_of: dt.date,
    fetched: dt.date | None = None,
) -> dict:
    """Decision 0040's test of `signal`'s new season in a re-vet's light curve, `prepared` as vet prepares it: the
    vet-v3 season, split at `season_gap_days` gaps, that holds the package's predicted sectors, judged by
    `holdout.judge` against the package's prediction and training depths once the package's counts pass holdout's two
    training gates. The result is replicated, missed or untested, or pending while a predicted sector has no data the
    test can use before `JUDGED_BY`. The season is judged once, complete: from `JUDGED_BY` on, one still missing a
    sector stays untested, and a light curve `fetched` on or after it completes none (decision 0041). `fetched` is
    None for the light curve the package was made from. The result names each predicted sector whose product the test
    can't use (`untestable_products`)."""
    found = json.loads((package / "references.json").read_text())
    if signal not in found["signals"]:
        raise ValueError(f"the package at {package.name} predicts no {signal}")
    p = found["signals"][signal]
    cfg, core = crit_vet["holdout"], crit_vet["depth"]["core_fraction"]
    test = {"holdout": cfg, "core_fraction": core, "families": crit_vet["families"]}
    if found["test"] != test:
        raise ValueError(
            f"vet-v3's [holdout] as given is not the test the package froze for {signal}"
        )
    # The package froze its judging date as it froze its test; the code's date must be that one.
    if found["judged_by"] != JUDGED_BY.isoformat():
        raise ValueError(
            f"the package at {package.name} froze the judging date {found['judged_by']}, but prereg.JUDGED_BY is "
            f"{JUDGED_BY}: a package is judged by the date it froze"
        )
    rows = pd.read_csv(package / "predictions.csv")
    sectors = sorted(int(s) for s in rows.loc[rows["signal"] == signal, "sector"].unique())
    # Said plainly, so a version can wait for a better product: a later re-vet takes one for such a sector.
    other = {
        str(s): product
        for s in sectors
        if s in prepared.noisy.sector
        and (product := PRODUCTS.get(prepared.good.sources[str(s)]["provenance"]))
        not in p["testable_with"]
    }
    out = {
        "predicted_sectors": sectors,
        "as_of": as_of.isoformat(),
        "judged_by": JUDGED_BY.isoformat(),
        "fetched": None if fetched is None else fetched.isoformat(),
        "untestable_products": other,
    }

    def untested(status: str, reason: str) -> dict:
        return {**out, "result": "untested", "status": status, "reason": reason}

    need = p["min_training_seasons"]
    seasons, with_transits = (
        len(p["training_seasons"]),
        sum(s["holds_transits"] for s in p["training_seasons"]),
    )
    # holdout's own gates and words, read from the counts the package froze.
    if seasons < need:
        return untested(
            "untestable",
            f"{seasons} training season(s), need {need}: one season can't predict a season a year away",
        )
    if with_transits < need:
        return untested(
            "untestable",
            f"{with_transits} of {seasons} training seasons hold a transit in their data, need {need}: one season "
            "can't predict a season a year away",
        )
    # The code sees when data were fetched, not when they were public, so the judging date applies to the fetch.
    if fetched is not None and fetched >= JUDGED_BY:
        return untested(
            "fetched_after_judged_by",
            f"the light curve was fetched on {fetched}, on or after the judging date {JUDGED_BY}: data fetched then "
            "complete no season",
        )
    missing = {s: why for s in sectors if (why := _unusable(prepared, s, p["testable_with"]))}
    if missing:
        listed = _words([f"S{s} ({why})" for s, why in missing.items()])
        if as_of < JUDGED_BY:
            return {
                **out,
                "result": "pending",
                "status": "pending",
                "reason": f"no light curve the test can use yet in {listed}; the season is judged once, complete, "
                f"or on {JUDGED_BY} as it stands then",
            }
        return untested(
            "no_light_curve", f"no light curve the test can use in {listed} by {JUDGED_BY}"
        )
    noisy = prepared.noisy
    labels = season_labels(noisy.time, cfg["season_gap_days"])
    held = np.unique(labels[np.isin(noisy.sector, sectors)])
    if len(held) != 1:
        raise ValueError(
            f"{signal}'s predicted sectors fall in {len(held)} seasons of the light curve, not one"
        )
    season = labels == held[0]
    # Sectors between the training seasons and the predicted ones (a timing-suspect sector redelivered clean, or one
    # M2 never fetched) can chain them into one season, which would then judge training cadences.
    trained = {s for t in p["training_seasons"] for s in t["sectors"]}
    shared = sorted(trained & {int(s) for s in np.unique(noisy.sector[season])})
    if shared:
        raise ValueError(
            f"{signal}'s judged season holds the training sector(s) {_words(shared)}: sectors between the training "
            "seasons and the predicted ones chain them into one season"
        )
    row = judge(
        noisy,
        family_labels(noisy, crit_vet["families"]),
        season,
        Ephemeris(**p["predicted"]),
        _trained(p["reference"]),
        cfg,
        core,
    )
    status = row["status"]
    # holdout gives a reason only for an untestable season; every untested result here carries one.
    if status == "no_predicted_transit_in_data":
        row["reason"] = f"fewer than {cfg['min_points']} cadences in the predicted cores"
    elif status == "underpowered":
        row["reason"] = (
            f"the expected depth is {row['expected_snr']:.2f} times the season's error, below "
            f"{cfg['min_expected_snr']:g}"
        )
    return {
        **out,
        "season": {
            "start": float(noisy.time[season].min()),
            "end": float(noisy.time[season].max()),
            "sectors": sorted(int(s) for s in np.unique(noisy.sector[season])),
        },
        **row,
        "result": RESULTS.get(status, "untested"),
    }


def trained_products(signals: dict[str, dict], records: dict[str, Path]) -> dict[str, list[int]]:
    """The products the predictions were trained on, each with its sectors: every sector of each signal's training
    seasons, under the product its record's `sources` names, in `CREDITED`'s order."""
    found = {}
    for name, p in signals.items():
        sources = json.loads((records[name] / "checks.json").read_text())["sources"]
        for season in p["training_seasons"]:
            for sector in season["sectors"]:
                product = PRODUCTS[sources[str(sector)]["provenance"]]
                found.setdefault(product, set()).add(sector)
    return {product: sorted(found[product]) for product in CREDITED if product in found}


def _sector_runs(sectors: list[int]) -> str:
    """Sectors as a reader lists them, three or more in a row as a range: "Sectors 9 to 12, 64 and 65"."""
    runs = []
    for sector in sorted(sectors):
        if runs and sector == runs[-1][-1] + 1:
            runs[-1].append(sector)
        else:
            runs.append([sector])
    items = [
        item
        for run in runs
        for item in ([f"{run[0]} to {run[-1]}"] if len(run) >= 3 else [str(s) for s in run])
    ]
    return f"Sector {items[0]}" if len(sectors) == 1 else f"Sectors {_words(items)}"


def acknowledgements(trained: dict[str, list[int]], what: str) -> str:
    """The acknowledgements and citations ACKNOWLEDGEMENTS.md asks of a data release, for the products and sectors
    `trained` gives (`trained_products`); `what` names the release ("package", "dataset")."""
    used = []
    for product, sectors in trained.items():
        name, doi, papers = CREDITED[product]
        cited = "; ".join(f"{who}, {where}" for who, where in papers)
        used.append(f"{name} from {_sector_runs(sectors)} (doi:{doi}; {cited})")
    tic = "; ".join(f"{who}, {where}" for who, where in TIC_PAPERS)
    text = [f"This {what} {TESS_CREDIT}"]
    if "QLP" in trained:
        text.append(QLP_CREDIT)
    text.append(
        f"The predictions were trained on {_words(used)}, with stellar parameters from the TESS Input Catalog v8.2 "
        f"({tic})."
    )
    text.append(f"Reuse of this {what} should carry these acknowledgements and citations.")
    return " ".join(text)


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
    timestamps, each review finding's claim quoted as the dossier quotes it (decision 0037), the model that wrote the
    review and its date, and RAVEN's period where the record lists one RAVEN row on the star."""
    checks = json.loads((record / "checks.json").read_text())
    eph = checks["ephemeris"]
    raven = [r for r in checks["catalogued"]["rows"] if r["source"] == "RAVEN"]
    dropped = checks["dropped_suspect"]
    found = {
        "signal": checks["signal"]["name"],
        "tic": str(checks["tic"]),
        "search_period": _number(eph["period"], ".6f"),
        "search_t0": _number(eph["t0"], ".4f"),
        "search_duration_h": _hours(eph["duration"]),
        "suspect": (
            f"Its vetted light curve leaves out {_sectors_words(dropped)}, flagged for suspect timestamps."
            if dropped
            else "Its vetted light curve leaves out no sector for suspect timestamps."
        ),
        "raven_period": _number(raven[0]["period"], ".3f") if len(raven) == 1 else None,
    }
    review = record / "review.json"
    if review.is_file():
        reviewed = calls.load_review(review)
        found |= {f"review_{f['id']}": _scrub(f["claim"]) for f in reviewed["findings"]}
        found |= {"review_model": reviewed["model"], "review_date": str(reviewed["date"])}
    return _filled(found)


def fact_values(facts: dict) -> dict[str, str]:
    """Each fact's value and its own read date (`fact_<key>`, `fact_<key>_read`), and every source with the date it was
    read: each sentence names the dates of the facts it states, so facts read on different days render."""
    sources = dict.fromkeys(f"- {fact['source']} (read {fact['read']})" for fact in facts.values())
    return (
        {f"fact_{key}": str(fact["value"]) for key, fact in facts.items()}
        | {f"fact_{key}_read": str(fact["read"]) for key, fact in facts.items()}
        | {"fact_sources": "\n".join(sources)}
    )


def _read_on(facts: dict, keys: tuple[str, ...]) -> str | None:
    """The dates the facts `keys` were read, one when they share it; None when one is missing, so its placeholder
    raises."""
    if not all(key in facts for key in keys):
        return None
    return _words(sorted({str(facts[key]["read"]) for key in keys}))


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


def _training(prediction: dict) -> str:
    """How many seasons train the prediction, how many of them hold a transit, and how many the test needs."""
    n = len(prediction["training_seasons"])
    held = sum(s["holds_transits"] for s in prediction["training_seasons"])
    if held == n:
        holding = "Both seasons hold" if n == 2 else f"All {n} seasons hold"
    else:
        holding = f"{held} of them {'holds' if held == 1 else 'hold'}"
    return (
        f"The prediction is trained on the {n} seasons of its vetted light curve.\n{holding} a transit in their "
        f"data, and the test needs at least {prediction['min_training_seasons']}."
    )


def _left_out(prediction: dict, lock_start: dt.date) -> str:
    """The sentences naming the sectors left out before the lock, and those of them still in the new season."""
    left = [s["sector"] for s in prediction["left_out"]]
    if not left:
        return ""
    one = len(left) == 1
    text = (
        f"\n{_sectors_words(left)} {'is' if one else 'are'} left out because {'it starts' if one else 'they start'} "
        f"before the lock on {lock_start}."
    )
    inside = [s["sector"] for s in prediction["left_out"] if s["in_season"]]
    if not inside:
        return text
    one = len(inside) == 1
    subject = ("It" if one else "They") if inside == left else _sectors_words(inside)
    return text + (
        f"\n{subject} still {'falls' if one else 'fall'} in the new season, so the test counts "
        f"{'its' if one else 'their'} cadences, though this package lists no transit in {'it' if one else 'them'}."
    )


def _offset(offsets: list[float]) -> str | None:
    """How much later or earlier than the refit's times the windows' mid-times run, in words."""
    if not all(math.isfinite(v) for v in offsets):
        return None
    low, high = min(offsets), max(offsets)
    if low >= 0:
        return f"{_span([low, high], '.0f')} min later than"
    if high <= 0:
        return f"{_span([-high, -low], '.0f')} min earlier than"
    return f"from {_number(-low, '.0f')} min earlier to {_number(high, '.0f')} min later than"


def _wide(windows: list[dict], period: float, sigmas: list[float]) -> str:
    """The sentence a signal's section adds when its observers' widest window, at the largest sigma `[predict]`
    reports, reaches half its refit period either side, and so spans a whole orbit; otherwise nothing."""
    sigma = max(sigmas)
    widest = max(w["half_width_minutes"][f"{sigma:g}"] for w in windows)
    orbit = period * MINUTES_PER_DAY
    if widest < 0.5 * orbit:
        return ""
    found = {
        "sigma": f"{sigma:g}",
        "widest": _number(widest, ".0f"),
        "orbit": _number(orbit, ".0f"),
    }
    return WIDE.substitute(_filled(found))


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
    testable = _either(prediction["testable_with"])
    found = record_values(record) | fact_values(facts)
    found |= _filled(
        {
            "training": _training(prediction),
            "seasons": _seasons_table(prediction),
            "period": _number(refit["period"], ".6f"),
            "t0": _number(refit["t0"], ".4f"),
            "duration_h": _hours(refit["duration"]),
            "core_minutes": _number(prediction["core_half_width_days"] * MINUTES_PER_DAY, ".0f"),
            "references": _references_table(prediction),
            "n_transits": str(len(prediction["transits"])),
            "kept": _sectors_words(kept),
            "left_out": _left_out(prediction, lock_start),
            "testable": (
                f"{testable} data can test the new season."
                if testable
                else "No product's data can test the new season."
            ),
            "n_windows": str(len(windows)),
            "fit_family": crit_vet["families"]["fit"].upper(),
            "sd": _span(sd, ".0f"),
            "offset": _offset(offsets),
            "wide": _wide(windows, refit["period"], crit_vet["predict"]["sigma"]),
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
            "families": " ".join(
                f"The {name.upper()} family holds {_words([PRODUCTS[p] for p in members])} light curves."
                for name, members in crit_vet["families"].items()
                if isinstance(members, list)
            ),
            "season_gap_days": f"{cfg['season_gap_days']:g}",
            "min_training_seasons": str(cfg["min_training_seasons"]),
            "min_points": str(cfg["min_points"]),
            "min_expected_snr": f"{cfg['min_expected_snr']:g}",
            "min_sigma": f"{cfg['min_sigma']:g}",
            "max_depth_tension": f"{cfg['max_depth_tension']:g}",
            "routes": _routes_table(predictions),
            # Said only when some training-depth table shows a family with "none".
            "no_cadences": (
                NO_CADENCES
                if any(
                    ref["ref_n"] == 0
                    for p in predictions.values()
                    for ref in p["reference"]["families"].values()
                )
                else ""
            ),
            "n_need_2min": str(len(need)),
            # The sentence assumes some signal needs 2-min data, as M4's do; with none its placeholder raises.
            "need_2min": _words(need) or None,
            "archives_read": _read_on(facts, ("tess_spoc_last_sector", "qlp_last_sector")),
            "lists_read": _read_on(facts, ("two_minute_lists", "off_two_minute_lists")),
            "zenodo_read": _read_on(facts, ZENODO_FACTS),
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
            "criteria": "\n".join(
                f"  - `{c['file']}`, sha256 {c['sha256']}" for c in provenance["criteria"]
            ),
            "catalogs": provenance["catalogs"],
            "known_sha256": inputs["known"]["sha256"],
            "manifest_sha256": inputs["catalog_manifest"]["sha256"],
            "sectors_sha256": inputs["tess_sectors"]["sha256"],
            "facts_sha256": inputs["facts"]["sha256"],
            "hashes": _hashes_table(provenance, predictions),
            "prediction_columns": _columns(PREDICTION_COLUMNS),
            "window_columns": _columns(_window_columns(crit_vet)),
            "credits": textwrap.fill(
                acknowledgements(trained_products(predictions, records), "package"),
                120,
                break_on_hyphens=False,
                break_long_words=False,
            ),
        }
    )
    return README.substitute(found)


def zenodo(
    provenance: dict,
    predictions: dict[str, dict],
    facts: dict,
    core_fraction: float,
    trained: dict[str, list[int]],
) -> str:
    """The Zenodo deposit form's text for a package: its title, resource type, description, keywords and licence.
    `core_fraction` is the test's, as the package's references.json holds it, and `trained` the products and sectors
    it was trained on (`trained_products`)."""
    kept = _kept_sectors(predictions)
    # A signal's note is where the README quotes its review.
    quoted = [name for name in predictions if name in NOTES]
    reviewed = (
        f", and the adversarial review of {_words(quoted)} that the README quotes was written by an AI model"
        if quoted
        else ""
    )
    found = fact_values(facts) | {
        "zenodo_read": _read_on(facts, ZENODO_FACTS),
        "reviewed": reviewed,
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
        "core_percent": f"{core_fraction * 100:g}",
        "credits": acknowledgements(trained, "dataset"),
    }
    description = DESCRIPTION.substitute(_filled(found))
    # Zenodo's description editor keeps line breaks, so each paragraph is pasted as one line.
    description = "\n\n".join(" ".join(p.split()) for p in description.split("\n\n"))
    return ZENODO.substitute(_filled(found | {"description": description}))


def _deposit_by(lock_start: dt.date, facts: dict) -> str:
    """The last day to deposit so that the files are fixed by `lock_start`. Zenodo lets the owner open an edit of a
    record's files within `zenodo_edit_days` of publishing and publish it within `zenodo_edit_publish_days`, so the
    files can change until the later of the two. A facts file without `zenodo_edit_publish_days` raises a KeyError
    that names it."""
    days = facts["zenodo_edit_publish_days"]["value"]
    return (lock_start - dt.timedelta(days=days)).isoformat()


def _ddt_ask(need: list[str], predictions: dict[str, dict], facts: dict) -> str:
    """The DDT proposal (decision 0039) of each signal only 2-min data can test, in the state its `ddt_<tic>` fact
    gives, which the maintainer's decision sets; a sent proposal is a request, which the TESS office decides."""
    states = {
        n: facts[f"ddt_{predictions[n]['tic']}"]
        for n in need
        if f"ddt_{predictions[n]['tic']}" in facts
    }
    rest = [n for n in need if n not in states]
    if not states:
        return "No DDT proposal asks for 2-min data on any of them, so no 2-min data are in sight for them."

    def stated(state: dict) -> str:
        # The state ends a sentence ("sent to the TESS DDT program on <date>", "not sent"). One that already names the
        # day it was recorded says it once; one that doesn't names that day, as each fact's sentence does.
        read = str(state["read"])
        return state["value"] if read in state["value"] else f"{state['value']} (as of {read})"

    texts = [
        f"For {n}, a Director's Discretionary Time (DDT) proposal asking for 2-min data on its star was\n"
        f"{stated(state)}.\n"
        f"The proposal is in tess-hunt's repository under `results/ddt/{n}/`."
        for n, state in states.items()
    ]
    texts.append("A sent proposal is a request, which the TESS office may or may not grant.")
    if rest:
        texts.append(f"For {_words(rest)}, no 2-min data are in sight.")
    return "\n".join(texts)


def _columns(names: list[str]) -> str:
    """A CSV's column names as the README's Files list shows them, wrapped under their item."""
    return textwrap.fill(
        ", ".join(f"`{c}`" for c in names),
        118,
        initial_indent="  ",
        subsequent_indent="  ",
        break_on_hyphens=False,
        break_long_words=False,
    )


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
    found = {"zenodo_read": _read_on(facts, ZENODO_FACTS), "packages": table}
    return INDEX.substitute(fact_values(facts) | _filled(found))


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


def deposit_form(run: Path) -> str:
    """The Zenodo deposit form's text for the package a finished predictions run made, from the run's own files and
    the published records it read."""
    made = json.loads((run / "provenance.json").read_text())
    if made.get("stage") != "predictions":
        raise SystemExit(f"run {run.name} is not a predictions run")
    if made.get("ended_at") is None:
        raise SystemExit(f"run {run.name} has not finished")
    rows = pd.read_csv(run / "predictions.csv")
    predictions = {
        name: {"tic": int(group["tic"].iloc[0]), "transits": group[["sector"]].to_dict("records")}
        for name, group in rows.groupby("signal", sort=False)
    }
    facts = tomllib.loads((run / "facts.toml").read_text())
    references = json.loads((run / "references.json").read_text())
    records = {name: _records() / name for name in references["signals"]}
    # The credits name each training sector's product from the records the run read.
    for name, record in records.items():
        if sha256_file(record / "checks.json") != made["inputs"][f"checks_{name}"]["sha256"]:
            raise SystemExit(
                f"results/vetting/{name}/checks.json is not the record run {run.name} read"
            )
    trained = trained_products(references["signals"], records)
    return zenodo(made, predictions, facts, references["test"]["core_fraction"], trained)


def cmd_zenodo(args) -> int:
    run = runs_dir() / args.run
    if not (run / "provenance.json").is_file():
        raise SystemExit(f"no run {args.run} under the data directory")
    print(deposit_form(run), end="")
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
    z = modes.add_parser(
        "zenodo", help="print the Zenodo deposit form's text for a finished predictions run"
    )
    z.add_argument("--run", required=True, help="the run id")
    z.set_defaults(func=cmd_zenodo)
