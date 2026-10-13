# 0017: A `signal_present` check asks whether there is a dip at the ephemeris at all

- Date: 2026-10-13
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

M1's final review (R9) vetted pure noise at an arbitrary ephemeris, and the odd and even, secondary eclipse and
per-sector depth checks all passed it. Each of them compares depths, and depths that are all consistent with zero agree
with each other. No check in vet-v1 asks whether there is a dip at the ephemeris in the first place, so those passes
read as support for a signal that isn't there.

## Decision

- `signal_present` in `src/tess_hunt/checks/photometry.py` takes the combined depth of the central
  `[depth] core_fraction` of every transit, inverse-variance weighted as the other depth checks do, on the light curve
  whose errors carry each sector's red-noise factor (decision 0006). Its statistic is that depth over its error.
- It passes when the statistic is at least `[signal_present] min_snr` in `criteria/vet-v2.toml`, 7.0. Below that, with
  fewer than `[signal_present] min_points` in-transit cadences, or with a non-finite statistic, it is inconclusive. It
  never fails: a weak dip is a lack of evidence for a planet, not evidence against one. A signal advances only when
  every check passes, so an inconclusive `signal_present` stops it.
- This is an exception to the spec's rule that every check ships a negative control that makes it fail
  (`docs/design.md` section 5.2): the check's own negative control, pure noise, is inconclusive, and the control that
  matters is the pipeline's, `test_noise_at_an_arbitrary_ephemeris_does_not_read_as_passes` in `tests/test_vet.py`,
  which shows such a signal does not advance.
- The evidence records the depth, its error, the statistic and the cadence count.
- The odd and even, secondary eclipse and per-sector depth checks still run and report as before. Their passes are read
  alongside `signal_present`.
- vet-v1 has no `[signal_present]` section, and `vet` runs the check only when the criteria have one, so M1's vets keep
  their seven checks.

## Evidence

- [tests/test_photometry_checks.py](../../tests/test_photometry_checks.py): `test_signal_present_passes_a_planet`,
  `test_signal_present_negative_control_noise_is_inconclusive` (white noise over nine sectors at an arbitrary
  ephemeris) and `test_signal_present_without_cadences_is_inconclusive`.
- [tests/test_vet.py](../../tests/test_vet.py): `test_noise_at_an_arbitrary_ephemeris_does_not_read_as_passes` (R9's
  case through `vet_signal`: `signal_present` is inconclusive and the signal does not advance),
  `test_clean_planet_advances` (`signal_present` passes a clean synthetic planet) and
  `test_vet_v1_runs_neither_signal_present_nor_radius`.
- M1's two real vets rerun under vet-v2 and published: `signal_present` passes
  [Pi Men c](../../results/benchmarks/20261013T083805Z-vet-456ad38-309e/checks.json) and
  [TOI-188.01](../../results/benchmarks/20261013T083805Z-vet-456ad38-a1cf/checks.json); the evidence carries each
  combined depth and its statistic.
