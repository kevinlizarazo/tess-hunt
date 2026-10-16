# tess-hunt: design

Status: approved 2026-10-08.
Amended for M2 from the M2 design of 2026-10-12 (kept outside the repository): sections 3, 4.1, 4.2, 5.2, 5.4, 5.6,
6.1, 6.2, 7 and 8. Each changed rule links its decision record in [docs/decisions/](decisions/).
Repo: `kevinlizarazo/tess-hunt` (private, written to go public later).

## 1. Goal

Find a new, credible transiting-planet candidate in public NASA TESS data and take it as far as an independent
researcher can:

- a vetted candidate with a reproducible dossier
- a Zenodo preprint and dataset
- transit times preregistered on Zenodo before TESS looks again
- a TESS Director's Discretionary Time (DDT) proposal for 2-min data

Confirmation (radial velocities, high-resolution imaging) needs other people's telescopes and is out of scope.

Model: Pavel Rabtsevich's TIC 4206066 (2026-10-07): a 3.18 d, ~500 ppm signal on a K dwarf, found by stacking
Sectors 6, 32 and 98. It was vetted over a month of agent-assisted work, preregistered on Zenodo, and TESS approved
his DDT proposal (Program 100) [R1][R2].

Division of work: Claude writes and runs the code. Kevin decides which questions matter, which tests count and every
pass/fail call.

### 1.1 Reporting route (changed in 2026)

ExoFOP paused community candidate (CTOI) uploads on 2026-03-31. It reopened them on 2026-08-19 with this rule:
"Candidates must be published in a peer-reviewed journal that offers online access before being uploaded to ExoFOP."
Upload access needs an approved Published Candidate Upload Request [R3][R4].

A Research Note of the AAS (RNAAS) qualifies only "if the methodology to detect and vet the candidate has been
previously published in a peer-reviewed journal that is available online and is cited by the Research Note" [R4].
RNAAS is not peer reviewed and is limited to 1,500 words with one figure or table [R5].

Consequences for this design:
- The endpoint is the Zenodo, preregistration and DDT route, not a CTOI.
- Methods stay close to published tools in their published configurations (LEO-Vetter, TRICERATOPS). A later RNAAS
  can then cite them. The search is BLS ([0007](decisions/0007-search-engine.md)).
- Whether a pipeline assembled from published tools satisfies the RNAAS clause is unknown. M4 asks
  exofop-support@ipac.caltech.edu before anyone writes a note.

## 2. Decisions (Kevin, 2026-10-08)

| Topic | Decision |
|---|---|
| Ambition | As far as Pavel: dossier, Zenodo preprint, preregistered predictions, DDT proposal |
| Search slice | A (bright Sun-like dwarfs on the newest sectors) first; B (long-period duo/tri-transits) later as a second search mode |
| Owner | `kevinlizarazo` personal account, private |
| Licenses | Code MIT, results CC BY 4.0, copyright "Kevin Lizarazo"; `CITATION.cff` carries the same name |
| Commit email | Repo-local GitHub noreply address; global git config untouched |
| Reviews | Fresh read-only Claude sessions using Kevin's reviewer-plus-refuter workflow, on his go-ahead |

## 3. Why slice A

What has been searched (sources in section 9):

- **SPOC:** searches 2-min targets every sector. Its latest multi-sector run is S1-S96 [L1]. It requires MES > 7.1
  and at least 2 transits [L2], and skips transits longer than 15 h [L3].
- **TESS-SPOC FFI light curves:** cover T <= 13.5 and stop at S85 on MAST [L3][L6].
- **QLP:** searches all data multi-sector to T < 13.5, with light curves through S104 [L7][L8]. Its nominal vetting
  goes only to T <= 10.5 [L7].
- **RAVEN:** S1-S55, 0.5-16 d [L16]. **COUNTESS:** S1-S55, northern CVZ, 6.7% of its catalog [L24].
- **eumemic/exoplanets (2026-10-07):**
  - K/M dwarfs with Teff <= 5300 K and T <= 11.5, plus fainter M dwarfs to T = 13.5
  - 6,430 TOI hosts and 14,112 unpromoted TCEs
  - BLS 0.5-30 d, and 20-100 d only for stars with at least 6 sectors [L4]

  At least five groups posted K/M-dwarf candidates between 2026-10-03 and 2026-10-08 [L4][L5][L28][L29].

Slice A is the complement:
- **Sample:** dwarfs with 5300 < Teff <= 6500 K and T <= 10.5, with at least 4 sectors including at least one of
  S97-S107. Year 8 (S97-S107) observed the southern ecliptic hemisphere, so every sample-A star is southern; section
  4.1 gives the size M2 measured.
- **Periods:** 1-40 d, at least 3 transits.
- **Hosts:** bright, quiet stars, the kind RV follow-up needs.

Costs and risks:
- **Shallow dips:** about 3x shallower than on eumemic's hosts of 0.75 solar radii or less. Expect few signals,
  mostly sub-Neptunes.
