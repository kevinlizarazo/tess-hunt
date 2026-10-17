# 0020: Triage refuses a threshold run made under other LEO-Vetter code or on other light curves

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design)

## Context

M2's final review (C1 and R6) found two gaps between a threshold run and the triage that cuts at it. The threshold is
the highest SDE among null signals that LEO-Vetter's false-alarm tests do not reject (decision 0019). Triage held the
threshold run to the same search criteria, search code and LEO-Vetter settings (`[leo]` and `[leo_metrics]`), but not
to the same LEO-Vetter code: every run's provenance records its commit and `uv_lock_sha256`, and nothing read them. A
leo-vetter release or a change to `src/tess_hunt/leo.py` between the two runs would cut the search at a value counted
by other tests. And the threshold run compared the null's light curves with the files on disk, and triage compared the
search's, but nothing compared the null's with the search's: a refetch between the null and the production search
would cut the search's signals at a false-alarm rate measured on other light curves. Neither gap changed an M2 result
(Evidence).

## Decision

- `check_leo_code(provenance, root)` in `src/tess_hunt/threshold.py` lists why LEO-Vetter in the checkout at `root`
  may not judge as it did in the run behind `provenance`: `uv.lock`'s sha256 is not the run's `uv_lock_sha256`;
  `src/tess_hunt/leo.py` is not the file at the run's commit (read with `git show`); that file cannot be read from the
  checkout; or the run's tree had uncommitted changes to it, so the commit's file is not the one that ran. The list is
  empty when none holds. LEO-Vetter's settings are criteria, which triage already compares, and the detrend,
  light-curve and ephemeris code it calls is in the search code hash, which triage holds to the null's.
- `check_null_light_curves(null_stars, search_stars, tics)` lists the stars among `tics` whose `lc_sha256` differs
  between the null's `stars.parquet` and the search's. A star the null did not search counts as differing.
- `triage run` refuses, before it starts a run:
  - a threshold run for which `check_leo_code` finds a problem, naming the run and each problem;
  - a search whose triaged stars (those with a sample signal at or above the threshold) have light curves other than
    the ones searched by the null that `threshold.json` names, naming the null, the threshold run and up to ten stars,
    or whose null has no `stars.parquet` under the data directory;
  - with `--production`, a threshold run that was not a production run (a production run's tree is clean, so its
    commit holds the code it ran);
  - a threshold run directory whose name is not the run id its provenance records: triage records that name as the
    threshold's run id, and `triage publish` finds `threshold.json` by it.
- A later stage that judges signals with LEO-Vetter against a threshold or triage run refuses on `check_leo_code` in
  the same way.

## Limitations

- The check reads `uv.lock`, not the installed environment. `uv sync --locked` installs what the lock pins; a package
  changed by hand in the environment would pass.
- `src/tess_hunt/checks/__init__.py`, whose result helpers the wrapper builds its outcome with, is in neither the
  wrapper check nor the search code hash. It has not changed since it was added.
- The light-curve check covers the triaged stars only. A star refetched between the null and the search with no signal
  at or above the threshold reaches no triage verdict, though the null's false-alarm count then describes a light curve
  the search did not search.

## Evidence

- Unit tests in [tests/test_threshold.py](../../tests/test_threshold.py):
  `test_check_leo_code_passes_the_same_lock_and_wrapper`, `test_check_leo_code_refuses_another_lock`,
  `test_check_leo_code_refuses_a_changed_wrapper` (a wrapper committed in a temporary repository, then edited),
  `test_check_leo_code_refuses_a_wrapper_it_cannot_trace` (a wrapper uncommitted when the run ran, a commit the
  checkout lacks), `test_null_and_search_light_curves_must_match` and
  `test_a_light_curve_the_null_did_not_search_does_not_match`.
- Through `triage run` in [tests/test_triage.py](../../tests/test_triage.py):
  `test_triage_refuses_a_threshold_run_under_another_lock`, `test_triage_refuses_a_run_it_cannot_trust` (a null light
  curve that differs from the search's, a null without `stars.parquet`, a threshold directory its provenance does not
  name), `test_production_triage_refuses_a_threshold_run_that_was_not_production`, and the control on the
  light-curve check's scope, `test_triage_compares_only_the_triaged_stars_light_curves_with_the_null`, where a star
  with no signal at the threshold has another null light curve and triage goes ahead. Every other triage test passes
  both checks against the checkout's own commit and `uv.lock`.
- M2's runs, checked on 2026-10-17 with the code of the commit that adds this record, by a script outside the
  repository that starts from the triage run's provenance and finds the threshold run, its null and the search from
  the recorded run ids. Its output:

  ```
  20261014T175116Z-threshold-0d6748e-40ac: commit 0d6748e, uv.lock a010156a71a8, dirty_paths [], production True
    check_leo_code: []
  20261015T155441Z-triage-7b12e25-3f57: commit 7b12e25, uv.lock a010156a71a8, dirty_paths [], production True
    check_leo_code: []
  null (threshold.json null_run) 20261013T151227Z-search-b76fd0b-6c16; the threshold read its signals: True
  search (triage search_run) 20261014T205855Z-search-fe29585-cdf2; triage read its stars: True
  triaged: 2993 signals on 1994 TICs (evidence/ names the same TICs: True)
  check_null_light_curves(null, search, 1994 TICs): []
  triage's refusal checks on 20261015T155441Z-triage-7b12e25-3f57's arguments: none refused
  ```

  The last line runs triage's refusal checks, every check this record adds among them, on the arguments the
  production triage recorded: the new checks do not refuse M2's own runs. The runs' provenance is published:
  [threshold](../../results/benchmarks/20261014T175116Z-threshold-0d6748e-40ac/provenance.json),
  [triage](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/provenance.json),
  [null](../../results/benchmarks/20261013T151227Z-search-b76fd0b-6c16/provenance.json) and
  [search](../../results/benchmarks/20261014T205855Z-search-fe29585-cdf2/provenance.json).
