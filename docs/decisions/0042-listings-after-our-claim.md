# 0042: A TOI or CTOI listed after our public claim doesn't make the signal known

- Date: 2026-10-30
- Status: Accepted. Made in the M5 design (section 4.2), approved by the maintainer with the M5 plan on 2026-10-30.
  The design left the stage's name, its file layouts and how `publish` takes the stage's run to the build; the build's
  choices are stated under Decision. One choice is the maintainer's answer during the build, on 2026-10-30: an ExoFOP
  planet-parameter row with no TOI whose name is an excepted CTOI belongs to that CTOI and doesn't block bar 2. The
  claim date of the four held signals outside the predictions package is the maintainer's statement, also on
  2026-10-30. Six rulings the M5 build's controller made on 2026-10-30, also stated under Decision, are the
  controller's, with no acceptance by the maintainer recorded: a TOI's first-listed date is ExoFOP's `toidate1` and a
  CTOI's its `ctoi_created`; a catalog row is matched only to ExoFOP's rows of its own kind, whichever form either
  writes its name in, and bar 2 reads a planet-parameter row's listing the same way; only the TOI and CTOI rows on the
  signal's own star are sorted, and a neighbour's row stays in the catalog the check is run on again; a row ExoFOP
  gives no disposition field for, or lists more than once, is kept; a production run of the stage reads only the
  committed `results/claims.toml`; and the dossier gives one sentence per excepted listing and the rerun's outcome
  once.

## Context

The novelty check asks whether a signal was already known, and answers from a catalog snapshot that keeps no date:
`known.parquet` has no column saying when a row was listed, so a row listed yesterday counts the same as one listed
years ago. M3 killed 44926986-1 on novelty because eumemic's public all-sky list held it "before tess-hunt made any
public claim" (its `call.toml`). That reading needs a claim to measure from.

tess-hunt's claims date from 2026-10-28. Zenodo published the predictions package for six held signals that day
(version DOI 10.5281/zenodo.23745923, [results/predictions/dois.toml](../../results/predictions/dois.toml),
[0040](0040-predictions-for-held-signals.md)), and by the maintainer's statement the repository, with the dossiers
of the four other held signals, was made public the same day. If the TOI team lists one of these signals after that,
the next re-vet's novelty check fails on the TOI row, and bar 2 of the "passed" bar
([0028](0028-outcomes-and-calls.md)) finds ExoFOP's row at the period. A TOI is likeliest for 241522065-1 if the DDT
proposal ([0039](0039-ddt-for-held-signals.md)) brings 2-min data in S112 to S114. The pass would then be blocked by a
listing made after our claim, possibly from the data we asked for.

## Decision