- **Closing window:** SPOC's next multi-sector run may report the same signals first.
- **Yield:** eumemic found about 2 candidates per 1,000 bright K/M dwarfs [L4]. Slice A will yield fewer
  (estimate, not sourced).

Slice B (later, M5): duo- and tri-transits with P >~ 20 d on the same stars. It combines Cycles 1 and 3 with
Year 8's sixteen consecutive southern sectors [L25][L30]. Nearly every automated search needs 2-3 transits or caps
the period.

## 4. Pipeline

One Python package, `tess_hunt`, with one CLI (`tess-hunt <stage>`). Each stage reads the previous stage's output
from a run directory and writes its own.

### 4.1 Stages

| Stage | Input | Output |
|---|---|---|
| `targets` | TIC v8.2 via MAST, sector coverage | Frozen target table (parquet) with the query and its date |
| `fetch` | Target table | Per-star slim light curves plus a manifest |
| `detrend` | Slim light curves | Detrended, quality-masked light curves, known transits masked |
| `search` | Detrended light curves | Up to 3 signals per star with SDE/SNR, period, epoch, depth, duration, transit count |
| `triage` | Signals | Shortlist after the null-calibrated threshold, novelty check, LEO-Vetter and pixel vetting |
| `vet` | Shortlist | One dossier per signal: fit, checks, plots, pass/fail/inconclusive per check |
| `publish` | A candidate Kevin passed | Preregistered windows, Zenodo package, DDT draft |

**targets**
- Dwarf cut: log g >= 4.0 from TIC v8.2, refined with Gaia DR3. A star whose FLAME log g (from Gaia DR3's FLAME mass
  and radius) is below 4.0 is dropped; a star without FLAME values keeps its TIC verdict. RUWE is recorded and shown
  for binarity, not cut ([0009](decisions/0009-gaia-dr3-dwarf-cut.md)).
- Sector coverage counts only sectors with an available light-curve product (section 4.2). The four-sector minimum
  counts any pointing that observed the star, including special pointings such as sector 1751, TESS's pointing at
  the comet 3I/ATLAS inside Sector 99, which is outside the S97-S107 window
  ([0010](decisions/0010-fetch-route-and-qlp-timing.md)).
- MAST queries cap near 500,000 rows [T27], so the TIC query runs in 18 declination bands of 10 degrees. Each band is
  retried, and a band near the cap is refused.
- Sample size: M2's targets run selected 30,195 stars, all in the southern ecliptic hemisphere
  ([0009](decisions/0009-gaia-dr3-dwarf-cut.md); `n_sample` in
  [threshold.json](../results/benchmarks/20261014T175116Z-threshold-0d6748e-40ac/threshold.json)).

**fetch**
- Product order per sector: SPOC 2-min PDCSAP, then TESS-SPOC PDCSAP, then QLP.
- Availability on 2026-10-08:
  - SPOC 2-min: through S107
  - QLP: through S104
  - TESS-SPOC: through S85

  FFI-only stars therefore get QLP for S86-S104. Our own photometry for S105+ FFI-only stars is out of scope.
- Reads the public bucket `s3://stpubdata` (us-east-1) anonymously. It is free to read and download [T15][T17].
  - SPOC 2-min: `tess/public/tid/sNNNN/...`
  - TESS-SPOC: `mast/hlsp/tess-spoc/sNNNN/...`
  - QLP: `mast/hlsp/qlp/sNNNN/...`
- On a bucket 404, fetches the same file from MAST's download API (`https://mast.stsci.edu/api/v0.1/Download/file`),
  also without credentials and with the same size check. The bucket lacks QLP S99-S104 and TESS-SPOC S82-S85. The
  manifest records the route per file, and production fetches use 4 workers
  ([0010](decisions/0010-fetch-route-and-qlp-timing.md)).
- A product whose error column is entirely non-finite gets errors from its flux scatter, flagged
  `errors_from_scatter` in the manifest ([0010](decisions/0010-fetch-route-and-qlp-timing.md)).
- QLP S99-S104 (`v01`) carry wrong barycentric timestamps [L8]. They are used for detection and flagged
  `timing_suspect`. Timing-sensitive work (M3's fits and held-out-season check, M4's predicted windows) excludes them
  until MAST redelivers them or a correction is validated ([0010](decisions/0010-fetch-route-and-qlp-timing.md)).
- Keeps only time, flux, flux error, quality flags and per-sector metadata in one compressed file per star, then
  discards the FITS. eumemic moved about 130 GB but stored 12 GB for about 10,000 stars [L4].
- The manifest records each source key and checksum, so any star can be re-fetched exactly.
- Cache location comes from `TESS_HUNT_DATA`, which defaults to `~/.cache/tess-hunt`, never inside the repo.

**detrend**
- wotan biweight per sector, window about 3x the longest searched duration [T6].
- Quality-flag masking and sigma clipping of upward outliers only.
- Known planets and TOIs on the star are masked by ephemeris before the search.
- Cadence differs by era: 30 min (S1-S26), 10 min (S27-S55), 200 s (S56+). Light curves are kept at native
  cadence. The search may bin; the fit does not.

