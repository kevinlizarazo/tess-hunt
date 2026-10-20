# 0031: The known planets vet-v3's controls fail: each one understood, no criteria change

- Date: 2026-10-20
- Status: Accepted (approved by the maintainer on 2026-10-19, after the controls' results were seen)

## Context

The M3 design (section 4.3) vets the 20 confirmed planets of `benchmarks/known_planets.csv` under vet-v3, at their
catalog ephemerides, and publishes each check's pass rate on them: "A check that fails a confirmed planet is
understood, with a decision record and Kevin's call, before it can kill a candidate." `criteria/vet-v3.toml` was
committed before the first control vet, so any change to it now is a new version with its own record.

The controls ran on 2026-10-17. The published controls run, `20261020T082333Z-benchmark-controls-16418d2-f45a`
([summary.md](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md), "the summary"
below, with its `controls.csv` and `pass_rates.csv`), gathers the vetting run, the TRICERATOPS runs and the pixel check
on the known planets. Besides novelty, which fails every known planet by design, five confirmed planets fail a vet-v3
check and three more are inconclusive on holdout and signal_present. A read-only diagnosis,
[`vet-v3-control-diagnosis-2026-10-17.md`](../../results/benchmarks/vet-v3-control-diagnosis-2026-10-17.md) ("the
diagnosis"), rebuilt each one from the run's files and found no coding error. It was made outside the pipeline, with
no committed script, and gates nothing.

The build stopped at Task 11 Step 7 with the results, the diagnosis and its recommendations. On 2026-10-19, after the
results were seen, the maintainer answered: "please go with your recommendations, keeping in mind i want integrity and
correctness." This record writes down that call. It is a call made on these results, not a rule set before them.

## Decision

- **No criteria change.** vet-v3 stands, and a fail on any of these checks still kills a candidate (decision 0028).
- **Each fail is understood.** The outcome is the summary's ("Failed and inconclusive controls, by check"); the cause
  is the diagnosis's.
  - **TOI-107.01 (WASP-94 A b) and TOI-747.01 (WASP-87 b), secondary.** Outcome: a dip at phase 0.5 of 94 ppm at 3.6
    sigma, and of 119 ppm at 3.2 sigma. Cause: probably each planet's own occultation, which vet-v3's secondary makes
    no allowance for. WASP-87 b's thermal emission alone can reach 241.6 ppm in the TESS band; WASP-94 A b's dip
    needs a geometric albedo near 0.3. No published TESS occultation was found for either planet (the archive's `ps`
    table and a web search), so this is unconfirmed. For TOI-747.01 the diagnosis adds a check-logic mismatch: the
    box's errors are scaled for red noise at half its timescale, and measured against scrambled periods the dip is
    about 2.5 sigma (diagnosis, items 1 and 2).
  - **TOI-191.01 (WASP-8 b), density.** Outcome: the transit implies 0.611 g/cm3 where the TIC gives 1.41, 3.5 sigma.
    Cause: an eccentric orbit (e 0.304, ω 274°), transiting near apoapsis; corrected for it, the tension is 0.44 sigma
    (diagnosis, item 3).
  - **TOI-396.01 (HR 858 c), sector_depth and holdout.** Outcome: depths disagree across sectors (p = 1.1e-14),
    transits are missing where predicted in all four seasons, and signal_present is inconclusive at 1.2 sigma. Cause:
    transit-timing variations of 0.30 to 0.40 d, near a 5:3 resonance with HR 858 b, so no linear ephemeris folds all
    four seasons (diagnosis, item 4).
  - **TOI-576.01 (WASP-166 b), holdout.** Outcome: transits missing where predicted in season 3. Cause: one transit
    half covered after a 5.2-hour data gap; without it the season passes, at a tension of 1.79 (diagnosis, item 5).
  - **TOI-451.02, TOI-451.03 and TOI-1097.02, holdout and signal_present inconclusive.** Outcome: combined depths of
    2.7, 3.1 and 1.1 sigma, below 7, and too few seasons to test. Cause: low SNR, 3.4 to 4.9 expected, on two young
    stars whose variability inflates the errors, with stale TOI periods for TOI-451.03 and TOI-1097.02 (diagnosis, item
    6). An inconclusive is a lack of evidence and kills nothing (0028).
- **What it means for candidates.** Task 13's review screens each kind of kill for the causes above:
  - a secondary that could be the planet's own occultation (for every shortlisted signal the diagnosis puts that bound
    at 8.7 ppm or less with the albedo capped at 0.5, and 15.2 ppm or less at an albedo of 1.0);
  - a density tension that an eccentric orbit could explain;
  - a holdout or sector_depth fail that transit-timing variations or a partly covered transit could explain;
  - an inconclusive at low SNR.
- **TOI-396.01 leaves the known-set pass rate.** Its control ephemeris is linear and can't fold the planet, and the
  checks did what they are built to do. The summary publishes both rates: over all 20 controls and over the 19 without
  it (for example, sector_depth 19 of 20 and 19 of 19, holdout 15 of 20 and 15 of 19).
- **Not taken.** The diagnosis's "Changes and their reach" weighed these; each would be a vet-v4 with its own record:

  | Change | Fixes | Negative controls | Shortlist |
  |---|---|---|---|
  | Planet-aware secondary bound, albedo cap 0.5 | TOI-107.01, TOI-747.01 | TOI-1399.01 still fails, by 3.9 sigma or more over the bound | the 3-sigma line moves by 8.7 ppm at most |
  | Secondary errors scaled by beta at the full duration | TOI-747.01 | TOI-1399.01 still fails (8.88 sigma) | secondary errors 0.99 to 1.36 times larger |
  | Eccentricity term of 0.11 dex in the density tension | TOI-191.01 | TOI-188.01 still fails (4.34); TOI-1399.01's density passes (2.71), its secondary still fails | tensions 3 to 30% lower, most for TIC 48010903 |
  | Partly covered transits left out of depth comparisons | TOI-576.01 | TOI-1175.01's holdout fail stays | may cost holdout or odd/even power at 3 to 5 transits |
  | Archive ephemerides for TOI-451.03 and TOI-1097.02 | nothing (they stay inconclusive at 4.1 and 3.9) | none | none |

  Why none was taken: the secondary bounds would vet the shortlist almost exactly as vet-v3 does, close to neutral
  in the diagnosis's words (their phase-0.5 errors are unknown until they are vetted, and the bound moves the 3-sigma
  line by up to 8.7 ppm); the density term loosens the check most on TIC 48010903, the deepest, highest-SNR signal on
  the shortlist; and the partial-transit rule could cost power on the signals with the fewest transits. A lower pass
  rate on the known set is the cost, and it is published.
