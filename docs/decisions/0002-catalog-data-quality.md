# 0002: Catalog epochs and durations outside set bounds count as missing

- Date: 2026-10-08
- Status: Accepted (approved by the maintainer)

## Context

The novelty check compares a candidate with every TOI, CTOI and Exoplanet Archive object on the same star or on a
neighbour. It carries each catalog epoch forward with the catalog period, so a wrong epoch puts the catalog transits
at the wrong phase, and a rediscovery of that object looks new. `known_ephemerides` uses the same epochs and durations
to mask known transits.

The catalog snapshot of 2026-10-09 holds CTOI epochs that cannot be right. Most are MJD values with 2457000 added,
which puts them more than a century in the future. Others have a misplaced decimal or a wrong digit, and one falls in the 1860s.
Some CTOI durations run to days or weeks, often on rows with a short period or no period at all. The TOI table and the
Archive have no epochs like these in that snapshot.

## Decision

- After conversion to BTJD, an epoch outside -20000 to 10000 becomes missing. That window runs from about 1960 to
  about 2042. It keeps the Archive's oldest epochs and its projected future ones, and drops the MJD-style and mistyped
  values.
- A duration over 1.0 d becomes missing.
- Both rules apply to all three catalogs, through `MIN_T0_BTJD`, `MAX_T0_BTJD` and `MAX_DURATION_DAYS` in
  `src/tess_hunt/catalogs.py`.
- A row with a missing epoch stays in the known table. Novelty matches it on period alone, which errs toward calling a
  signal known. `known_ephemerides` leaves it out, since a mask needs an epoch.
- A row with a missing duration gets the caller's fallback duration in `known_ephemerides`. The duration rule also
  clears a few real transits longer than a day, on long-period planets or large stars. Novelty does not use durations,
  so the cost is a fallback-width mask on those stars.
- An epoch inside the window can still be wrong, for example a placeholder at exactly BJD 2457000. Decision 0003
  covers those: an object whose period matches but whose epoch does not makes the check inconclusive.

## Evidence

- The catalog snapshot `catalogs/2026-10-09` under the data directory, written by provenance run
  `20261009T010603Z-catalogs-6c45148-8290`.
- Unit tests in [tests/test_catalogs.py](../../tests/test_catalogs.py): `test_ctoi_epoch_outside_window_is_missing`
  (an MJD-style epoch and an epoch from the 1860s), `test_old_archive_epoch_inside_window_is_kept` and
  `test_ctoi_duration_over_a_day_is_missing`.
