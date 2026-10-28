# Predictions for 6 held tess-hunt signals in TESS Sectors 112 to 114

tess-hunt is an independent search for transiting planets in public TESS light curves. Its vetting held these
6 signals (103312990-1, 241522065-1, 296819076-1, 399023421-1, 423100454-1 and 438857197-1): not passed and not killed, because the public data can't decide them. Each is a
candidate signal, not a planet. TESS looks at their stars again from Sector 110 on; this package predicts
their transits in the sectors from 112 to 114, which start after its files lock (below).

This package fixes, before those sectors are observed, the prediction each signal's held-out season test will judge,
and the test itself. It was made on 2026-10-28 (UTC) by one run of `tess-hunt predictions run`, 20261028T162309Z-predictions-4b7423f-0aa5, from the signals'
published vetting records and the light curves their vetting run, 20261020T174317Z-vetting-run-61b5944-2d70, read. Every number in it comes from
those files, from that run, from the criteria file and the sector dates file that vetting run read, and from the
`facts.toml` beside this README; the text it quotes from a review says so where it begins.

## What is judged

vet-v3, tess-hunt's vetting criteria, has a held-out season check: it refits a signal's period and epoch on every
season but one, near the period and epoch tess-hunt's search found, and measures the left-out season's depth only in
the central 50% of each transit the refit predicts (its core). Each signal's vetted light curve is the one
vetting run 20261020T174317Z-vetting-run-61b5944-2d70 read for it, as its checks saw it: without the sectors flagged for suspect timestamps,
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

The new season is judged by vet-v3's `[holdout]` measurement and thresholds, read from `criteria/vet-v3.toml` (sha256
9b01a9067e0728ddc2eaded3e7cb2b4de98e4fb15c3353a5413706979ec1aec4), with the published prediction and training depths in place of a fresh refit:

- Seasons are split at gaps of more than 60 days.
- A season is tested only if at least 2 training seasons hold a transit in their data.
- Its depth is measured in the cores, and needs at least 5 cadences there.
- It is untestable if a product family in its cores has fewer than 5 training cadences in them. Otherwise
  its expected depth is each family's own training depth, weighted as its cadences weight the season's depth; if that
  is less than 4 times the season's depth error, the season is underpowered.
- It is replicated when its depth is at least 2 times its error and, in every family with 5
  cadences in the cores on both sides, within 3 sigma of the same family's training depth. Otherwise
  it is missed.

The result for each signal is the new season's status: replicated (`predicted`), missed (`missed`), or untested
(`underpowered`, `untestable`, `no_predicted_transit_in_data`, no light curve, or a light curve fetched on or after the
judging date below). On the unchanged vetted light curve
this is exactly what vet-v3's check computes for that season (tess-hunt's test `test_prediction_equals_holdout_refit`).
Judging with the published numbers keeps the result fixed if a later re-vet's training data change.

## Which data can test it

