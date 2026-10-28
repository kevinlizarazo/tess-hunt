# 0028: Passed, killed or held; the "passed" bar `vetting publish` holds a call to; the record of each call

- Date: 2026-10-17
- Status: Accepted. Approved by the maintainer in the M3 design (2026-10-16): the three outcomes, the five items of the
  "passed" bar, the record, what the dossier shows, and the second list's rule that a pixel fail kills a row as it
  would have in triage (M3 design, sections 4.7 to 4.10). [0033](0033-second-list-decisions.md) sets the second list's
  pixel kill aside for one row, 423100454-1, on the maintainer's call of 2026-10-20. Accepted by the maintainer on
  2026-10-22: the five rulings the M3 build's controller made after that approval, Ruling Q (bar 2's "ExoFOP shows
  nothing at the period" checked against every ExoFOP planet-parameter row on period alone, at the novelty harmonics),
  Ruling R (`hits_read` names every hit the review flagged), Ruling U (how the second list's pixel check reaches the
  call: `pixels.json` through `--second-list`, an inconclusive or missing pixel check blocking a second-list row's
  pass, and a failed pixel check counted as a kill's ground for every signal), Ruling V (the second list's SPOC DV
  statistics and ExoMiner score matched at the novelty harmonics and looked up on the stars novelty matched as well as
  the signal's own, each row naming the TIC, TCE and ratio it came from) and Ruling W (every pass, not only a
  second-list row's, needs a pixel pass); and the choices this record makes in building it: each run's provenance
  copied into the record, production runs only, unknown call keys refused, a signal a TRICERATOPS or literature run
  never judged allowed in, the README listing only published calls that stand, and the timing-suspect marks in the
  centroid table. Rulings C (the TRICERATOPS, literature and second-list runs refuse vet criteria other than the
  vetting run's: one run, one criteria file) and M ([0026](0026-triceratops.md)), which this record also cites, are
  the controller's: no acceptance of them by the maintainer is recorded. Added on 2026-10-28, with no acceptance by
  the maintainer recorded: the build choices the acceptance of 2026-10-22 did not name, each stated under Decision (a
  call names the signal its directory holds, and its `criteria` the vet criteria version the checks ran under;
  `[answers]` names no finding but a confirmed one; `vetting dossier` takes `--evidence-only` and `--signals` and
  keeps drafts out of `results/`; the dossier's Literature hits section; and, in Ruling U's build, the second list's
  own centroid plot, `pixels.png`, shown in place of the vetting run's `plots/centroids.png`); and five changes the M4
  build made for the M3 build's deferred minors: `vetting dossier` refuses an `--out` anywhere in the repository;
  `calls.problems` refuses a `review.json` written for another signal; a plot that raises leaves the vet standing,
  with its error in `checks.json`'s `plot_errors`, and the dossier names it where the plot would be; a record holds a
  second-list run's provenance only for a second-list row; and a `publish` whose copy fails partway removes the files
  it copied. Three more, by the controller's ruling of the same day, change what a dossier rendered after M4 shows,
  the published dossiers staying as they were published: page one's Triage row names the triage run the vetting run
  read and the criteria file it judged under, which `vetting run` now records as input `triage_criteria` (a record
  made before says its vetting run recorded none); a finding rated kill or hold that no refuter ran on is headed
  "confirmed, no refuter ran on it"; and the windows table leaves out the 1-sigma half-width, which is the sd.

## Context

The spec ends vetting with each shortlisted signal "passed or killed", on the maintainer's call. M3 brings the evidence
for that call together (the vet-v3 checks, the neighbour table, TRICERATOPS, the literature by name, an adversarial
review) and publishes it. Two things can go wrong at that point. A call can claim more than the evidence supports: a
pass with a check that did not pass, a literature search a rate limit cut short, or a review finding nobody answered.
And a published record can mix runs: a TRICERATOPS result made from another vet, or numbers typed into a dossier by
hand. The M3 design (sections 4.7 to 4.10) settles both; this record states the rules as the code enforces them.

## Decision

- **Three outcomes** (M3 design, section 4.9).
  - **killed:** a check failed, or a confirmed review finding the maintainer accepts shows it is not a planet, or it
    is known.
  - **held:** not passed and not killed, because the public data can't decide. The call names the evidence that
    would decide it (2-min data, high-resolution imaging, ground-based photometry, a QLP redelivery). An inconclusive
    result is a lack of evidence, not evidence against (0017's reasoning), so calling it killed would misstate it. A
    held signal does not advance.
  - **passed:** clears the bar below.
- **The call** is `results/vetting/<name>/call.toml`, the maintainer's file: `signal`, `outcome`, `date` (a TOML date),
  `reasons` (his words), `rests_on` (check names and review finding ids), `criteria` (the versions it was judged under),
  and by outcome `deciding_evidence` (required when held), `promotion` (second-list rows only: the TCE matched and the
  reason), `[answers]` (one per confirmed finding), `[sentences]` (`not_a_binary`, `not_another_star`,
  `not_an_artefact_or_known`, required when passed) and `hits_read` (required when passed, an empty list when the review
  flagged none). Its words, numbers included, are the maintainer's; the dossier quotes it
  ([0037](0037-quoted-text-in-the-dossier.md)). `calls.load` refuses a key outside this list, since a misspelt key would
  otherwise be dropped without a word, and a `rests_on` name that is neither a check in the record (vet-v3's checks,
  `neighbours`, `pixels`, `triceratops`, `literature`) nor a review finding.
- **The review** is `review.json`, written by the review workflow (M3 design, section 4.8): `signal`, `model`, `date`,
  `findings` (each with `id`, `lens` of `on_star`, `planet` or `real_new`, `rating` of `kill`, `hold` or `note`,
  `claim`, `evidence` and `refuters`, each `{refuted, reason}`), `hits_flagged` and `summary`. A finding is
  **confirmed** when it is rated kill or hold and no refuter refuted it. One no refuter has answered yet stands, which
  errs toward an answer being owed. `calls.load_review` refuses a lens or rating off its list: a rating of "Hold"
  read loosely would leave a finding nobody must answer.
- **The "passed" bar** (M3 design, section 4.9), as `calls.problems` checks it against the files beside the call:
  1. every vet-v3 check in `checks.json` passed;
  2. novelty passed, or, for a second-list row (`kind = "second"`), is inconclusive only as `known_to_spoc` and the
     call's `promotion` stands in for it (0013 allows a promotion by hand; M3 design, section 4.10); ExoFOP shows
     nothing at the period: no row of ExoFOP's planet parameters in `literature.json` (confirmed planets, TOIs and
     user uploads, each with its period) matches the signal's period on period alone, at vet-v3's novelty harmonics
     within search-v2's `[match]` tolerance, as novelty matches a star's own rows; the literature search passed (every
     source, every searched name, ADS included: 0027); and every hit the review flagged is in `hits_read`;
  3. TRICERATOPS passed (`triceratops.json`), which by 0025 and 0026 means every Gaia DR3 neighbour that could host
     the signal was among the stars it weighed;
  4. a review exists, every confirmed finding has an answer in `[answers]`, and `[answers]` names no other finding;
  5. the three sentences are there.

  The match tolerance is read from the criteria files the vetting run's provenance names, each checked against the
  sha256 the run recorded. Every pass also needs a pixel pass (Ruling W): triage's, in `checks.json`, or for a
  second-list row the second list's (below). `vetting run` never checks that a candidate was shortlisted, so the bar
  reads the pixel record instead of trusting the shortlist; a candidate whose record is missing or inconclusive can't
  be passed.
- **A second-list row's pixel check** (Ruling U; M3 design, section 4.10). Triage runs its pixel check only on
  signals that passed novelty, so it never ran on a second-list row, and the row's `checks.json` holds triage's "not
  run". `tess-hunt vetting second-list` runs it as triage runs it, writes the result as `pixels.json` and draws its
  centroid plot from it as `pixels.png`. For a second-list row that is the pixel check `calls.problems` and the dossier
  read (`calls.pixels`), and the plot the dossier shows in place of the vetting run's `plots/centroids.png`, which drew
  triage's empty record; for every other signal the pixel check is triage's, in `checks.json`. A pixel fail kills the
  row as it would have in triage: a failed pixel check is a ground a kill may rest on (for any signal), and a
  second-list row's pass needs a `pixels.json` whose outcome is pass. Without the second list's record, `pixels` is not
  a name a second-list row's call may rest on.
- **The second list's table** (M3 design, section 4.10; Ruling V). `vetting second-list` also writes
  `second-list.csv` and `second-list.md`: per row the vet's outcomes, the pixel check, SPOC's DV statistics and the
  ExoMiner score for the row at the signal's period, and the next TESS sectors. SPOC and ExoMiner rows match on period
  alone within search-v2's `[match]` tolerance at vet-v3's novelty harmonics, on the signal's star first and then on
  each star novelty matched it to; of several, the latest sector run's. Each row names the TIC, the TCE or ExoMiner row
  and the ratio it came from, and lists every TCE that matched with its run and ratio, so a neighbour's or a
  harmonic's numbers can't pass for the target's at its period.
- **A kill** rests on a failed check (TRICERATOPS's and the pixel check's fails included) or a confirmed finding:
  `rests_on` must name one.
  **A hold** needs `deciding_evidence`. For every outcome the call names the signal its directory holds and lists the
  vet criteria version the checks ran under.
- **The record** under `results/vetting/<name>/`, written by `tess-hunt vetting publish --name NAME --run VETTING_RUN
  --triceratops RUN --literature RUN [--evidence-only RUN] [--second-list RUN] [--titles RUN]`:
  - from the vetting run: `checks.json`, `neighbours.csv`, `plots/*.png`; from the TRICERATOPS run: `triceratops.json`,
    `probs.csv`; from the literature run: `literature.json`, trimmed with the titles run's lookups since decision
    [0038](0038-literature-trim-and-username-scrub.md), with that run's provenance as `provenance-titles.json`; from the
    evidence-only run: its `checks.json` as `checks-with-suspect.json`; from the second-list run, for a second-list row:
    `pixels.json` and `pixels.png` (outside `plots/`, so every file there stays the vetting run's, behind
    `provenance-checks.json`). Beside each run's files goes that run's `provenance.json`, unchanged, as
    `provenance-<file>.json` (`provenance-checks.json`, `provenance-triceratops.json`, `provenance-literature.json`,
    `provenance-checks-with-suspect.json`, `provenance-second-list.json`), so the record names its runs, commits and
    criteria. A signal a check killed has no TRICERATOPS result unless the stage was given it by name (44926986-1,
    [0026](0026-triceratops.md)); without one, the run's provenance still goes, and the dossier says the run did not
    judge it.
  - The runs must belong together (Ruling C's rule, one run, one criteria file): each is a finished production run;
    `--run` is not evidence-only and `--evidence-only` is; the TRICERATOPS, literature and second-list runs were made
    from `--run` and recorded the sha256 of this signal's `checks.json` as `--run` holds it; every run's criteria shas
    equal `--run`'s; the evidence-only run vetted the signal at the same ephemeris. Nothing reads the evidence-only
    run's `advances`.
  - `publish` refuses when `call.toml` is absent or `calls.problems` is not empty. It judges the call and renders the
    dossier and `results/vetting/README.md` from a staged copy before it copies anything, so a refusal, or a render
    that raises, leaves `results/` as it was. Published files are never overwritten: the same run's file again is no
    change, any other is refused. Only `dossier.md` and the README are rendered again, from what sits beside them;
    `dossier.md` is written last of a signal's record.
  - `results/vetting/README.md` has one row per published signal whose call stands (its record and `dossier.md` are
    there and `calls.problems` is empty): name, outcome, date and reason. A call written before its signal is
    published, or one that no longer stands on its record, is left out, and `publish` prints which and why.
- **The dossier** (`dossier.render`, M3 design, section 4.7) reads only the files in the signal's directory. Page one:
  the signal and the star (names, Teff, radius, Tmag, RUWE, CROWDSAP per sector, the sectors vetted and left out, the
  criteria versions, the runs); every check with its outcome and reason; the three questions with their evidence (on the
  star: centroid offsets per sector, with each timing-suspect sector marked and the sector whose offset triage's pixel
  check judged named, from the second list's pixel check for a second-list row, the neighbour table's possible hosts,
  each beside the TRICERATOPS star matched to it at the TIC's epoch and the depth TRICERATOPS gave that star (the M3
  design's cross-check, section 4.4), TRICERATOPS's NFPP, the possible hosts it did not weigh and those it gave zero
  depth (Ruling M, 0026), RUWE; a planet rather than a binary: odd and even, the secondary at phase 0.5 and at any phase
  from LEO-Vetter's ModShift, the search's other signals on the star with their period ratios, shape, density, Rp from
  both fits, the density-prior fit's parameters, TRICERATOPS's FPP; real and new: signal present, the held-out seasons,
  sector depths, novelty, the literature search, ExoFOP); the next TESS sectors with the predicted windows and their
  widths; and the DDT note. Then the plots, every catalogued row on the star with the transits of ours its mask window
  overlaps (vet-v3 leaves the search's non-masked kinds unmasked, 0021, so the dossier shows what they would have cut;
  `vetting run` writes this as `checks.json`'s `catalogued`), the literature hits, the evidence-only vet beside the vet,
  the review (`dossier.render_review`) and the call.
  - Each number names the fit it comes from: shape, density and the radius check read the flat-prior fit; Rp, b,
    a/R* and the ephemeris come from the density-prior fit, whose Rp is shown with the 16th and 84th percentiles and
    whose other parameters with their spread below and above the median.
  - The template is a `string.Template` filled with `substitute`, and every value is read from the record by its key,
    so a value the record lacks raises rather than rendering (`docs/design.md`, section 5.5). A value the record holds
    as null renders as "missing". QLP publishes no CROWDSAP, so its sectors say so instead of raising.
  - A TRICERATOPS record holds every field `tricera.run` records on every path (`tricera.RUN_FIELDS`): a run that
    raised keeps the fields it reached and names the exception (`raised`), and None marks a step it never reached
    (0026). A run that raised before or after its cadence group, its fold or a finished `calc_probs` run, one that
    stopped before or after `calc_depths`, and one that finished all render, each saying only what the record shows of
    how far TRICERATOPS got.
  - **The DDT note** (M3 design, section 4.5): which stars get 2-min data in a sector is decided per cycle, so
    tess-point can't say whether an upcoming sector will have it; the note gives the upcoming sectors and whether the
    star had SPOC 2-min data in the sectors fetched, then the rule for the call's outcome. A passed signal goes to the
    DDT ask when its next look is full-frame images only; a held one only on the maintainer's call and only when the
    deciding evidence is the transit's shape (a hold on blending does not go: 2-min data come from the same pixels); a
    killed one does not. With no upcoming look there is no ask, and M4 decides the route.
- **Drafts.** `tess-hunt vetting dossier --run VETTING_RUN [--triceratops RUN] [--literature RUN] [--evidence-only
  RUN] [--second-list RUN] [--signals NAME ...] --out DIR` lays out each signal's record in `DIR/<name>/` as
  `publish` would, under the same run checks except production, and renders `dossier.md`, with a `review.json` or
  `call.toml` already in the directory rendered too. It refuses a `DIR` under the repo's `results/`, so `publish` stays
  the only way in.
- **ExoFOP's periods.** ExoFOP's TOI and CTOI entries carry no period; its planet parameters do. `vetting literature`
  now keeps each planet parameter row (provenance, name, TOI, period, epoch, duration, disposition) in the ExoFOP
  record, and a page without them is a failed ExoFOP read (0027).

## Limitations

- The code checks that the answers and sentences exist, not that they answer. Reading them is the maintainer's job and
  the reader's.
- An ExoFOP row with no period (a single transit) can't match on period, so it does not stop a pass; the dossier lists
  every row with its period or "no period", and the review's "real and new" lens reads them.
- `hits_flagged` and `hits_read` are matched as text; the review workflow and the call must use the same ids.
- The DDT note can't classify a hold's deciding evidence as shape or blending; it prints the rule and the evidence,
  and the maintainer decides.
- A literature run made before ExoFOP's planet parameters were kept can't carry a pass; the signal is searched again.
- A draft rendered before a review or a call exists says so; it is not a record and is never committed.

## Evidence

- [tests/test_calls.py](../../tests/test_calls.py): `test_confirmed_finding_needs_both_refuters_unrefuted`,
  `test_a_pass_the_evidence_supports_has_no_problems`, `test_a_pass_the_evidence_does_not_support_is_refused` (a
  failed check, an inconclusive check, an inconclusive or missing literature search, an inconclusive or missing
  TRICERATOPS, an unanswered confirmed finding, a missing sentence, an unread flagged hit, a missing `hits_read`, no
  review, an ExoFOP row at twice the period, an unpromoted `known_to_spoc` novelty: each refused),
  `test_a_planet_elsewhere_on_exofop_does_not_stand_in_the_way`, `test_kill_must_rest_on_a_failure`,
  `test_hold_needs_deciding_evidence`, `test_promotion_stands_in_for_known_to_spoc`,
  `test_a_kill_may_rest_on_a_failed_pixel_check`, `test_a_second_list_pass_needs_the_pixel_check_to_pass`,
  `test_a_candidate_pass_needs_triages_pixel_pass`, `test_a_call_file_that_breaks_the_schema_is_refused`,
  `test_a_review_file_that_breaks_the_schema_is_refused`, `test_no_call_is_a_problem`.
- [tests/test_secondlist.py](../../tests/test_secondlist.py): `test_dv_fields_match_by_period` (the latest run, each
  matching TCE with its run and ratio, a harmonic only at the harmonics), `test_no_spoc_row_is_none`,
  `test_exominer_prefers_v2`, `test_second_list_runs_pixels_as_triage_did` (the DV row found on the star novelty
  matched, named as such), `test_the_dossier_shows_the_second_lists_pixel_check` (its table, its plot in place of the
  vetting run's, and no claim of a second list when none was given),
  `test_publish_carries_the_second_lists_pixel_record` (a kill resting on the pixel check is refused without the
  second list's record and published with it; `plots/` holds only the vetting run's files; a second-list run made
  from another vetting run is refused).
- [tests/test_dossier.py](../../tests/test_dossier.py): `test_page_one_answers_the_three_questions`,
  `test_render_fails_on_a_missing_value`, `test_review_renders_findings_ratings_and_both_refuters`,
  `test_dossier_draft_says_what_it_lacks`, `test_publish_refuses_without_a_call` (and copies the record, re-renders
  only the dossier and the README, refuses another run's file, and is not stopped by another signal's call written
  before its publish), `test_publish_refuses_a_pass_the_evidence_does_not_support`,
  `test_publish_refuses_runs_that_do_not_belong_together` (another vetting run, other criteria, another
  `checks.json`, the main run as evidence-only and the reverse, a run that is not production),
  `test_readme_lists_every_call` (not a call with no record, a record with no call, or a call that no longer stands),
  `test_a_triceratops_record_from_any_path_renders` (records `vetting triceratops` wrote after TRICERATOPS raised,
  found no cadence group, got too few cutouts, or found no target light).
- [tests/test_tricera.py](../../tests/test_tricera.py): `test_every_path_records_the_same_fields`.
- [tests/test_vetting.py](../../tests/test_vetting.py):
  `test_every_catalogued_row_on_the_star_is_listed_with_the_transits_it_overlaps`.
- [tests/test_literature.py](../../tests/test_literature.py): `test_exofop_record_keeps_comments_and_imaging` (the
  planet parameters with their periods; a page without them is a failed read).
- Added on 2026-10-28. [tests/test_secondlist.py](../../tests/test_secondlist.py): the three second-list tests the
  list above leaves out, `test_a_missing_value_renders_as_missing`,
  `test_a_row_without_leo_vetter_metrics_is_inconclusive` and `test_second_list_refuses_inputs_it_cannot_stand_on`
  (since that date also a changed triage criteria file, a targets file the vetting run did not read, a changed
  `stars.parquet`, a changed light curve and a triage run that is not production);
  `test_the_dossier_shows_the_second_lists_pixel_check` (no second-list run in another signal's record, and a
  second-list run that drew no `pixels.png`). [tests/test_calls.py](../../tests/test_calls.py):
  `test_a_pass_on_an_evidence_only_vet_is_refused`, `test_a_pass_on_criteria_changed_since_the_vetting_run_is_refused`,
  `test_a_review_of_another_signal_is_refused`. [tests/test_dossier.py](../../tests/test_dossier.py):
  `test_a_pass_the_record_supports_is_published`, `test_publish_renders_the_readme_before_it_copies_anything`,
  `test_a_copy_that_fails_partway_leaves_no_new_file`, `test_a_draft_call_that_breaks_the_schema_is_not_rendered`,
  `test_a_plot_the_vetting_run_could_not_draw_is_named_with_its_error`, `test_dossier_draft_says_what_it_lacks` (an
  `--out` anywhere in the repository), `test_a_finding_no_refuter_ran_on_says_so`,
  `test_page_one_names_the_triage_run_and_its_criteria`, `test_page_one_answers_the_three_questions` (the windows
  table without the 1-sigma column), `test_seen_utc_matches_the_dossier` (each published windows table less that
  column). [tests/test_vetting.py](../../tests/test_vetting.py): `test_a_plot_that_raises_is_named_and_the_vet_stands`,
  `test_modshift_and_pixels_come_from_the_triage_run` (the triage criteria file recorded).
