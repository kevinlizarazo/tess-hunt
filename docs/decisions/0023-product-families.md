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
- The held-out seasons compare depths only within a family too, in both places they compare one:
  - The expected SNR, the power guard that decides whether a season can be tested, takes its expected depth from each
    family's own training depth: the training depth of each family with cadences in the held-out season's predicted
    transits, weighted as the held-out depth weights that family's cadences (inverse variance), so it is the depth the
    held-out measurement should read. A training depth pooled over every family would overstate it for a season
    mostly in a diluted family, and let a season be tested whose diluted depth sits near `[holdout] min_sigma`. If such
    a family has no training cadences of its own, or fewer than `[holdout] min_points` in predicted transits, the
    season is untestable with that reason, never missed. This replaces the M3 plan's rule that the expected SNR use
    every cadence, which the build's review found could fail a planet on dilution alone near the guard.
  - The depth tension compares each family's held-out depth with the same family's training depth, where both have
    `min_points` cadences in predicted transits, and takes the largest. When no family has that many held-out
    cadences, the season row records `tension_skipped` and the season is judged on detection alone.
  - Detection itself, the held-out depth over its error against `min_sigma`, still uses every held-out cadence.
  - Each season row lists every family's held-out depth, training depth and tension (`family_depths`) and the expected
    depth (`expected_depth`).
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
- A held-out season holding a family its training seasons lack is untestable, so a signal whose seasons each sit in
  a different family can leave the held-out check inconclusive where vet-v2 would have tested it.

## Evidence

- [tests/test_families.py](../../tests/test_families.py): `test_family_of_known_and_unknown_provenance` (the `fit`
  string is not a family, so a substring of it is no member), `test_split_groups_sectors_by_family` and
  `test_per_family_fail_beats_pass_and_none_passing_is_inconclusive`.
- [tests/test_holdout.py](../../tests/test_holdout.py):
  - `test_family_tension_compares_like_with_like` (QLP at 0.6 of the depth in different shares of the last two
    seasons: the check fails without families and passes with them) and its negative control,
    `test_family_tension_still_fails_a_depth_change_inside_a_family` (half the depth in one PDCSAP sector).
  - `test_expected_snr_stays_within_a_family` (the Task 3 review's case, at a fixed seed: an all-QLP last season,
    faint and diluted, trained mostly on PDCSAP. The pooled expected SNR clears the guard and the season is missed, so
    the check fails; QLP's own expected SNR does not clear it, so the season is underpowered and the check passes) and
    its negative control, `test_a_diluted_family_season_without_its_dip_is_still_missed` (QLP's training depth shows
    the dip clearly and an all-QLP season without it is missed).
  - `test_a_held_out_family_without_training_cadences_is_untestable` (an all-QLP season trained on PDCSAP alone: missed
    without families, untestable with them, with the reason) and
    `test_tension_skipped_when_no_family_has_enough_held_out_cadences` (three held-out cadences in each of two
    families: detected, with the tension skipped and recorded).
- [tests/test_vet.py](../../tests/test_vet.py): `test_diluted_qlp_does_not_fail_a_planet` (PDCSAP at full depth and
  QLP at 0.6 of it in every season: vet-v2 fails sector depths; vet-v3 passes every check, with the fit given the
  PDCSAP sectors alone), `test_one_family_odd_even_binary_still_fails` (the negative control: an eclipsing binary at
  twice the period fails odd and even in the PDCSAP family while the noisier, diluted QLP sector passes it) and
  `test_no_fit_family_data_leaves_fit_checks_inconclusive`.