Depths are compared only within a product family (tess-hunt's decision 0023), so the new season is testable only if
every family in its cores is one with training data. tess-hunt takes one product per sector, so a season that mixes in
a sector of a family with no training data is untestable as a whole.

| Signal | Training families | Data that can test the new season |
|---|---|---|
| 103312990-1 | PDCSAP: 9, 10 and 36; QLP: 90 | SPOC 2-min, TESS-SPOC or QLP |
| 241522065-1 | PDCSAP: 38, 64 and 65 | SPOC 2-min or TESS-SPOC |
| 296819076-1 | PDCSAP: 11 and 12; QLP: 65 | SPOC 2-min, TESS-SPOC or QLP |
| 399023421-1 | PDCSAP: 11, 37, 38 and 64 | SPOC 2-min or TESS-SPOC |
| 423100454-1 | PDCSAP: 12, 39 and 65 | SPOC 2-min or TESS-SPOC |
| 438857197-1 | PDCSAP: 11, 38 and 64 | SPOC 2-min or TESS-SPOC |

A family with no training cadences in the cores shows none for its depth and error in its signal's section, and can't
test the new season.

TESS-SPOC's full-frame light curves stop at Sector 85, and MAST holds QLP's only through a
partial Sector 105 (as read on 2026-10-27). So for 4 of the 6 signals
(241522065-1, 399023421-1, 423100454-1 and 438857197-1) only SPOC 2-min data can test the prediction. As read on 2026-10-27, none of the 6 stars is on
the final 2-min and 20-s target lists for Sector 110 or the Guest Investigator priority lists for Sectors 111 to 114, and a list can still change before its sector. For 241522065-1, tess-hunt has a DDT proposal asking for 2-min data (`results/ddt/241522065-1/` in its repository); its state, as `facts.toml` records it on 2026-10-28: sent to the TESS DDT program on 2026-10-28. A sent proposal is a request, which the TESS office may or may not take. For 399023421-1, 423100454-1 and 438857197-1 no 2-min data are in sight. Each of the 4 is predicted
anyway: anyone can check a public prediction by eye. Any other product, the project's own full-frame photometry
included, needs a decision record saying how the test applies to it, made before it is run on these stars.

## When it is judged

Once for each signal, on the complete season: at the first re-vet whose light curve covers every predicted sector for
that star with data the test can use. A re-vet judged as of a day before 2027-12-31, on a light curve that lacks a
predicted sector, may run but reports the result as pending. The judging date, 2027-12-31, applies to when a re-vet's
light curve was fetched, since that is what the code can see, not when the data went public or when the re-vet runs.
A light curve fetched before it that covers every predicted sector is judged whenever the re-vet runs; one fetched on
or after it completes no season; and a season that still lacks a predicted sector in a re-vet judged as of that date
or later stays untested. A result once judged stands for every later re-vet. A season runs from gap to gap, so a
sector left out of the prediction (below) can still fall in the new season; its cadences stay in it, as vet-v3 counts
them, and each signal's section says which.

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

Zenodo lets a record's owner edit its files for 30 days after publishing (as read on
2026-10-27).
Deposited by 2026-11-20, this package's files are locked by 2026-12-20, so only sectors starting on or after
2026-12-20 are predicted. Each earlier sector in a record's windows is left out, and its signal's section names it.
Sector dates come from tess-hunt's `benchmarks/tess_sectors.csv` (tess.mit.edu's sector pages, read 2026-10-16).

## 103312990-1 (TIC 103312990)

The search's ephemeris, which the refit starts from: period 7.523205 d, t0 BTJD 1545.9350, duration
2.00 h. Sectors left out of its vetted light curve for suspect timestamps: 99.

The 3 seasons of its vetted light curve train the prediction, and 3 of them hold a transit in
their data, where the test needs 2:

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 9 and 10 | 2019 | 20 | yes |
| 1 | 36 | 2021 | 36 | yes |
| 2 | 90 | 2025 | 139 | yes |

The refit: period 7.523135 d, t0 BTJD 1545.9444, duration 2.55 h. Each predicted transit's core runs 38 min
either side of its mid-time. The training depths in the cores:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 9, 10 and 36 | 343 | 51 | 36 | 4576 |
| QLP | 90 | 419 | 83 | 89 | 10283 |
| All families | 9, 10, 36 and 90 | 364 | 44 | 125 | 14859 |

Predicted: 7 transits in Sectors 112 and 113. Left out: Sectors 110 and 111, which start before the lock on 2026-12-20. The new season still holds Sectors 110 and 111: the test counts their cadences as part of it, though this package lists no transit in them. Data that can test the new season:
SPOC 2-min, TESS-SPOC or QLP.

Observers' windows: 7 in Sectors 112 and 113, from the density-prior fit to the PDCSAP family alone, with mid-time
sd 64 to 65 min. Each window's mid-time less the refit's nearest predicted mid-time: +18 min.

## 241522065-1 (TIC 241522065)

The search's ephemeris, which the refit starts from: period 17.436664 d, t0 BTJD 2340.4470, duration
3.00 h. Sectors left out of its vetted light curve for suspect timestamps: 99, 101 and 102.

The 2 seasons of its vetted light curve train the prediction, and 2 of them hold a transit in
their data, where the test needs 2:

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 38 | 2021 | 36 | yes |
| 1 | 64 and 65 | 2023 | 143 | yes |