**search**
- BLS on 30-minute bins over the full multi-sector baseline, 1-40 d. M1 benchmarked BLS against TLS on speed and
  injection recovery and chose BLS ([0007](decisions/0007-search-engine.md)); TLS left the search with the search fix
  ([0008](decisions/0008-search-fix.md)).
- Up to 3 signals per star, under the search fix ([0008](decisions/0008-search-fix.md)):
  - at each period, box durations reach at most twice the central transit duration for the star's density;
  - periods at a listed harmonic of an emitted signal are left out of the later ranks;
  - every emitted signal has at least 3 transits with data in them; a peak with fewer is masked and the search
    retried.
- The search goes on to a further rank only while the SDE is at least `continue_sde`, which production takes from
  the null threshold (section 5.4).
- Budget: in the typical-star injection run, each search of a random production target took a median of 38 s
  ([summary.md](../results/benchmarks/20261015T131443Z-benchmark-inject-fe29585-8496/summary.md)).

**triage**
- **Threshold:** detection threshold from our own null (section 5.4). Triage takes the sample signals at or above it.
  It refuses a search run whose positive controls failed (section 5.6), whose search criteria or search code differ
  from the null's, or whose `continue_sde` is below the threshold
  ([0011](decisions/0011-positive-controls-in-production.md), [0019](decisions/0019-null-threshold.md)).
- **Novelty check** against one frozen, hashed snapshot of every machine-readable source, taken for the triage run and
  refreshed before M3 ([0013](decisions/0013-novelty-sources.md)). Each row has a kind: planet, candidate, community,
  eb (eclipsing binary) or tce.
  - ExoFOP TOIs and CTOIs [T28]
  - the NASA Exoplanet Archive `ps` and `pscomppars` tables [T30] (gotcha: `pscomppars.tic_id` is a string like
    "TIC 281461362")
  - SPOC TCE tables: single-sector S1-S107, multi-sector to S1-S96 [T31] (kind tce)
  - ExoMiner++ catalogs (Zenodo 10.5281/zenodo.15466292 and 10.5281/zenodo.17707413) [T32] (kind tce)
  - the RAVEN and T16 candidate catalogs
  - community searches: eumemic's candidates and its re-measured unpromoted TCEs (kind tce), Cao, and the
    single-object records of Rabtsevich, Thawani, Barve, Ozturk, Chopra and Th0rgal, listed with their parsers in
    `src/tess_hunt/sources.py`. tess-transit-hunter publishes HTML only and is not parsed; the literature search
    covers it, and its one candidate is an M dwarf, outside sample A.
  - eclipsing binaries: the TESS EB catalogs (Prša et al. 2022, Kostov et al. 2025, Justesen and Albrecht 2021),
    Gaia DR3's `vari_eclipsing_binary` for the sample's stars, and VSX's eclipsing types within 5" of each sample star
    through the CDS cross-match service

  Matching covers the same TIC and TIC neighbors within 2.5', period harmonics and epoch consistency. Rows without a
  usable epoch match on period alone ([0002](decisions/0002-catalog-data-quality.md)): Gaia DR3's eclipsing binaries
  (their reference time is not an eclipse time), VSX, and Cao, whose epochs are estimates. A match of any kind but
  tce kills the signal as "known", with the match recorded. A match only to tce rows is inconclusive: the signal is
  not shortlisted and goes to a "known to SPOC" table that the maintainer can promote by hand
  ([0013](decisions/0013-novelty-sources.md)).
- **Literature:** Zenodo, arXiv and OpenAlex, searched by TIC without keys, for shortlisted signals only. Hits are
  evidence for M3, not an outcome. ADS needs a token and is searched by hand in M3
  ([0013](decisions/0013-novelty-sources.md)).
- **LEO-Vetter 1.2.0:** its automated false-alarm and false-positive tests [T10] with the thresholds of the paper's
  text, which differ from 1.2.0's code defaults in two tests, each written out in `criteria/triage-v1.toml` [T49].
  Its input is the native-cadence light curve, re-detrended with the signal's transits held out of the trend and the
  star's other signals and known objects dropped. A test whose comparison reads a missing or non-finite metric, or a
  missing stellar value, makes the outcome inconclusive ([0012](decisions/0012-leo-vetter-configuration.md)).
- **Pixels:** for signals that pass novelty and the flux tests, LEO-Vetter's pixel vetting: transit-diffImage
  difference-image centroids on the latest five sectors with data. The published rule makes a signal a false positive
  when the best-quality sector's offset exceeds 15". TESS pixels are 21". NaN, no usable sector or an exception is
  inconclusive ([0012](decisions/0012-leo-vetter-configuration.md)).
- **Shortlist:** a novelty pass, a flux-level planet candidate and a pixel pass. Only explicit passes advance (section
  5.1).

