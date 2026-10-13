# 0019: The detection threshold is the highest null SDE that survives LEO-Vetter's false-alarm tests

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

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
  the threshold. It is an upper bound: the sample size counts every target, including those the search will not
  search (no light curve, not covered after fetch, too few points).
- The production search takes the threshold as its `continue_sde`. Triage refuses a search whose criteria or search
  code differ from the null's, whose `continue_sde` is not a finite number at least the threshold it ran with, or whose
  `continue_sde` is below the highest threshold computed for the same criteria and code.

## Limitations

- The scramble keeps part of a real periodic signal: each segment keeps its own transits in phase, so a weaker peak can
  remain near the real period. The decoherence test (`test_scramble_decoheres_a_planet`) bounds it only from above: on
  a synthetic planet, the median over seeds 1 to 5 of the top scrambled SDE over the unscrambled SDE must stay below one
  half. The exclusion above drops such a peak when the object is catalogued and the peak lies within the match
  tolerance of one of its harmonics.
- The scramble can also leave some of a real planet's or binary's own transits evenly spaced by chance, enough for the
  search's `min_transits`. That peak sits at a period that is no harmonic of the real one, and its events are real
  transits of one depth and shape, so the false-alarm tests that compare events have nothing to reject. The exclusion
  matches on period harmonics and misses it. Only `[detrend] mask_sources` objects are masked before the scramble, so
  an uncatalogued planet or binary, a TCE or a catalogued eclipsing binary keeps its transits in the null. One such
  star can set the threshold. The rule stays as decided. For each of the top null signals and the highest surviving
  one, the threshold run searches the star unscrambled (the same detrend, masks and search criteria), traces the null
  signal's in-transit cadences back through the scramble, and records in `threshold.json` whether half or more of them
  fall inside the transits of one signal found there, with that signal's period and SDE and the share. For a signal of
  rank 2 or lower the traced cadences include some the null search had masked for the star's higher-ranked signals.
  The maintainer reviews those rows before the threshold stands.

## Evidence

- Unit tests in [tests/test_threshold.py](../../tests/test_threshold.py): the rule and the guards
  (`test_threshold_is_the_highest_passing_sde_and_stops_early`,
  `test_exclude_known_matches_period_only_on_the_same_star`, `test_check_search_refuses_other_hashes_and_a_grown_null`,
  `test_check_search_refuses_a_continue_sde_below_its_threshold_or_not_a_finite_number`,
  `test_threshold_cli_refuses_a_null_it_cannot_reproduce`,
  `test_threshold_cli_refuses_light_curves_other_than_the_ones_the_null_searched`), unjudged signals
  (`test_leo_job_counts_an_unjudged_signal_as_surviving_and_says_why`,
  `test_an_unjudged_pass_sets_the_threshold_and_evaluation_goes_on_to_a_judged_one`), the trace-back
  (`test_a_null_peak_made_of_the_stars_own_transits_traces_back_to_them` and its negative control
  `test_a_noise_peak_on_a_star_with_a_planet_does_not_trace_back_to_it`) and the command end to end
  (`test_threshold_cli_drops_known_objects_and_traces_the_threshold_row`,
  `test_threshold_cli_counts_unjudged_signals_and_keeps_the_floor`,
  `test_threshold_cli_goes_past_an_unjudged_pass_to_a_judged_one`).
- The scramble's tests in [tests/test_scramble.py](../../tests/test_scramble.py), with its negative control
  `test_scramble_decoheres_a_planet` and `test_placement_gap_outlasts_detrend_break_tolerance`.
- The threshold run's `threshold.json` (Task 14, Step 6), published under `results/` and linked here when it exists.
- The sector structure the scramble splits (Task 6 Step 6), `results/benchmarks/sector-structure-<date>.txt`, linked
  here when it is published.
