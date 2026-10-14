# 0019: The detection threshold is the highest null SDE that survives LEO-Vetter's false-alarm tests

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design); amended 2026-10-13 with the host exclusion, the
  maintainer's choice

## Context

Spec 5.4 sets the threshold by running scrambled light curves through the full pipeline, with the rule (null
maximum or a quantile with an expected false-alarm count) fixed before the null runs. The LEO-Vetter paper scrambles by
shuffling the orbits within each sector and then the sectors (section 5.4) and used the scrambles to measure
reliability after vetting, not as a raw cut. On real sample-A stars, stellar variability survives scrambling at high
SDE (the M1 review's C1 stars), so a maximum on raw SDE would sit above known planets the search must recover.

## Decision

- Every sample star is scrambled once (`search --scramble <seed>`, design 4.5) and searched with the production code at
  the provisional `continue_sde`.
- The scramble splits each sector into segments at every internal gap longer than `[null] segment_gap_days`, shuffles
  the segments within each sector and then the sectors. Each sector keeps its slot's start, and the segments within it
  are placed a fixed `[null] placement_gap_days` apart (1.0 d in `criteria/search-v2.toml`), not at their original gap
  as the M2 design first wrote: after a shuffle a segment's neighbour has moved, so that gap is undefined. The fixed gap
  stays above detrend's `break_tolerance_days`, so moved segments are detrended apart, as orbits are.
- Null signals that match, on period at any harmonic, a known object on their own star in the triage snapshot (any
  kind, TCEs and catalogued eclipsing binaries included) are dropped: real signals that survive scrambling are not false
  alarms. Nothing is removed by hand.
- Every null signal on a star that hosts a catalogued object of kind `planet`, `candidate`, `community` or `eb` in the
  triage snapshot (`[threshold] exclude_host_kinds`) is dropped as well, whatever its period. The maintainer chose this
  on 2026-10-13, after the scramble probe (Evidence) found null peaks on a synthetic planet star at periods that are no
  harmonic of the planet's, which passed every false-alarm test. Stars whose only rows are `tce` stay in the null:
  many are variables, and their peaks are the false alarms the null exists to measure. A signal both exclusions drop
  counts once, under the harmonic one, so the harmonic count keeps its meaning. The threshold run writes every
  dropped signal, with the rule that dropped it, to `null_dropped.csv`, and records in `threshold.json` how many
  of the null's sample stars and signals the host exclusion dropped. It refuses a `--catalogs` that is not a v2
  snapshot with TCE and binary rows.
- The rest are run through LEO-Vetter's false-alarm tests (`criteria/triage-v1.toml` `[leo]`) from the highest SDE
  down. The threshold is the highest SDE among those that no false-alarm test rejects. A signal LEO-Vetter cannot judge
  (an exception, a missing stellar value, a false-alarm test it cannot evaluate) counts as passing, so an unknown can
  only raise the threshold. The threshold never falls below the provisional `continue_sde`: below it the null emitted
  no signals, so it says nothing there.
- `threshold.json` records, for each of the top null signals (`[threshold] report_top`) and for the highest surviving
  null signal (which sets the threshold unless the floor is higher), whether LEO-Vetter judged it and why not, and
  whether the highest surviving one was unjudged. It also records the highest SDE among signals that LEO-Vetter judged
  and passed, which is the threshold as it would be if unjudged signals did not count, and how many unjudged signals
  rank above it. Evaluation goes on past an unjudged pass until it reaches a judged one; when there is none among all
  candidates, that SDE is recorded as missing with the reason.
- The threshold run rebuilds the null's scrambled light curves, so it refuses a null it cannot reproduce: another mask
  snapshot, targets file, search criteria or search code, or a light curve that changed since the null searched it.
- The expected number of false alarms in the production search is the sample size over the null's size, recorded with
  the threshold. The null's size counts the sample stars the null searched that the host exclusion did not drop. It
  is an upper bound: the sample size counts every target, including those the search will not search (no light curve,
  not covered after fetch, too few points).
- The production search takes the threshold as its `continue_sde`. Triage refuses a search whose criteria or search
  code differ from the null's, whose `continue_sde` is not a finite number at least the threshold it ran with, or whose
  `continue_sde` is below the highest threshold computed for the same criteria and code.

## Limitations

- The scramble keeps part of a real periodic signal: each segment keeps its own transits in phase, so a weaker peak can
  remain near the real period. The decoherence test (`test_scramble_decoheres_a_planet`) bounds it only from above: on
  a synthetic planet, the median over seeds 1 to 5 of the top scrambled SDE over the unscrambled SDE must stay below one
  half. The harmonic exclusion drops such a peak when the object is catalogued and the peak lies within the match
  tolerance of one of its harmonics; the host exclusion drops it when the star hosts a catalogued object of a listed
  kind.
- The scramble can also leave some of a real planet's or binary's own transits evenly spaced by chance, enough for the
  search's `min_transits`. That peak sits at a period that is no harmonic of the real one, and its events are real
  transits of one depth and shape, so the false-alarm tests that compare events have nothing to reject. The harmonic
  exclusion misses it. Only `[detrend] mask_sources` objects are masked before the scramble, so an uncatalogued planet
  or binary, a TCE or a catalogued eclipsing binary keeps its transits in the null. The host exclusion drops the null
  signals of stars with a catalogued planet, candidate, community object or binary, but an uncatalogued real signal,
  or a real signal on a star whose only rows are TCEs, can still leave such a peak, and one such star can set the
  threshold. For each of the top null signals and the highest surviving one, the threshold run searches the star
  unscrambled (the same detrend, masks and search criteria), traces the null signal's in-transit cadences back through
  the scramble, and records in `threshold.json` whether half or more of them fall inside the transits of one signal
  found there, with that signal's period and SDE and the share. For a signal of rank 2 or lower the traced cadences
  include some the null search had masked for the star's higher-ranked signals. The maintainer reviews those rows
  before the threshold stands.
- The production search still searches host stars, and the threshold applies to them, though the null no longer
  measures false alarms on those stars.
- Every TOI and CTOI has kind `candidate` whatever its disposition, so a star whose only catalogued object is a TOI
  dispositioned a false positive or false alarm also leaves the null.

## Evidence

- Unit tests in [tests/test_threshold.py](../../tests/test_threshold.py): the rule and the guards
  (`test_threshold_is_the_highest_passing_sde_and_stops_early`,
  `test_exclude_known_matches_period_only_on_the_same_star`, `test_check_search_refuses_other_hashes_and_a_grown_null`,
  `test_check_search_refuses_a_continue_sde_below_its_threshold_or_not_a_finite_number`,
  `test_threshold_cli_refuses_a_null_it_cannot_reproduce`,
  `test_threshold_cli_refuses_light_curves_other_than_the_ones_the_null_searched`,
  `test_threshold_cli_refuses_catalogs_without_tce_or_binary_rows`), the host exclusion
  (`test_threshold_cli_drops_every_signal_on_a_star_that_hosts_a_catalogued_object`, for each listed kind, and its
  negative control, the star with only a TCE that sets the threshold in
  `test_threshold_cli_drops_known_objects_and_traces_the_threshold_row`, and
  `test_threshold_cli_counts_ok_sample_hosts_and_checks_only_candidates_light_curves`), unjudged signals
  (`test_leo_job_counts_an_unjudged_signal_as_surviving_and_says_why`,
  `test_an_unjudged_pass_sets_the_threshold_and_evaluation_goes_on_to_a_judged_one`), the trace-back
  (`test_a_null_peak_made_of_the_stars_own_transits_traces_back_to_them` and its negative control
  `test_a_noise_peak_on_a_star_with_a_planet_does_not_trace_back_to_it`) and the command end to end
  (`test_threshold_cli_drops_known_objects_and_traces_the_threshold_row`,
  `test_threshold_cli_counts_unjudged_signals_and_keeps_the_floor`,
  `test_threshold_cli_goes_past_an_unjudged_pass_to_a_judged_one`).
- The scramble probe behind the host exclusion, [benchmarks/scramble_leo_probe.py](../../benchmarks/scramble_leo_probe.py),
  and its output, [results/benchmarks/scramble-leo-probe-2026-10-13.json](../../results/benchmarks/scramble-leo-probe-2026-10-13.json).
  It searches a synthetic planet star (3.7 d) on 8 and on 4 sectors, TOI-188.01 (an eclipsing binary) and Pi Men c
  as null stars, for scramble seeds 1 to 5 and once unscrambled, and judges every signal with LEO-Vetter's
  false-alarm tests as the threshold run does. Of the 59 scrambled signals, none of the 18 at a harmonic of the true
  period passed. Four on the synthetic star passed every false-alarm test at periods that are no harmonic of 3.7 d:
  37.47 d at SDE 19.52 on 8 sectors, and 16.94 d at 10.15, 19.84 d at 10.35 and 23.53 d at 8.75 on 4 sectors. No
  scrambled signal on TOI-188.01 or Pi Men c passed. This output is a rerun on 2026-10-13; the first run, at e4047f1,
  is recorded only in build notes outside the repository, and the rerun matched its table of all 69 signals in
  period, SDE, outcome and failed tests.
  `test_a_null_peak_made_of_the_stars_own_transits_traces_back_to_them` shows the scramble building such a peak from
  the star's own transits.
- The scramble's tests in [tests/test_scramble.py](../../tests/test_scramble.py), with its negative control
  `test_scramble_decoheres_a_planet` and `test_placement_gap_outlasts_detrend_break_tolerance`.
- The threshold run, [results/benchmarks/20261014T175116Z-threshold-0d6748e-40ac/threshold.json](../../results/benchmarks/20261014T175116Z-threshold-0d6748e-40ac/threshold.json),
  with every dropped null signal in [null_dropped.csv](../../results/benchmarks/20261014T175116Z-threshold-0d6748e-40ac/null_dropped.csv). On the null
  run `20261013T151227Z-search-b76fd0b-6c16` (30,195 sample stars, 30,175 searched with status `ok`, 62,102 signals) and the snapshot
  `2026-10-13T163454Z`, the harmonic exclusion dropped 877 signals and the host exclusion 1,574 more, on 832 of the
  null's sample stars, leaving 29,343 stars in the null and 1.03 expected false alarms. LEO-Vetter judged the 1,200
  highest remaining signals, none unjudged. The threshold is SDE 20.24 (TIC 309963553 at 39.39 d, 5 transits), above
  the floor of 9.0; it does not trace back to the star's own transits. Every one of the 20 highest null signals failed
  a false-alarm test.
- The sector structure the scramble splits (Task 6 Step 6),
  [results/benchmarks/sector-structure-2026-10-13.txt](../../results/benchmarks/sector-structure-2026-10-13.txt).