**vet** (per shortlisted signal)
- **Fit:** batman plus emcee, with a stellar-density prior from TIC/Gaia.
- **Light-curve checks:**
  - signal present: the combined in-transit depth over its red-noise error
    ([0017](decisions/0017-signal-present-check.md))
  - odd/even depth
  - secondary eclipse
  - per-sector depth consistency
  - shape (V vs U)
  - duration vs stellar density, with the fit error taken on the posterior's side facing the TIC value
    ([0016](decisions/0016-density-error-and-nan-posteriors.md))
  - radius: the fitted Rp/R* times the TIC radius, failing above 22 Earth radii
    ([0018](decisions/0018-deep-eclipsing-binary-rule.md))
- **Held-out-season prediction (Pavel's test):** fit on all seasons but one, predict the hidden season's transits,
  and test only those windows. Repeat for each season.
- **Criteria:** `criteria/vet-v2.toml`, built in M2 with one decision record per rule
  ([0014](decisions/0014-vet-constants-in-criteria.md) to [0018](decisions/0018-deep-eclipsing-binary-rule.md)). M1's
  vets stay under vet-v1.
- **Pixels:** read from triage's evidence (above). M3 reviews the per-sector offsets.
- **Neighbors:** Gaia DR3 stars within about 1', each with the depth it would need if it were the source.
- **TRICERATOPS 1.1.0:** FPP and NFPP averaged over 10 runs [L4]. Thresholds from the TRICERATOPS paper [T48]:
  - validated: FPP < 0.015 and NFPP < 10^-3
  - likely planet: FPP < 0.5 and NFPP < 10^-3
  - likely nearby false positive: NFPP > 10^-1

  Caveat: with 30-min data alone "there does not appear to be a region of parameter space in which planets can be
  confidently validated" [T48].
- **Output:** a dossier rendered from the run's outputs (section 5.5).

**publish** (M4, only for a candidate Kevin passes)
- **Preregistration:** predicted transit windows with uncertainties for TESS's upcoming sectors, plus the pass/fail
  rule, deposited on Zenodo before the data exists.
- **Zenodo preprint and dataset:** each version is its own record with its own DOI, under one concept DOI; 50 GB
  per record; a license is required [T44][T45].
- **DDT proposal:** for 2-min cadence through the TESS DDT page (`https://tess.mit.edu/science/ddt/`).
- **Acknowledgements and DOIs:** per section 6.

### 4.2 Data access facts (verified 2026-10-08)

| Product | Size per file | DOI |
|---|---|---|
| SPOC 2-min LC | ~2.0 MB | 10.17909/t9-nmc8-f686 |
| SPOC TPF | 49-76 MB | 10.17909/t9-yk4w-zc73 |
| SPOC DV (single, multi) | ~11 MB PDF | 10.17909/t9-2tc5-a751, 10.17909/t9-yjj5-4t42 |
| TESS-SPOC FFI LC (CC BY 4.0) | ~1.1 MB | 10.17909/t9-wpz1-8s54 |
| QLP LC (CC BY 4.0) | ~0.5 MB | 10.17909/t9-r086-e880 |

- New sectors reach the bucket monthly. S107 is the latest fully public sector, and S108's FFIs arrive in weekly
  batches through about 2026-10-09 [L39].
- TESScut is limited to 10,000 pixels per cutout and 5 requests per second [T25].
- QLP light curves run through S104. S99-S104 await corrected timestamps, and the files served are still `v01` [L8].
  The bucket lacks QLP S99-S104 and TESS-SPOC S82-S85, which MAST's download API serves (verified 2026-10-12;
  [0010](decisions/0010-fetch-route-and-qlp-timing.md)).

## 5. Rigor

These rules come from the TIC 4206066 thread and its replies. Each is enforced in code, not left as a habit.

### 5.1 Three outcomes per check
Every vetting check returns `pass`, `fail` or `inconclusive`, with the evidence it used (inputs, counts, numbers).
Empty input, a skipped step or a missing dependency gives `inconclusive`, never `pass`. A signal advances only on
explicit passes. The thread's recurring bug was "an empty list wired to pass".

### 5.2 Every check proven to fail
Each check ships with a negative-control test on synthetic data that must make it fail:

| Check | Planted failure |
|---|---|
| Odd/even, secondary | Eclipsing binary at twice the period |
| Centroids (triage's pixel check) | Offset blend (below) |
| Held-out season | Wrong period |
| Novelty | A known TOI |
| Duration vs density | A giant-star host |
| LEO-Vetter flux tests (triage) | A variable; eclipsing binaries (below) |
| Radius | A deep eclipse with true Rp/R* 0.6 ([0018](decisions/0018-deep-eclipsing-binary-rule.md)) |
| Positive controls | A run missing a required planet (below) |

Triage's pixel check fails a 16" offset, and the real nearby eclipsing binaries TOI-1175.01 and TOI-1058.01 in
network tests. LEO-Vetter's flux tests reject a sinusoidal variable as a false alarm. Of two eclipsing binaries
searched at half their period, they reject a deep one as a false alarm through the individual-transit test, and a
shallower one as a false positive through odd/even ([0012](decisions/0012-leo-vetter-configuration.md)). A
production search that misses a required positive control is invalid
([0011](decisions/0011-positive-controls-in-production.md)).

One exception: `signal_present` never fails, because a weak dip is a lack of evidence for a planet, not evidence
against one. Its negative control, pure noise at an arbitrary ephemeris, is inconclusive rather than a fail. The
control that matters is the pipeline's: such a signal does not advance (the pure-noise test in `tests/test_vet.py`;
[0017](decisions/0017-signal-present-check.md)).

