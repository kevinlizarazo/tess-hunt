# Transit predictions for 6 held tess-hunt signals in TESS Sectors 112 to 114

tess-hunt is an independent search for transiting planets in public TESS light curves. Each signal is named by its
star's TIC number and its rank on that star. tess-hunt's vetting neither passed nor rejected these 6
signals, because the public data cannot decide them, and holds them for new data:
103312990-1, 241522065-1, 296819076-1, 399023421-1, 423100454-1 and 438857197-1.
Each is a candidate signal, not a planet. TESS observes their stars again from Sector 110 on. This package
predicts their transits in Sectors 112 to 114, which start after its files are fixed (see The lock).

The package fixes the prediction for each signal's new season, and the test that will judge it, before TESS observes
those sectors. It was made on 2026-10-28 (UTC). tess-hunt's code computed every number in it from the signals'
published vetting records, the light curves they were vetted on and the other files listed under Provenance.
tess-hunt's code and this text were written with LLM assistance.

## What is judged

tess-hunt's vetting criteria, vet-v3, include a held-out season check. It refits a signal's period and epoch on every
season but one, searching near the period and epoch tess-hunt's search found, and measures the left-out season's depth
only in the central 50% of each transit the refit predicts (the transit's core).

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

The new season is judged with the held-out check's measurement and thresholds, read from `criteria/vet-v3.toml` (listed
with its sha256 under Provenance), using the published prediction and training depths in place of a fresh refit:

- Seasons are split at gaps of more than 60 days.
- The new season is tested only if at least 2 training seasons hold a transit in their data.
- Its depth is measured in the predicted cores. With fewer than 5 cadences there, it is untested.
- If a product family present in its cores has fewer than 5 training cadences in the cores, it is untested.
- Its expected depth is each family's training depth, weighted as that family's cadences weight the season's depth. If
  the expected depth is less than 4 times the season's depth error, the season's data are too noisy
  to show the dip, and it is untested.
- Otherwise the season is replicated when its depth is at least 2 times its error and, in every family with
  at least 5 cadences in the cores both in the season and in training, within 3 sigma of
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
The PDCSAP family holds SPOC 2-min and TESS-SPOC light curves. The QLP family holds QLP light curves.
The new season can therefore be tested only if every family in its cores also has training data. tess-hunt takes one
product per sector, so a season that includes a sector from a family without training data is untested as a whole.

| Signal | Training families | Data that can test the new season |
|---|---|---|
| 103312990-1 | PDCSAP: 9, 10 and 36; QLP: 90 | SPOC 2-min, TESS-SPOC or QLP |
| 241522065-1 | PDCSAP: 38, 64 and 65 | SPOC 2-min or TESS-SPOC |
| 296819076-1 | PDCSAP: 11 and 12; QLP: 65 | SPOC 2-min, TESS-SPOC or QLP |
| 399023421-1 | PDCSAP: 11, 37, 38 and 64 | SPOC 2-min or TESS-SPOC |
| 423100454-1 | PDCSAP: 12, 39 and 65 | SPOC 2-min or TESS-SPOC |
| 438857197-1 | PDCSAP: 11, 38 and 64 | SPOC 2-min or TESS-SPOC |

TESS-SPOC's full-frame light curves stop at Sector 85, and MAST holds QLP's only through a
partial Sector 105 (as read on 2026-10-27). For 4 of the 6 signals
(241522065-1, 399023421-1, 423100454-1 and 438857197-1) the table allows only SPOC 2-min or TESS-SPOC data,
so only SPOC 2-min data can test their predictions.

As read on 2026-10-27, none of the 6 stars is on
the final 2-min and 20-s target lists for Sector 110 or the Guest Investigator priority lists for Sectors 111 to 114.
A list can still change before its sector.

For 241522065-1, a Director's Discretionary Time (DDT) proposal asking for 2-min data on its star was
sent to the TESS DDT program on 2026-10-28.
The proposal is in tess-hunt's repository under `results/ddt/241522065-1/`.
A sent proposal is a request, which the TESS office may or may not grant.
For 399023421-1, 423100454-1 and 438857197-1, no 2-min data are in sight.

