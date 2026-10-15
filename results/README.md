# Results

Copyright (c) 2026 Kevin Lizarazo. Everything under `results/` is licensed under CC BY 4.0 ([LICENSE](LICENSE) in
this directory).

Attribute as: Kevin Lizarazo, tess-hunt, https://github.com/kevinlizarazo/tess-hunt.

These files are derived from TESS light curves, from the TESS Input Catalog, and from the ExoFOP and NASA Exoplanet
Archive catalogs. Reuse must also carry the acknowledgements in [../ACKNOWLEDGEMENTS.md](../ACKNOWLEDGEMENTS.md).

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
  themselves stay in the run directory.
- `threshold`: the detection threshold from the null search ([decision 0019](../docs/decisions/0019-null-threshold.md)).
  `threshold.json` holds the threshold, the counts behind it and the highest null signals with their LEO-Vetter
  outcomes; `null_dropped.csv` lists every null signal left out and the rule that dropped it.
- `vet`: every vetting check on one signal. `checks.json` holds each check's outcome and evidence, the per-sector
  red-noise factors and the transit-fit summary.

## Catalog snapshots

Each directory under `catalogs/` holds the manifest of one novelty-source snapshot
([decision 0013](../docs/decisions/0013-novelty-sources.md)): each file's URL, size, sha256 and Last-Modified. The
downloaded files themselves are not republished here.