The refit: period 17.436807 d, t0 BTJD 2340.4302, duration 3.82 h. Each predicted transit's core runs 57 min
either side of its mid-time. The training depths in the cores:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 38, 64 and 65 | 464 | 39 | 126 | 25431 |
| All families | 38, 64 and 65 | 464 | 39 | 126 | 25431 |

Predicted: 5 transits in Sectors 112, 113 and 114. Left out: none. Data that can test the new season:
SPOC 2-min or TESS-SPOC.

Observers' windows: 5 in Sectors 112, 113 and 114, from the density-prior fit to the PDCSAP family alone, with mid-time
sd 13 to 14 min. Each window's mid-time less the refit's nearest predicted mid-time: -13 to -12 min.

## 296819076-1 (TIC 296819076)

The search's ephemeris, which the refit starts from: period 2.279660 d, t0 BTJD 1601.0147, duration
2.00 h. Sectors left out of its vetted light curve for suspect timestamps: 99, 100, 101 and 102.

The 2 seasons of its vetted light curve train the prediction, and 2 of them hold a transit in
their data, where the test needs 2:

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 11 and 12 | 2019 | 65 | yes |
| 1 | 65 | 2023 | 300 | yes |

The refit: period 2.279710 d, t0 BTJD 1601.0220, duration 2.55 h. Each predicted transit's core runs 38 min
either side of its mid-time. The training depths in the cores:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 11 and 12 | 629 | 77 | 39 | 1812 |
| QLP | 65 | 470 | 166 | 174 | 9354 |
| All families | 11, 12 and 65 | 601 | 70 | 213 | 11166 |

Predicted: 13 transits in Sector 114. Left out: none. Data that can test the new season:
SPOC 2-min, TESS-SPOC or QLP.

Observers' windows: 12 in Sector 114, from the density-prior fit to the PDCSAP family alone, with mid-time
sd 1342 to 1354 min. Each window's mid-time less the refit's nearest predicted mid-time: +1081 to +1091 min.

## 399023421-1 (TIC 399023421)

The search's ephemeris, which the refit starts from: period 3.926959 d, t0 BTJD 1600.8528, duration
3.00 h. Sectors left out of its vetted light curve for suspect timestamps: 99, 100, 101 and 102.

The 3 seasons of its vetted light curve train the prediction, and 3 of them hold a transit in
their data, where the test needs 2:

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 11 | 2019 | 30 | yes |
| 1 | 37 and 38 | 2021 | 198 | yes |
| 2 | 64 | 2023 | 375 | yes |

The refit: period 3.926888 d, t0 BTJD 1600.8794, duration 2.92 h. Each predicted transit's core runs 44 min
either side of its mid-time. The training depths in the cores:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 11, 37, 38 and 64 | 363 | 43 | 295 | 17954 |
| All families | 11, 37, 38 and 64 | 363 | 43 | 295 | 17954 |

Predicted: 21 transits in Sectors 112, 113 and 114. Left out: none. Data that can test the new season:
SPOC 2-min or TESS-SPOC.

Observers' windows: 21 in Sectors 112, 113 and 114, from the density-prior fit to the PDCSAP family alone, with mid-time
sd 30 to 31 min. Each window's mid-time less the refit's nearest predicted mid-time: -41 to -40 min.

tess-hunt's adversarial review of this signal found its timing-suspect QLP transits arriving later than the observers'
windows predict. The review's finding F9, quoted word for word: "The timing-suspect QLP sectors S99 to S102 show the transit at a consistent, diluted depth, but about 30 to 50 minutes later than the density-prior ephemeris predicts there, so the S112 to S114 windows may run early by about one of their standard deviations." The refit leaves those QLP sectors out,
as every check does. It stands as published: if the new season's transits arrive late against its cores, the season
can be missed, and a miss on drift counts as a miss.