A check without a passing negative-control test is not merged.

### 5.3 Criteria frozen before the data
- Thresholds and pass/fail rules live in versioned files under `criteria/`. A production run refuses to start if
  the criteria files have uncommitted changes, and it stamps their hash into the run.
- Changing a criterion after seeing results needs an entry in `docs/decisions/` with the reason. Kevin approves it.
- Every dossier names the criteria version it was judged under.

### 5.4 Threshold from our own null, with injection-recovery
- **Threshold:** set by running scrambled light curves through the full pipeline. Sector order and time offsets
  are shuffled so real periodic signals decohere, following LEO-Vetter's method; inverted light curves are rejected
  there because of scattered light and flares [T49]. The threshold rule (null maximum or a stated quantile with an
  expected false-alarm count) is fixed in the criteria file. The threshold is recomputed whenever the null set grows,
  and a run fails if its threshold sits below the current null's value.
- **Scramble (M2):** as in the LEO-Vetter paper [T49], each sector is split into segments at every internal gap
  longer than `[null] segment_gap_days` (in most sectors, its two orbits; the fetched stars'
  [sector structure](../results/benchmarks/sector-structure-2026-10-13.txt)), the segments are shuffled within the
  sector, and then the sectors are shuffled. The "time offsets" are the shifts that move each segment into its new
  slot. Segments within a sector are placed a fixed `[null] placement_gap_days` apart (1.0 d in
  `criteria/search-v2.toml`), above detrend's 0.5 d break tolerance, so moved segments are detrended apart as orbits
  are. Every sample star is scrambled once; the null scrambles the raw light curve, with known-object masks
  following their cadences, then runs the production detrend and search
  ([0019](decisions/0019-null-threshold.md)).
- **Exclusions:** before the threshold is counted, two rules drop null signals. A null signal that matches, on period
  alone at a listed harmonic, a known object of any kind on its own star in the triage snapshot (TCEs and catalogued
  eclipsing binaries included) is dropped. So is every null signal on a star that hosts a catalogued planet,
  candidate, community candidate or eclipsing binary; stars whose only catalogued rows are TCEs stay in the null, the
  maintainer's choice on 2026-10-13. Nothing is removed by hand ([0019](decisions/0019-null-threshold.md)).
- **Rule:** the threshold is the highest SDE among the remaining null signals that pass LEO-Vetter's false-alarm
  tests (`criteria/triage-v1.toml` `[threshold]`); a signal LEO-Vetter cannot judge counts as passing. The expected
  number of false alarms is the sample size over the null's size. Production takes the threshold as its
  `continue_sde`, and triage refuses a search whose criteria or search code differ from the null's, or whose
  `continue_sde` is below the highest threshold computed for them ([0019](decisions/0019-null-threshold.md)). M2's
  threshold, with the null it came from:
  [threshold.json](../results/benchmarks/20261014T175116Z-threshold-0d6748e-40ac/threshold.json).
- **Injection-recovery:** one planet per light curve, injected before detrending:
  - P uniform in 1-40 d
  - Rp log-uniform over 0.5-16 R_Earth
  - b uniform in 0-1
  - epoch uniform in phase, quadratic limb darkening, circular orbits
  - redraw if fewer than 3 transits

  The full detrend and search then reruns, and a match uses the Coughlin et al. criterion [T49]. The output is a
  completeness map in period and radius. M2's map for the sample comes from random production targets searched at
  the production threshold:
  [summary.md](../results/benchmarks/20261015T131443Z-benchmark-inject-fe29585-8496/summary.md).

### 5.5 Numbers come from code
Dossiers and reports are rendered from run outputs by templates. No number in a dossier, README, preprint draft or
proposal is typed by hand or copied from an agent's summary. A report test fails if a template references a value
missing from the run.

### 5.6 Positive controls in every run
Each production run includes the known-planet set (section 7, M1) with their masks off. If the run does not recover
them at their known periods, it is marked invalid and its signals are not triaged.

In M2 the controls run inside the production search, alongside the sample. Each is classified against its catalog
ephemeris at the production threshold, with search-v2's `[match]` and `[benchmark]` rules; triage has no controls
table of its own. A missed required planet makes the run invalid and triage refuses it; a missed non-required planet
is a warning ([0011](decisions/0011-positive-controls-in-production.md)).

### 5.7 Provenance
Each run directory carries `provenance.json`:
- git commit, plus a refusal on a dirty tree for production runs
- `uv.lock` hash and criteria hash
- data manifest hash
- command line, start and end time

Runs are immutable once finished.

