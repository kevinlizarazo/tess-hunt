# 0013: Novelty checks every machine-readable source; a match to SPOC alone is inconclusive

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

M1's novelty check reads ExoFOP's TOI and CTOI tables and the Exoplanet Archive's `pscomppars`. The spec (section 4.1)
adds SPOC TCEs, ExoMiner++, community searches and literature by TIC. A survey on 2026-10-12 found more
machine-readable lists in our domain than the spec names (Cao, RAVEN, T16) and some single-object records. The spec
says a match kills a signal as known; but a SPOC TCE that never became a TOI was detected and not promoted, and some
unpromoted TCEs are real planets.

## Decision

- `catalogs refresh` downloads every source into one snapshot, normalises each into the known table with a `kind`
  (`planet`, `candidate`, `community`, `eb`, `tce`), fills missing positions from the TIC, and writes a manifest with
  each file's URL, size, sha256 and Last-Modified. The positions it used are kept in the snapshot as
  `tic_positions.parquet`, and the manifest counts the TICs the TIC could not place. A failed or empty source fails
  the whole refresh; a snapshot is never partial or overwritten.
- A match of any kind but `tce` fails novelty as known. A match only to `tce` rows (SPOC TCEs, ExoMiner++,
  eumemic's re-measured TCEs) is inconclusive with category `known_to_spoc`; triage lists those signals for the
  maintainer to promote by hand, and does not shortlist them.
- `vet` applies the same rule under vet-v2, which lists `tce` in `[novelty] inconclusive_kinds`. vet-v1 has no such
  key, so M1's vets still fail a TCE match.
- One snapshot serves a triage run and its threshold; a fresh one is taken before M3.
- Literature by TIC (Zenodo, arXiv, OpenAlex, all keyless) runs on shortlisted signals only, and its hits are evidence,
  not an outcome. ADS needs a token, so it is searched by hand in M3.
- The source list, URLs and formats are in `src/tess_hunt/sources.py`.

## Evidence

- Unit tests in [tests/test_sources.py](../../tests/test_sources.py), [tests/test_catalogs.py](../../tests/test_catalogs.py)
  (`test_failed_source_leaves_no_snapshot`) and [tests/test_novelty.py](../../tests/test_novelty.py)
  (`test_tce_only_match_is_inconclusive_known_to_spoc`).
- [tests/test_vet.py](../../tests/test_vet.py): `test_tce_only_match_is_inconclusive_under_vet_v2_and_fails_under_v1`.
- The production snapshot's manifest (Task 14) is linked here when it exists.