RAVEN (Lafarga et al. 2026, MNRAS, https://doi.org/10.1093/mnras/stag512, arXiv:2603.22597) lists a dip on the star at 9.825 d. The review's
finding F4, quoted word for word: "The RAVEN row on this star (9.825 d, 395 ppm) is most likely this signal at a 5:2 alias, not a second body: the three transits it shares with ours carry no extra depth and neither carry nor make our signal, its other epochs show about half its depth, and RAVEN publishes no row at our period, so our period is not catalogued but the star's dip is, and a CTOI should cite RAVEN."

## 423100454-1 (TIC 423100454)

The search's ephemeris, which the refit starts from: period 14.186255 d, t0 BTJD 1631.4629, duration
4.50 h. Sectors left out of its vetted light curve for suspect timestamps: 102 and 103.

The 3 seasons of its vetted light curve train the prediction, and 3 of them hold a transit in
their data, where the test needs 2:

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 12 | 2019 | 267 | yes |
| 1 | 39 | 2021 | 54 | yes |
| 2 | 65 | 2023 | 162 | yes |

The refit: period 14.186119 d, t0 BTJD 1631.4718, duration 4.39 h. Each predicted transit's core runs 66 min
either side of its mid-time. The training depths in the cores:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 12, 39 and 65 | 582 | 43 | 236 | 32056 |
| All families | 12, 39 and 65 | 582 | 43 | 236 | 32056 |

Predicted: 2 transits in Sector 113. Left out: none. Data that can test the new season:
SPOC 2-min or TESS-SPOC.

Observers' windows: 2 in Sector 113, from the density-prior fit to the PDCSAP family alone, with mid-time
sd 10 min. Each window's mid-time less the refit's nearest predicted mid-time: +11 min.

## 438857197-1 (TIC 438857197)

The search's ephemeris, which the refit starts from: period 3.659160 d, t0 BTJD 1603.5364, duration
1.00 h. Sectors left out of its vetted light curve for suspect timestamps: 101 and 102.

The 3 seasons of its vetted light curve train the prediction, and 3 of them hold a transit in
their data, where the test needs 2:

| Season | Sectors | Year | Cadences in transit | Holds a transit |
|---|---|---|---|---|
| 0 | 11 | 2019 | 8 | yes |
| 1 | 38 | 2021 | 36 | yes |
| 2 | 64 | 2023 | 125 | yes |

The refit: period 3.659171 d, t0 BTJD 1603.5359, duration 0.97 h. Each predicted transit's core runs 15 min
either side of its mid-time. The training depths in the cores:

| Family | Training sectors | Depth (ppm) | Error (ppm) | Cadences in the cores | Training cadences |
|---|---|---|---|---|---|
| PDCSAP | 11, 38 and 64 | 1032 | 85 | 82 | 15100 |
| All families | 11, 38 and 64 | 1032 | 85 | 82 | 15100 |

Predicted: 15 transits in Sectors 112 and 114. Left out: none. Data that can test the new season:
SPOC 2-min or TESS-SPOC.

Observers' windows: 15 in Sectors 112 and 114, from the density-prior fit to the PDCSAP family alone, with mid-time
sd 11 min. Each window's mid-time less the refit's nearest predicted mid-time: -12 min.

## Provenance

- Code: tess-hunt commit 4b7423f3381b1ae4a2f162f23dad342146d1285f.
- Criteria: `criteria/search-v2.toml` sha256 16d5906d2ea2a9e685fe05ab02758254e358e41113e9517721368a54a978890d; `criteria/vet-v3.toml` sha256 9b01a9067e0728ddc2eaded3e7cb2b4de98e4fb15c3353a5413706979ec1aec4.
- The vetting run the records come from: 20261020T174317Z-vetting-run-61b5944-2d70. This package's run: 20261028T162309Z-predictions-4b7423f-0aa5; its `provenance.json` is here.
- The catalog snapshot that vetting run read, 2026-10-17T142814Z: `known.parquet` sha256 8a87504a96e483e921aeb8fba567538e77c9b3acb66944d7121fc284c40495ed, `manifest.json` sha256
  f722fdd58328b01eabfc8e4fbc1fc576a3de934f0b97e836087086a577a6ba5d.
- Sector dates: `benchmarks/tess_sectors.csv`, sha256 2055f8a42c38bea916a78a58af778126b8d844386fe2217fa466589a5ae88092.
- Facts about archives and the DDT proposal: `facts.toml`, sha256 0dff75d2a7c6908b2e47b58b325d4f777a063a16a25cd88c8baafca76dc31769.

Each signal's published record, `results/vetting/<signal>/` in the tess-hunt repository, and the light curve its
vetting run read:

| Signal | Record | Light curve |
|---|---|---|
| 103312990-1 | `checks.json` a513d03f99c0aa8d42a2118a1eff7c5beecdc255304a244ad6a01e2b803332e9 | TIC 103312990: 955172c695e312119374aac16c67cf7a0649c1ce087b527b5b8de21c0d058398 |
| 241522065-1 | `checks.json` fbb69b34ebb0a4132b6f566812ab2a512eaed9bf762327317df4b0b5102b7c06 | TIC 241522065: 010beb2551a15c870c0dca8032e6fb7f951fbd6c602caae706d49977e4513362 |
| 296819076-1 | `checks.json` cd5b60f9ce9de318c2d7cece5d31f850068af6d5813a7f34798aace81e4cecf4 | TIC 296819076: 4bb3d64ea85517cc22bab6b7d11fc62e6f81ed3029f0a191b6c09974a005bb6b |
| 399023421-1 | `checks.json` 39d96c5d2dfc4d5c6cfa0683d4147faba664a479968f7ef1fd20b97004d59928 | TIC 399023421: 45aea53680b1f0d294ac53898ad27e692f320e14e61e7e29470c5cea839c98af |
| 423100454-1 | `checks.json` a28085c111c611893252bf81e382c3655c6a61dae554c6dc63c15b6915f2c8be | TIC 423100454: 7fb744d3030a0096b401f11b63fe27a5413acc1ed435a1288e761e5d50bff03f |
| 438857197-1 | `checks.json` a51cf18a913c2245ddffb8f1dceb2be60c2ff1d9acff95f1b6745861e4e69813 | TIC 438857197: 7d9651a8982fbed7c8bcd1ccaa8e7594eaaedfbee106d87a727649c827889e18 |

## Files

- `predictions.csv`: one row per predicted transit: `signal`, `tic`, `sector`, `epoch`, `mid_btjd`, `mid_utc`, `period`, `t0`, `core_half_width_days`. `epoch` counts periods from the refit's t0;
  `mid_btjd` is BJD_TDB - 2457000; `mid_utc` is the mid-time as seen from Earth; `period` and `t0` are the refit's,
  in days and BTJD.
- `references.json`: for each signal, the refit (`predicted`, with BLS's duration and depth), the core half-width,
  the training depths (`reference`, as fractions of the flux, and by family), the training seasons and families, the
  products that can test it (`testable_with`) and the sectors left out; and the test's criteria values (`test`).
- `windows.csv`: the observers' windows: `signal`, `tic`, `sector`, `epoch`, `mid_btjd`, `mid_utc`, `sd_minutes`, `half_width_1sigma_minutes`, `half_width_3sigma_minutes`, `duration_days`. `epoch` counts periods from the density-prior fit's t0.
- `facts.toml`: the facts about archives and the DDT proposal this README states, each with its source and the date it
  was read.
- `provenance.json`: the run's commit, criteria, inputs with their sha256, and command line.
- `zenodo.md`: the deposit's title, description, keywords and licence.

## Licence and sources

CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/). The package holds no Gaia data. It is derived from TESS
light curves (SPOC, TESS-SPOC and QLP, from MAST) and the TESS Input Catalog. The facts in `facts.toml` come from:
https://help.zenodo.org/docs/deposit/manage-files/ (read 2026-10-27); https://archive.stsci.edu/hlsp/tess-spoc (read 2026-10-27); https://archive.stsci.edu/hlsps/qlp/ (read 2026-10-27); https://tess.mit.edu/public/target_lists/target_lists.html (read 2026-10-27); results/ddt/241522065-1/proposal.md (read 2026-10-28); https://zenodo.org/records/19661443 (read 2026-10-27).
