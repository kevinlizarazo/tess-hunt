# 0025: The neighbour table: Gaia DR3 stars within 1' and the eclipse depth each would need

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design), except Ruling N (a DR3 id joined for a star whose
  targets row lacks one), which the M3 build's controller made after that approval and is Proposed until the
  maintainer reviews it

## Context

TESS pixels are 21" across, so a dip in a target's light curve can come from another star whose light falls in the
same aperture: an eclipsing binary a few magnitudes fainter, diluted down to a planet's depth. Triage's pixel check
measures where the dip sits in the difference image, and it misses a blend close enough to stay inside its rule
(TOI-1399.01, `benchmarks/README.md`). The spec asks for the Gaia DR3 stars within about 1' of each target, each with
the depth it would need if it were the source (`docs/design.md`, Neighbors; M3 design, section 4.4). TRICERATOPS
(Task 7) weighs the stars the TIC lists within 10 pixels; the table is how a Gaia star the TIC merged or lacks gets
seen.

## Decision

- `neighbours.gaia_cone` takes every `gaiadr3.gaia_source` row within `[neighbours] radius_arcmin` (1.0) of the
  target's TIC position: `source_id`, `ra`, `dec`, `phot_g_mean_mag`, `bp_rp`, the separation in arcseconds, and the
  proper motion `pmra` (times cos dec) and `pmdec` in mas/yr (null for a two-parameter solution) with the positions'
  `ref_epoch`, nearest first. The table keeps the proper motions so TRICERATOPS's cross-check can match each possible
  host at the TIC's epoch (Ruling S, decision 0026). It goes through `gaia.launch_gaia` (an asynchronous job, removed
  from the archive afterwards) with `retry.retry`: 3 attempts, 30 s times the attempt number between them. After the
  last it raises `NeighbourError`.
- Each star's TESS magnitude comes from Stassun et al. 2019 (AJ 158, 138), section 2.3.1, eq. 1:
  `T = G - 0.00522555 c^3 + 0.0891337 c^2 - 0.633923 c + 0.0324473`, `c = BP - RP`, on Gaia's observed magnitudes
  (`tmag_from = "colour"`).
- A star with G and no colour takes the brightest T that eq. 1 gives over `[neighbours] bp_rp_range` (0.0 to 3.0),
  found analytically: eq. 1 at both ends of the range and at any turning point inside it. Eq. 1 has no real turning
  point, so T falls as the colour reddens and the red end decides. The paper's own rule for such a star, eq. 2
  (`T = G - 0.430`, a solar colour), is a guess at the colour; a red neighbour read at a solar colour comes out fainter
  than it is and could be ruled out wrongly. The brightest T can add a possible host but never lose one
  (`tmag_from = "g_only"`).
