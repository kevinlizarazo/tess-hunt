# 0023: vet-v3 compares depths only within one product family and fits the PDCSAP family alone

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design)

## Context

Fetch takes each sector's light curve from SPOC (2-minute), TESS-SPOC (full-frame images) or QLP (full-frame images).
SPOC's and TESS-SPOC's PDCSAP fluxes are corrected for the light of nearby stars in the aperture. On crowded stars,
QLP's depths read shallower: in [qlp-dilution-2026-10-13.txt](../../results/benchmarks/qlp-dilution-2026-10-13.txt)
QLP `sap_flux` depths are 0.599 to 0.987 of SPOC's PDCSAP depths in S99 to S103 on five crowded stars, and 0.814 to
1.039 on three of them in sectors before S94 (decision 0010). vet-v2's odd and even, sector-depth and held-out-season
checks compare depths across every sector, so a planet observed in both QLP and PDCSAP sectors can fail them on
dilution alone, and a fit across both would read a smaller planet. Most shortlisted signals mix the two (M3 design,
section 3).

## Decision

- `criteria/vet-v3.toml` has `[families]`: `pdcsap = ["SPOC", "TESS-SPOC"]` and `qlp = ["QLP"]`, each listing the
  provenances fetch records, and `fit = "pdcsap"`, the family the fit uses. Only list-valued keys are families. A
  sector of any other provenance is a family of its own, named by the provenance.
- `src/tess_hunt/checks/families.py` gives `family_of`, `split` (the light curve by family) and `per_family`.
- Odd and even and sector depths run on each family's cadences, and `per_family` combines the results: the check fails
  if any family failed, passes if at least one passed and none failed, and is otherwise inconclusive. The evidence keeps
  each family's result.
- The held-out season's depth tension compares each family in the held-out season with the training cadences of the
  same family and takes the largest. A family with no training cadences, or with fewer than `[holdout] min_points`
  cadences in predicted transits on either side, is recorded and not compared. With no family compared, the season
  row records `tension_skipped` and the season is judged on detection alone. Detection (`min_sigma`) and the expected
  SNR still use every cadence.
- The checks that ask whether a dip is there use every family: `signal_present` and the secondary at phase 0.5.
  Dilution only makes a dip smaller.
- The fit, and so shape, density and radius, uses the PDCSAP family alone. With no PDCSAP cadences the three are
  inconclusive with the reason "no pdcsap data to fit".
- The report gives `criteria_version: "vet-v3"` and each family's sectors (`families`).
- vet-v1 and vet-v2 compare and fit across every sector, so their vets reproduce.

## Limitations

- A family with a single sector cannot test sector depths, and one with too few cadences on odd or even transits
  cannot test odd and even. That family is inconclusive and counts neither way, so an eclipsing binary that shows only
  there is not caught by that check.
- A depth difference between the families themselves is not tested. An eclipse on a neighbour that QLP's photometry
  and SPOC's aperture take in different proportions would show as one; the pixel check and M3's neighbour and
  TRICERATOPS steps look at blends.
- The secondary at phase 0.5 combines both families, so a secondary eclipse seen mostly in diluted QLP sectors reads
  weaker than it is.
- A signal with no PDCSAP sector gets no fit under vet-v3. Every shortlisted signal has PDCSAP transits to fit (M3
  design, section 4.2).

## Evidence

- [tests/test_families.py](../../tests/test_families.py): `test_family_of_known_and_unknown_provenance` (the `fit`
  string is not a family, so a substring of it is no member), `test_split_groups_sectors_by_family` and
  `test_per_family_fail_beats_pass_and_none_passing_is_inconclusive`.
- [tests/test_holdout.py](../../tests/test_holdout.py): `test_family_tension_compares_like_with_like` (QLP at 0.6 of
  the depth in two sectors of the last season: the check fails without families and passes with them),
  `test_family_tension_still_fails_a_depth_change_inside_a_family` (the negative control: half the depth in one PDCSAP
  sector) and `test_tension_skipped_without_a_shared_family` (an all-QLP season trained on PDCSAP seasons is judged on
  detection and records why).
- [tests/test_vet.py](../../tests/test_vet.py): `test_diluted_qlp_does_not_fail_a_planet` (PDCSAP at full depth and
  QLP at 0.6 of it in every season: vet-v2 fails sector depths; vet-v3 passes every check, with the fit given the
  PDCSAP sectors alone), `test_one_family_odd_even_binary_still_fails` (the negative control: an eclipsing binary at
  twice the period fails odd and even in the PDCSAP family while the noisier, diluted QLP sector passes it) and
  `test_no_fit_family_data_leaves_fit_checks_inconclusive`.
