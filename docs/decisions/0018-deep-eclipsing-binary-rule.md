# 0018: The fit's Rp/R* bound rises to 1, and a `radius` check fails a body too large for a planet

- Date: 2026-10-13
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

M1's fit bounded Rp/R* below 0.5. An eclipse with a true Rp/R* above that, as an eclipsing binary gives, piled the
posterior up against the bound, and the shape check passed it. No check compared the size of the eclipsing body with
the star, so nothing else caught a stellar companion.

## Decision

- `fit_transit` bounds Rp/R* by `[fit] max_rp_rs`, 1.0 in `criteria/vet-v2.toml`, as LEO-Vetter 1.2.0 does with its
  `max_RpRs` default. The walkers start at most 0.9 of the bound, so an eclipse deeper than the bound allows still
  starts inside the prior.
- A new `radius` check in `src/tess_hunt/checks/physical.py`: the posterior median Rp/R* times the TIC stellar radius,
  in Earth radii. It fails above `[radius] max_rearth`, 22, the limit of LEO-Vetter's `large` false-positive test, and
  passes otherwise. A missing, non-finite or non-positive TIC radius, or an empty or non-finite Rp/R* posterior, is
  inconclusive; without a fit it is inconclusive with the fit's reason, as shape and density are.
- The evidence records the radius in Earth radii, the median Rp/R* and the TIC radius.
- vet-v1 keeps M1's bound of 0.5 (`VET_V1_CODE_VALUES` in `src/tess_hunt/vet.py`) and has no `[radius]` section, so
  `vet` runs no radius check under it and M1's vets reproduce.

## Limitations

The check uses the median Rp/R* and the TIC radius without their errors, so a body near the limit can land on either
side of it. Light from a neighbour dilutes an eclipse and makes the body look smaller, so a blended binary can pass
this check. Triage's pixel check can catch one whose eclipse sits on a resolved neighbour.

## Evidence

- [tests/test_fit.py](../../tests/test_fit.py): `test_deep_eclipse_is_not_pinned_at_the_bound` (a central eclipse with
  a true Rp/R* of 0.6 gives a posterior centred above 0.5 rather than piled at it) and
  `test_eclipse_deeper_than_the_prior_still_starts_inside_it`.
- [tests/test_physical_checks.py](../../tests/test_physical_checks.py):
  `test_radius_negative_control_eclipsing_binary_fails` (Rp/R* 0.6 around a solar-radius star) and
  `test_radius_of_a_planet_passes_and_missing_tic_radius_is_inconclusive`.
- [tests/test_vet.py](../../tests/test_vet.py): `test_clean_planet_advances` (`radius` passes a clean synthetic
  planet), `test_no_cadence_inside_the_transits_leaves_shape_and_density_inconclusive` (radius too) and
  `test_vet_v1_gets_the_values_its_code_held` (vet-v1's bound stays 0.5).
