# 0011: Every production search carries the known set as positive controls

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

Spec 5.6: each production run includes the known-planet set with masks off, and a run that misses them is invalid.
M1 ran the known set as a separate benchmark. The set is 20 planets on 18 hosts, minutes against a search of days.

## Decision

- `search --production` without `--scramble` needs `--controls benchmarks/known_planets.csv` and
  `--control-targets` (a targets run for the hosts). The hosts are searched again with masks off, as rows tagged
  `control`, alongside the sample.
- Each control is classified against its catalog ephemeris with `recovery.classify` at the run's threshold (the null
  threshold's value; the provisional SDE when no threshold is given).
- A missed `required` planet makes the run invalid: `controls_valid` is false in the summary, the stage exits 1, and
  triage refuses the run. Missed non-required planets are listed as warnings.
- Sample stars must still be covered after fetch (at least four usable sectors, one of S97 to S107); controls are
  exempt, since the known set has its own selection rule.

## Evidence

Unit tests in [tests/test_search.py](../../tests/test_search.py): `test_controls_found_make_a_valid_run`,
`test_a_sample_star_masks_its_known_planet_and_its_control_finds_it`, `test_controls_are_judged_at_the_threshold`,
`test_a_missed_required_control_invalidates_the_run`,
`test_a_control_host_without_a_light_curve_invalidates_the_run`,
`test_a_control_host_missing_from_control_targets_is_refused_before_the_run`,
`test_production_search_needs_threshold_and_controls` and `test_search_skips_a_star_not_covered_after_fetch`. The
production search's [controls.csv](../../results/benchmarks/20261014T205855Z-search-fe29585-cdf2/controls.csv)
(run `20261014T205855Z-search-fe29585-cdf2`, threshold SDE 20.24): all 15 required controls recovered and 17 of 20 in
all; the three missed, TOI-451.02, TOI-451.03 and TOI-1097.02, are not required, and the known-set rerun under
`criteria/search-v2.toml`
([20261013T012650Z-benchmark-known-b62e857-936d](../../results/benchmarks/20261013T012650Z-benchmark-known-b62e857-936d/summary.md))
missed the same three.