All 4 are predicted anyway, since anyone can check a public prediction by eye. No other product, tess-hunt's
own full-frame photometry included, can test a prediction unless a decision record in tess-hunt's repository says how
the test applies to it, made before that product is run on these stars.

## When it is judged

tess-hunt vets a held signal again when new data arrive (a re-vet). Each signal is judged once, at the first re-vet
whose light curve covers every predicted sector with data the test can use. Until then, and only before the judging
date, a re-vet reports the result as pending.

The judging date is 2027-12-31. It applies to the date a re-vet's light curve was downloaded, which tess-hunt
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

Zenodo lets a record's owner open an edit of its files within 30 days of publishing, and the edit
must be published within 45 days of publishing (as read on 2026-10-28). A record's files
are therefore fixed 45 days after it is published. This package was deposited by
2026-11-05, so its files are fixed by 2026-12-20, and it predicts only sectors that start on or after that date. A
sector in a signal's windows that starts earlier is left out, and the signal's section names it.

Sector dates are from tess.mit.edu's sector pages (read 2026-10-16), as tess-hunt's
`benchmarks/tess_sectors.csv` holds them.

## 103312990-1 (TIC 103312990)

The search found the signal at period 7.523205 d, t0 BTJD 1545.9350 and duration 2.00 h.
The refit starts from this ephemeris.
Its vetted light curve leaves out Sector 99, flagged for suspect timestamps.

The prediction is trained on the 3 seasons of its vetted light curve.
All 3 seasons hold a transit in their data, and the test needs at least 2.

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 9 and 10 | 2019 | 20 | yes |
| 1 | 36 | 2021 | 36 | yes |
| 2 | 90 | 2025 | 139 | yes |

The refit gives period 7.523135 d, t0 BTJD 1545.9444 and duration 2.55 h. Each predicted transit's core runs
38 min either side of its mid-time. The training depths in the cores are:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 9, 10 and 36 | 343 | 51 | 36 | 4576 |
| QLP | 90 | 419 | 83 | 89 | 10283 |
| All families | 9, 10, 36 and 90 | 364 | 44 | 125 | 14859 |

The package predicts 7 transits in Sectors 112 and 113.
Sectors 110 and 111 are left out because they start before the lock on 2026-12-20.
They still fall in the new season, so the test counts their cadences, though this package lists no transit in them.
SPOC 2-min, TESS-SPOC or QLP data can test the new season.

For observers, the vetting record gives 7 transit windows in Sectors 112 and 113, from the density-prior fit
to the PDCSAP family alone. Their mid-times have standard deviations of 64 to 65 min
and run 18 min later than the refit's nearest predicted mid-times.

## 241522065-1 (TIC 241522065)

The search found the signal at period 17.436664 d, t0 BTJD 2340.4470 and duration 3.00 h.
The refit starts from this ephemeris.
Its vetted light curve leaves out Sectors 99, 101 and 102, flagged for suspect timestamps.

The prediction is trained on the 2 seasons of its vetted light curve.
Both seasons hold a transit in their data, and the test needs at least 2.

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 38 | 2021 | 36 | yes |
| 1 | 64 and 65 | 2023 | 143 | yes |

The refit gives period 17.436807 d, t0 BTJD 2340.4302 and duration 3.82 h. Each predicted transit's core runs
57 min either side of its mid-time. The training depths in the cores are:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 38, 64 and 65 | 464 | 39 | 126 | 25431 |
| All families | 38, 64 and 65 | 464 | 39 | 126 | 25431 |

The package predicts 5 transits in Sectors 112, 113 and 114.
SPOC 2-min or TESS-SPOC data can test the new season.

For observers, the vetting record gives 5 transit windows in Sectors 112, 113 and 114, from the density-prior fit
to the PDCSAP family alone. Their mid-times have standard deviations of 13 to 14 min
and run 12 to 13 min earlier than the refit's nearest predicted mid-times.

