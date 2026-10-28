# 0040: Held signals get a public prediction of their next season, judged by the held-out check's own test

- Date: 2026-10-27
- Status: Accepted. Made in the M4 design and approved by the maintainer with it on 2026-10-27. Six choices the M4
  build's controller made on 2026-10-27, stated in full under Decision, are the controller's, with no acceptance by the
  maintainer recorded: the package records what the held-out check's two training gates read (PF5); the index of
  packages reads an optional `dois.toml` (PF6); the archive facts the package states come from a committed
  `results/predictions/facts.toml`, the sector dates from `benchmarks/tess_sectors.csv`, and the judging date is this
  record's rule, one constant in `prereg.py`; RAVEN's citation is a fact in that file, read from its Zenodo record,
  because the record's literature search holds no RAVEN paper; the 2-min target lists the controller read on
  2026-10-27 are a fact there too; and so is the state of 241522065-1's DDT proposal (`ddt_241522065`), which renders
  the maintainer's decision to send it or not, set with its date before the production run. How a re-vet applies
  "When it is judged" is [0041](0041-revets-as-versions.md)'s, by the controller's rulings of 2026-10-28: a result that
  is not pending stands, and every later re-vet carries it; a light curve fetched on or after the judging date
  completes no season, since the code sees when data were fetched, not when they were public; and a result is judged
  as of a day between its vetting run's start and the day the test runs. Amended 2026-10-28 by the maintainer's
  decision, after the package's pre-release review found that Zenodo lets an edit of a record's files, opened within
  30 days of publishing, be published until day 45: the deposit deadline moved from 2026-11-20 to 2026-11-05, 45 days
  before the same lock start, and `facts.toml` holds the 45-day limit as `zenodo_edit_publish_days`.

## Context

The spec preregisters only a passed candidate's transit windows ([0024](0024-density-prior-fit-and-windows.md)). Six
held signals have TESS sectors ahead: 103312990-1 (S110 to S113), 241522065-1 (S112 to S114), 296819076-1 (S114),
399023421-1 (S112 to S114), 423100454-1 (S113) and 438857197-1 (S112 and S114). For each, those sectors are the last
TESS gives through S134 (tess-point, M4 design section 3), so a prediction public before them is the only one any of
them will get from TESS.

The record's windows come from the density-prior fit (0024), but the held-out season check never reads them. With a
season held out it refits the period on the other seasons near the search's ephemeris (`checks.holdout`) and measures
depth only in each predicted transit's core. With the new season held out, the other seasons are exactly the M3 light
curve, so the prediction the check will judge is fixed now. Zenodo lets a deposit's owner open an edit of its files
within 30 days of publishing and publish the edit within 45 days ([facts.toml](../../results/predictions/facts.toml)),
so a deposit's files are fixed 45 days after publishing, and a prediction is locked only for sectors that start after
that.

## Decision

- **Which signals and sectors.** Each held signal with a window sector that starts on or after the lock start, the
  date the deposit's files lock (`--lock-start`). Deposited by 2026-11-05, the files are fixed by 2026-12-20, so
  103312990-1's S110 and S111 are left out and named with the reason; every other sector above is predicted. Only a
  published record whose call is `held` is predicted.
- **What is judged.** The prediction the test will judge, computed now: `holdout.refit_ephemeris` on the M3 light
  curve (the vetting run's sectors, timing-suspect sectors left out, its masks, its red-noise depth errors, as
  `vet.prepare` makes it), the core half-width, and each predicted transit's mid-time in the predicted sectors; and the
  reference, `holdout.reference` over every M3 cadence: the training depth, error and cadence count in those cores,
  pooled and per product family. Beside them the package records what the check's two training gates read: the M3
  seasons, which of them hold a transit in their data, and `min_training_seasons` (the controller's ruling PF5, so a
  re-vet can apply the gates from the package alone).
- **What is not judged.** The density-prior fit's windows from each record's `checks.json`, copied unchanged with
  their standard deviations, for anyone checking by eye. The package says they are not what is judged.
