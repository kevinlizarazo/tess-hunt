# 0035: Held-out seasons count only the training seasons whose data hold a transit

- Date: 2026-10-20
- Status: Proposed (awaiting the maintainer)

## Context

The held-out season check refits the ephemeris without one season, then measures the depth only where the refit
predicts transits in that season ([decision 0004](0004-holdout-training-seasons.md)). 0004 made a held-out season
untestable when its training set spans fewer than `min_training_seasons = 2` seasons, because:

> With two seasons, each refit sees a single season. The error on a period fitted to a few weeks of data grows with
> every cycle across a gap of a year or more, and the check measures depth only inside the central half of each
> predicted transit. The predicted transits drift out of that window, so a real planet seen in two seasons was usually
> marked missed and failed the check. Review reproduced this with synthetic light curves over many seeds. With three
> seasons every training set spans a gap and the period holds.

`criteria/vet-v3.toml` says it beside the value: "a period fitted on one season can't predict a season a year away".
The code counted a training season when it had any cadences (`holdout.py:111` at f9c55b1,
`len(np.unique(labels[train]))`), not when its data held a transit. A season whose transits all fall in its gaps gives
the refit nothing to fit, so the code met 0004's letter and broke its intent.

Task 13's adversarial review of 441010857-1 found it (its finding F1; both refuters reproduced it and neither refuted
it). S11's only transit (epoch 0, BTJD 1613.83) falls in its mid-sector gap (1609.162 to 1615.912), so season 1 was
predicted from S64's single transit. The BLS grid, not transits, set the refit period: 268 of 801 grid periods sit
within 0.5 of the best likelihood. The prediction put the two S38 transits 3.60 h and 3.47 h from the flat fit's
mid-times, against a core half-width of 0.37 h, the season was missed and the check failed. At the flat fit's
ephemeris, season 1 holds an 11.8 sigma transit. The M3 design, section 4.8: "A finding that shows a check is wrong
goes to a decision record, never a quiet rerun." This is that record.

## Decision

1. **The fix.** A training season counts toward `min_training_seasons` only when its own cadences hold at least
   `min_points` cadences inside the core window of a transit predicted at the check's input ephemeris, the one the
   refit starts from: `box_depth`'s window (`core_fraction` of the duration) and count. A held-out season with fewer
   such training seasons is `untestable`, with a reason such as "1 of 2 training seasons hold a transit in their data,
   need 2: one season can't predict a season a year away". Every season's evidence records both counts:
   `training_seasons`, those with data, as before, and `training_seasons_with_transits`.
   - It changes how `min_training_seasons` is applied, not its value. It reads only `[holdout]`'s `min_points` and
     `[depth]`'s `core_fraction`; no criteria key is added and nothing under `criteria/` changes.
   - It only makes seasons untestable. With fewer than two seasons tested the check is inconclusive, which kills
     nothing ([decision 0028](0028-outcomes-and-calls.md)).
   - A held-out season with no transit in its data is `no_predicted_transit_in_data`, as before.
   - The check's code serves every criteria version, so a vet under vet-v1 or vet-v2 applies the rule too. By the
     screen's count (item 2) it reaches none of the four vets published under `results/benchmarks/`.
2. **Reach** ([the evidence](../../results/benchmarks/holdout-training-seasons-2026-10-20.md)): the review's screen
   of the runs' `checks.json`, then the fixed check run on each signal's rebuilt inputs, which reproduces every season
   it leaves alone field for field.
   - **441010857-1:** fail to inconclusive, in the vet and in the evidence-only vet. The signal stays killed by
     density (its review's F2).
   - **438857197-1:** pass to inconclusive in the vet; its evidence-only vet keeps the pass, its QLP season giving
     each tested season a second training season with a transit. It is a promoted second-list row
     ([decision 0033](0033-second-list-decisions.md)). A pass needs every vet-v3 check passed (0028, bar item 1), so on
     the rerun's record it can't be passed.
   - **The controls:** no holdout outcome changes, so the published controls stand, 0031's holdout rates among them.
3. **What the rule costs 438857197-1.** Its S11, at 30-minute cadence, holds 8 cadences inside the transit and 4 in
   the core after detrending, under `min_points`, so it no longer counts. Yet it pins the refit's period: trained with
   it, as the vet was, seasons 1 and 2 are predicted 0.09 h and 0.07 h from the flat fit, against a core half-width of
   0.25 h, and show the transit at 8.3 and 7.0 sigma; trained without it, 8.88 h and 6.86 h off. Counting cadences
   inside the whole transit instead of the core would keep S11 and the pass, and would still leave 441010857-1's S11
   out (0 cadences); in the three runs it changes nothing else. This record takes the core window, the window every
   depth in the check is measured in; the whole transit is the alternative put to the maintainer.
4. **Rerun.** The signals' chain is being redone for [decision 0034](0034-neighbour-table-epochs.md) (its item 2),
   and this rides in the same rerun. Compared run against run, every holdout outcome but these two signals' must
   reproduce, in the vet and in the evidence-only vet; every season gains `training_seasons_with_transits`. The
   controls are not rerun (0034, item 3), and no control outcome changes here.

## Evidence

- [tests/test_holdout.py](../../tests/test_holdout.py):
  - `test_a_training_season_whose_transit_falls_in_a_gap_does_not_count`: three seasons, the last cut to four days of
    S28 around one transit that falls in a data gap. The first two seasons are untestable with the reason, the last
    is `no_predicted_transit_in_data` and the check is inconclusive. Before the fix the check passed.
  - `test_a_training_season_with_one_transit_in_its_data_counts`: the same four days with the transit in the data.
    Every season trains on two seasons with transits, and all three are predicted.
  - `test_a_season_without_cadences_in_predicted_transits_is_not_tested` gains a fourth season. On its three, each
    tested season trained on one season with transits, the case this record makes untestable.
  - The tests 0004 cites pass unchanged.
- [`holdout-training-seasons-2026-10-20.md`](../../results/benchmarks/holdout-training-seasons-2026-10-20.md): the
  screen, the fixed check on the three runs' rebuilt inputs, 438857197-1's refits with and without S11, and the core
  window against the whole transit, each script quoted in full with its output and command. A read-only analysis
  outside the pipeline that gates nothing.
- Task 13's review of 441010857-1, finding F1 with both refuters (`review.json`), goes into the signal's record with
  its call; it is not yet under `results/`.