### 5.8 Independent review
- **Each milestone** ends with Kevin's review workflow: reviewer lenses plus two refuters per finding, fresh
  read-only sessions.
- **Each shortlisted signal** gets a fresh read-only session asked to kill it.
- Kevin makes the pass/fail call and records it in the dossier.

## 6. Repo

```
tess-hunt/
  pyproject.toml, uv.lock
  src/tess_hunt/      cli, targets, fetch, detrend, search, triage, novelty, vet/ (one module per check),
                      publish, provenance, report
  criteria/           versioned pass/fail rules (TOML)
  benchmarks/         known-planet set, injection config
  tests/              unit tests and negative controls on synthetic light curves
  docs/               design.md (this spec), decisions/
  results/            CC BY 4.0: candidate tables, dossiers, plots
  LICENSE (MIT), results/LICENSE (CC BY 4.0), CITATION.cff, ACKNOWLEDGEMENTS.md, README.md
  .github/workflows/ci.yml
```

### 6.1 Environment
Python 3.12 with a uv lockfile. Resolution was checked with uv 0.12.10 on Linux x86_64 [T]. M1 confirmed the
environment by running it, and CI installs it from the lockfile.

| Package | Pin | Note |
|---|---|---|
| transitleastsquares | ==2.0 | Released 2026-10-06 with fixes that change results; batman no longer required |
| triceratops | ==1.1.0 | Changes FPP/NFPP for crowded targets; pins pytransit 2.2. On 3.12 it forces numpy<2, scipy<1.14 and setuptools<81 (pytransit imports pkg_resources); uv resolved astropy 7.2.2, numpy 1.26.4, scipy 1.13.1 |
| lightkurve | 2.6.0 | Caps pandas<3 |
| astroquery | 0.4.11 | |
| wotan | 1.10 | Dormant since 2021; install scikit-learn, not `sklearn` |
| leo-vetter | 1.2.0 | Pixel vetting needs transit-diffImage. GPL-3.0 |
| transit-diffImage | git commit `2b13199` | Not on PyPI; GPL-3.0; see below |
| batman-package | 2.5.3 | |
| emcee | 3.1.6 | |
| numba | 0.68.0 | Requires numpy<2.6 |

transit-diffImage's undeclared imports (spiceypy, lightkurve, pandas, matplotlib, requests) are declared in
`pyproject.toml`, and it brings tess-point. It shells out to curl, unzip and rm, so `curl` and `unzip` are system
requirements, and its PRF URL is plain http, which redirects to https.

Without the triceratops pin, uv silently falls back to triceratops 1.0.21. Supported platforms are Linux and macOS;
Windows is supported through WSL only. LEO-Vetter and transit-diffImage are GPL-3.0; tess-hunt's code is MIT and
imports them.

### 6.2 Public-readiness from day one
- **No secrets.** All data is public and S3 is read unsigned. No credentials appear in code, config or CI.
- **No machine paths.** The cache comes from `TESS_HUNT_DATA`; nothing assumes a username or drive.
- **Commits** use a repo-local GitHub noreply email.
- **README** states that every candidate is a candidate, not a confirmed planet.
- **`ACKNOWLEDGEMENTS.md`** carries:
  - the TESS mission acknowledgement text [T40]
  - the product DOIs in section 4.2, cited with sector ranges [T41]
  - ExoFOP's DOI 10.26134/ExoFOP5 [T43]
  - QLP's citations (Huang 2020a,b; Kunimoto 2021, 2022) [T23]; S27+ users are invited, not required, to offer a
    QLP team member co-authorship
  - TESS-SPOC's citation (Caldwell 2020) [T24]
  - the acknowledgement or citation each source M2 added asks for: Gaia DR3, CDS's VizieR and cross-match service,
    VSX, the eclipsing-binary and novelty catalogs, arXiv and OpenAlex, LEO-Vetter, transit-diffImage, tess-point,
    TESScut, SpiceyPy and SPICE
- **Raw data never enters git.** Only small results go under `results/`.

### 6.3 CI
A GitHub-hosted Ubuntu runner runs lint and unit tests, including every negative control, on synthetic light
curves with no network. Integration runs against real data are local.

## 7. Milestones

Each milestone gets its own implementation plan. The first plan covers M1 only.

**M1: Foundation.**
- Repo, environment, CI, provenance, criteria files and the decision log.
- `fetch`, `detrend`, `search` and the `vet` checks working on a small set: the known-planet set plus about 200
  random sample-A stars.
- The known-planet set is about 20 TOIs with TFOPWG disposition KP or CP, on hosts matching sample A, with periods
  of 1-40 d and depths spread from about 100 ppm up. Pi Men c (TIC 261136679) is the single-sector smoke test.
- BLS vs TLS benchmark.

Done when:
- the known-planet set is recovered at its known periods
- injection-recovery produces a completeness map
- every check's negative control fails as designed
- the search-engine choice is recorded in `docs/decisions/`
- CI is green

