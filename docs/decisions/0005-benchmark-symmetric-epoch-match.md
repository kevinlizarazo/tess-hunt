# 0005: A benchmark recovery counts when the epoch matches under either period

- Date: 2026-10-09
- Status: Accepted (approved by the maintainer)

## Context

`classify` decides whether a search signal recovers a known or injected planet. It called `ephemeris_match` with the
signal as the candidate and the truth as the reference, so the truth's epoch was carried to the signal's epoch with
the truth's period. `ephemeris_match` carries that way because a catalog epoch is often hundreds of cycles old and a
candidate's period error would accumulate over them. The novelty check (decision 0003) uses the same direction.

The known-planet benchmark can reverse that. The run `20261009T171758Z-benchmark-known-b64d6e2-d508` missed the
required planet TOI-396.01 (HR 858 c). The search found it at the right period with a strong signal, but not at the
top of its list. The benchmark truth is the TOI's linear ephemeris, with its epoch in a recent sector, while the
search put the signal's epoch in the early sectors. Carried back over hundreds of cycles with the catalog period, the
truth's transits land just outside the phase tolerance. Carried with the signal's period, which the search fitted
across the whole baseline, they line up. The catalog's linear ephemeris does not reach the early sectors, and the
search found the planet. Whether a planet counts as recovered should not depend on which of the two periods carries
the epoch.

## Decision

- In `classify`, a signal matches the truth at a ratio when `ephemeris_match` succeeds in either order: the signal as
  the candidate and the truth as the reference, or the truth as the candidate and the signal as the reference.
- The rule applies to the recovery test at the true period and to the alias test over `ALIASES`. In the reversed
  order a ratio k means the truth's period is k times the signal's. `ALIASES` holds the inverse of each ratio, so a
  signal at a harmonic is still an alias and never a recovery.
- A signal at the right period and the wrong phase fails in both orders and is still a miss.
- The rest of `classify` is unchanged: recovery still needs the SDE threshold, every signal is tried at the true
  period before any is tried as an alias, and the returned fields are the same.
- `ephemeris_match` itself and the novelty check keep the one-way carry of decision 0003.
- Injection-recovery is effectively unaffected. An injected epoch and the epoch the search finds both sit near the
  start of the data, so few cycles separate them and either period carries one onto the other.

## Evidence

- Known-planet benchmark run `20261009T171758Z-benchmark-known-b64d6e2-d508`, before this decision, written under the
  data directory's `runs/` and not published.
- The rerun after this decision, published:
  [summary.md](../../results/benchmarks/20261009T180940Z-benchmark-known-0801864-d6f6/summary.md).
- The same rerun repeated after the final review, with light-curve hashes and the fetch manifest recorded:
  [summary.md](../../results/benchmarks/20261012T144539Z-benchmark-known-bcd8d2e-5e48/summary.md).
- Unit tests in [tests/test_benchmark.py](../../tests/test_benchmark.py):
  `test_classify_recovers_when_catalog_period_drifts` (the TOI-396.01 ephemeris and the signal the search found for
  it), `test_classify_recovers_when_search_period_drifts` (the mirror case, where only the truth's period carries
  the epoch onto the signal) and `test_classify_still_rejects_wrong_phase` (a signal at the true period, half a period off, is neither
  recovered nor an alias). The earlier tests pass unchanged: `test_classify_recovered`,
  `test_classify_below_threshold_is_not_recovery`, `test_classify_alias_is_not_recovery` and `test_classify_missed`.
