# 0004: Held-out seasons need two training seasons and a reference from training data

- Date: 2026-10-09
- Status: Accepted (approved by the maintainer)

## Context

The held-out season check fits the ephemeris on every season but one, then measures the depth only where that
ephemeris puts transits in the held-out season. It runs once per season. Review of the first version found two
problems.

- With two seasons, each refit sees a single season. The error on a period fitted to a few weeks of data grows with
  every cycle across a gap of a year or more, and the check measures depth only inside the central half of each
  predicted transit. The predicted transits drift out of that window, so a real planet seen in two seasons was usually
  marked missed and failed the check. Review reproduced this with synthetic light curves over many seeds. With three
  seasons every training set spans a gap and the period holds.
- The depth tension compared the held-out depth with the depth from all seasons, the held-out season included, and
  added the two errors in quadrature as if they were independent. They are correlated, so the computed tension
  understated the real one and the limit acted looser than written, more so with fewer seasons. It also departed
  from the spec's "fit on all seasons but one".

## Decision

- `criteria/vet-v1.toml` gains `min_training_seasons = 2` under `[holdout]`.
- A held-out season whose training set spans fewer than `min_training_seasons` seasons is `untestable` and does not
  count as tested. The check still needs two tested seasons, so a star seen in one or two seasons is inconclusive.
- For each held-out season, the reference depth is measured on the training cadences with the refit ephemeris and the
  same core window. Expected SNR is that reference over the held-out depth error. Tension is the difference between
  the held-out and reference depths over their errors in quadrature, which are now independent.
- A season with fewer than `min_points` training cadences inside the predicted transits is `untestable` too, so a
  missing reference can never read as a miss.
- Each season's evidence records the reference depth, its error and its cadence count. The all-season depth is no
  longer computed.
- The cost: a planet seen in only two seasons gets no held-out-season evidence either way, and leans on the other
  checks.

## Evidence

Unit tests in [tests/test_holdout.py](../../tests/test_holdout.py): `test_two_seasons_are_untestable_not_fail` (a
clean planet in two seasons is inconclusive with both seasons untestable). The task brief's tests pass unchanged under
the training-only reference: `test_planet_in_every_season_is_predicted`,
`test_negative_control_signal_missing_from_one_season`, `test_single_season_is_inconclusive` and
`test_underpowered_seasons_are_inconclusive_not_fail`.
