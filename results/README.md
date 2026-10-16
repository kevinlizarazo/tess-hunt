# Results

Copyright (c) 2026 Kevin Lizarazo. Everything under `results/` is licensed under CC BY 4.0 ([LICENSE](LICENSE) in
this directory). The one exception is the `ruwe` column of the published triage tables: it is Gaia DR3 data (credit:
ESA/Gaia/DPAC) and stays under ESA's CC BY-NC 3.0 IGO terms (https://www.cosmos.esa.int/web/gaia-users/license), not
CC BY 4.0.

Attribute as: Kevin Lizarazo, tess-hunt, https://github.com/kevinlizarazo/tess-hunt.

These files are derived from TESS light curves, from the TESS Input Catalog, from Gaia DR3, and from the ExoFOP and
NASA Exoplanet Archive catalogs. Reuse must also carry the acknowledgements in
[../ACKNOWLEDGEMENTS.md](../ACKNOWLEDGEMENTS.md).

## Runs

Each directory under `benchmarks/` is one run, named `<UTC start>-<stage>-<commit>-<id>`. `tess-hunt benchmark
publish` copied its tables, summaries and plots unchanged from the run directory. Every run has a `provenance.json`
recording the commit, the criteria files and their hashes, the input files and their hashes, and the command line.
Published runs are never edited; a correction is a new run.

- `benchmark-known`: recovery of the known-planet set (`benchmarks/known_planets.csv`). `known.csv` has one row per
  planet; `summary.md` is the table.
- `benchmark-inject`: injection-recovery. `injections.csv` has one row per injected planet and search engine; the
  `completeness_*.csv` tables and `completeness_*.png` maps bin the recovered fraction; `summary.md` collects them.
- `search`: a production search. `controls.csv` has one row per positive control, the known-planet set searched
  alongside the sample ([decision 0011](../docs/decisions/0011-positive-controls-in-production.md)); the signals
  themselves stay in the run directory. The null search (`--scramble`,
  [decision 0019](../docs/decisions/0019-null-threshold.md)) has only its `provenance.json`, whose summary counts the
  stars it searched and the signals it emitted.
- `targets`: the all-sky sample. Only `provenance.json` is published; its summary counts the stars the TIC query
  returned, those in the sample, those matched to Gaia DR3 and with a FLAME log g, those the FLAME cut kept and those
  covered ([decision 0009](../docs/decisions/0009-gaia-dr3-dwarf-cut.md)). The targets table stays in the run
  directory.
- `fetch`: the sample's light-curve fetch. Only `provenance.json` is published; its summary counts the stars by fetch
  status ([decision 0010](../docs/decisions/0010-fetch-route-and-qlp-timing.md)). The fetch manifest, with every
  sector source's route and flags, stays in the run directory.
- `threshold`: the detection threshold from the null search
  ([decision 0019](../docs/decisions/0019-null-threshold.md)). `threshold.json` holds the threshold, the counts behind
  it and the highest null signals with their LEO-Vetter outcomes; `null_dropped.csv` lists every null signal left out
  and the rule that dropped it.
- `vet`: every vetting check on one signal. `checks.json` holds each check's outcome and evidence, the per-sector
  red-noise factors and the transit-fit summary.

The loose files beside the run directories in `benchmarks/` were written by the scripts listed in
[benchmarks/README.md](../benchmarks/README.md):

- `20261013T012920Z-benchmark-inject-b62e857-d86f-comparison.md`: the search fix's replay of M1's injections
  (`compare_replay.py`, [decision 0008](../docs/decisions/0008-search-fix.md)).
- `qlp-timing-2026-10-13.txt`: QLP minus SPOC transit times in QLP S99 to S104 (`qlp_timing.py`,
  [decision 0010](../docs/decisions/0010-fetch-route-and-qlp-timing.md)).
- `qlp-timing-robust-2026-10-13.txt`: the same offsets, timed against each sector's own SPOC fit
  (`qlp_timing_robust.py`, decision 0010).
- `qlp-dilution-2026-10-13.txt`: QLP against SPOC transit depths on crowded stars (`qlp_dilution.py`, decision 0010).
- `scramble-leo-probe-2026-10-13.json`: LEO-Vetter's false-alarm tests on scrambled signals
  (`scramble_leo_probe.py`, [decision 0019](../docs/decisions/0019-null-threshold.md)).