- **Not covered here.** TRICERATOPS is inconclusive on four known planets (the summary): TOI-747.01 (mean FPP 0.568
  in the summary, sd 0.458 in `controls.csv`; decision 0026's Controls paragraph), TOI-451.03 and TOI-1097.02 (NFPP
  between the bars; [decision 0032](0032-nearby-binary-triceratops.md)), and TOI-396.01 (mean FPP 1, on a linear fold
  as well; its cause was not diagnosed further). The pixel check fails four known planets (TOI-144.01, TOI-2011.02, TOI-396.03 and
  TOI-4307.01, the summary). It is triage-v1's check, not vet-v3's: a pixel fail keeps a signal off triage's
  shortlist, and the check's completeness on the known set belongs to Task 15's triage completeness. This record does
  not decide it.

## Evidence

- The controls run's
  [summary.md](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md), with
  [`controls.csv`](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/controls.csv) and
  [`pass_rates.csv`](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/pass_rates.csv): every
  outcome above, both pass-rate tables, and the input runs.
- [The diagnosis](../../results/benchmarks/vet-v3-control-diagnosis-2026-10-17.md): every cause above and the changes
  table, read-only analysis outside the pipeline.
- [tests/test_controls.py](../../tests/test_controls.py): `benchmark controls`, which wrote the summary
  (`test_controls_counts_each_check_over_the_known_planets`, `test_a_left_out_control_leaves_only_the_second_table`).
