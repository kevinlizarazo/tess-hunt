# 0014: Vet constants that decide outcomes move from code into vet-v2

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

M1's final review (R8) found values that decide vet outcomes written in code rather than in `criteria/vet-v1.toml`:
the red-noise binning rules in `red_noise_beta`, the fit's minimum cadence count and minimum acceptance in
`fit_transit`, and the period grid of the held-out season refit in `refit_ephemeris`. A change to any of them would
change results with no criteria change and no decision record.

## Decision

- `criteria/vet-v2.toml` holds them with the values M1's code held: `[red_noise]` `exclude_width`, `min_bins`,
  `kept_bin_fraction` and `min_cadences_per_bin`; `[fit]` `min_points` and `min_acceptance`; `[holdout]`
  `refit_resolutions`, `refit_points` and `refit_duration_factors`. The values are unchanged, so no result changes.
- `red_noise_beta` takes the `[red_noise]` section, `refit_ephemeris` the `[holdout]` section, and `fit_transit` reads
  its minimums from `[fit]`. `fit.MIN_ACCEPTANCE` is gone.
- `vet` defaults to `criteria/vet-v2.toml` and `criteria/search-v2.toml`.
- `criteria/vet-v1.toml` stays as M1 published it. Given vet-v1, `vet` fills in the values its code held
  (`VET_V1_CODE_VALUES` in `src/tess_hunt/vet.py`), so M1's vets reproduce.

## Evidence

- M1's tests in [tests/test_photometry_checks.py](../../tests/test_photometry_checks.py),
  [tests/test_holdout.py](../../tests/test_holdout.py), [tests/test_fit.py](../../tests/test_fit.py),
  [tests/test_physical_checks.py](../../tests/test_physical_checks.py) and [tests/test_vet.py](../../tests/test_vet.py)
  now read vet-v2 and pass with the outcomes they asserted under vet-v1.
- [tests/test_fit.py](../../tests/test_fit.py): `test_fit_window_is_a_half_width` (the minimum cadence count comes from
  the criteria) and `test_fit_below_the_criteria_acceptance_raises`.
- [tests/test_vet.py](../../tests/test_vet.py): `test_vet_v1_gets_the_values_its_code_held` (vet-v1's filled-in values
  equal vet-v2's) and `test_clean_planet_still_advances_under_vet_v1_with_m1s_density_error`.