**M2: Search sample A.** The search fix ([0008](decisions/0008-search-fix.md)), `targets` for the full sample with
the Gaia DR3 cut, bulk `fetch`, null calibration, the full search with its positive controls, `triage` (novelty,
LEO-Vetter and pixels) and vet-v2's criteria.

Done when:
- the production search's positive controls pass (every required known planet recovered at the production threshold)
- the null threshold is recorded, with the null it came from
- the triage run's shortlist exists, each row with novelty, LEO-Vetter flux and pixel evidence
- the search fix's benchmark reruns and the typical-star completeness map are published under `results/`
- CI is green

**M3: Vetting.** Dossiers for every shortlisted signal, one adversarial review per signal, and Kevin's calls. Done
when each signal is passed or killed with reasons in `results/`. M3 also takes up a treatment for short-period
variables whose other multiples take the search's ranks ([0008](decisions/0008-search-fix.md)).

**M4: Publication** (only if a candidate survives).
- Preregistered transit windows published before TESS's next look.
- The Zenodo preprint and dataset.
- The DDT proposal.
- The exofop-support question about the RNAAS route.
- Contact with professionals: TFOP accepts general members without observing facilities [T39], and researchers
  offered help in the TIC 4206066 thread.

Done when the prediction is public before the data exists.

**M5: Slice B.** A long-period duo/tri-transit search mode on the same light curves, with alias lists for the
period. It meets the same bar as M2 and M3.

## 8. Risks and open questions

- **Timing:** SPOC's next multi-sector run or a QLP release may report our signals first. M2 searched the whole
  sample at once for that reason.
- **Coverage gap:** TESS-SPOC stops at S85 and QLP at S104, so FFI-only stars have no S105-S107 light curves
  without our own photometry, which is out of scope.
- **30-min data:** a candidate seen mostly in 30-min data cannot be validated by TRICERATOPS alone; that is the case
  for the DDT ask.
- **Unverified estimates:** the yield is an estimate. M2's runs replaced the sample-size and search-cost estimates
  (section 4.1).
- **Real signals in the null:** the scramble keeps each segment's transits in phase and can leave some of a real
  planet's or binary's transits evenly spaced by chance, so an uncatalogued real signal can set a null peak above the
  noise. In the scramble probe, 4 of the 59 scrambled signals passed every false-alarm test, all on a synthetic planet
  star at periods that are no harmonic of its own, the highest at SDE 19.52
  ([output](../results/benchmarks/scramble-leo-probe-2026-10-13.json)). The host exclusion drops stars with
  catalogued objects; a real signal it misses can only raise the threshold, so the error is conservative
  ([0019](decisions/0019-null-threshold.md)).
- **Completeness at the threshold:** injection-recovery on random production targets at the production threshold
  recovered 0.385 of 2,000 injections: none below an expected SNR of 10, 0.0541 from 10 to 15 and 0.43 from 15 to 20
  ([summary.md](../results/benchmarks/20261015T131443Z-benchmark-inject-fe29585-8496/summary.md)).
- **LEO-Vetter's strictness:** its thresholds were tuned on QLP light curves of M dwarfs [T49]. In the production
  triage run it passed 18 of the 78 signals that match a catalogued candidate at its period, and rejected 175 of the
  176 that match a catalogued eclipsing binary at its period or a harmonic. The tests failed most often were
  `non_unique` (1,775 signals) and `unphysical_duration` (1,578) ([0012](decisions/0012-leo-vetter-configuration.md)).
  Triage therefore misses many real planets; M3 measures triage's completeness before any setting changes.
- **Planets on short-period variables:** the search can spend later ranks on a pulsator's other multiples, so
  completeness on those stars is low ([0008](decisions/0008-search-fix.md)). M3 takes up a treatment.
- **QLP S99-S104 timing:** their timestamps are wrong until MAST redelivers them [L8]. An ephemeris-independent
  comparison with SPOC puts every reliable median offset within 10 minutes, the largest -6.50 min
  ([output](../results/benchmarks/qlp-timing-robust-2026-10-13.txt)). Detection tolerates minutes; M3 and M4 must not
  fit or predict from those sectors until they are redelivered or corrected
  ([0010](decisions/0010-fetch-route-and-qlp-timing.md)).
- **QLP dilution:** on crowded stars, QLP `sap_flux` depths in S99-S103 read 0.60 to 0.99 of SPOC's
  crowding-corrected depths ([output](../results/benchmarks/qlp-dilution-2026-10-13.txt)). For a signal seen mainly
  in QLP sectors, LEO-Vetter's radius tests can read a planet too small
  ([0012](decisions/0012-leo-vetter-configuration.md)).
- **transit-diffImage's timing:** its bundled SPICE ephemeris ends on 2020-10-26, so for later sectors its in-transit
  window sits minutes off TESScut's barycentric times. On the pixel controls it moved at most 77 of a sector's 698
  in-transit cadences, below the fifth that would have stopped the build
  ([output](../results/triage/pixel-timing-2026-10-14.txt), [0012](decisions/0012-leo-vetter-configuration.md)).
