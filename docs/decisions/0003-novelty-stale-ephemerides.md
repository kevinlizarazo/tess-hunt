# 0003: Novelty flags a period match whose catalog epoch has gone stale

- Date: 2026-10-08
- Status: Accepted (approved by the maintainer)

## Context

`ephemeris_match` carries a catalog epoch forward with the catalog period and accepts it only when the candidate's
transits land within a fixed fraction of the shorter period. A catalog period has an error, and the phase error it
causes grows with every cycle between the catalog epoch and the candidate's. TOI epochs are often hundreds of cycles
old by the time a later sector is searched. A rediscovered TOI whose true period sits inside its catalog error can
then fall outside the phase tolerance, and the novelty check would pass it as new. Review reproduced this with the
published ephemerides of TOI-300.01 and TOI-304.01, carried a few hundred cycles forward with periods inside their
catalog errors.

A wrong epoch that survives decision 0002, such as a placeholder, fails the full match in the same way.

## Decision

- When a nearby catalog object with a positive period fails the full match, novelty compares it again on period
  alone.
- For an object on the same star, the period-only comparison uses the configured harmonics. For a neighbour inside the
  blend radius it uses the same period only, so a chance harmonic on another star does not hold up a candidate.
- Outcomes, in order:
  1. A full match fails the check, as before.
  2. Otherwise a period-only match makes it inconclusive. The evidence lists each match's source, name, TIC, period,
     ratio and the cycle offset between the candidate's epoch and the catalog's.
  3. Otherwise an object on the same star with no period makes it inconclusive, as before.
  4. Otherwise the check passes.

## Evidence

Unit tests in [tests/test_novelty.py](../../tests/test_novelty.py):
`test_same_star_period_match_out_of_phase_is_inconclusive`,
`test_neighbour_period_match_out_of_phase_is_inconclusive` and `test_neighbour_at_half_period_out_of_phase_passes`.
The task brief's novelty tests pass unchanged.
