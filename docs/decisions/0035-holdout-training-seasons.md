# 0035: Held-out seasons count only the training seasons whose data hold a transit

- Date: 2026-10-20
- Status: Accepted (approved by the maintainer on 2026-10-20)

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
mid-times, against a core half-width of 0.37 h. The season was missed and the check failed. At the flat fit's
ephemeris, season 1 holds an 11.8 sigma transit. The M3 design, section 4.8: "A finding that shows a check is wrong
goes to a decision record, never a quiet rerun." This is that record.

On 2026-10-20 the maintainer was asked: "Fix it now and run it in the same rerun as the neighbour fix, with its own
decision record, 0035". Before he answered, the question was corrected: "I've switched the fix to count a training
season when its transit window holds enough data points" (item 2 says why). His answer, at about 17:08 UTC: "yes".
This record writes down that call.

## Decision

1. **The fix.** A training season counts toward `min_training_seasons` only when its own cadences hold at least
   `min_points` cadences inside the transits predicted at the check's input ephemeris, the one the refit starts from,
   over each transit's whole duration (`in_transit` at its default width of one duration). A held-out season with
   fewer such training seasons is `untestable`, with a reason such as "1 of 2 training seasons hold a transit in their
   data, need 2: one season can't predict a season a year away". Every season's evidence records both counts:
   `training_seasons`, those with data, as before, and `training_seasons_with_transits`.
   - **The whole transit, not the core.** A season constrains the refit's period when its data hold a transit. The
     core (`core_fraction` of the duration) is the window the check measures depths in, not a test of whether a
     transit is there: a season sampled every 30 minutes can hold few core cadences and still time its transits, as
     438857197-1's S11 does (item 2).
   - It changes how `min_training_seasons` is applied, not its value. It reads only `[holdout]`'s `min_points`; no
     criteria key is added and nothing under `criteria/` changes.
   - It only makes seasons untestable. With fewer than two seasons tested the check is inconclusive, which kills
     nothing ([decision 0028](0028-outcomes-and-calls.md)).
   - A held-out season with fewer than `min_points` core cadences of its own is `no_predicted_transit_in_data`, as
     before.
   - The check's code serves every criteria version, so a vet under vet-v1 or vet-v2 applies the rule too. By the
     review's screen it reaches none of the four vets published under `results/benchmarks/`.
2. **How the window was chosen.** The first version of the fix counted core cadences, the window and count of
   `box_depth`. Run on the three M3 vetting runs it also turned 438857197-1's holdout pass inconclusive. That signal's
   S11, at 30-minute cadence (`cadence_s` 1800 in `sources` of its `checks.json` in vetting run
   `20261020T010149Z-vetting-run-62882b5-c3ee`), holds 8 cadences inside the transit and 4 in the core after detrending,
   so the core count left it out, yet it pins the refit's period. Trained with S11, as the vet was, seasons 1 and 2 are
   predicted 0.09 h and 0.07 h from the flat fit, against a core half-width of 0.25 h, and show the transit at 8.3 and
   7.0 sigma. Trained without it, they are predicted 8.88 h and 6.86 h off and show -0.5 and -1.0 sigma. The fix was
   switched to the whole transit before the maintainer answered. Both windows' reach on the three runs, from the runs'
   own season statuses:

   | Run | Core window | Whole transit |
   |---|---|---|
   | `20261020T010149Z-vetting-run-62882b5-c3ee` (the 19 signals) | 441010857-1 fail to inconclusive; 438857197-1 pass to inconclusive | 441010857-1 fail to inconclusive |
   | `20261020T011247Z-vetting-run-62882b5-d92b` (its evidence-only twin) | 441010857-1 fail to inconclusive | 441010857-1 fail to inconclusive |
   | `20261017T155223Z-vetting-run-62882b5-4867` (the 24 controls) | none | none |

   The windows differ only on 438857197-1's S11. 441010857-1's S11 holds no cadence inside a transit at all.
3. **Reach** ([the evidence](../../results/benchmarks/holdout-training-seasons-2026-10-20.md)): the fixed check, run
   on each signal's inputs rebuilt as the vet builds them, reproduces every season it leaves alone field for field.
   - **441010857-1:** fail to inconclusive, in the vet and in the evidence-only vet. The signal stays killed by
     density (its review's F2).
   - **438857197-1:** its holdout pass stands. It is a promoted second-list row
     ([decision 0033](0033-second-list-decisions.md)). The review's screen flags it because the screen counts core
     cadences, at each season's own refit ephemeris.
   - **The controls:** no holdout outcome changes, so the published controls stand, 0031's holdout rates among them.
4. **Rerun.** The signals' chain is being redone for [decision 0034](0034-neighbour-table-epochs.md) (its item 2),
   and this rides in the same rerun. Compared run against run, every holdout outcome but 441010857-1's must
   reproduce, in the vet and in the evidence-only vet; every season gains `training_seasons_with_transits`. The
   controls are not rerun (0034, item 3), and no control outcome changes here.

## Evidence

- [tests/test_holdout.py](../../tests/test_holdout.py):
  - `test_a_training_season_whose_transit_falls_in_a_gap_does_not_count`: three seasons, the last cut to four days of
    S28 around one transit that falls in a data gap. The first two seasons are untestable with the reason, the last
    is `no_predicted_transit_in_data` and the check is inconclusive. Before the fix the check passed.
  - `test_a_training_season_whose_transit_has_few_core_cadences_still_counts`: the same four days with the transit
    in the data at 30-minute cadence, 6 cadences inside it and 3 in its core. The last season is too sparse to
    measure as held out, yet every season trains on two seasons with transits, the first two are predicted and the
    check passes. Under the core count the first two were untestable.
  - `test_a_season_without_cadences_in_predicted_transits_is_not_tested` gains a fourth season. On its three, each
    tested season trained on one season with transits, the case this record makes untestable.
  - The tests 0004 cites pass unchanged.
- [`holdout-training-seasons-2026-10-20.md`](../../results/benchmarks/holdout-training-seasons-2026-10-20.md): the
  review's screen, the fixed check on the three runs' rebuilt inputs, 438857197-1's refits with and without S11, both
  windows' counts and outcomes on the three runs, and the screen on the published vets, each script quoted in full
  with its output and command. A read-only analysis outside the pipeline that gates nothing.
- Task 13's review of 441010857-1, finding F1 with both refuters (`review.json`), goes into the signal's record with
  its call; it is not yet under `results/`.