- **The test.** vet-v3's `[holdout]` measurement and thresholds as `criteria/vet-v3.toml` holds them, applied to the
  new season with the published prediction and reference in place of a fresh refit (`holdout.judge`): seasons split at
  gaps over `season_gap_days`, the two training gates, depths in the cores, the expected SNR and the depth tension
  compared within a family. The result per signal is the new season's status: replicated (`predicted`), missed
  (`missed`) or untested (`underpowered`, `untestable`, `no_predicted_transit_in_data`, or no light curve). On an
  unchanged M3 light curve this is exactly what `checks.holdout` computes for that season, and a test proves it. Judging
  with the published numbers keeps the result fixed if a re-vet's training data later change (a QLP redelivery, a new
  mask). No rule is new: vet-v3 was frozen before M3's first control ran.
- **The data that can test it.** A held-out season is testable only in a product family that has training data
  ([0023](0023-product-families.md)), so the package names, per signal, the products of each family with at least
  `[holdout] min_points` training cadences in the cores: SPOC 2-min and TESS-SPOC for the PDCSAP family, QLP for the
  QLP family. fetch takes one product per sector, so a season that mixes in a sector of a family with no training data
  is untestable as a whole. Any other product, the project's own FFI photometry included, needs a decision record,
  made before it is run on these stars, saying how the test applies to it.
- **When it is judged.** Once per signal, on the complete season: at the first re-vet whose light curve covers every
  predicted sector for that star with data the test can use, or, failing that, on 2027-12-31, when whatever is
  untested stays untested. Re-vets before then may run, but report the result as pending. A season runs from gap to
  gap, so 103312990-1's season holds S110 and S111 as well as the predicted S112 and S113; their cadences stay in it,
  as vet-v3 counts them, and the package says so.
- **What a result means.** A replicated season shows the dip is real, periodic and where it was predicted. It does not
  show the dip is on the target: the blending holds stay until their own evidence comes. The held-out check as a whole
  fails when two or more seasons are tested and one is missed, which is a failed vet-v3 check and a ground for a kill
  under [0028](0028-outcomes-and-calls.md). With fewer than two tested it stays inconclusive, and a missed new season
  is then evidence against the signal that the maintainer weighs in the call, not a failed check. The package states
  both cases.