- **The rule.** A catalog row does not make a signal known when all of these hold:
  - it is on the signal's own star (the same TIC). A listing on a neighbour at the same period is evidence that the
    dip may be the neighbour's, and stays known;
  - it is an ExoFOP TOI or CTOI, and the record's literature run (fresh at every re-vet,
    [0041](0041-revets-as-versions.md)) finds it in ExoFOP's record for the star with the date it was first listed;
  - that date is after the signal's claim date. Strictly: a row listed on the claim day counts as known;
  - ExoFOP's dispositions of the row are each PC or empty: TESS's and TFOPWG's for a TOI (`disp_tess`, `disp_tfop`),
    the uploader's and TFOPWG's for a CTOI (`cdisp`, `tdisp`). Any other disposition carries someone else's evidence
    about the signal, so the row is not excepted: it counts as a match like any other, blocks the pass and can ground
    a kill on the maintainer's call.

  When unsure, the row counts as known: a row whose first-listed date doesn't read as a plain date, a row ExoFOP's
  record lacks, lists more than once or gives no disposition field for (the controller's ruling), every row when
  ExoFOP's record was not read, and every row of a signal with no claim.
- **Claim dates.** `results/claims.toml` gives each held signal's claim: the day it was first public and the public
  record a reader can check that day against. 103312990-1, 241522065-1, 296819076-1, 399023421-1, 423100454-1 and
  438857197-1 have 2026-10-28 and the predictions record's DOI. 146282666-1, 164767175-1, 277774870-1 and 370977908-1
  have 2026-10-28 and the repository's URL, on the maintainer's statement of the day the repository was made public,
  since GitHub keeps no public record of it. A signal with no entry gets no exception, and the four killed signals have
  none. The file changes only with a decision record.
- **First-listed dates** (the controller's ruling, from pin P2). A TOI was first listed on its `toidate1`, which equals
  the TOI catalog's "Date TOI Alerted (UTC)"; a CTOI on its `ctoi_created`, which on the three rows checked equals the
  day in the CTOI export's "CTOI lastmod" column and is never later than `cdate` (which moves when a CTOI is promoted
  or dispositioned). The snapshot keeps a CTOI the TOI team promoted as a row of its own beside its TOI, and each is
  dated by its own field. So a TOI promoted from a CTOI listed before the claim is excepted on its alert date, while
  the CTOI's row stays known and the signal with it. That is the rule on its narrow side, not a gap: the CTOI was a
  public listing before our claim.
- **Names** (the controller's ruling). The snapshot writes `TOI-185.01` and `CTOI-17361.01`; ExoFOP writes
  `TOI 185.01`, `TIC 17361.01`, and `TIC 17361.01 (now TOI 3127.01)` for a CTOI the TOI team promoted. A snapshot row
  is matched to ExoFOP's rows of its own kind only, a TOI to ExoFOP's TOIs and a CTOI to its CTOIs, since a TOI and a
  CTOI can share a number. Every ExoFOP TOI row also gives its star's listing as `TIC <tic>.NN`; that is not a CTOI.
- **How it is computed.** The novelty check's record can't say what the check would have found without the excepted
  rows (on a fail it keeps the matches, not the stale-epoch period matches or the no-period objects), so the rows are
  taken out and the check is run again. `tess-hunt vetting claims --run VETTING_RUN --literature LITERATURE_RUN`
  reads the claims file, the literature run's ExoFOP record for each signal and the catalog snapshot the vetting run
  recorded. It refuses a vetting run that is unfinished, evidence-only or on other criteria, a literature run made from
  another vetting run, a snapshot whose files are not the ones the vetting run read, and, in a production run, any
  claims file but the committed `results/claims.toml` (the controller's ruling). For each signal it sorts the TOI and
  CTOI rows on the star (the controller's ruling: a neighbour's row is never a candidate and stays in the catalog the
  check is run on again), takes the excepted rows out of the snapshot and runs the unchanged `novelty.check_novelty`
  with vet-v3's settings. Its `claims.json` gives the claim, each excepted row with its first-listed date and
  dispositions, each row of the star it kept with the reason, ExoFOP's read status, and the rerun (`novelty`, null
  when nothing is excepted). The run records the vetting and literature runs, the snapshot, the claims file, each
  record it read and each `claims.json`'s sha256. The rerun covers whatever the excepted rows caused: a fail,
  `stale_catalog_epoch` (a later TOI whose epoch misses) or `no_period_object` (a later TOI with no period). Its
  outcome can be a pass, `known_to_spoc`, or a fail on rows the rule keeps.
- **Claims runs are for re-vets.** The stage reads the snapshot its vetting run recorded by name (`catalogs`,
  recorded since 0041). The M3 vetting run, `20261020T174317Z-vetting-run-61b5944-2d70`, recorded none, so `vetting
  claims` refuses it as `--run`. The fourteen published records hold no `claims.json`.
- **Where it applies.** vet-v3, every criteria file and `novelty.py` stay as they are. The novelty check still fails,
  and `checks.json` and the dossier's table of checks say so. `calls.problems` reads novelty through `calls.novelty`:
  where the record's `claims.json` excepts at least one row, its rerun stands in for the vetting run's novelty in the
  "passed" bar and in the kill rule. A kill can't rest on a novelty fail the rerun doesn't repeat, and a second-list
  row's promotion stands in for a rerun at `known_to_spoc` as it does for novelty's own
  ([0013](0013-novelty-sources.md)). Without `claims.json`, or with one that excepts nothing, every bar is as it was.
- **Bar 2.** ExoFOP's planet-parameter rows carry periods; the TOI and CTOI entries don't. A row that belongs to an
  excepted listing doesn't block bar 2: a row whose `toi` names an excepted TOI (its rows under "TOIs (TESS Project)"
  and under "User uploaded" both do), and a row with no `toi` whose `name` is an excepted CTOI, as a CTOI the TOI team
  never promoted has its uploaded row (the maintainer's answer). A TOI's rows give its star's listing in `name`
  (`TIC 17361.01`), which is not read when `toi` is set, and a name is read only in its own kind's form (`TOI` for a
  TOI, `TIC` for a CTOI), so a TOI and a CTOI that share a number stay apart (the controller's ruling). Every other
  row at the period blocks bar 2 as before, a confirmed planet's and one whose name reads as no listing included.
- **Publish and the dossier.** `vetting publish` and `vetting dossier` take `--claims RUN`: a finished claims run
  (production, for `publish`) made from `--run` on the same criteria, whose literature run is `--literature`'s. Both
  also check (the build's choice) that its `claims.json` is the file the run wrote (the sha256 it recorded) and that
  the run read the literature record the record holds. Any failure refuses the record before anything is copied. The
  record holds `claims.json` and `provenance-claims.json`, and a later publish compares them with the run's files like
  any other copied file. A version takes no claims run from an earlier record: its own literature run dates the
  listings. The dossier names the claims run among the record's runs and, after novelty's own result under "Real and
  new?", gives for each excepted listing "Decision 0042: LISTING was first listed on ExoFOP on DATE, after this signal
  was made public on CLAIM DATE (RECORD).", linked to this record, then the rerun's outcome once: "Without it, novelty
  is OUTCOME: REASON." ("Without them" for several). A record without `claims.json` renders as before: the fourteen
  published records render byte for byte as they did before this change.
- **What it leaves out.**
  - SPOC TCE and ExoMiner rows. A later TCE from the same 2-min data leaves novelty at `known_to_spoc`, which a
    second-list row's promotion already covers (241522065-1, 423100454-1 and 438857197-1 are second-list rows). For a
    shortlisted signal it stays inconclusive and blocks the pass. None of the shortlisted held signals can pass on
    TESS data alone, so the gap is recorded here, not closed.
  - A listing on a neighbour; an archive planet, a planet others confirm after our claim included; and a row from any
    other source, eumemic, RAVEN, Zenodo records and the rest.
  - A TOI or CTOI with any disposition but PC or empty, and any row the rule can't date.
  - An answer from the call. A call has no way to answer a listing the rule keeps, and none is added.
- **Why now.** Decided after a TOI appeared, the rule would be a change made on seeing a result. Decided now, it is
  fixed before any spring data exists: S112 starts on 2026-12-22. It is narrow on purpose. It protects only the order
  of discovery on the signal's own star, and gives way to any evidence another team adds.

## Limitations

- A CTOI's first-listed date rests on `ctoi_created` matching the CTOI export's "CTOI lastmod" day on three rows (pin
  P2). If ExoFOP moved that field on an edit, a CTOI listed before the claim could read as listed after it.
- The four repository claims rest on the maintainer's statement. On 2026-10-30 the repository read as private, for a
  reason not known, and was made public again that day; no public record shows the 2026-10-28 date.
- Dates and dispositions are ExoFOP's as the record's literature run read them. A disposition entered later is seen at
  the next re-vet's literature run.

## Evidence

- [tests/test_claims.py](../../tests/test_claims.py): `test_a_same_star_pc_toi_listed_after_the_claim_is_excepted`,
  `test_a_toi_listed_on_the_claim_day_is_kept`, `test_a_row_without_a_first_listed_date_is_kept`,
  `test_a_neighbours_toi_is_kept`, `test_a_row_from_any_other_source_on_the_star_stays_known` (an archive planet and
  eumemic's list), `test_a_disposition_other_than_pc_is_kept` (FP, APC and no TFOPWG field),
  `test_a_later_toi_with_a_missed_epoch_or_no_period_is_excepted`,
  `test_a_toi_excepted_beside_a_spoc_tce_leaves_known_to_spoc`, `test_a_signal_without_a_claim_excepts_nothing`,
  `test_snapshot_and_exofop_names_match_across_forms`, `test_an_exofop_read_that_failed_excepts_nothing`,
  `test_the_rerun_without_exceptions_reproduces_the_vetting_runs_novelty`,
  `test_claims_refuses_what_it_cannot_stand_on` (another snapshot included),
  `test_claims_writes_one_record_per_signal_with_provenance`,
  `test_a_production_run_refuses_a_claims_file_from_elsewhere`,
  `test_a_production_run_refuses_an_uncommitted_claims_file`,
  `test_the_claims_file_dates_each_held_signal_and_no_killed_one`, `test_load_claims_refuses_an_entry_it_cannot_read`.
- [tests/test_calls.py](../../tests/test_calls.py): `test_a_pass_stands_on_a_novelty_fail_0042_excepts`,
  `test_a_pass_on_a_kept_listing_is_refused`,
  `test_a_rerun_at_known_to_spoc_passes_a_promoted_row_and_blocks_a_shortlisted_one`,
  `test_a_planet_parameter_row_under_an_excepted_toi_does_not_block_bar_2` (and one under another TOI does, its `name`
  an excepted CTOI's included), `test_a_planet_parameter_row_under_an_excepted_ctoi_does_not_block_bar_2` (and rows
  under any other name do), `test_a_kill_cannot_rest_on_a_novelty_fail_the_rerun_does_not_repeat`,
  `test_without_claims_json_the_bar_is_unchanged`.
- [tests/test_dossier.py](../../tests/test_dossier.py): `test_publish_carries_the_claims_record` (the pass refused
  without the claims run and published with it), `test_publish_refuses_a_claims_run_that_does_not_belong` (made from
  another vetting run or literature run, a `claims.json` changed after its run, another literature record read, other
  criteria, not production, unfinished), `test_a_draft_with_claims_needs_the_literature_run_they_read`,
  `test_the_dossier_names_each_excepted_listing` (one listing and two, and a record without `claims.json` or with one
  that excepts nothing rendered as before).
