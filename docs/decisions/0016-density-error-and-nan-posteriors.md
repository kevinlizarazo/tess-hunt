# 0016: The density tension uses the posterior's side facing the TIC value; NaN posteriors are inconclusive

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

M1's density check divides the distance between the fit's median log density and the TIC's by the fit error and the
TIC error added in quadrature, with the fit error taken as half the 16th to 84th percentile spread. Log-density
posteriors are skewed, often with a long tail. When the TIC value sits in that tail, the symmetric error understates
the denominator, and the check can falsely fail a planet around a slightly evolved star.

M1 also left two ways for a broken posterior to pass. A NaN impact parameter counts as non-grazing, so `shape` passes
it; a NaN log density gives a NaN tension, which compares False against the threshold, so `density` passes it.

## Decision

- Under vet-v2, the fit error in the density tension is the side of the posterior facing the TIC value: the median
  minus the 16th percentile when the TIC value is lower, the 84th percentile minus the median when it is higher. The
  evidence records the side used (`fit_log_rho_sd`) and both sides (`fit_log_rho_minus`, `fit_log_rho_plus`).
- A posterior with any non-finite sample, in any parameter, makes `shape` and `density` inconclusive. This holds under
  vet-v1 too, since the rigor rules never let a non-finite statistic pass. M1's two published vets report finite fit
  summaries, which a NaN sample would have made NaN, so neither is affected.
- vet-v1 keeps the symmetric error, so M1's vets reproduce: `vet` passes `symmetric_error` to `density` for a vet-v1
  file.

## Evidence

- [tests/test_physical_checks.py](../../tests/test_physical_checks.py): `test_density_uses_the_side_facing_the_tic_value`
  (a posterior with a long low tail and the TIC value inside it passes, where the symmetric error fails it),
  `test_density_still_fails_on_the_short_side`, `test_nan_samples_are_inconclusive` (a NaN impact parameter makes both
  checks inconclusive) and `test_vet_v1s_symmetric_density_error_still_fails_the_long_tail`.
- [tests/test_vet.py](../../tests/test_vet.py): `test_clean_planet_still_advances_under_vet_v1_with_m1s_density_error`.
- M1's published vets: [Pi Men c](../../results/benchmarks/20261009T190108Z-vet-c7a2625-fe36/checks.json) and
  [TOI-188.01](../../results/benchmarks/20261009T191134Z-vet-c7a2625-ce0e/checks.json).