- **The pixel rule's known miss:** TOI-1399.01, a nearby-eclipsing-binary false positive, passes the 15" rule
  ([output](../results/triage/pixel-controls-2026-10-14.txt), [0012](decisions/0012-leo-vetter-configuration.md)).
- **Slow or unstable services:** TESScut is slow and rate-limited [T25], so pixels run only on the few signals that
  reach them. MAST's download API documents no rate limit, so fetch uses 4 workers with retries
  ([0010](decisions/0010-fetch-route-and-qlp-timing.md)). The Gaia archive may be unstable before DR4; the targets
  stage retries each chunk and fails the run rather than write a partial join.
- **Gaia data licence:** Gaia DR3 data are distributed under CC BY-NC 3.0 IGO, not CC BY 4.0. The eclipsing-binary
  rows only drop null signals and fail novelty, and are not republished. The `ruwe` column of the published triage
  tables is Gaia DR3 data, so it is the one exception to the CC BY 4.0 licence of `results/` and stays under ESA's
  terms ([results/README.md](../results/README.md), [ACKNOWLEDGEMENTS.md](../ACKNOWLEDGEMENTS.md)).
- **Fragile dependencies:** wotan is dormant and transit-diffImage is unpackaged. If either breaks on the pinned
  stack, the fallback is a decision-log entry, not a silent swap.
- **RNAAS eligibility** is unknown until exofop-support answers.

## 9. Sources

Facts marked [R], [L] and [T] were fetched on 2026-10-08. The [L] and [T] numbers come from unpublished working notes,
which is why they have gaps; only the URLs listed here are the sources.

- [R1] Reddit thread "I think I found a planet nobody knew existed", and https://x.com/p_rabtsevich/status/2107803696058822742
- [R2] https://gist.github.com/MrBoostie/b7a34b9ec96fbfb37e8fd250ba6debba; preprint https://doi.org/10.5281/zenodo.22967456; predictions https://doi.org/10.5281/zenodo.23175179; https://tess.mit.edu/science/ddt/
- [R3] https://exofop.ipac.caltech.edu/tess/news.php
- [R4] https://exofop.ipac.caltech.edu/tess/candidate_help.php
- [R5] https://journals.aas.org/research-notes/
- [L1] https://archive.stsci.edu/tess/bulk_downloads/bulk_downloads_ffi-tp-lc-dv.html
- [L2] https://arxiv.org/abs/2103.12538
- [L3] https://archive.stsci.edu/hlsp/tess-spoc
- [L4] https://github.com/eumemic/exoplanets
- [L5] https://github.com/eumemic/exoplanets/blob/main/results_public/novelty_check.md
- [L6] MAST CAOM count query for TESS-SPOC products, 2026-10-08 (0 products for S86-S120)
- [L7] https://tess.mit.edu/qlp
- [L8] https://archive.stsci.edu/hlsp/qlp
- [L16] https://arxiv.org/abs/2603.22597 (RAVEN)
- [L24] https://arxiv.org/abs/2606.13789 (COUNTESS I)
- [L25] https://arxiv.org/abs/2310.17268 (duotransits)
- [L28] https://gist.github.com/MrBoostie/b7a34b9ec96fbfb37e8fd250ba6debba
- [L29] https://comdex4.github.io/tess-transit-hunter/findings.html
- [L30] https://tess.mit.edu/observations/sector-107/
- [L39] https://outerspace.stsci.edu/display/TESS/TESS+Holdings+Available+by+MAST+Service
- [T6] https://github.com/hippke/wotan
- [T10] https://github.com/mkunimoto/LEO-Vetter
- [T15] https://registry.opendata.aws/mast-tess/
- [T17] https://outerspace.stsci.edu/x/GAPvCw
- [T23] https://archive.stsci.edu/hlsp/qlp
- [T24] https://archive.stsci.edu/hlsp/tess-spoc
- [T25] https://mast.stsci.edu/tesscut/docs/getting_started.html
- [T27] https://mast.stsci.edu/api/v0/
- [T28] https://exofop.ipac.caltech.edu/tess/Introduction_to_ExoFOP_php_functions.php
- [T30] https://exoplanetarchive.ipac.caltech.edu/docs/TAP/usingTAP.html
- [T31] https://archive.stsci.edu/tess/bulk_downloads/bulk_downloads_tce.html
- [T32] https://github.com/nasa/ExoMiner/releases
- [T39] https://tess.mit.edu/followup/apply-join-tfop/
- [T40] https://archive.stsci.edu/publishing/mission-acknowledgements
- [T41] https://archive.stsci.edu/publishing/doi
- [T43] https://exofop.ipac.caltech.edu/tess/pcp.php
- [T44] https://about.zenodo.org/policies/
- [T45] https://help.zenodo.org/docs/deposit/manage-versions/
- [T48] https://arxiv.org/abs/2002.00691 (TRICERATOPS)
- [T49] https://arxiv.org/abs/2509.10619 (LEO-Vetter)
- [T] uv dependency resolution, run 2026-10-08
