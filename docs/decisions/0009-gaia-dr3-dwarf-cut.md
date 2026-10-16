# 0009: Gaia DR3 refines the dwarf cut through FLAME log g

- Date: 2026-10-12
- Status: Accepted (approved by the maintainer in the M2 design)

## Context

The spec (section 4.1) defines sample A's dwarf cut on TIC v8.2 log g and says it is "refined with Gaia DR3 in M2
(RUWE recorded for binarity)". TIC v8.2 log g comes from Gaia DR2 radii and masses from colour relations. Gaia DR3's
FLAME module gives each star a mass and radius from its luminosity and temperature.

## Decision

- `targets sample --all-sky` joins every in-sample star to Gaia DR3 through `gaiadr3.dr2_neighbourhood`, keeping the
  nearest DR3 neighbour of the TIC's DR2 source.
- Stars with a FLAME log g (from `mass_flame` and `radius_flame`) below `[sample] flame_logg_min` in
  `criteria/search-v2.toml` are dropped. A star without FLAME values keeps its TIC log g verdict.
- RUWE is recorded in the targets table and shown with every triage signal, with no cut: binaries host planets, and
  the place to weigh them is M3's vetting.
- The run summary counts the stars before and after the cut.

## Evidence

- Unit tests in [tests/test_gaia.py](../../tests/test_gaia.py) (`test_dr3_join_keeps_the_nearest_neighbour`,
  `test_logg_flame_is_solar_for_one_solar_mass_and_radius`) and
  [tests/test_targets.py](../../tests/test_targets.py) (`test_flame_cut_keeps_missing_values`).
- The production targets run
  [20261013T031523Z-targets-cce2f6e-b0d4](../../results/benchmarks/20261013T031523Z-targets-cce2f6e-b0d4/provenance.json),
  from its summary: the TIC query returned 142,378 stars, 142,347 in sample. All 142,347 matched a Gaia DR3 source and
  130,822 have a FLAME log g. The cut kept 139,237, dropping 3,110. Of those kept, 30,195 pass the coverage rule and
  form sample A. The run is marked complete.
- Sector 1751, TESS's special pointing at the comet 3I/ATLAS ([0010](0010-fetch-route-and-qlp-timing.md)), counts
  toward the four-sector minimum, because the targets code counts every sector MAST lists for the star. 56 of these
  stars (55 after the fetch) reach four sectors only with it. The rule was kept as coded rather than changed after the
  targets run: the targets code is part of the hashed search code, frozen from the null search to the production
  search, and both searches use the same sample.