- A star with no G has no TESS magnitude (`tmag_from = "none"`).
- The target is left out by its Gaia DR3 `source_id` (the targets table's `dr3_source_id`, or for a star whose
  targets row lacks it, the one `vetting run` joins through the TIC's Gaia DR2 id, Ruling N), or without one, the one
  star within 1" of its TIC position. When the cone does not identify the target, `required_depths` raises
  `NeighbourError` and the table is inconclusive: a given source id that is not in the cone (an id rounded through a
  float is one way to get there), or, without an id, no star within 1" (the target moved or is missing) or more than
  one (the target can't be told from a close companion). A wrong guess would keep the target in the table as its own
  possible host at the observed depth, or leave out a close companion.
- Each other star gets `required_depth = depth * 10 ** (0.4 * (tmag - t_target))`, with `depth` the observed depth as
  a fraction and `t_target` the target's TIC `tmag`: the target's flux over the neighbour's. It counts the
  neighbour's whole light and no light from any third star, so it is the smallest depth the neighbour could need. A
  star is a possible host when `required_depth <= [neighbours] max_required_depth` (1.0): an eclipse deeper than total
  cannot make the dip.
- `neighbours.neighbour_check` (`"neighbours"`) passes with `possible_hosts` (each one's source id, separation and
  required depth) and the whole table as evidence. It is inconclusive when there is no table (the Gaia query failed or
  the target was not identified; the error is recorded), when a star within the radius has no G (`no_g` lists them),
  since the table can't say whether that star could host the signal, and when a required depth is not finite (a
  missing observed depth or target magnitude), which would otherwise read as no possible host at all.
- It never fails. This is an exception to the spec's rule that every check ships a negative control that makes it fail
  (`docs/design.md` section 5.2), as for `signal_present` (decision 0017). A star that could host the signal does not
  show that it does: the dip is as possible on the target as on each possible host, and a field can hold several (each
  nearby-binary control below has more than its binary). Deciding between them takes the light curve's shape, the
  stars' priors and the aperture, which is TRICERATOPS's job (Task 7), and the review's. The control the table needs is
  that a real blend shows up as a possible host, which the nearby-binary controls test.
- The result is stored beside the checks as `report["neighbours"]`, not among them, so it never counts toward
  advancing. It reaches the call through TRICERATOPS: an inconclusive table, or a possible host TRICERATOPS did not
  weigh, makes TRICERATOPS inconclusive (M3 design, section 4.4; Task 7).
- Licence: the table's values are Gaia DR3 data or computed from it (credit ESA/Gaia/DPAC) and stay under ESA's
  CC BY-NC 3.0 IGO terms (https://www.cosmos.esa.int/web/gaia-users/license), not the results' CC BY 4.0.
  `results/README.md` says so for every published file that carries them (`neighbours.csv` and the `neighbours` record
  in `checks.json`) when the vetting results are published.

## Limitations

- The separations are from the TIC position (epoch 2000) to Gaia DR3 positions (epoch 2016.0) with no proper motion
  applied, so a fast-moving star's separation is off by its motion over those years. Without a source id, a target
  that moved more than 1" between the epochs, or one with a companion within 1", leaves the table inconclusive. Every
  sample target has a `dr3_source_id`. A control's targets table has none, so `vetting run` joins one (Ruling N); only
  where that join fails or finds no DR3 source (`checks.json`'s `star` row says so in `dr3_from` and `dr3_reason`)
  does the table rest on the 1" match.
- Eq. 1 is applied to observed magnitudes; the TIC applies it to de-reddened ones and adds the extinction back. It is
  fitted for -0.2 < BP-RP < 3.5 and is extrapolated outside that range.
- The required depth assumes the neighbour's whole light falls in the aperture. A star away from the aperture puts
  only part of its light in it, so it needs a deeper eclipse than the table says and may be listed when it could not be
  the source. TRICERATOPS's per-star `tdepth`, computed through the aperture, is the cross-check (Task 7).
- Gaia DR3 does not resolve the closest companions, so a companion very close to the target can be missing from the
  table. RUWE (TRICERATOPS's blocker, Task 7) and high-resolution imaging speak to those.
- Stars beyond 1' are not in the table. TRICERATOPS's 10-pixel search reaches them where the TIC lists them.

## Evidence

- [tests/test_neighbours.py](../../tests/test_neighbours.py):
  - `test_tess_mag_at_a_solar_colour_matches_eq_2` (eq. 1 at BP-RP 0.82 gives eq. 2's G - 0.430 within 0.001 mag).
  - `test_required_depth_and_possible` (a neighbour 5 mag fainter than a 233 ppm target needs 2.33%, a possible host;
    10 mag fainter needs 2.33, not one; the check passes and lists only the first).
  - `test_target_is_not_its_own_neighbour` (by source id and by the one star within 1"; `NeighbourError` for a source
    id rounded through a float, for no star within 1", and for an empty cone with or without an id).
  - `test_close_companion_without_an_id_is_inconclusive` (two stars within 1" and no id: inconclusive).
  - `test_g_only_takes_the_brightest_magnitude` (the brightest T over the range matches a 3,001-point grid and eq. 1 at
    the red end; a relation with a turning point inside the range is searched there).
  - `test_star_without_g_is_inconclusive`, `test_missing_target_magnitude_is_inconclusive` and
    `test_gaia_failure_is_inconclusive` (3 attempts, then `NeighbourError`, then inconclusive with the error).
  - `test_gaia_cone_asks_for_the_radius_and_sorts_by_separation` (each star's proper motion and epoch kept, a
    missing one as null), and `test_required_depth_and_possible` (the table keeps them).
- [tests/test_vetting.py](../../tests/test_vetting.py): `test_a_star_without_dr3_values_gets_them_from_the_join` (the
  control's target found by its joined id) and `test_a_star_the_join_gives_nothing_keeps_nulls_and_the_reason` (a
  failed join, or none found: the 1" match, as before).
- The network test `test_nearby_eb_controls_show_a_possible_host`, run by hand: TOI-1058.01 and TOI-1175.01 from
  [benchmarks/pixel_controls.csv](../../benchmarks/pixel_controls.csv), at their ExoFOP TOI depths and TESS
  magnitudes, each list the eclipsing binary they were retired to (TIC 31553886 and TIC 30329564) among their possible
  hosts. On 2026-10-17 it printed 7 possible hosts among 91 stars for TOI-1058.01, its binary at 20.90" needing a
  0.0367 eclipse, and 13 among 83 for TOI-1175.01, its binary at 23.53" needing 0.0489.
