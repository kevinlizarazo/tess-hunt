# 0012: LEO-Vetter runs with the paper text's thresholds on native cadence; pixels use its 15" rule

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

The spec (section 4.1) runs "LEO-Vetter 1.2.0: its automated false-alarm and false-positive tests, in their published
configuration". leo-vetter 1.2.0's code defaults set `max_SES_to_MES` to 0.8 and `ASYM` to 8; the paper's text and its
tutorial 5 give 0.88 and 10. Re-scoring the repository's own metric tables with the text's values reproduces the
paper's completeness and effectiveness; the code defaults do not. The paper's cadence study found that rebinning hurts.
Its pixel test is an offset above 15" in the best-quality sector, with no uncertainty, and a failed cutout leaves the
offset NaN, which the comparison passes.

## Decision

- Every LEO-Vetter threshold is written out in `criteria/triage-v1.toml` `[leo]`, with the paper text's 0.88 and 10.
- `compute_flux_metrics` takes 1.2.0's arguments, written out in `[leo_metrics]`.
- LEO-Vetter gets the native-cadence light curve, re-detrended with the signal's transits held out of the trend and the
  star's other signals and known objects dropped.
- LEO-Vetter's star is the TIC radius, mass, Teff, log g and density with their errors. The density is the TIC's when
  it comes with an error, else mass over radius cubed with the error carried from the mass and radius errors. A missing
  radius, mass or Teff error takes its `[leo_metrics]` default.
- `tess_hunt.leo` lists the metrics each test reads, on the branches where they can change its verdict. A test whose
  comparison reads a non-finite or missing metric is unknown, and the outcome is inconclusive, never a pass. A missing
  stellar value is inconclusive.
- Pixels: the published 15" rule on the best-quality sector among the latest five with data, for signals that pass the
  flux tests and novelty. NaN, no usable sector or an exception is inconclusive. Controls: TOI-1175.01 and TOI-1058.01
  must fail; TOI-1399.01 passes the rule and is recorded as its known miss.

## Limitations

On crowded stars, QLP's S99 to S103 depths read shallower than SPOC's crowding-corrected depths
([qlp-dilution-2026-10-13.txt](../../results/benchmarks/qlp-dilution-2026-10-13.txt)). QLP Data Release Notes 004
(https://arxiv.org/abs/2603.22236) say QLP's ePSF model removes contamination from nearby stars as of Sector 94. For a
signal seen mainly in QLP sectors, LEO-Vetter's radius tests (`large` and `vshaped`) can read a planet too small.

## Evidence

- Unit tests in [tests/test_leo.py](../../tests/test_leo.py), including
  `test_paper_thresholds_differ_from_the_code_only_where_decided`,
  `test_evaluate_counts_a_nan_input_as_unknown_not_a_pass`,
  `test_evaluate_judges_a_branch_only_where_it_can_change_the_verdict`,
  `test_leo_star_density_is_the_tic_value_else_mass_over_radius_cubed` and the synthetic controls
  `test_leo_clean_planet_is_a_candidate`, `test_leo_sinusoid_is_false_alarm` and
  `test_leo_sinusoid_at_four_times_its_period_is_false_alarm`; the pixel tests in
  [tests/test_pixels.py](../../tests/test_pixels.py).
- A deep eclipsing binary searched at half its period is rejected as a false alarm by the individual-transit test
  (`invalid_transits`), and a shallower one as a false positive by `odd_even`:
  `test_leo_deep_eclipsing_binary_is_a_false_alarm_on_its_individual_transits` and
  `test_leo_eclipsing_binary_at_twice_the_period_is_a_false_positive` in [tests/test_leo.py](../../tests/test_leo.py).
- Kunimoto et al. 2025, https://arxiv.org/abs/2509.10619, sections 3, 4.5 and 6.2.
- The pixel controls against TESScut on 2026-10-16,
  [results/triage/pixel-controls-2026-10-16.txt](../../results/triage/pixel-controls-2026-10-16.txt)
  (`test_real_nearby_eb_controls`, controls in [benchmarks/pixel_controls.csv](../../benchmarks/pixel_controls.csv)):
  TOI-1058.01 and TOI-1175.01 fail the pixel check as expected, at best-quality offsets of 21.47" and 25.06", and
  TOI-1399.01 passes at 11.63", the 15" rule's recorded miss. The file lists every sector's offset and quality. A first
  run on 2026-10-14 gave the same outcomes; its log recorded no offsets and was replaced by this one.
- The pixel-timing check on the difference images of the 2026-10-14 control run,
  [results/triage/pixel-timing-2026-10-14.txt](../../results/triage/pixel-timing-2026-10-14.txt): after 2020-10-26
  transit-diffImage's bundled ephemeris gives no barycentric correction, so in the 12 control sectors after that date
  its pixel times sit 4.83 to 8.28 minutes off TESScut's barycentric times (0.09 to 0.58 minutes in the 3 before), and
  2.6% to 11.0% of the in-transit cadences differ between its in-transit window and the one on TESScut's times. The
  limit, set before the check, was a fifth of a sector's in-transit cadences. The file is the output of
  [benchmarks/pixel_timing.py](../../benchmarks/pixel_timing.py).
- The production triage run,
  [results/triage/20261015T155441Z-triage-7b12e25-3f57](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/summary.md):
  of the 2,993 signals at or above the threshold, LEO-Vetter passed 57, failed 2,932 (2,825 as false alarms, 107 as
  false positives) and left 4 inconclusive. The pixel check ran on the 15 that also passed novelty: 9 passed and 6
  failed, at offsets of 15.6" to 92.8". Of the 208 signals matching a catalogued eclipsing binary, on their own star
  or a neighbour, at its period or a harmonic, LEO-Vetter rejected 206; of the 56 matching a catalogued candidate
  (TOI, CTOI, RAVEN or T16) at its period and no eclipsing binary, it passed 18. The tests failed most often were
  `non_unique` (1,775 signals) and `unphysical_duration` (1,578). The counts and their definitions are in
  [leo-strictness-2026-10-16.txt](../../results/triage/leo-strictness-2026-10-16.txt), written by
  [benchmarks/leo_strictness.py](../../benchmarks/leo_strictness.py), which reruns novelty's matching on the run's
  catalog snapshot and targets table; those two are not published.