- `sector-structure-2026-10-13.txt`: each sector's span and gaps on 500 random fetched stars (`sector_structure.py`,
  decision 0019).

## Triage

Each run directory under `triage/` is one triage run, which `tess-hunt triage publish` copied unchanged from the run
directory with the `threshold.json` it was cut at. `summary.md` counts every step's outcomes; `signals.csv` has one
row per signal at or above the threshold with its novelty, LEO-Vetter and pixel outcomes; `shortlist.csv` holds the
shortlisted rows; `known_to_spoc.csv` lists the signals that match only a SPOC TCE or ExoMiner row, for the maintainer
to promote by hand ([decision 0013](../docs/decisions/0013-novelty-sources.md)). Every row is a candidate signal, not a
planet. The per-signal evidence and literature files stay in the run directory.

The three CSV files share these columns. Times are BTJD (BJD_TDB - 2457000).

- `tic`: the star's TIC ID. `rank`: the order in which the search found the signal on the star, from 1.
- `period` (days), `t0` (mid-transit epoch, BTJD), `duration` (days): the search's box ephemeris.
- `depth`: the box depth as a fraction of the flux, not ppm. `depth_snr`: the depth over its error, from the box fit.
- `sde`: the peak's signal detection efficiency, the statistic the threshold cuts. `n_transits`: transits with
  enough cadences on data.
- `engine`: the search engine (`bls`). `control`: whether the star is a positive control (`False` on every row).
- `novelty`: `pass`, `fail` or `inconclusive`. `novelty_category`, empty on a pass: `known` (matches a catalogued
  object), `stale_catalog_epoch` (the period matches but the epoch does not), `no_period_object` (the star hosts a
  known object with no period), `known_to_spoc` (matches only SPOC TCE or ExoMiner rows), `missing_input` or
  `catalogs_not_loaded`. `novelty_reason`: the check's reason; on a fail it names the first matching object.
- `leo_flux`: LEO-Vetter's flux tests, `pass`, `fail` or `inconclusive`. `leo_disposition`: `PC` (planet
  candidate), `FA` (false alarm) or `FP` (false positive), empty when LEO-Vetter could not judge the signal.
  `leo_reason`: the failed tests after the disposition (`FA: non_unique, chi`), or why it could not judge.
  `leo_unknown`: the tests it could not judge, because a metric they read was missing or not finite, or because they
  raised (then the exception type follows the test's name).
- `pixels`: the centroid check, `pass`, `fail` or `inconclusive`; it runs only on signals that passed novelty and
  the flux tests, and is `inconclusive` ("not run") on the rest. `pixels_reason`: its reason, with the best-quality
  sector's centroid offset when it ran.
- `timing_suspect_transits`: the signal's transits in sectors flagged `timing_suspect` (QLP S99 to S104,
  [decision 0010](../docs/decisions/0010-fetch-route-and-qlp-timing.md)).
- `ruwe`: the star's Gaia DR3 RUWE, under Gaia's licence (above).
- `shortlisted`: `True` only when novelty, LEO-Vetter and pixels all pass.

The loose files in `triage/` ([decision 0012](../docs/decisions/0012-leo-vetter-configuration.md)):

- `leo-strictness-2026-10-16.txt`: LEO-Vetter's outcomes on the triage run's signals that match a catalogued
  eclipsing binary or planet candidate, and the tests it failed most often (`benchmarks/leo_strictness.py`).
- `pixel-controls-2026-10-16.txt`: the pixel check on its three real nearby-binary controls, with every sector's
  offset (`test_real_nearby_eb_controls` in `tests/test_pixels.py`).
- `pixel-timing-2026-10-14.txt`: transit-diffImage's pixel times against TESScut's on the controls' difference
  images (`benchmarks/pixel_timing.py`).

## Catalog snapshots

Each directory under `catalogs/` holds the manifest of one novelty-source snapshot
([decision 0013](../docs/decisions/0013-novelty-sources.md)): each file's URL, size, sha256 and Last-Modified. The
downloaded files themselves are not republished here.
