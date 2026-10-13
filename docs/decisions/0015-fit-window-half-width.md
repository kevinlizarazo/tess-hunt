# 0015: The fit window's key says it is a half-width

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

vet-v1's `[fit] window_durations` is a half-width: the fit keeps cadences within that many transit durations either
side of mid-transit. `in_transit`'s `width`, and with it `[red_noise] exclude_width`, is a full width centred on
mid-transit. The same number therefore spans twice as far in the fit as in the other checks, and the key's name does
not say which convention it follows.

## Decision

- vet-v2 names the key `window_half_width_durations` and keeps vet-v1's value, so no result changes.
- A vet-v1 file's `window_durations` is read as the half-width, as M1's code read it.

## Evidence

- [tests/test_fit.py](../../tests/test_fit.py): `test_fit_window_is_a_half_width` (the fit counts every cadence within
  the half-width either side of mid-transit, more than `in_transit` keeps for the same number), and M1's fit tests
  passing on the renamed key.
- [tests/test_vet.py](../../tests/test_vet.py): `test_vet_v1_gets_the_values_its_code_held` and
  `test_clean_planet_still_advances_under_vet_v1_with_m1s_density_error`.
