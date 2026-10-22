# 0030: Short-period variables: M3 counts them; their treatment moves to a search milestone paired with M5

- Date: 2026-10-22
- Status: Accepted (approved by the maintainer in the M3 design on 2026-10-16: question 8 and section 4.12)

## Context

[Decision 0008](0008-search-fix.md)'s harmonic exclusion covers the listed harmonics and nothing else. Its Limitations:
"A short-period pulsator can still fill later ranks with its other multiples (4x, 5x, 10/3x) ... a planet on such a
star is then missed", so "short-period variables need their own treatment, carried to M3". `docs/design.md`'s M3
entry (section 7) says M3 takes up that treatment.

The M3 design (question 8 and section 4.12) splits it. A treatment, prewhitening a pulsator before BLS or a different
rank rule, changes the search code that `search_code_sha256` hashes (`src/tess_hunt/search.py`), and triage refuses a
search whose code differs from the null's behind its threshold (`check_search` in `src/tess_hunt/threshold.py`). So
the treatment needs a new null, a new threshold and a new production search. The last null,
`20261013T151227Z-search-b76fd0b-6c16`, ran from 2026-10-13 15:12 UTC to 2026-10-14 16:57 UTC (its
[provenance.json](../../results/benchmarks/20261013T151227Z-search-b76fd0b-6c16/provenance.json)). The M3 design:
"That is a search milestone, best paired with M5's slice B, which needs its own null anyway." Slice B is a
long-period search mode on the same light curves (`docs/design.md`, section 7). M3 changes no search code (M3
design, section 5); it measures the problem, with a committed script.

## Decision

1. **The measurement.** [`benchmarks/short_period_variables.py`](../../benchmarks/short_period_variables.py) reads the
   production search `20261014T205855Z-search-fe29585-cdf2`, triage run `20261015T155441Z-triage-7b12e25-3f57` and
   inject run `20261015T131443Z-benchmark-inject-fe29585-8496`. A star counts when every one of its signals at or
   above the threshold has a period within 1.24% of n/m times one of them under 5 days, n and m from 1 to 5, and
   LEO-Vetter failed every one of them on non_unique or sinusoidal. Its output,
   [`short-period-variables-2026-10-17.txt`](../../results/benchmarks/short-period-variables-2026-10-17.txt):
   - 30,175 sample stars searched (status ok); 1,994 with a signal at or above the threshold (SDE 20.24), holding
     2,993 signals.
   - 969 of those stars have every signal at n/m of one period under 5 days.
   - 778 of the 969 had every signal failed on non_unique or sinusoidal: the short-period variables. They hold 1,206
     of the 2,993 signals.
   - The inject run recovered 12 of its 48 injections on those 778 stars (0.250), and 757 of 1,952 on the other stars
     (0.388).
2. **The treatment moves out of M3**, to a later search milestone paired with M5's slice B, with this measurement as
   its starting point. Until then the search, the null, the threshold and triage stay as they are, and a planet on
   one of these stars can be missed as 0008 describes.
3. **The spec.** The M3 design's amendments for `docs/design.md` (its section 6, the "7, M3" bullet) move the
   treatment out of M3's entry to that later milestone, with this measurement.

## Limitations

- The count is the script's rule and no more. A star whose search found something besides the variable's multiples,
  such as a planet's signal, is not counted, nor is one whose multiples LEO-Vetter failed on other tests. The first
  are the stars where a treatment could matter most. 778 is not a count of the planets these variables hide.
- 48 injections is a small sample. The inject run drew its targets at random from the production sample, not from
  these stars, and its recovery is the search's alone, before triage.
- The search's `stars.parquet` and `signals.parquet` and the triage run's evidence files, which the script reads,
  stay in the run directories and are not published.

## Evidence

- [`short-period-variables-2026-10-17.txt`](../../results/benchmarks/short-period-variables-2026-10-17.txt): every
  number in item 1. It was written on 2026-10-17 at 04:08 UTC by
  [`benchmarks/short_period_variables.py`](../../benchmarks/short_period_variables.py) as committed in e6719c6, which
  is unchanged since. Anyone with the three run directories can repeat the check: at this commit, from the repository
  root,

  ```
  uv run python benchmarks/short_period_variables.py \
      "$TESS_HUNT_DATA/runs/20261014T205855Z-search-fe29585-cdf2" \
      "$TESS_HUNT_DATA/runs/20261015T155441Z-triage-7b12e25-3f57" \
      "$TESS_HUNT_DATA/runs/20261015T131443Z-benchmark-inject-fe29585-8496" > short-period-variables.txt
  ```

  writes a file whose sha256 is the committed file's,
  `e3c432dbe53daac00f2d7095b5d5a2cc5d4ca29fde8c88ed758e2e3f8dca78a0`.
- The production search's published
  [provenance.json](../../results/benchmarks/20261014T205855Z-search-fe29585-cdf2/provenance.json), the triage run's
  [summary.md](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/summary.md) and the inject run's
  [summary.md](../../results/benchmarks/20261015T131443Z-benchmark-inject-fe29585-8496/summary.md): the runs the
  script read.
- The null's [provenance.json](../../results/benchmarks/20261013T151227Z-search-b76fd0b-6c16/provenance.json): its
  start and end in Context.
- [tests/test_threshold.py](../../tests/test_threshold.py): `test_check_search_refuses_other_hashes_and_a_grown_null`
  (a search run with other code than the null behind its threshold is refused).
