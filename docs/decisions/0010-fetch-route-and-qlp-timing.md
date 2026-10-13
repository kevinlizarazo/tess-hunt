# 0010: Fetch falls back to MAST's download API, and late QLP sectors are flagged for timing

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

The spec (section 4.1) reads light curves from the public S3 bucket. On 2026-10-12 the bucket lacked every QLP
product from S99 to S106 and TESS-SPOC S82 to S85, though MAST listed them; most sample-A stars get their only S97 to
S107 data from QLP. Some QLP products in S94 to S97 carry an all-NaN error column. The QLP page at MAST says QLP's
barycentric timestamps are wrong from Orbit 210 (second half of S99) to Orbit 220 (end of S104), and that corrected
files have not been redelivered; the files served are version `v01`.

## Decision

- A bucket 404 falls through to `https://mast.stsci.edu/api/v0.1/Download/file?uri=<dataURI>`, with the same size
  check and retries. The manifest records the route per sector. Production fetches use 4 workers.
- A product whose error column is entirely non-finite gets 1.4826 times the median absolute deviation of its flux as
  every cadence's error, flagged `errors_from_scatter`. Detrend replaces errors with each sector's scatter anyway.
- A product matching a `[[fetch.timing_suspect]]` rule in `criteria/search-v2.toml` (QLP, S99 to S104, `v01`) is kept
  and flagged `timing_suspect`. A product of that provenance and sector whose version can't be read from its filename
  is flagged too. Search and triage use it: an error of minutes is small against 30-minute bins and boxes of an hour or
  more. M3's fits and held-out-season check and M4's predicted windows exclude flagged sectors until MAST redelivers
  them or a correction is validated.
- A redelivery changes the product's key, so the next fetch replaces the file. As an implementation detail of the
  fetch, added during the build and not part of the approved design, a cached light curve any of whose source entries
  has no `timing_suspect` field is fetched again, so no cached sector goes unflagged.

## Evidence

- Unit tests in [tests/test_mast.py](../../tests/test_mast.py) (`test_bucket_404_falls_through_to_the_mast_api`) and
  [tests/test_fetch.py](../../tests/test_fetch.py) (`test_fetch_falls_back_to_mast_api`,
  `test_qlp_v01_late_sectors_are_timing_suspect`,
  `test_unreadable_version_in_an_affected_sector_is_timing_suspect`, `test_new_product_key_refetches`,
  `test_cached_file_without_timing_flags_refetches`, `test_all_nan_errors_become_scatter_errors`).
- QLP timing offset (Task 6, Step 1). The plan's script, [benchmarks/qlp_timing.py](../../benchmarks/qlp_timing.py),
  read two QLP minus SPOC medians above 10 minutes
  ([output](../../results/benchmarks/qlp-timing-2026-10-13.txt)). +75.00 min on TIC 7439481 S102 is an artifact: the
  TOI ephemeris has drifted beyond the 40 minutes either side that the script searches. -20.50 min on TIC 22560356
  S100 is too noisy to count as a measured offset: it rests on 3 transits with a spread of 11.66 min, the star is
  faint and crowded, its SPOC 2-minute scatter per point exceeds its transit depth, and the same star reads -2.00 min
  in S99 and +1.13 min in S101, which is also inside the affected window. The ephemeris drift and the scatter come
  from build diagnostics that are not in the repo. The ephemeris-independent remeasurement,
  [benchmarks/qlp_timing_robust.py](../../benchmarks/qlp_timing_robust.py), picks its own 31 pairs (24 reliable),
  which share no star with the plan script's 8 pairs and so do not include those two. It times each QLP transit
  against that sector's own SPOC fit and puts every reliable pair's median offset under 10 minutes, the largest at
  -6.50 min ([output](../../results/benchmarks/qlp-timing-robust-2026-10-13.txt)). Single transits in reliable pairs
  reach +35.25 min.
- On 2026-10-13 the maintainer ruled that QLP S99 to S104 is used for detection, flagged `timing_suspect`, as
  designed.
- QLP dilution (Task 6, Step 1b). The header of a QLP S100 light curve carries no crowding or dilution keyword. QLP
  Data Release Notes 004 (https://arxiv.org/abs/2603.22236) say the TGLC method forward models the FFIs with the
  ePSF "to remove contamination from nearby stars", and that it "is implemented as of Sector 94 in QLP light curves".
  The depth comparison, [benchmarks/qlp_dilution.py](../../benchmarks/qlp_dilution.py)
  ([output](../../results/benchmarks/qlp-dilution-2026-10-13.txt)), shows QLP `sap_flux` depths at 0.60 to 0.99 of
  SPOC PDCSAP depths on five crowded stars in S99 to S103. Three of the same stars read 0.81 to 1.04 in sectors before
  S94, before TGLC, so the comparison does not show what causes the shallow QLP depths. SPOC's CROWDSAP describes
  SPOC's aperture, not QLP's, so it is only a rough guide to the crowding in QLP's photometry.
- https://archive.stsci.edu/hlsp/qlp, "Corrected timestamps for QLP Sectors 99-104", read 2026-10-12.
- The production sample fetch `20261013T111341Z-fetch-cce2f6e-e14b` (Task 6), from targets run
  `20261013T031523Z-targets-cce2f6e-b0d4`, wrote all 30,195 stars. Of their 253,783 sector sources, 211,947 came from
  the bucket and 41,836 through the MAST API: every QLP S99 to S104 source (41,348, all `v01` and all flagged
  `timing_suspect`) and 488 TESS-SPOC sources from sector 1751. 17,924 QLP sources, all but one in S94 to S104, got
  scatter errors (`errors_from_scatter`). 138 sectors on 133 stars were dropped, each a QLP file with too few good
  cadences (136 with none, one with 13, one with 20); 19 of those stars fall below the coverage rule after the fetch,
  leaving 30,176 covered.
- The control fetch `20261013T151147Z-fetch-cce2f6e-0f95`, from targets run `20261013T031523Z-targets-cce2f6e-630d`
  (the 18 hosts in [benchmarks/known_planets.csv](../../benchmarks/known_planets.csv)): 17 hosts came from the cache
  and one was fetched. All 161 of its sector sources are bucket sources; for a cached host the manifest repeats the
  route recorded by the earlier fetch that wrote the file.
- Sector 1751. 501 sample stars got a sector labelled 1751: 488 TESS-SPOC (200 s, through the MAST API) and 13 SPOC
  (2 min, from the bucket). It is TESS's special pointing at the interstellar comet 3I/ATLAS inside Sector 99
  (2026-01-15 to 2026-01-22); a safe mode lost about 2.8 days and SPOC ran only a subset of its pipeline modules
  (https://heasarc.gsfc.nasa.gov/docs/tess/sector1751_summary.html). Its data sit at BTJD 4055.8 to 4063.0 and overlap
  no other sector's data on any of the 501 stars. It is outside the coverage rule's S97 to S107 window but counts
  toward the four-sector minimum: 56 targets reach four sectors only with it (55 after the fetch). The light curves
  are kept as fetched.
