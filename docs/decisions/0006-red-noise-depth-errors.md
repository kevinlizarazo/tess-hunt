# 0006: Vet depth errors carry each sector's red-noise factor

- Date: 2026-10-09
- Status: Accepted (approved by the maintainer)

## Context

Detrend sets each sector's error to that sector's scatter, and `box_depth` divides it by the square root of the
number of cadences it averages. That is right for white noise. On a bright star observed at 2-min cadence, the
residuals stay correlated over hours, so averaging a transit's worth of cadences cuts the noise less than the square
root says and the depth errors come out too small.

Vetting Pi Men c (TIC 261136679), a confirmed planet with many SPOC 2-min sectors, showed the effect. In the run
`20261009T181228Z-vet-0801864-99a5` the fit's period and epoch matched the TOI, yet the per-sector depth check failed
on a large chi-square and the held-out season check failed on one season's depth tension. Measured on the same
detrended light curve, the out-of-transit binned scatter at the core timescale exceeded the white-noise expectation in
every sector, by a different amount in each. With each sector's depth error scaled by that factor, the sector depths
agreed.

The real eclipsing binary TOI-188.01 (TIC 280830734) failed the odd and even check in the run
`20261009T182044Z-vet-0801864-e073`. A fix for Pi Men c must not let it through.

## Decision

- `red_noise_beta` in `src/tess_hunt/checks/photometry.py` estimates a red-noise factor per sector by the
  time-averaging method. It uses only cadences outside a window of three transit durations centred on each transit of
  the signal under test, bins them into consecutive bins of the timescale, and keeps bins that hold at least 80% of
  the fullest bin's cadences. Beta is the standard deviation of the kept bin means over the median error divided by
  the square root of the median cadences per kept bin, floored at 1.
- A sector with fewer than 20 kept bins, or fewer than 3 cadences per bin on average, gets beta 1 and a note saying
  why. A window shorter than a few cadences can't build up correlated noise by averaging, so there is nothing to
  correct.
- `vet_signal` measures beta at the core timescale, `[depth] core_fraction` times the duration, after detrending. It
  multiplies each sector's errors by its beta and runs the odd and even, secondary eclipse, per-sector depth and
  held-out season checks on that light curve. The held-out season's BLS refit uses the same errors.
- The transit fit, and the shape and density checks built on it, keep the white errors, as does the novelty check,
  which does not use the light curve.
- The vet report records each sector's beta, bin count, cadences per bin and any note under `red_noise`.
- No criteria value changes.

## Evidence

- Vet runs `20261009T181228Z-vet-0801864-99a5` (Pi Men c) and `20261009T182044Z-vet-0801864-e073` (TOI-188.01),
  written under the data directory's `runs/`. They are not yet published to `results/`; link them here once they
  are.
- Unit tests in [tests/test_photometry_checks.py](../../tests/test_photometry_checks.py):
  `test_red_noise_beta_is_one_on_white_noise` (white noise at 2-min and 30-min cadence gives beta near 1, and a window
  under three cadences gives 1 with a note), `test_red_noise_beta_sees_correlated_noise`,
  `test_sector_depth_red_noise_fails_on_white_errors_and_passes_inflated` (a constant-depth planet in correlated noise
  fails the per-sector depth check with white errors and passes with the inflated ones) and
  `test_with_red_noise_scales_each_sectors_errors`.
- [tests/test_vet.py](../../tests/test_vet.py): `test_report_carries_red_noise_and_depth_errors_use_it`. The existing
  photometry, held-out season and vet tests pass unchanged.
- Method: Pont, Zucker and Queloz 2006, MNRAS 373, 231; Winn et al. 2008, ApJ 683, 1076.
