# 0041: A re-vet is a new version of a signal's record, published beside the old one

- Date: 2026-10-28
- Status: Accepted. Made in the M4 design (section 4.5) and approved by the maintainer with it on 2026-10-27. The
  design left the command's shape, the cache layout, the version naming and how `publish` and the README handle
  versions to the build; the build's choices are stated under Decision. Six rulings the M4 build's controller made,
  also stated there, are the controller's, with no acceptance by the maintainer recorded: a sector is redelivered only
  when the same product comes again; `vetting run` records where it read its light curves, and the stages after it
  read them from there; `publish` checks that a re-vet's light curve was merged onto the light curve the previous
  record's vetting run read; a preregistered result that is not pending stands, and every later version carries it;
  `--as-of` lies between the vetting run's start and the day the test runs; and a light curve fetched on or after the
  judging date completes no season.

## Context

M3 published fourteen records under `results/vetting/<name>/`; ten are held, each naming the evidence that would
decide it ([0028](0028-outcomes-and-calls.md)). For most of them that is data TESS has not yet delivered: new sectors
(S112 to S114 for 241522065-1), or a QLP redelivery of S99 to S104, whose timestamps are suspect
([0022](0022-vet-without-timing-suspect-sectors.md)). When it lands the signal is vetted again. Three things must not
happen then. A published record must not change: it is what the maintainer's call rested on. The new vet must not
read a light curve other than the one it records, or mix the old record's runs with the new ones (0028: runs belong
together). And a held signal with a preregistered prediction ([0040](0040-predictions-for-held-signals.md)) must be
judged by that prediction, not by a fresh refit.

## Decision