## 296819076-1 (TIC 296819076)

The search found the signal at period 2.279660 d, t0 BTJD 1601.0147 and duration 2.00 h.
The refit starts from this ephemeris.
Its vetted light curve leaves out Sectors 99, 100, 101 and 102, flagged for suspect timestamps.

The prediction is trained on the 2 seasons of its vetted light curve.
Both seasons hold a transit in their data, and the test needs at least 2.

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 11 and 12 | 2019 | 65 | yes |
| 1 | 65 | 2023 | 300 | yes |

The refit gives period 2.279710 d, t0 BTJD 1601.0220 and duration 2.55 h. Each predicted transit's core runs
38 min either side of its mid-time. The training depths in the cores are:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 11 and 12 | 629 | 77 | 39 | 1812 |
| QLP | 65 | 470 | 166 | 174 | 9354 |
| All families | 11, 12 and 65 | 601 | 70 | 213 | 11166 |

The package predicts 13 transits in Sector 114.
SPOC 2-min, TESS-SPOC or QLP data can test the new season.

For observers, the vetting record gives 12 transit windows in Sector 114, from the density-prior fit
to the PDCSAP family alone. Their mid-times have standard deviations of 1342 to 1354 min
and run 1081 to 1091 min later than the refit's nearest predicted mid-times.
These windows are too wide to place a transit: at 3 sigma they reach up to 4061 min either side of their
mid-times, against a refit period of 3283 min. Use the refit's times in `predictions.csv` instead.

## 399023421-1 (TIC 399023421)

The search found the signal at period 3.926959 d, t0 BTJD 1600.8528 and duration 3.00 h.
The refit starts from this ephemeris.
Its vetted light curve leaves out Sectors 99, 100, 101 and 102, flagged for suspect timestamps.

The prediction is trained on the 3 seasons of its vetted light curve.
All 3 seasons hold a transit in their data, and the test needs at least 2.

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 11 | 2019 | 30 | yes |
| 1 | 37 and 38 | 2021 | 198 | yes |
| 2 | 64 | 2023 | 375 | yes |

The refit gives period 3.926888 d, t0 BTJD 1600.8794 and duration 2.92 h. Each predicted transit's core runs
44 min either side of its mid-time. The training depths in the cores are:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 11, 37, 38 and 64 | 363 | 43 | 295 | 17954 |
| All families | 11, 37, 38 and 64 | 363 | 43 | 295 | 17954 |

The package predicts 21 transits in Sectors 112, 113 and 114.
SPOC 2-min or TESS-SPOC data can test the new season.

For observers, the vetting record gives 21 transit windows in Sectors 112, 113 and 114, from the density-prior fit
to the PDCSAP family alone. Their mid-times have standard deviations of 30 to 31 min
and run 40 to 41 min earlier than the refit's nearest predicted mid-times.

tess-hunt's adversarial review of this signal was written by an AI model,
claude-opus-5-5, on 2026-10-21, updated 2026-10-22. Its finding F9, quoted word for word:

> The timing-suspect QLP sectors S99 to S102 show the transit at a consistent, diluted depth, but about 30 to 50 minutes later than the density-prior ephemeris predicts there, so the S112 to S114 windows may run early by about one of their standard deviations.

The refit leaves those QLP sectors out, as every check does, and is published as it stands. If the new season's
transits arrive late against its cores, the season can be missed, and a miss caused by drift counts as a miss.

