# 0007: Search engine: BLS on 30-minute bins

- Date: 2026-10-09
- Status: Accepted (approved by the maintainer)

## Context

The design (section 4.1) asked M1 to benchmark BLS against TLS on speed and injection recovery and to record the
choice before the full search. M1 ran injection-recovery on a sample of 200 sample-A stars near the southern
continuous viewing zone, two planets per star, with three engines: BLS on 30-minute bins (`bls30`, the criteria's
setting), BLS on 10-minute bins (`bls10`) and TLS on 30-minute bins (`tls`, on the first 20 stars, one planet each).
The TLS run used the same seeds as the BLS run, so its 20 injected planets are the BLS run's first planet on each of
those stars, and the three engines can be compared planet by planet.

The runs were made at different commits. The one commit between them, c7a2625, changed only the vetting depth errors
(decision 0006); the search, injection and classify code was identical in both.

## Decision

- M2 searches with BLS on 30-minute bins, as `criteria/search-v1.toml` already specifies. The criteria do not change,
  so there is no `search-v2.toml`.
- `bls10` recovered the same injected planets as `bls30` with one exception, at roughly twice the runtime. Finer bins
  buy nothing measurable for this sample.
- TLS recovered exactly the same planets as both BLS settings on the paired injections, at several times the BLS
  runtime per search. TLS does not earn a place in M2's search.
- The measured runtime per search is well above the design's estimate of 10 to 20 seconds per star. These stars have
  many sectors, so they sit near the worst case, but M2's compute plan should start from the measured value.

## Limitations

The injection-recovery maps understate the losses on variable stars. The search can spend its signal slots on the
star's own variability: its duration grid is the same for every period, so a box far longer than a transit at
that period can fit the variability, and it can detect the same variability more than once.
M2 fixes the search and reruns the benchmark.

## Evidence

- BLS injection-recovery, both bin sizes:
  [summary.md](../../results/benchmarks/20261009T181208Z-benchmark-inject-0801864-5082/summary.md), with
  [injections.csv](../../results/benchmarks/20261009T181208Z-benchmark-inject-0801864-5082/injections.csv) and the
  completeness maps in the same directory.
- TLS injection-recovery:
  [summary.md](../../results/benchmarks/20261009T202102Z-benchmark-inject-c7a2625-6dae/summary.md), with
  [injections.csv](../../results/benchmarks/20261009T202102Z-benchmark-inject-c7a2625-6dae/injections.csv).
  Joining the two `injections.csv` files on `tic` and `injection` pairs the planets: the injected period and epoch
  agree row for row, and the `recovered` column agrees for every pair.
- Known-planet recovery with `bls30`:
  [summary.md](../../results/benchmarks/20261009T180940Z-benchmark-known-0801864-d6f6/summary.md),
  and the same run repeated with light-curve hashes and the fetch manifest recorded:
  [summary.md](../../results/benchmarks/20261012T144539Z-benchmark-known-bcd8d2e-5e48/summary.md).
