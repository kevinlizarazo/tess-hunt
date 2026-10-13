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
  must fail; TOI-1399.01 (11") passes the rule and is recorded as its known miss.

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
  `test_leo_sinusoid_at_four_times_its_period_is_false_alarm`; the pixel tests in Task 16.
- A deep eclipsing binary searched at half its period is rejected as a false alarm by the individual-transit test
  (`invalid_transits`), and a shallower one as a false positive by `odd_even`:
  `test_leo_deep_eclipsing_binary_is_a_false_alarm_on_its_individual_transits` and
  `test_leo_eclipsing_binary_at_twice_the_period_is_a_false_positive` in [tests/test_leo.py](../../tests/test_leo.py).
- Kunimoto et al. 2025, https://arxiv.org/abs/2509.10619, sections 3, 4.5 and 6.2.
- The published pixel control runs (Task 18) are linked here when they exist, with the pixel-timing check: after
  2020-10-26 transit-diffImage's bundled ephemeris gives no barycentric correction, so its pixel times are minutes
  off TESScut's and its in-transit window moves by that much.