- **Never overwrite a light curve a run read.** `tess-hunt revet fetch` fetches each star again and writes the merged
  light curve into its own run's `lc/`, with `merge.json`: per star, per sector, its status, both products and the
  sha256 of the light curve it merged onto. `vetting run --lc-dir DIR` vets `DIR/<tic>.npz`, records each file's
  sha256 as input `light_curve_<tic>` as before, and records the directory (`lc_dir`, scrubbed as provenance is),
  the revet fetch run whose `lc/` it is (`revet_run`) and the catalog snapshot's name (`catalogs`). `vetting
  triceratops`, `vetting second-list` and `vetting prereg` read the light curves from `lc_dir` and refuse a file whose
  sha256 is not the one the vetting run recorded (the controller's ruling). A vetting run made before this decision
  recorded no directory and read the shared cache, where the stages read it still.
- **Old sectors stay as M2 fetched them.** Each sector of the earlier light curve is kept byte for byte (`kept`); a
  sector only the new fetch has is added (`added`); a sector both have is taken from the new fetch only when it is the
  same product delivered again, the earlier file timing-suspect and the new one not (`redelivered`, the controller's
  ruling). Any other change is not taken (`kept_m2`): a better product appearing later, say TESS-SPOC reaching past
  S85 over a QLP sector, or a suspect product replaced by another suspect one. A source fetched before fetch flagged
  timing can't show it was suspect, so it is kept.
- **Same signal, same rules.** A version vets the previous record's signal at the same ephemeris, on the same star,
  as the same kind, under the same criteria files (their sha256), with the same triage run, and `publish` refuses any
  other. Its evidence-only twin must have read the same light curve and catalog snapshot as its vetting run. vet-v3's
  `[predict] first_sector` stays, so the windows a re-vet lists for sectors its light curve already holds are
  post-dictions, and the dossier names them so.
- **The pixel check is carried, not rerun.** A shortlisted signal keeps triage's pixel and ModShift evidence through
  `--triage-run`, the previous record's triage run, as before. A second-list row's version carries the previous
  record's second-list pixel check: its `--second-list` may name the second-list run the previous record holds, made
  from another vetting run. `publish` checks that the run's `provenance.json` is the previous record's
  `provenance-second-list.json`, that the run read the `checks.json` of the record its own vetting run made (the M3
  record, for every version), and that its `pixels.json` and `pixels.png` are the previous record's; the version holds
  them and that provenance unchanged, and its `vetting_run`, not the version's, shows it was carried. A second-list
  row's version without it is refused. `vetting second-list` runs the pixel check only on the light curve the search
  searched, as triage would have, and refuses a re-vet's.
- **A fresh catalog snapshot.** The re-vet refreshes the snapshot with the same sources and parsers, and vets with it.
  A version's dossier lists the masked rows, the catalogued rows on the star and the novelty matches that differ
  between its `checks.json` and the previous record's, with both snapshots' names, without reading either snapshot.
- **The whole chain again.** TRICERATOPS, the literature search and the titles lookups run from the new vetting run
  ([0028](0028-outcomes-and-calls.md)); a fresh review (spec section 5.8) runs on the maintainer's go-ahead; the
  maintainer makes the call. The "passed" bar is unchanged.
- **A version, never an overwrite.** `tess-hunt vetting publish --name NAME --version N --run VETTING_RUN
  --lc-run REVET_RUN --triceratops RUN --literature RUN --titles RUN [--evidence-only RUN] [--second-list RUN]
  [--prereg RUN]` writes `results/vetting/<name>/r<N>/` (N from 2; the M3 record is the first) with the files an M3
  record holds, and the revet fetch run's `merge.json` with its provenance as `provenance-merge.json`. A record is
  published once `publish` has written its `dossier.md`, which it writes last. It refuses when the previous version
  (the M3 record for r2, else r<N-1>) is not published; when `r<N>` is, so a version is published once; when the
  vetting run's light curve is not the revet fetch run's file for the star; and when the revet fetch run merged onto
  another light curve than the one the previous record's vetting run read (the controller's ruling). An interrupted
  publish, which left files but no `dossier.md`, is finished by the same runs, since a file the same run made again is
  no change and any other is refused. Nothing outside `r<N>` changes but
  `results/vetting/README.md`, which has one row per signal: its latest version whose call stands, with links to the
  versions before it. With no version published it is the M3 README unchanged. `calls.problems` judges a version as it
  judges an M3 record, from the files in its directory; its call names the signal, not `r<N>`.
- **The version's dossier** reads its own directory and the previous version's `checks.json` and provenance. Its
  title names the version. A section after the call's line links the version before it and says what changed: the
  sectors added, redelivered and kept though another product was found (from `merge.json`), the post-dictions, a
  carried pixel check, and the snapshot's changes above. A carried preregistered result names the version that judged
  it, found among the records beside it by its vetting run. `tess-hunt vetting dossier --version N --lc-run RUN
  --signals NAME` drafts it outside `results/`, beside copies of the previous record's `checks.json`, provenance and
  dossier.
- **The predictions.** `tess-hunt vetting prereg --run VETTING_RUN --package DIR --catalogs SNAP --as-of DATE` writes
  `prereg.json` for each signal of the package the vetting run vetted. `prereg.judge_signal` applies 0040's test: the
  package's counts through holdout's two training gates; then each predicted sector must hold data the test can use (in
  the light curve, not timing-suspect, of a product the package names in `testable_with`); then the season of the
  vetted light curve, split at `season_gap_days`, that holds the predicted sectors is judged by `holdout.judge` with the
  package's prediction and training depths. The result is replicated, missed or untested (with the status and reason),
  or pending while a predicted sector has no usable data before `prereg.JUDGED_BY`, 2027-12-31. The season is judged
  once, complete, so from that date a season still missing a sector stays untested (`no_light_curve`). The code sees
  when data were fetched, not when they were public, so the judging date applies to the fetch (the controller's
  ruling): a light curve from a revet fetch run that started on or after 2027-12-31 completes no season, and a signal
  not judged before is untested (`fetched_after_judged_by`) whatever the light curve holds. A vetting run on the
  package's own light curve is not touched by this; one on a light curve neither the package nor a revet fetch run
  made is refused, since when it was fetched is unknown. `--as-of` lies between the day the vetting run started and
  the day the test runs (the controller's ruling), so no result can be backdated to pending. It refuses criteria other
  than the package's test and a package made on other criteria than the vetting run.
- **A result once judged stands** (decision 0040, "once per signal"; the controller's ruling). The earliest version
  whose `prereg.json` is not pending judged the signal. Every later version carries that version's `prereg.json` and
  `provenance-prereg.json` byte for byte, as a second-list row's version carries its pixel check: `--prereg` names the
  run that version holds, and `publish` checks its provenance, that it read the `checks.json` of the version it
  judged, and its result file. `vetting prereg` refuses to judge such a signal again, and `publish` refuses any other
  preregistered-test run for it. The dossier says the result was carried and from which version. A version of a
  signal that a package under `results/predictions/` predicts must carry a result (`--prereg`, from a run on that
  package); `--prereg` for a signal no published package predicts is refused. The dossier gives the result beside
  vet-v3's own held-out result.
- **The runbook, in order.** Every run is a production run (`--production`).
  1. `tess-hunt targets tics --from CSV`, the star's TIC in a `tic` column: its targets and products tables.
  2. `tess-hunt revet fetch --targets TARGETS --products PRODUCTS --base-lc-dir DIR`, with `DIR` the directory of the
     light curve the previous record's vetting run read (the shared cache for r2 while it holds that file, the
     previous version's revet fetch run's `lc/` after).
  3. `tess-hunt catalogs refresh --targets TARGETS_RUN`, the targets run the snapshots have used: a new snapshot.
  4. `tess-hunt vetting run --signals CSV --targets ... --catalogs NEW_SNAPSHOT --triage-run TRIAGE_RUN --lc-dir
     REVET_RUN/lc`, and its evidence-only twin with `--include-suspect`.
  5. For a signal a package predicts and no earlier version judged: `tess-hunt vetting prereg --run VETTING_RUN
     --package results/predictions/<run id> --catalogs NEW_SNAPSHOT --as-of DATE`, with `DATE` the day it runs.
  6. `tess-hunt vetting triceratops --run VETTING_RUN`, `tess-hunt vetting literature --run VETTING_RUN` and `tess-hunt
     vetting titles --literature LITERATURE_RUN`.
  7. `tess-hunt vetting dossier --version N --run ... --lc-run REVET_RUN --signals NAME --out DIR`, with the other
     runs as `publish` takes them, for the review workflow, which runs on the maintainer's go-ahead and writes
     `review.json` into `results/vetting/<name>/r<N>/`.
  8. The maintainer's call, `results/vetting/<name>/r<N>/call.toml`.
  9. `tess-hunt vetting publish --name NAME --version N ...`.

## Limitations

- A re-vet's pixel check is M3's. The new sectors' difference images are not judged; they can be shown as evidence
  only, and the pixel check's known weaknesses ([0033](0033-second-list-decisions.md)) stay as they were.
- A fresh snapshot can change the masks: a catalogued object added since M3 masks its transits in the new vet, and
  one removed unmasks them, so a check can change for that reason alone. The dossier lists every masked row that
  changed, so the reader can tell.
- A QLP season can make 241522065-1's two old seasons testable and lift its hold under vet-v3's own held-out check,
  while the preregistered test of its new season stays untested (no QLP training data in the package). vet-v3 allows
  that. The dossier gives both results side by side, so it says which happened.
- The second-list exception trusts the previous record: it carries whatever pixel record that record holds, the fail
  423100454-1's record keeps ([0033](0033-second-list-decisions.md)) included.
- `merge.json` holds every star of its revet fetch run; a version holds the whole file, as its run wrote it.
- Which predicted sectors hold usable data is read from the light curve's products; a product the package never named
  (the project's own FFI photometry) is not usable until a decision says how the test applies to it (0040).

## Evidence

- [tests/test_revet.py](../../tests/test_revet.py): `test_merge_keeps_m2_sectors_and_takes_only_a_suspect_redelivery`
  (a better product over an old sector, a suspect sector replaced by another suspect file, and TESS-SPOC over a suspect
  QLP sector are all kept as M2 fetched them).
- [tests/test_vetting.py](../../tests/test_vetting.py): `test_vetting_run_reads_lc_dir`,
  `test_vetting_run_records_the_shared_cache`.
- [tests/test_tricera.py](../../tests/test_tricera.py): `test_triceratops_reads_the_light_curve_its_vetting_run_read`
  (with the shared cache rewritten after the vetting run).
- [tests/test_calls.py](../../tests/test_calls.py): `test_a_version_is_judged_as_an_m3_record`.
- [tests/test_dossier.py](../../tests/test_dossier.py): `test_the_committed_readme_is_its_render`,
  `test_readme_lists_the_latest_standing_call`, `test_version_published_beside_the_m3_record` (every M3 file's bytes
  unchanged), `test_version_refuses_a_gap_or_an_existing_version`,
  `test_version_refuses_a_light_curve_not_from_its_lc_run` (the evidence-only twin's included),
  `test_version_keeps_the_previous_records_triage_run`, `test_an_interrupted_version_is_finished`,
  `test_a_version_is_drafted_beside_its_previous_record`, `test_dossier_says_what_changed`,
  `test_a_version_of_a_predicted_signal_carries_the_preregistered_test` (`--as-of` before the vetting run's start or
  after today, `--prereg` with no published package, r3 carrying r2's judged result while `vetting prereg` and another
  run are refused, and the fetch date recorded).
- [tests/test_secondlist.py](../../tests/test_secondlist.py): `test_second_list_row_carries_the_m3_pixel_record` (r2
  and r3).
- [tests/test_prereg.py](../../tests/test_prereg.py): `test_prereg_results` (replicated, missed, untested for a family
  without training data, pending before 2027-12-31 with a sector missing and untested from it on, a light curve
  fetched on or after it untested, the training gates from the package's counts),
  `test_prereg_equals_holdout_on_an_unchanged_light_curve`.
