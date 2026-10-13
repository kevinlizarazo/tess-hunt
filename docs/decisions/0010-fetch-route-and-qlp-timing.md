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
  fetch, added during the build and not part of the approved design, a cached light curve whose sources lack
  `timing_suspect` is fetched again, so no cached sector goes unflagged.

## Evidence

- Unit tests in [tests/test_mast.py](../../tests/test_mast.py) (`test_bucket_404_falls_through_to_the_mast_api`) and
  [tests/test_fetch.py](../../tests/test_fetch.py) (`test_fetch_falls_back_to_mast_api`,
  `test_qlp_v01_late_sectors_are_timing_suspect`,
  `test_unreadable_version_in_an_affected_sector_is_timing_suspect`, `test_new_product_key_refetches`,
  `test_cached_file_without_timing_flags_refetches`, `test_all_nan_errors_become_scatter_errors`).
- QLP timing offset (Task 6, Step 1). The plan's script, [benchmarks/qlp_timing.py](../../benchmarks/qlp_timing.py),
  read two QLP minus SPOC medians above 10 minutes
  ([output](../../results/benchmarks/qlp-timing-2026-10-13.txt)), and both are artifacts: +75.00 min on TIC 7439481
  S102, where the TOI ephemeris has drifted beyond the 40 minutes either side that the script searches, and -20.50
  min on TIC 22560356 S100, a faint star whose scatter exceeds its transit depth. The ephemeris-independent
  remeasurement, [benchmarks/qlp_timing_robust.py](../../benchmarks/qlp_timing_robust.py), times each QLP transit
  against that sector's own SPOC fit and puts every reliable pair under 10 minutes, the largest at -6.50 min
  ([output](../../results/benchmarks/qlp-timing-robust-2026-10-13.txt)).
- On 2026-10-13 the maintainer ruled that QLP S99 to S104 is used for detection, flagged `timing_suspect`, as
  designed.
- QLP dilution (Task 6, Step 1b). The header of a QLP S100 light curve carries no crowding or dilution keyword. QLP
  Data Release Notes 004 (https://arxiv.org/abs/2603.22236) say the TGLC method forward models the FFIs with the
  ePSF "to remove contamination from nearby stars", and that it "is implemented as of Sector 94 in QLP light curves".
  The depth comparison, [benchmarks/qlp_dilution.py](../../benchmarks/qlp_dilution.py)
  ([output](../../results/benchmarks/qlp-dilution-2026-10-13.txt)), shows QLP `sap_flux` depths in S99 to S103
  reading shallower than SPOC PDCSAP depths on crowded stars, so the removal is incomplete there.
- https://archive.stsci.edu/hlsp/qlp, "Corrected timestamps for QLP Sectors 99-104", read 2026-10-12.
