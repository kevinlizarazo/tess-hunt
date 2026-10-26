# 0021: vet-v3 masks only the kinds of known object the search masked

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design)

## Context

Before it checks a signal, `vet` masks the star's other known transits, so they neither bend the detrending nor add to
the depths it measures. Under vet-v1 and vet-v2, `other_known_transits` masks every row of the catalog snapshot on the
star except the signal under test, found by period (decision 0003): TOIs, CTOIs and archive planets, and also SPOC TCEs,
ExoMiner and eumemic rows, community candidates and eclipsing binaries. The search and triage mask only the sources in
`[detrend] mask_sources` of `criteria/search-v2.toml`, TOI, CTOI and archive; every other row is evidence for novelty
only (decision 0013). The M2 final review (PF21) found the mismatch. It matters for the shortlist: the M3 design
(section 4.2) found SPOC and eumemic TCE rows at other periods on TIC 146282666 whose masks fall on some of the transits
under test, so vet-v2 would cut out part of the signal it is vetting, data the search used to find it.

## Decision

- `criteria/vet-v3.toml` has `[masks] sources`, the snapshot sources whose rows `vet` masks. It equals search-v2's
  `[detrend] mask_sources`: `["TOI", "CTOI", "archive"]`.
- `other_known_transits` in `src/tess_hunt/vet.py` takes the list as `sources` and passes it to
  `catalogs.known_ephemerides`. The signal under test is still left unmasked by decision 0003's period match.
- Every other row on the star stays in the light curve. Novelty still reads every row (decision 0013).
- vet-v1 and vet-v2 mask every row as before, so their vets reproduce.

## Limitations

- A real planet or eclipsing binary known only from a row the list leaves out stays in the light curve: a TCE, a
  community candidate (RAVEN among them), an eclipsing-binary catalog entry, or a row of the archive's per-reference
  table (`archive_ps`). Where such a body's transits overlap the signal's, they add to the depths the checks measure,
  as they did in the search. The M3 dossier lists every other catalogued row on the star with the signal's transits it
  overlaps.

## Evidence

- [tests/test_vet.py](../../tests/test_vet.py): `test_vet_v3_mask_sources_match_the_search`;
  `test_vet_v3_masks_only_the_search_kinds` (a SPOC TCE at another period whose one transit in the data lands on one
  of the signal's: vet-v2 masks it and the check loses that transit's in-transit cadences, vet-v3 masks nothing and
  keeps them, and vet-v2's report has none of vet-v3's fields); `test_signal_with_stale_catalog_epoch_is_not_masked`
  (decision 0003's rule, unchanged).