RAVEN (Lafarga et al. 2026, MNRAS, https://doi.org/10.1093/mnras/stag512, arXiv:2603.22597)
lists a dip on the star at 9.825 d. The review's finding F4, quoted word for word:

> The RAVEN row on this star (9.825 d, 395 ppm) is most likely this signal at a 5:2 alias, not a second body: the three transits it shares with ours carry no extra depth and neither carry nor make our signal, its other epochs show about half its depth, and RAVEN publishes no row at our period, so our period is not catalogued but the star's dip is, and a CTOI should cite RAVEN.

## 423100454-1 (TIC 423100454)

The search found the signal at period 14.186255 d, t0 BTJD 1631.4629 and duration 4.50 h.
The refit starts from this ephemeris.
Its vetted light curve leaves out Sectors 102 and 103, flagged for suspect timestamps.

The prediction is trained on the 3 seasons of its vetted light curve.
All 3 seasons hold a transit in their data, and the test needs at least 2.

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 12 | 2019 | 267 | yes |
| 1 | 39 | 2021 | 54 | yes |
| 2 | 65 | 2023 | 162 | yes |

The refit gives period 14.186119 d, t0 BTJD 1631.4718 and duration 4.39 h. Each predicted transit's core runs
66 min either side of its mid-time. The training depths in the cores are:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 12, 39 and 65 | 582 | 43 | 236 | 32056 |
| All families | 12, 39 and 65 | 582 | 43 | 236 | 32056 |

The package predicts 2 transits in Sector 113.
SPOC 2-min or TESS-SPOC data can test the new season.

For observers, the vetting record gives 2 transit windows in Sector 113, from the density-prior fit
to the PDCSAP family alone. Their mid-times have standard deviations of 10 min
and run 11 min later than the refit's nearest predicted mid-times.

## 438857197-1 (TIC 438857197)

The search found the signal at period 3.659160 d, t0 BTJD 1603.5364 and duration 1.00 h.
The refit starts from this ephemeris.
Its vetted light curve leaves out Sectors 101 and 102, flagged for suspect timestamps.

The prediction is trained on the 3 seasons of its vetted light curve.
All 3 seasons hold a transit in their data, and the test needs at least 2.

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 11 | 2019 | 8 | yes |
| 1 | 38 | 2021 | 36 | yes |
| 2 | 64 | 2023 | 125 | yes |

The refit gives period 3.659171 d, t0 BTJD 1603.5359 and duration 0.97 h. Each predicted transit's core runs
15 min either side of its mid-time. The training depths in the cores are:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 11, 38 and 64 | 1032 | 85 | 82 | 15100 |
| All families | 11, 38 and 64 | 1032 | 85 | 82 | 15100 |

The package predicts 15 transits in Sectors 112 and 114.
SPOC 2-min or TESS-SPOC data can test the new season.

For observers, the vetting record gives 15 transit windows in Sectors 112 and 114, from the density-prior fit
to the PDCSAP family alone. Their mid-times have standard deviations of 11 min
and run 12 min earlier than the refit's nearest predicted mid-times.

## Provenance

- Code: tess-hunt commit 98bf4175cbaa320fe034cd473f83e0c72c0cc00f.
- This package: run 20261028T204003Z-predictions-98bf417-0ef5.
  Its `provenance.json` lists the run's inputs with their sha256 and its command line.
- Vetting records: from vetting run 20261020T174317Z-vetting-run-61b5944-2d70.
- Criteria:
  - `criteria/search-v2.toml`, sha256 16d5906d2ea2a9e685fe05ab02758254e358e41113e9517721368a54a978890d
  - `criteria/vet-v3.toml`, sha256 9b01a9067e0728ddc2eaded3e7cb2b4de98e4fb15c3353a5413706979ec1aec4
- Catalog snapshot read by the vetting run, 2026-10-17T142814Z:
  - `known.parquet`, sha256 8a87504a96e483e921aeb8fba567538e77c9b3acb66944d7121fc284c40495ed
  - `manifest.json`, sha256 f722fdd58328b01eabfc8e4fbc1fc576a3de934f0b97e836087086a577a6ba5d
- Sector dates: `benchmarks/tess_sectors.csv`, sha256
  2055f8a42c38bea916a78a58af778126b8d844386fe2217fa466589a5ae88092.
- Facts about archives, target lists, RAVEN's citation and the DDT proposal: `facts.toml`, sha256
  5acec57e1f66b2dc2e593deca22af711f33f297c055a5702caaf8e1b03678d90.

Each signal's published record, `results/vetting/<signal>/` in tess-hunt's repository, and the light curve its vetting
run read:

| Signal | Record | Light curve |
|---|---|---|
| 103312990-1 | `checks.json` a513d03f99c0aa8d42a2118a1eff7c5beecdc255304a244ad6a01e2b803332e9 | TIC 103312990: 955172c695e312119374aac16c67cf7a0649c1ce087b527b5b8de21c0d058398 |
| 241522065-1 | `checks.json` fbb69b34ebb0a4132b6f566812ab2a512eaed9bf762327317df4b0b5102b7c06 | TIC 241522065: 010beb2551a15c870c0dca8032e6fb7f951fbd6c602caae706d49977e4513362 |
| 296819076-1 | `checks.json` cd5b60f9ce9de318c2d7cece5d31f850068af6d5813a7f34798aace81e4cecf4 | TIC 296819076: 4bb3d64ea85517cc22bab6b7d11fc62e6f81ed3029f0a191b6c09974a005bb6b |
| 399023421-1 | `checks.json` 39d96c5d2dfc4d5c6cfa0683d4147faba664a479968f7ef1fd20b97004d59928 | TIC 399023421: 45aea53680b1f0d294ac53898ad27e692f320e14e61e7e29470c5cea839c98af |
| 423100454-1 | `checks.json` a28085c111c611893252bf81e382c3655c6a61dae554c6dc63c15b6915f2c8be | TIC 423100454: 7fb744d3030a0096b401f11b63fe27a5413acc1ed435a1288e761e5d50bff03f |
| 438857197-1 | `checks.json` a51cf18a913c2245ddffb8f1dceb2be60c2ff1d9acff95f1b6745861e4e69813 | TIC 438857197: 7d9651a8982fbed7c8bcd1ccaa8e7594eaaedfbee106d87a727649c827889e18 |

## Files

- `predictions.csv`: one row per predicted transit, with columns
  `signal`, `tic`, `sector`, `epoch`, `mid_btjd`, `mid_utc`, `period`, `t0`, `core_half_width_days`.
  `epoch` counts periods from the refit's t0, `mid_btjd` is BJD_TDB - 2457000, `mid_utc` is the mid-time in UTC as
  seen from Earth, and `period` and `t0` are the refit's, in days and BTJD.
- `references.json`: for each signal, the refit (`predicted`, with BLS's duration and depth), the core half-width, the
  training depths (`reference`, as fractions of the flux, pooled and by family), the training seasons and families,
  the products that can test it (`testable_with`) and the sectors left out; and the test's criteria values (`test`).
- `windows.csv`: the observers' windows, with columns
  `signal`, `tic`, `sector`, `epoch`, `mid_btjd`, `mid_utc`, `sd_minutes`, `half_width_1sigma_minutes`,
  `half_width_3sigma_minutes`, `duration_days`.
  `epoch` counts periods from the density-prior fit's t0.
- `facts.toml`: the facts this README states about archives, target lists, RAVEN's citation and the DDT proposal,
  each with its source and the date it was read.
- `provenance.json`: the run's commit, criteria, inputs with their sha256, and command line.

## Licence and sources

CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). It contains no Gaia data, so CC BY 4.0 covers all of it.
It is derived from TESS light curves (SPOC, TESS-SPOC and QLP, from MAST) and the TESS Input Catalog. The facts in
`facts.toml` come from:

- https://help.zenodo.org/docs/deposit/manage-files/ (read 2026-10-28)
- https://archive.stsci.edu/hlsp/tess-spoc (read 2026-10-27)
- https://archive.stsci.edu/hlsps/qlp/ (read 2026-10-27)
- https://tess.mit.edu/public/target_lists/target_lists.html (read 2026-10-27)
- results/ddt/241522065-1/proposal.md (read 2026-10-28)
- https://zenodo.org/records/19661443 (read 2026-10-27)
