# Results

Copyright (c) 2026 Kevin Lizarazo. Everything under `results/` is licensed under CC BY 4.0 ([LICENSE](LICENSE) in
this directory). The exceptions are Gaia DR3 data (credit: ESA/Gaia/DPAC): the `ruwe` column of the published triage
tables, the RUWE values the published controls quote, the Gaia DR3 values the pixel check's diagnosis and the
neighbour-epoch measurements quote or hold (all under [Runs](#runs)), and the Gaia DR3 parts of the vetting records,
listed under [Vetting](#vetting). They stay under ESA's CC BY-NC 3.0 IGO terms
(https://www.cosmos.esa.int/web/gaia-users/license), not CC BY 4.0.

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
- `benchmark-controls`: vet-v3's controls, the known planets and the negative controls, from a vetting run, the
  TRICERATOPS runs on it and triage's pixel check on the known planets. `controls.csv` has one row per control: each
  check's outcome, the neighbour table's count of possible hosts, the pixel check's outcome and offset (known planets
  only), and TRICERATOPS's outcome, mean and sd of FPP and NFPP, blockers, the run it came from and any earlier run's
  outcome it replaced. `pass_rates.csv` counts each check's outcomes over the known planets, all of them and without
  the ones left out; `summary.md` collects them with each fail's reason. The RUWE values quoted in `blockers` and in
  the TRICERATOPS reasons are Gaia DR3 data (above).
- `benchmark-pixel-completeness`: triage's pixel check on the known-planet set at their catalog ephemerides.
  `pixels.csv` has one row per planet: the outcome, its reason, the best-quality sector's offset and the number of
  sectors measured (`good_sectors`); `summary.md` is the table.
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

One loose file has no script: `vet-v3-control-diagnosis-2026-10-17.md`, a read-only diagnosis of the known planets
vet-v3's controls fail, made outside the pipeline. It gates nothing; its causes are cited by
[decision 0031](../docs/decisions/0031-known-set-control-fails.md).

`pixel-check-diagnosis-2026-10-20.md` is a read-only diagnosis of the pixel check's fails on the known planets and the
second list, made outside the pipeline. Its scripts and their small outputs are in
`pixel-check-diagnosis-2026-10-20-scripts.tar.gz` beside it, byte for byte. It gates nothing; its causes are cited by
[decision 0033](../docs/decisions/0033-second-list-decisions.md). The Gaia DR3 source ids and the neighbour table's
values in its section 2 are Gaia DR3 data (above).

`neighbour-epoch-reach-2026-10-20.md` measures how far the neighbour table's mixed epochs (the TIC position at J2000
against Gaia DR3 at J2016.0) reach across M3's 62 tables, and `pixel-check-reference-position-2026-10-20.md` which
position the pixel check measures its offsets from. Both are read-only, made outside the pipeline, and gate nothing;
[decision 0034](../docs/decisions/0034-neighbour-table-epochs.md) cites them. Their scripts and small outputs are in
`neighbour-epoch-reach-2026-10-20-scripts.tar.gz` beside them, byte for byte, one folder each (`t13-epoch/`,
`pixel-diag/`). The Gaia DR3 source ids, positions, proper motions, magnitudes and separations in both files and in
the tarball are Gaia DR3 data (above).

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
  at least `min_points_per_transit` binned points on data (`criteria/search-v2.toml`).
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

## Vetting

Each directory under `vetting/` is one signal's record, named `<tic>-<rank>` as triage names the signal.
`tess-hunt vetting publish` wrote it once the maintainer's call was in it
([decision 0028](../docs/decisions/0028-outcomes-and-calls.md)); `vetting/README.md` lists every published call that
stands on its record. Published files are never edited: only `dossier.md` and `vetting/README.md` are rendered again
from the files beside them, and a correction is a new run. A passed signal is a planet candidate, not a confirmed
planet.

- `call.toml`: the maintainer's call: `outcome` (passed, killed or held), `date`, `reasons` in his words, `rests_on`
  (the checks and review findings it rests on), `criteria`, and as the outcome needs, `deciding_evidence` (what would
  decide a held signal), `promotion` (a second-list row's TCE and the reason), `[answers]` (one per confirmed review
  finding), `[sentences]` (why it is not a binary, not another star's light, not an artefact or a known object) and
  `hits_read`. It holds no numbers.
- `review.json`: the adversarial review: each finding's lens, rating (kill, hold or note), claim, evidence and each
  refuter's verdict, the literature hits it flagged, and a summary.
- `dossier.md`: the dossier, rendered from the files beside it; every number in it comes from them.
- `checks.json`: the vet under vet-v3 (`tess-hunt vetting run`): each check's outcome, reason and evidence; the
  flat-prior fit's summary (`fit`) and the density-prior fit's (`fit_prior`); the star's targets row, its Gaia DR3 id
  and RUWE joined where the row lacks them, with where they came from (`star`: `dr3_from`, `dr3_reason`); each
  sector's light-curve source (`sources`); the neighbour table (`neighbours`,
  [decision 0025](../docs/decisions/0025-neighbours.md); its `centre` names the position the separations run from,
  [decision 0034](../docs/decisions/0034-neighbour-table-epochs.md)); every catalogued row on the star with the
  transits of ours it overlaps (`catalogued`); the upcoming sectors and predicted transit windows; triage's ModShift and
  pixel evidence and the search's other signals on the star.
- `checks-with-suspect.json`: the same vet with the timing-suspect sectors kept in, as evidence only, never used for
  the call ([decision 0022](../docs/decisions/0022-vet-without-timing-suspect-sectors.md)).
- `neighbours.csv`: the Gaia DR3 stars in the neighbour cone, each with its TESS magnitude and the eclipse depth it
  would need to make the dip.
- `plots/`: each transit, the fold per season and product family, odd and even transits, the whole orbit with phase
  0.5 and the ModShift secondary, and the centroid offsets per sector with the neighbours that could host the signal
  (for a second-list row, `centroids.png` draws triage's record, which holds no offsets; its own are in `pixels.png`).
- `triceratops.json`, `probs.csv`: TRICERATOPS ([decision 0026](../docs/decisions/0026-triceratops.md)): the outcome,
  each run's FPP and NFPP, the stars it weighed and the possible hosts matched to them; `probs.csv` is the last run's
  scenario table. A signal a check killed has none.
- `literature.json`: the literature search by name, NASA ADS and ExoFOP
  ([decision 0027](../docs/decisions/0027-literature-by-name.md)).
- `pixels.json`, `pixels.png`: a second-list row's pixel check, which triage runs only on novelty passes, run on it as
  triage runs it by `tess-hunt vetting second-list`: the outcome and reason, each measured sector's centroid offset
  and quality, and the offset limit (decision 0028); `pixels.png` plots those offsets with the neighbours that could
  host the signal. Other signals' pixel check is triage's, in `checks.json`, and their centroid plot is
  `plots/centroids.png`.
- `provenance-checks.json`, `provenance-checks-with-suspect.json`, `provenance-triceratops.json`,
  `provenance-literature.json`, `provenance-second-list.json`: each run's `provenance.json`, copied unchanged: the
  commit, the criteria files and their hashes, the inputs and their hashes, and the command line of the run the files
  beside it came from.
  `provenance-checks.json` stands behind `checks.json`, `neighbours.csv` and `plots/`.

Gaia DR3 data in these records stay under ESA's CC BY-NC 3.0 IGO terms (above), not CC BY 4.0: `neighbours.csv`, the
neighbour table in `checks.json` and `checks-with-suspect.json` (`neighbours`), the possible hosts and the RUWE in
`triceratops.json` (`hosts`, `ruwe`), and the Gaia DR3 columns of the star's row in both checks files
(`dr3_source_id`, `angular_distance`, `ruwe`, `logg_gspphot`, `mass_flame`, `radius_flame`, `logg_flame`), the
possible hosts drawn in `plots/centroids.png` and `pixels.png`, and the same values where `dossier.md` shows them.

## Catalog snapshots

Each directory under `catalogs/` holds the manifest of one novelty-source snapshot
([decision 0013](../docs/decisions/0013-novelty-sources.md)): each file's URL, size, sha256 and Last-Modified. The
downloaded files themselves are not republished here.