- **The package.** `tess-hunt predictions run --vetting-run DIR --records NAME ... --catalogs SNAP --lock-start DATE
  --production` writes it into one run directory: `predictions.csv` (one row per predicted transit), `references.json`
  (per signal, the refit, the reference, the gates' inputs, the families, the products that can test it and the sectors
  left out; and the test's criteria values), `windows.csv` (the observers' windows), `README.md`, `zenodo.md` (the
  deposit's title, description, keywords and licence, naming no person) and a copy of `facts.toml`. It refuses a
  record whose call is not `held`, a record whose `checks.json` is not the vetting run's file for that signal, a light
  curve whose sha256 is not the one the vetting run recorded, a catalog snapshot, criteria or sectors file other than
  the run's, and a window sector, predicted or left out, that starts within `season_gap_days` of the vetted light
  curve's last cadence, which the test would merge with that light curve's last season. A production run takes only
  `results/predictions/facts.toml` from the checkout its code runs from, and refuses it with uncommitted changes, since
  the clean-tree check covers the code and not `results/`. `tess-hunt predictions publish --run RUN_ID` copies a
  production run's package into `results/predictions/<run id>/` and renders `results/predictions/README.md`, the index
  of packages, which reads an optional `results/predictions/dois.toml` (package run id to DOI and publication date)
  and shows "DOI pending" without it (the controller's ruling PF6); `tess-hunt predictions index` renders the index
  again. The maintainer deposits each package as one Zenodo record and records its DOI there.
- **Where the words and numbers come from** (`docs/design.md`, section 5.5). The README and the Zenodo text are filled
  with `substitute`: the numbers from the run, the records and the criteria file the run read; the facts (the Zenodo
  window, the last TESS-SPOC and QLP sectors, the 2-min target lists read and the stars on none of them, RAVEN's
  citation, and the state of 241522065-1's DDT proposal) from `results/predictions/facts.toml`, each with its source
  and read date, and each sentence names the read dates of the facts it states; the sector dates from
  `benchmarks/tess_sectors.csv` as vet-v3's `[predict]` reads it; the judging date from this record
  (`prereg.JUDGED_BY`). A value missing, null or NaN raises. 399023421-1's section
  quotes its review's F9 (the timing-suspect QLP transits arrive 30 to 50 minutes after the windows) and F4 (the RAVEN
  row is most likely a 5:2 alias of this signal) word for word ([0037](0037-quoted-text-in-the-dossier.md)), gives
  RAVEN's period from the record's catalogued row and cites RAVEN from `facts.toml`, read from Zenodo record 19661443,
  the record the catalog snapshot took RAVEN's table from. The package holds no Gaia data, so it is CC BY 4.0 whole.

## Limitations

- Four of the six signals have training data only in the PDCSAP family, and TESS-SPOC's FFI light curves stop at S85
  (`facts.toml`), so only SPOC 2-min data can test their predictions. As read on 2026-10-27, none of the six stars is
  on S110's final 2-min or 20-s lists or the Guest Investigator priority lists for S111 to S114, though a list can
  change before its sector. Of the four, only 241522065-1 has a DDT proposal ([0039](0039-ddt-for-held-signals.md)),
  which even sent is a request the TESS office may not take; for the other three no 2-min data are in sight. The
  package says both, with the proposal's state as `facts.toml` records it. All four are predicted anyway: a public
  prediction costs a row, and anyone can check it by eye. For 241522065-1 a QLP season could still make its two old
  seasons testable and lift its hold while the predicted season itself stays untested; vet-v3 allows that, and the
  re-vet's dossier must say which happened.
- A miss on drift counts as a miss. 399023421-1's review found its timing-suspect QLP transits running late against
  the windows by about the half-width of a core (F9); if the refit drifts the same way, the test can call a real
  transit missed. The test is the prediction, so the package quotes the finding and does not move the refit.
- The windows are not judged. They come from another fit and can sit far from the refit: 296819076-1's come from a
  PDCSAP-only fit whose 3-sigma half-width is wider than its period, while the refit also uses QLP S65. A transit
  found inside a window but outside the refit's cores is a miss.
- Which sectors fall in the new season is judged from the sectors' dates; the test itself splits seasons on the
  cadences the re-vet's light curve holds.
- The lock rests on Zenodo's two limits on editing a record's files as read on the dates `facts.toml` gives, and
  Zenodo can still change a record's files "in duly justified cases". The package is made for a deposit by
  2026-11-05; deposited later, its files are fixed later than the lock start it states.

## Evidence

- [tests/test_prereg.py](../../tests/test_prereg.py): `test_prediction_equals_holdout_refit` (with each season of a
  three-season light curve removed, the prediction and reference equal holdout's row for that season, the gates'
  counts included), `test_sectors_before_the_lock_are_left_out`, `test_testable_routes`,
  `test_observer_windows_equal_the_records`, `test_package_fails_on_a_missing_value`,
  `test_399023421_section_quotes_the_review_and_cites_raven`, `test_predictions_run_and_publish` (a production run,
  its publication, the index with and without `dois.toml`), `test_refuses_a_light_curve_the_vetting_run_did_not_read`,
  `test_refuses_a_record_not_held`, `test_refuses_inputs_other_than_the_vetting_runs`,
  `test_refuses_a_new_season_that_would_merge_with_the_vetted_ones`,
  `test_a_production_run_states_only_the_committed_facts`, `test_a_family_without_cadences_in_the_cores_shows_none`,
  `test_the_ddt_proposal_s_state_comes_from_facts` (its state recorded on a later day than every other fact),
  `test_every_window_sector_is_checked_against_the_last_vetted_cadence`,
  `test_publish_refuses_a_run_that_was_not_production`, `test_the_committed_index_is_its_render`,
  `test_deposit_by_is_the_lock_less_zenodo_s_publish_limit`.
- The M4 build's check of the prediction on the M3 light curves of 423100454-1, 399023421-1, 438857197-1 and
  103312990-1 (the last with QLP S90 in training), each season with a refit removed in turn, against the season rows of
  their published `checks.json`.
- [results/predictions/](../../results/predictions/): `facts.toml`, the index and, once published, the package.
- The six calls: [103312990-1](../../results/vetting/103312990-1/call.toml),
  [241522065-1](../../results/vetting/241522065-1/call.toml),
  [296819076-1](../../results/vetting/296819076-1/call.toml),
  [399023421-1](../../results/vetting/399023421-1/call.toml),
  [423100454-1](../../results/vetting/423100454-1/call.toml),
  [438857197-1](../../results/vetting/438857197-1/call.toml).
