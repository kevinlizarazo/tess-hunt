# 0022: vet-v3 leaves timing-suspect sectors out of every check and the fit

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design)

## Context

QLP's barycentric timestamps are wrong in Sectors 99 to 104, and MAST still serves the uncorrected `v01` files.
Decision 0010 kept them for detection, flagged `timing_suspect` by fetch's `[[fetch.timing_suspect]]` rule in
`criteria/search-v2.toml`, and named M3's fits and held-out-season check as leaving them out. The ephemeris-independent
comparison ([qlp-timing-robust-2026-10-13.txt](../../results/benchmarks/qlp-timing-robust-2026-10-13.txt)) puts every
reliable pair's median QLP minus SPOC offset under 10 minutes, the largest -6.50 min, and single transits in reliable
pairs at up to +35.25 min. The depth checks average the central half of each transit at the ephemeris. On a transit of
two to three hours, a shift of half an hour moves that core window toward ingress or egress, where the transit is
shallower, and shifts some transits more than others, so it can shave depths unevenly and fake an odd and even
difference or a depth change between sectors. The fits and the held-out season are not the only places a timing error
reaches.

## Decision

- `criteria/vet-v3.toml` has `[timing] exclude_timing_suspect = true`. `vet_signal` then runs on
  `checks.families.good_timestamps(lc)`, the light curve without each sector whose source has `timing_suspect` set.
  Every check that reads the light curve sees only those sectors: the red-noise factors, odd and even, the secondary,
  sector depths, the held-out seasons and `signal_present`, and so does the fit behind shape, density and radius.
- The report lists the sectors left out as `dropped_suspect`.
- `vet_signal(..., include_suspect=True)` runs an evidence-only vet with them in; its report says
  `evidence_only: true` and `dropped_suspect` is empty. It is shown beside the vet and never used for the call.
- This widens 0010's rule from the fits and the held-out season to every check. vet-v1 and vet-v2 keep every sector, so
  their vets reproduce.
- When MAST redelivers a sector, it arrives under a new key and fetch takes it without the flag (0010).

## Limitations

- A signal whose transits fall mostly in QLP S99 to S104 keeps only its other transits. A check left with too little
  data is inconclusive with the reason, never failed, and the evidence-only vet shows what the dropped sectors say.

## Evidence

- [tests/test_families.py](../../tests/test_families.py): `test_good_timestamps_drops_flagged_sectors` (flagged sectors
  and their source entries go; a source with the flag false or absent stays).
- [tests/test_vet.py](../../tests/test_vet.py): `test_suspect_sectors_never_reach_a_check`. A planet in six PDCSAP
  sectors, and a flagged QLP S100 whose even transits are deeper, as an eclipsing binary's are. vet-v3 passes odd and
  even, the secondary, sector depths, the held-out seasons and `signal_present`, reports S100 in `dropped_suspect`, and
  gives S100 no red-noise factor. The evidence-only vet uses S100 and fails odd and even in the QLP family.
- [qlp-timing-robust-2026-10-13.txt](../../results/benchmarks/qlp-timing-robust-2026-10-13.txt) and decision 0010 for
  the offsets.
