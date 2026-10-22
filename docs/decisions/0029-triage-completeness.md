# 0029: Triage completeness: what novelty, LEO-Vetter and the pixel check keep of the planets the search finds

- Date: 2026-10-22
- Status: Proposed. The measurements are published; the maintainer's answer to the LEO-Vetter question (below,
  "The maintainer's answer") is not yet given.

## Context

Triage passes a signal on novelty, LEO-Vetter's flux tests and the pixel check
([decision 0012](0012-leo-vetter-configuration.md)). M2's injection run measured the search alone: of 2,000
injections on random production targets it recovered 0.385 at the production threshold
([summary.md](../../results/benchmarks/20261015T131443Z-benchmark-inject-fe29585-8496/summary.md)). In the production
triage run LEO-Vetter failed 2,932 of the 2,993 signals at or above the threshold
([summary.md](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/summary.md)). `docs/design.md` (section 8,
"LEO-Vetter's strictness") notes that LEO-Vetter's thresholds were tuned on QLP light curves of M dwarfs, says triage
therefore misses many real planets, and says M3 measures triage's completeness before any setting changes.

The M3 design (question 3 and section 4.11, approved by the maintainer on 2026-10-16) measures it in two parts:

- **Flux:** each injection that inject run `20261015T131443Z-benchmark-inject-fe29585-8496` recovered is planted and
  searched again as that run did it, and the signal the search matched to it is judged by novelty and LEO-Vetter's
  flux tests as triage run `20261015T155441Z-triage-7b12e25-3f57` judged its signals. `tess-hunt benchmark
  triage-completeness` (`src/tess_hunt/completeness.py`) refuses unless its inputs, `uv.lock`, `leo.py` and the
  triage criteria's novelty and LEO-Vetter sections are the ones those runs used.
- **Pixels:** an injected transit is not in the pixels, so the pixel check runs on the known set's planets at their
  catalog ephemerides, which should all pass.

Then the maintainer decides whether a LEO-Vetter change is worth making. This record gives the numbers for that
question and leaves room for the maintainer's answer.

The two production runs:

- triage completeness, `20261017T040740Z-benchmark-triage-completeness-e6719c6-f34c`, finished on 2026-10-17 at 05:48
  UTC and published with this record
  ([summary.md](../../results/benchmarks/20261017T040740Z-benchmark-triage-completeness-e6719c6-f34c/summary.md), "the
  summary" below, with the CSV tables beside it);
- pixel completeness, `20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33`, published on 2026-10-20 for
  [decision 0033](0033-second-list-decisions.md)
  ([summary.md](../../results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/summary.md), with
  its `pixels.csv`).

## Decision

1. **Novelty and LEO-Vetter on the recovered injections.** The inject run recovered 769 of its 2,000 injections at
   SDE 20.24 or above. The replay reproduced all 769: the summary counts 769 judged, 0 not reproduced and 0 errors,
   and each binned table's `judged` column sums to 769. The shares leave out not-reproduced and error rows
   (`summarise` in `completeness.py`); with none in this run, every share below is over all 769 recovered
   injections. Each was found at its injected period (`rows.csv`'s `alias` is False on every judged row).

   | step | pass | fail | inconclusive |
   |---|---|---|---|
   | novelty | 766 | 0 | 3 |
   | LEO-Vetter flux | 637 | 123 | 9 |

   The counts are `outcomes.csv`'s. Novelty's three inconclusives are one each of `no_period_object`,
   `stale_catalog_epoch` and `known_to_spoc` (`rows.csv`'s `novelty_category`).

2. **The pixel check on the known planets** passes 16 of 20, fails 4 and leaves none inconclusive (`pixels.csv`).
   [Decision 0033](0033-second-list-decisions.md), item 1, understands the four fails: TOI-144.01 and TOI-2011.02 sit
   on saturated hosts and the fit follows the bleed column; TOI-396.03's saturating host barely holds its transit in
   the images; TOI-4307.01's transit is not measurable in a sector's difference image. The pixel check is not binned,
   and the summary's `product` (the inject run's search completeness times `triage_pass`) leaves it out.
   [Decision 0031](0031-known-set-control-fails.md) left this measurement to this record. Nothing here changes the
   pixel check, which M3 keeps frozen (0033, item 5).

3. **The numbers for the LEO-Vetter question.**
   - **The share it calls a planet candidate, by bin.** From the summary: `searched` and `search` are the inject run's
     injections and search completeness, `judged` the recovered injections, `leo_pc` the share LEO-Vetter called a
     planet candidate, `novelty_pass` the share novelty passed, `triage_pass` the share that passed both novelty and
     LEO-Vetter, and `product` `search` times `triage_pass`. The rest of each bin failed or was inconclusive. No
     injection was recovered below an expected SNR of 10 or a radius of 1 Earth radius, so those bins have no shares
     (`nan`).

     | expected SNR | searched | search | judged | leo_pc | novelty_pass | triage_pass | product |
     |---|---|---|---|---|---|---|---|
     | [0.0, 5.0) | 755 | 0 | 0 | nan | nan | nan | nan |
     | [5.0, 7.0) | 89 | 0 | 0 | nan | nan | nan | nan |
     | [7.0, 10.0) | 105 | 0 | 0 | nan | nan | nan | nan |
     | [10.0, 15.0) | 111 | 0.0541 | 6 | 0.833 | 1 | 0.833 | 0.045 |
     | [15.0, 20.0) | 79 | 0.43 | 34 | 0.824 | 1 | 0.824 | 0.354 |
     | [20.0, 50.0) | 290 | 0.686 | 199 | 0.844 | 1 | 0.844 | 0.579 |
     | [50.0, inf) | 571 | 0.928 | 530 | 0.823 | 0.994 | 0.819 | 0.76 |

     | period (days) | searched | search | judged | leo_pc | novelty_pass | triage_pass | product |
     |---|---|---|---|---|---|---|---|
     | [1, 2) | 45 | 0.489 | 22 | 0.909 | 0.955 | 0.864 | 0.422 |
     | [2, 4) | 117 | 0.504 | 59 | 0.932 | 0.983 | 0.915 | 0.462 |
     | [4, 8) | 232 | 0.474 | 110 | 0.945 | 0.991 | 0.945 | 0.448 |
     | [8, 16) | 418 | 0.423 | 177 | 0.864 | 1 | 0.864 | 0.366 |
     | [16, 40) | 1188 | 0.338 | 401 | 0.761 | 1 | 0.761 | 0.257 |

     | radius (Earth radii) | searched | search | judged | leo_pc | novelty_pass | triage_pass | product |
     |---|---|---|---|---|---|---|---|
     | [0.5, 1.0) | 402 | 0 | 0 | nan | nan | nan | nan |
     | [1.0, 2.0) | 400 | 0.0125 | 5 | 1 | 1 | 1 | 0.0125 |
     | [2.0, 4.0) | 393 | 0.285 | 112 | 0.866 | 1 | 0.866 | 0.247 |
     | [4.0, 8.0) | 408 | 0.743 | 303 | 0.861 | 1 | 0.861 | 0.64 |
     | [8.0, 16.0) | 397 | 0.879 | 349 | 0.785 | 0.991 | 0.779 | 0.685 |

   - **The tests it failed them on** (`failed_tests.csv`, injections per test; one injection can fail several).
     False-alarm tests: invalid_transits 26, non_unique 20, data_gapped 15, chi 8, single_event 7, dmm 5,
     sinusoidal 4, weak 4, chases 3, unphysical_duration 2. False-positive tests: odd_even 36, secondary 24. Not
     judged: odd_even 9, asymmetric 1. The nine inconclusives are the injections with a test not judged (`rows.csv`'s
     `leo_reason`: odd_even 8, asymmetric 1), and the ninth odd_even not judged is an injection that failed on
     secondary.
   - **M2's measure of its strictness**, on the production triage run's signals
     ([leo-strictness-2026-10-16.txt](../../results/triage/leo-strictness-2026-10-16.txt)): it failed 206 of the 208
     that match a catalogued eclipsing binary, and passed 18 of the 56 that match a catalogued planet candidate (a
     CTOI, RAVEN, T16 or TOI row) at its own period and no eclipsing binary. Of the 2,932 signals it failed, the tests
     failed most often were non_unique (1,775), unphysical_duration (1,578), sinusoidal (750), invalid_transits (703)
     and chi (701).
   - **What they show on sample A.**
     - On injected planets the search recovers, `leo_pc` barely moves with SNR: 0.823 to 0.844 in each bin from an
       expected SNR of 15 up. By period it peaks at 0.945 from 4 to 8 days and falls to 0.761 from 16 to 40 days,
       the bin that holds 401 of the 769. By radius it is lowest at the largest, 0.785 from 8 to 16 Earth radii.
     - The tests that fail injections are not the ones that fail most production signals. non_unique and
       unphysical_duration, which lead in production, fail 20 and 2 injections. The false-positive tests odd_even and
       secondary fail 36 and 24 injections, whose transits are identical from one to the next and which carry no
       secondary eclipse (`inject` in `src/tess_hunt/inject.py`).
     - The two measures ask different questions: the 56 are catalogued candidates, not confirmed planets, and the
       injections are planets by construction (Limitations).

## The maintainer's answer

**Not yet given.** The question (M3 design, section 4.11): on the numbers in item 3, is a LEO-Vetter change worth
making?

- Answer: _to be filled in, in the maintainer's words, with the date._

Either way M3 builds no change (M3 design, section 5). A change would be its own follow-up after M3: chosen on
injections and controls only, never on which sample signals it would add, with its own decision record, a new
threshold run and a new triage run; any signal it adds gets M3's treatment then (section 4.11). Without one,
LEO-Vetter stays as [decision 0012](0012-leo-vetter-configuration.md) configured it.

## Limitations

- The injections are single planets on circular orbits at the TIC's density, with limb-darkened transits
  ([decision 0008](0008-search-fix.md), `inject.py`), in the light curves of random production targets. How
  LEO-Vetter treats a real planet with an eccentric orbit, transit-timing variations or a companion is not measured.
- The shares are over recovered injections, which lean to large planets: the inject run recovered 5 of its 400
  injections from 1 to 2 Earth radii and none smaller (`by_radius.csv`). Bins with few judged injections (6 from an
  expected SNR of 10 to 15, 5 from 1 to 2 Earth radii) say little.
- The pixel figure is from 20 known planets, several on saturated hosts (0033), not from the sample's typical stars,
  and there is no binned pixel completeness to enter the product.

## Evidence

- The triage completeness run's
  [summary.md](../../results/benchmarks/20261017T040740Z-benchmark-triage-completeness-e6719c6-f34c/summary.md) and,
  in [its directory](../../results/benchmarks/20261017T040740Z-benchmark-triage-completeness-e6719c6-f34c/),
  `rows.csv`, `by_snr.csv`, `by_period.csv`, `by_radius.csv`, `failed_tests.csv`, `outcomes.csv` and
  `provenance.json` (commit e6719c6, the input runs, the criteria files and their hashes): every number in items 1
  and 3 but M2's measure.
- The pixel completeness run's
  [summary.md](../../results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/summary.md) and
  [`pixels.csv`](../../results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/pixels.csv):
  item 2's counts. Their causes: [decision 0033](0033-second-list-decisions.md) and
  [the pixel check's diagnosis](../../results/benchmarks/pixel-check-diagnosis-2026-10-20.md).
- [leo-strictness-2026-10-16.txt](../../results/triage/leo-strictness-2026-10-16.txt), written by
  [benchmarks/leo_strictness.py](../../benchmarks/leo_strictness.py)
  ([decision 0012](0012-leo-vetter-configuration.md)): M2's measure in item 3.
- The inject run's [summary.md](../../results/benchmarks/20261015T131443Z-benchmark-inject-fe29585-8496/summary.md)
  and the triage run's [summary.md](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/summary.md): the counts
  in Context.
- [tests/test_completeness.py](../../tests/test_completeness.py):
  `test_replay_job_runs_leo_on_the_found_signal_not_the_truth`,
  `test_replay_job_does_not_judge_a_search_that_differs_from_the_inject_run`,
  `test_triage_completeness_judges_only_the_recovered_injections`,
  `test_triage_completeness_refuses_another_lock_or_wrapper`, `test_triage_completeness_refuses_other_triage_criteria`,
  `test_triage_completeness_refuses_runs_it_cannot_replay`, `test_summarise_bins_and_counts` and
  `test_pixel_completeness_uses_the_catalog_ephemeris`.
