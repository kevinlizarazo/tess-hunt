# Results

Copyright (c) 2026 Kevin Lizarazo. Everything under `results/` is licensed under CC BY 4.0 ([LICENSE](LICENSE) in
this directory). The exceptions are Gaia data (credit: ESA/Gaia/DPAC): the `ruwe` column of the published triage
tables, the RUWE values the published controls quote, the Gaia DR3 values the pixel check's diagnosis, the
neighbour-epoch measurements and the TIC-duplicate measurement quote or hold, the TIC-carried Gaia DR2 values the
TIC-duplicate measurement holds (all under [Runs](#runs)), and the Gaia DR3 parts of the vetting records and the
Gaia DR2 and DR3 values their reviews quote, listed under [Vetting](#vetting). They stay under ESA's CC BY-NC 3.0 IGO
terms (https://www.cosmos.esa.int/web/gaia-users/license), not CC BY 4.0.

ExoFOP's rows in the vetting records' `literature.json` (TOIs, CTOIs, planet parameters, confirmed planets and imaging
rows), and the same rows where `dossier.md` shows them, stay under ExoFOP's terms, not CC BY 4.0: its data-use
guidelines (https://exofop.ipac.caltech.edu/tess/pcp.php) treat data as its provider's property. The paper titles in
`literature.json` come only from arXiv's, OpenAlex's and Zenodo's metadata
([decision 0038](../docs/decisions/0038-literature-trim-and-username-scrub.md)), each read 2026-10-26: arXiv's API terms
of use (https://info.arxiv.org/help/api/tou.html) say "You are free to use descriptive metadata about arXiv e-prints
under the terms of the Creative Commons Universal (CC0 1.0) Public Domain Declaration"; OpenAlex's about page
(https://openalex.org/about) says "Our data is CC0"; Zenodo's policies (https://about.zenodo.org/policies/) say
"Metadata is licensed under CC0, except for email addresses." Bibcodes, DOIs and arXiv ids are identifiers. From NASA
ADS the records keep those identifiers and each search's query, total and status, never a title.

Attribute as: Kevin Lizarazo, tess-hunt, https://github.com/kevinlizarazo/tess-hunt.

These files are derived from TESS light curves, from the TESS Input Catalog, from Gaia DR3, from the ExoFOP and
NASA Exoplanet Archive catalogs, and from SIMBAD, NASA ADS, arXiv, OpenAlex and Zenodo, which the literature
search reads. Reuse must also carry the acknowledgements in [../ACKNOWLEDGEMENTS.md](../ACKNOWLEDGEMENTS.md).

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
- `benchmark-triage-completeness`: triage's novelty and LEO-Vetter flux tests on the injections an inject run
  recovered, each planted and searched again as the inject run did it and judged as a triage run judged its signals
  ([decision 0029](../docs/decisions/0029-triage-completeness.md)). `rows.csv` has one row per injection: the inject
  run's row, the replay's outcome and the signal it judged, and each step's outcome. `by_snr.csv`, `by_period.csv` and
  `by_radius.csv` give per bin the search completeness, the shares each step passed and their product;
  `failed_tests.csv` counts the injections that failed, or left unjudged, each LEO-Vetter test; `outcomes.csv` counts
  each step's outcomes; `summary.md` collects them.
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
- `vetting-second-list`: the second list, the light checks on the ten triage signals that matched only a SPOC TCE or
  ExoMiner row and passed LEO-Vetter's flux tests with a normal RUWE
  ([decision 0033](../docs/decisions/0033-second-list-decisions.md)). `second-list.csv` has one row per signal: each
  vet-v3 check's outcome, the pixel check's outcome, reason and offsets, SPOC's DV statistics and ExoMiner's score for
  the rows matched at its period, on its star or a star novelty matched it to (`dv_tic`, `exominer_tic`), and its
  upcoming sectors; `second-list.md` is the table. Each row's pixel files and the vetting
  run's records stay in the run directories; a promoted row's are in its `vetting/` record.

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
- `short-period-variables-2026-10-17.txt`: the sample stars whose signals all sit at simple ratios of one period
  under 5 days and that LEO-Vetter rejected as non-unique or sinusoidal, and the injection recovery on them against
  the rest (`short_period_variables.py`, [decision 0030](../docs/decisions/0030-short-period-variables.md)).

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
`pixel-diag/`), with the pixel follow-up's memory-cap wrapper in `t13/`. The Gaia DR3 source ids, positions, proper
motions, magnitudes and separations in both files and in the tarball are Gaia DR3 data (above).

`holdout-training-seasons-2026-10-20.md` measures which held-out seasons in M3's vetting runs trained on a single
season whose data hold a transit, and what [decision 0035](../docs/decisions/0035-holdout-training-seasons.md)'s fix
changes there. It is read-only, made outside the pipeline, and gates nothing; its scripts and their outputs are quoted
in it in full.

`triceratops-tic-duplicates-2026-10-21.md` measures how far TRICERATOPS's weighing of the TIC's DUPLICATE and ARTIFACT
rows reaches across M3's TRICERATOPS runs, and what dropping them changes. It is read-only, made outside the pipeline,
and gates nothing; [decision 0036](../docs/decisions/0036-triceratops-tic-duplicates.md) cites it. Its scripts and
their outputs are in `triceratops-tic-duplicates-2026-10-21-scripts.tar.gz` beside it, byte for byte (`t13-dup/`,
with the single-seed rerun's memory-cap wrapper in `t13/`), without the TESScut cutouts, the field-star file or the TIC
paper. The RUWE values in the tarball's `signals.csv` and the Gaia DR3 source ids in its `hosts_check.txt` are Gaia DR3
data, and the Gaia DR2 values the TIC carries are Gaia DR2 data: the `GAIA` source ids in `tic.csv`, `flagged.csv` and
`reach.txt`, and `tic.csv`'s `plx`. Both stay under ESA's terms (above).

`triceratops-phase-binning-2026-10-17.md` is the timing probe behind TRICERATOPS's phase binning (pin P2): binned and
unbinned runs on one star, TIC 146282666, with one seed unbinned. It is read-only, made outside the pipeline before
the M3 build, and gates nothing; [decision 0026](../docs/decisions/0026-triceratops.md) cites it. Its script is in
`triceratops-phase-binning-2026-10-17-scripts.tar.gz` beside it. The probe's command lines and output logs were not
kept; its numbers come from the build's notes written at the time.

`neighbour-controls-2026-10-23.txt` is the output of the network test `test_nearby_eb_controls_show_a_possible_host` in
`tests/test_neighbours.py`, run by hand with `-rP`: each of the neighbour check's two real nearby-binary controls lists
the nearby eclipsing binary its dip comes from among its possible hosts. Decision
[0034](../docs/decisions/0034-neighbour-table-epochs.md) cites it. Its Gaia DR3 source ids and separations are Gaia DR3
data (above).

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
stands on its record. A re-vet adds a version beside the record ([Versions](#versions)). Published files are never
edited, and a correction is a new run. The one exception is decision 0038's: `tess-hunt vetting trim` trimmed the
literature records published before it and scrubbed the home directory from their reviews. In M3 only `dossier.md` and
`vetting/README.md` were rendered again from the files beside them, and `vetting/README.md` still is at every
publish. From M4 on a dossier is rendered once, when its record is published, so a later change to the render code
shows only in later versions. The M3 dossiers keep the text they were published with, without what M4 changed in the
held signals' DDT note ([decision 0039](../docs/decisions/0039-ddt-for-held-signals.md)), on page one (a Triage row),
for review findings no refuter ran on, and in the windows table (decision 0028's Status lists these). A passed signal
is a planet candidate, not a confirmed planet.

- `call.toml`: the maintainer's call: `outcome` (passed, killed or held), `date`, `reasons` in his words, `rests_on`
  (the checks and review findings it rests on), `criteria`, and as the outcome needs, `deciding_evidence` (what would
  decide a held signal), `promotion` (a second-list row's TCE and the reason), `[answers]` (one per confirmed review
  finding), `[sentences]` (why it is not a binary, not another star's light, not an artefact or a known object) and
  `hits_read`. Its words, numbers included, are the maintainer's, quoted in the dossier, not rendered from the runs
  ([decision 0037](../docs/decisions/0037-quoted-text-in-the-dossier.md)).
- `review.json`: the adversarial review: each finding's lens, rating (kill, hold or note), claim, evidence and each
  refuter's verdict, the literature hits it flagged, and a summary. The dossier quotes it as written (decision 0037).
- `review-notes.toml`, where there is one: notes added to the record under decision 0037, each with its date and the
  finding it sits beside in the dossier. They are not part of the review or the call. A slip in the review's text is
  noted there, never edited in `review.json`.
- `review-scripts.tar.gz`: the review's scripts and their small outputs, from the scratch directory its evidence cites
  as `/tmp/t13/<name>/`, each file under 1 MB (1,000,000 bytes), with a `MANIFEST.txt` listing every file left out and
  why (fetched from a service, 1 MB or over, a copy of a published file and the like). Home and data directories in it
  read `~` and `$TESS_HUNT_DATA`, and the maintainer's name reads "the maintainer"
  ([decision 0038](../docs/decisions/0038-literature-trim-and-username-scrub.md)). Beside the records,
  `vetting/review-scripts.tar.gz` holds the scripts every review shared (`/tmp/t13/`), and `vetting/review-brief.md` the
  brief every reviewer and refuter was given; `vetting/README.md` says what the reviews' paths and run names stand for.
- `dossier.md`: the dossier, rendered from the files beside it; every number in it comes from them, except in the
  review and the call, which it quotes (decision 0037).
- `checks.json`: the vet under vet-v3 (`tess-hunt vetting run`): each check's outcome, reason and evidence; the
  flat-prior fit's summary (`fit`) and the density-prior fit's (`fit_prior`); the star's targets row, its Gaia DR3 id
  and RUWE joined where the row lacks them, with where they came from (`star`: `dr3_from`, `dr3_reason`); each
  sector's light-curve source (`sources`); the neighbour table (`neighbours`,
  [decision 0025](../docs/decisions/0025-neighbours.md); its `centre` names the position the separations run from,
  [decision 0034](../docs/decisions/0034-neighbour-table-epochs.md)); every catalogued row on the star with the
  transits of ours it overlaps (`catalogued`); the upcoming sectors and predicted transit windows; triage's ModShift and
  pixel evidence and the search's other signals on the star; and `plot_errors`, each plot the vetting run could not
  draw with its error, which the dossier names where the plot would be (empty when every plot was drawn; a record
  vetted before M4 has none).
- `checks-with-suspect.json`: the same vet with the timing-suspect sectors kept in, as evidence only, never used for
  the call ([decision 0022](../docs/decisions/0022-vet-without-timing-suspect-sectors.md)).
- `neighbours.csv`: the Gaia DR3 stars in the neighbour cone, each with its TESS magnitude and the eclipse depth it
  would need to make the dip.
- `plots/`: each transit, the fold per season and product family, odd and even transits, the whole orbit with phase
  0.5 and the ModShift secondary, and the centroid offsets per sector with the neighbours that could host the signal
  (for a second-list row, `centroids.png` draws triage's record, which holds no offsets; its own are in `pixels.png`).
- `triceratops.json`, `probs.csv`: TRICERATOPS ([decision 0026](../docs/decisions/0026-triceratops.md)): the outcome,
  each run's FPP and NFPP, the stars it weighed and the possible hosts matched to them, and the TIC's DUPLICATE and
  ARTIFACT rows it left out (`dropped_stars`, [decision 0036](../docs/decisions/0036-triceratops-tic-duplicates.md));
  `probs.csv` is the last run's scenario table. A record from a run made before decision 0036 has no `dropped_stars`
  and no `disposition` in its `stars`. A signal a check killed has none, but for 44926986-1: its novelty failed, and
  TRICERATOPS was run on it by name so the binary question would have an answer beside eumemic's listing
  ([decision 0026](../docs/decisions/0026-triceratops.md)); its kill rests on the novelty fail and on TRICERATOPS's.
- `literature.json`: the literature search by name, NASA ADS and ExoFOP
  ([decision 0027](../docs/decisions/0027-literature-by-name.md)), trimmed for publication
  ([decision 0038](../docs/decisions/0038-literature-trim-and-username-scrub.md)). It keeps every identifier (bibcode,
  DOI, arXiv id), who found each paper, each search's query, total and status, and ExoFOP's rows with only the fields
  decision 0038 lists, but no title ADS gave, no ExoFOP comment or file name, and no submitter's or observer's user name
  or notes. Each paper's title comes from an open source, which `title_source` names (`arxiv`, `openalex` or `zenodo`
  for the search's own hits, `openalex_doi` for OpenAlex's record of the paper's DOI), or is null where none has it.
  `trim` gives the sha256 of the run's record it was cut from, the titles run (and `replaced_titles_run`, a titles
  run it replaced) and the fields dropped.
- `pixels.json`, `pixels.png`: a second-list row's pixel check, which triage runs only on novelty passes, run on it as
  triage runs it by `tess-hunt vetting second-list`: the outcome and reason, each measured sector's centroid offset
  and quality, and the offset limit (decision 0028); `pixels.png` plots those offsets with the neighbours that could
  host the signal. Other signals' pixel check is triage's, in `checks.json`, and their centroid plot is
  `plots/centroids.png`.
- `provenance-checks.json`, `provenance-checks-with-suspect.json`, `provenance-triceratops.json`,
  `provenance-literature.json`, `provenance-second-list.json`, `provenance-titles.json`: each run's
  `provenance.json`, copied unchanged: the
  commit, the criteria files and their hashes, the inputs and their hashes, and the command line of the run the files
  beside it came from.
  `provenance-checks.json` stands behind `checks.json`, `neighbours.csv` and `plots/`; `provenance-titles.json` is
  the run of `tess-hunt vetting titles` that looked up, in OpenAlex by DOI, the titles no search's own open-source
  hit gave.

Gaia DR3 data in these records stay under ESA's CC BY-NC 3.0 IGO terms (above), not CC BY 4.0: `neighbours.csv`, the
neighbour table in `checks.json` and `checks-with-suspect.json` (`neighbours`), the possible hosts and the RUWE in
`triceratops.json` (`hosts`, `ruwe`), and the Gaia DR3 columns of the star's row in both checks files
(`dr3_source_id`, `angular_distance`, `ruwe`, `logg_gspphot`, `mass_flame`, `radius_flame`, `logg_flame`), the
possible hosts drawn in `plots/centroids.png` and `pixels.png`, and the same values where `dossier.md` shows them.
The Gaia DR2 and DR3 values the review (`review.json`) quotes, such as radial velocities and their scatter
(`rv_amplitude_robust`, `rv_chisq_pvalue`), astrometric noise (`astrometric_excess_noise`, `ipd_frac_multi_peak`)
and non-single-star flags, are Gaia data too, and so are the same text in `dossier.md` and the Gaia
values in the outputs in `review-scripts.tar.gz`.

### Versions

A re-vet is a new version of a signal's record, never an overwrite
([decision 0041](../docs/decisions/0041-revets-as-versions.md)). `tess-hunt vetting publish --version N` writes
`vetting/<name>/r<N>/`, N from 2 (the M3 record is the first), and changes nothing outside it but `vetting/README.md`,
whose row for the signal then shows its latest version whose call stands and links the versions before it. A version
is published once its `dossier.md`, written last, is there, and never changes after. It holds the files a record
holds, as above, from runs made from its own vetting run, and these:

- `call.toml`, `review.json`, `review-scripts.tar.gz` and any `review-notes.toml`, written into `r<N>/` before it is
  published. The call names the signal, not `r<N>`.
- `provenance-checks.json`, which also names the directory the vetting run read its light curves from (`lc_dir`), the
  revet fetch run whose `lc/` that is (`revet_run`) and the catalog snapshot (`catalogs`).
- For a second-list row, `pixels.json`, `pixels.png` and `provenance-second-list.json`: the previous record's, byte
  for byte, since a re-vet carries the pixel check rather than rerunning it. That provenance names the M3 vetting run,
  not the version's; the dossier says the check was carried.
- `merge.json` and `provenance-merge.json`: what the revet fetch run that wrote the vetting run's light curve did, and
  that run's `provenance.json`, whose summary counts the stars and lists those that `failed` (no sector added or
  redelivered, so no light curve). `merge.json` holds every star of that run, by TIC: `base_sha256`, the sha256 of the
  light curve it merged onto (for the version's star, the one the previous record's vetting run read); `lc_sha256`,
  the merged light curve's, null for a star that failed; `fetch`, the fetch's status and problems; `unfetched`, the
  sectors fetched with problems that got no file; and `sectors`, each sector's status with both products (provenance,
  S3 key, sha256 and timing flag): `kept` (the earlier file), `added` (a sector only the new fetch has),
  `redelivered` (the same product again, clean, over a timing-suspect file) or `kept_m2` (another file found and not
  taken). `sectors` is null for a star whose fetch got nothing.
- For a signal a package under `predictions/` predicts, `prereg.json` and `provenance-prereg.json`: the preregistered
  test of its new season ([decision 0040](../docs/decisions/0040-predictions-for-held-signals.md)) and the run of
  `tess-hunt vetting prereg` that made it. `prereg.json` gives the `signal` (its name and TIC); the `result`
  (`replicated`, `missed`, `untested` or `pending`), the season's `status` and, for an untested or pending result, its
  `reason`; the `predicted_sectors`, the `package` and the `vetting_run`; the day it was judged as of (`as_of`), the
  judging date (`judged_by`) and the day the light curve's revet fetch run started (`fetched`, null for the package's
  own light curve); and, once the season is judged, the `season` and the depths and statistics the test compared. The
  provenance's `skipped` names each signal of the vetting run it left out because an earlier version had judged it,
  with that version and its result. A result once judged stands: every later version holds the judging version's two
  files byte for byte, and its dossier says which version judged it.

A version's `dossier.md` names the version in its title. A section after the call's line links the version before it
and says what changed: the sectors added, redelivered, and kept though another product was found; the windows it
lists for sectors its light curve already holds, which are post-dictions; a carried pixel check; and the masked rows,
catalogued rows and novelty matches that differ from the previous record's, with both catalog snapshots named. It
gives the preregistered test's result beside vet-v3's own held-out result.

## DDT proposals

Each directory under `ddt/` holds one DDT ask for a held signal, named as the signal's record under `vetting/`
([decision 0039](../docs/decisions/0039-ddt-for-held-signals.md)). `tess-hunt ddt render` wrote `proposal.md` and
`targets.csv` from the files beside them and the signal's published record; nothing in them is typed by hand.

- `proposal.template.md`: the proposal's words, in the DDT template's sections, with a placeholder for each value.
- `proposal.md`: the template filled with `substitute`, so a value the sources lack raises instead of rendering. The
  numbers come from the published record (`checks.json`, `triceratops.json`, `literature.json` for the star's names,
  `call.toml`, `review.json` and `provenance-checks.json`) and the criteria files its runs read; the facts about
  archives, sector dates and target lists come from `facts.toml`. The review's text it quotes is quoted word for word
  ([decision 0037](../docs/decisions/0037-quoted-text-in-the-dossier.md)). Its author line is a placeholder, and the
  maintainer pastes it into the TESS office's template to send it.
- `targets.csv`: the target list in the shape of the TESS office's template: its `#` header block, the column line and
  one row, with CRLF line ends. The DDT PI and who made the file when keep the template's placeholders.
- `facts.toml`: each fact the proposal states about archives, dates and target lists, with the page it was read from
  and the date it was read.

Sending a proposal is the maintainer's act; `predictions/facts.toml` records 241522065-1's state with its date
(`ddt_241522065`). These files hold no Gaia data, the star's Gaia DR3 source id included, so they are CC BY 4.0 whole.

## Predictions

Each directory under `predictions/` is one package of preregistered predictions for held signals, made by one
production run of `tess-hunt predictions run` and copied unchanged by `tess-hunt predictions publish`
([decision 0040](../docs/decisions/0040-predictions-for-held-signals.md)). The package's own `README.md` says what is
predicted, the test that will judge it, when, and what a result means, and describes each of its files.
[predictions/README.md](predictions/README.md), rendered by `predictions publish` and `tess-hunt predictions index`,
lists the packages.

- `predictions/facts.toml`: each fact the packages state about archives, target lists, RAVEN's citation and the state
  of a DDT proposal, with the page or file it was read from and the date it was read. A production run takes it only
  from the checkout its code runs from and refuses it with uncommitted changes; each package holds a copy.
- `predictions/dois.toml`, once the maintainer writes it: each package's run id with the DOI and publication date
  Zenodo gave its deposit. Without it the index shows "DOI pending".

The packages hold no Gaia data, so they are CC BY 4.0 whole.

## Catalog snapshots

Each directory under `catalogs/` holds the manifest of one novelty-source snapshot
([decision 0013](../docs/decisions/0013-novelty-sources.md)): each file's URL, size, sha256 and Last-Modified. The
downloaded files themselves are not republished here.
