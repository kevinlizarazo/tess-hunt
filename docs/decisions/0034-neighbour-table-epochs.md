# 0034: The neighbour table on one epoch: separations from the target's own Gaia DR3 position

- Date: 2026-10-20
- Status: Accepted (a defect fix; no criteria change)

## Context

The neighbour table ([decision 0025](0025-neighbours.md)) lists the Gaia DR3 stars within 1' of a target, each with
its separation from the target and the eclipse depth it would need to make the dip. Until this record,
`neighbours.gaia_cone` centred its cone on the target's TIC position, at epoch J2000, and measured `sep_arcsec` from
there to each star's DR3 position, at J2016.0, with no proper motion applied. 0025's first Limitation named the mixed
epochs. On a fast-moving target every separation is off by the target's motion over those 16 years, and a star near
the 60" edge falls in or out of the cone wrongly: TIC 44926986's bound companion, TIC 44926982, read 12.50" for a true
9.86".

Task 13's adversarial review of 44926986-1 found it (its finding F3). The M3 design, section 4.8: "A finding that
shows a check is wrong goes to a decision record, never a quiet rerun." This is that record.

Its reach was measured read-only across every table M3 made, in
[`neighbour-epoch-reach-2026-10-20.md`](../../results/benchmarks/neighbour-epoch-reach-2026-10-20.md) ("the
measurement" below):
- 62 tables in three vetting runs: the 19 signals' `20261020T010149Z-vetting-run-62882b5-c3ee`, its evidence-only twin
  `20261020T011247Z-vetting-run-62882b5-d92b` (identical row for row), and the 24 controls'
  `20261017T155223Z-vetting-run-62882b5-4867` ("the control vet"). They cover 41 stars.
- 24 of the 41 targets sit more than 0.5" from their TIC position at J2016.0, each by its DR3 proper motion times 16
  years to within 0.013": 9 of the 19 signals and 15 control stars. TOI-2011.02's target moved 26.36".
- Possible-host membership changes in 8 tables (103312990-1, 296819076-1, 410399327-1, 423100454-1, 44926986-1,
  458290782-1, TOI-652.01 and TOI-755.01), and 458290782-1's `no_g` list grows from 1 star to 2.
- No check outcome or TRICERATOPS blocker changes: every possible host added to a signal a finished TRICERATOPS run
  judged matches one of its stars, and nothing `calc_probs` sees comes from the table (its sections 3 and 5).
  410399327-1, 423100454-1 and 458290782-1, which no finished run judged, gain hosts no star list has been checked
  against.

## Decision

1. **The fix.** When the target's Gaia DR3 source id is known (its targets row's `dr3_source_id`, or the one
   `vetting run` joins, 0025's Ruling N), `neighbours.gaia_cone` asks the archive for the target's own DR3 row, then
   centres the cone on its `ra` and `dec`. Every position and separation in the table is then DR3's own, at J2016.0,
   and needs no proper motion, which two-parameter solutions lack. Every M3 target has an id.
   - Two queries, not the measurement's tested self-join (one ADQL query joining `gaia_source` to itself on the source
     id): the archive answered the self-join for the measurement earlier on 2026-10-20, then aborted it at its time-out
     in 10 tries of 10 between 15:18 and 15:34 UTC while the id lookup and the cone each took about 10 s, as its note
     of 2025-12-17 says cone searches combined with joins can (https://www.cosmos.esa.int/web/gaia/news).
   - With an id, nothing is guessed. If either query fails after its 3 attempts, or the archive has no row for the id,
     `gaia_cone` raises `NeighbourError` and the table is inconclusive with the reason, as a failed cone was before.
   - Without an id, the cone stays on the TIC position and the target is the one star within 1" of it (0025). A target
     that moved more than 1" by J2016.0 usually leaves no star there and the table inconclusive, but a field star that
     happens to sit within 1" of the stale position would be taken for it, as before this record.
   - The check's evidence names what the separations run from: `centre` is `"Gaia DR3 <id>, J2016.0"` or
     `"TIC position, J2000"`. The dossier's possible-host table says it.
   - Ruling S ([decision 0026](0026-triceratops.md)) is unchanged: it moves each possible host to J2000 with its own
     proper motion and never read `sep_arcsec`.
2. **The signals' runs are redone on the fix.** The controller reruns them and records the new run ids in a later
   commit: `vetting run --production` on the 19 signals; the evidence-only `vetting run`; `vetting second-list`;
   `vetting triceratops`; `vetting literature`, resumed from `20261020T091938Z-vetting-literature-2315775-066c`; and the
   19 dossiers. Compared run against run, every check outcome must reproduce, the neighbour table's and those of the
   finished TRICERATOPS run `20261020T013408Z-vetting-triceratops-62882b5-e092` included. Only the table's possible
   hosts and separations may differ, and with them its cone and the counts in its reason.
   - Done on 2026-10-20 and 21 (UTC), at commit 61b5944: the vet `20261020T174317Z-vetting-run-61b5944-2d70`; the
     evidence-only vet `20261020T175536Z-vetting-run-61b5944-7f4e`; the second list
     `20261020T180844Z-vetting-second-list-61b5944-7096`; literature `20261020T181539Z-vetting-literature-61b5944-69b7`,
     which left 458290782-1 inconclusive on an OpenAlex HTTP 429, then
     `20261021T001540Z-vetting-literature-61b5944-07de`, resumed from it, complete for all 19; and TRICERATOPS on the
     six, `20261020T181658Z-vetting-triceratops-61b5944-1bbf`. The five promoted rows' TRICERATOPS run,
     `20261021T025929Z-vetting-triceratops-61b5944-55f4`, was stopped unfinished for
     [decision 0036](0036-triceratops-tic-duplicates.md), which reran them and four of the six (its item 2).
   - Every check outcome reproduced in both vets but 441010857-1's holdout, which
     [decision 0035](0035-holdout-training-seasons.md) changed from fail to inconclusive. Outside the neighbour record
     and the holdout, every check matched to the bit. In the other 18 signals every holdout field the old runs had
     matched, and each season gained 0035's `training_seasons_with_transits`. The second list matched cell for cell.
     TRICERATOPS matched e092's every outcome and reason, and its means to within 3e-3 relative (0036, item 5).
3. **The controls are not rerun.** The control vet, its TRICERATOPS runs
   (`20261017T162256Z-vetting-triceratops-62882b5-d0f8` and `20261018T012940Z-vetting-triceratops-62882b5-e3d7`) and
   the published controls run `20261020T082333Z-benchmark-controls-16418d2-f45a` (cited by 0026, 0031 and 0032) stand,
   with this record as their note. The measurement shows no change on the 24 control tables to a neighbour outcome, a
   blocker or a count the controls summary publishes, and TRICERATOPS takes from the table only the outcome and the
   possible hosts, which match its star list before and after (its sections 3 and 5).
   - What does change in the published controls:
     [`controls.csv`](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/controls.csv)'s
     `possible_hosts` for TOI-652.01 (3 to 2) and TOI-755.01 (9 to 10), and, in the control vet's tables,
     TOI-2011.02's separations, off by up to 26.36".
   - This is Ruling AX, the M3 build controller's, put to the maintainer, who can ask for the rerun: about 11 h, 10.4 h
     of it TRICERATOPS (the measurement, section 5).
   - Rerun on 2026-10-22 and 23 (UTC) at the maintainer's call, at cd4e7a2:
     `20261023T031548Z-benchmark-controls-cd4e7a2-ca9f`
     ([summary.md](../../results/benchmarks/20261023T031548Z-benchmark-controls-cd4e7a2-ca9f/summary.md)). Every outcome
     and both pass-rate tables match. In `controls.csv` only `possible_hosts` (as above), TRICERATOPS's means, sds and
     run ids, and `superseded` (TOI-118.01's lone rerun in place of TOI-4307.01's) moved
     ([0036](0036-triceratops-tic-duplicates.md), item 4).
4. **TRICERATOPS on the promoted five.** Its first run on 241522065-1, 277774870-1, 370977908-1, 438857197-1 and
   423100454-1, `20261020T140004Z-vetting-triceratops-d039859-f7bc`, was stopped unfinished because it read the
   defective table. Nothing from it is used.
5. **Quoted separations.** Corrected in place, each marked "(corrected in 0034)":
   - 0026, Ruling S: 44926986's possible host TIC 44926982 at 9.86", which the table read as 12.5".
   - 0033, item 3: 423100454-1's nearest possible host at 8.42", which the table read as 6.5"; Gaia DR3
     5836453499849301760 moves inside 15", from 16.61" to 14.98".
   - 0025's first Decision bullet and first Limitation say what the table now measures from.
   - Left as they are: 0025, 0026 and 0032's 20.90" and 23.53" for the binaries near TOI-1058.01 and TOI-1175.01. They
     came from the network test, whose cone was centred on `benchmarks/pixel_controls.csv`'s positions, 0.277" and
     0.705" from the TIC's and near the DR3 ones, and they hold within 0.05": centred on each target's DR3 row, the test
     printed 20.95" and 23.54" on 2026-10-20. Production's own table, the control vet's, read 22.85" for TOI-1175.01's
     binary.
   - The dossier drafts quote the table's separations (280 of their 723 host rows move by more than 0.5", in 8 drafts)
     and are rendered again from the rerun.

## The pixel check's reference position

The measurement left one question open: the pixel check (triage-v1: LEO-Vetter through transit-diffImage) is handed
the TIC's J2000 position too (`pixels.py:88, 105`), and the four known planets it fails have fast hosts. The follow-up,
[`pixel-check-reference-position-2026-10-20.md`](../../results/benchmarks/pixel-check-reference-position-2026-10-20.md),
answers it from the check's own saved images:
- The check measures each centroid offset from the target's TIC position carried by its proper motion to the mean time
  of that sector's pixels (`tessDiffImage.py:480-504`). That position sits within 0.02" of Gaia DR3's carried to the
  same time in every sector measured: 54 for the four known-planet fails, TOI-396.01 and the second list's six fails,
  45 for the 9 vetted signals off the second list, and 20 for the second list's four passes. The defect doesn't reach
  the pixel check, and 0033's account of the four known-planet fails (item 1) stands.
- The J2000 position only centres the TESScut cutout, which also sets where the fit starts, and picks the camera and
  CCD. With the fit started on the target instead (a 7 x 7 box on its pixel, or its catalogue position), all four
  known-planet verdicts still fail: TOI-2011.02 at 32.8" in place of 69.0", the other three unchanged.
- A side finding, on where the fit starts rather than on epochs: started at the target's catalogue position,
  423100454-1's S102 and S65 fits fall from 118.6" and 115.7" to 7.3" and 7.0", with qualities of 0.12 and 0.17, so
  the best-quality sector becomes S39 (5.8") and the row would pass the rule. 0033's exception for that row rests on
  its fail being the variable neighbour capturing the fit, and this supports it. The same start moves TOI-396.01's S105
  (59.0" to 10.6") and 337885456-1's S66 (42.3" to 18.0"). `pixels.py` is frozen and no pixel record changes.
- The published pixel diagnosis
  ([`pixel-check-diagnosis-2026-10-20.md`](../../results/benchmarks/pixel-check-diagnosis-2026-10-20.md)) gives the
  "From target" distances in its section 2 table from `neighbours.csv`, so they carry the defect: 173369850-1 0.4",
  295140687-1 0.2", 322826591-1 1.7", 337885456-1 0.8", 423100454-1 2.2" and 458290782-1 0.4". A note under that table
  points here; no number in it changes. Whether a star could host the signal doesn't depend on its separation.

## Limitations

- Without a source id the separations still mix epochs, by under 1" where the target is found. No M3 target lacks an
  id; 16 of the 41 measured targets sit more than 1" from their TIC position, so without one their tables would be
  inconclusive.
- The cone's centre goes into the query to 10 decimal places of a degree (3.6e-7"), so the target's own separation
  reads about 1e-7" rather than 0. It is left out of the table by its id.
- The published controls keep their mixed-epoch tables (item 3).
- The measurement did not check whether a TRICERATOPS rerun gets the same field-star population (its section 5); the
  runs are seeded.

## Evidence

- [tests/test_neighbours.py](../../tests/test_neighbours.py):
  - `test_the_cone_centres_on_the_targets_own_dr3_row`: 44926986's TIC position and four of its DR3 rows, through a
    stand-in archive that measures from the centre each query names. The companion reads 9.859", the edge star
    (61.50" from the target) is out, and at 44926986-1's depth and TESS magnitude the companion is the one possible
    host.
  - `test_without_an_id_the_cone_stays_on_the_tic_position`: the same stand-in gives the archive's own 2.752", 12.504"
    and 59.039" from the TIC position, and with no star within 1" the table raises `NeighbourError`.
  - `test_a_cone_is_never_centred_on_a_guess`: the id lookup failing, the cone failing, and no DR3 row for the id each
    raise `NeighbourError` and read inconclusive, with no cone asked on the TIC position.
- [tests/test_vetting.py](../../tests/test_vetting.py): `test_vetting_run_writes_one_directory_per_signal` (`centre`
  for an id and for none), `test_a_star_without_dr3_values_gets_them_from_the_join` (the cone centred on the joined
  id) and `test_a_star_the_join_gives_nothing_keeps_nulls_and_the_reason` (no id: the TIC position).
- [tests/test_dossier.py](../../tests/test_dossier.py): `test_page_one_answers_the_three_questions` (the possible-host
  table names its centre).
- The network test `test_nearby_eb_controls_show_a_possible_host` in `tests/test_neighbours.py`, now centred on each
  target's DR3 row, run by hand on 2026-10-20 and again on 2026-10-23
  ([output](../../results/benchmarks/neighbour-controls-2026-10-23.txt)): 7 possible hosts among 91 stars for
  TOI-1058.01, its binary at 20.95" needing 0.0367, and 13 among 82 for TOI-1175.01, its binary at 23.54" needing
  0.0489.
- [The measurement](../../results/benchmarks/neighbour-epoch-reach-2026-10-20.md) and
  [the pixel follow-up](../../results/benchmarks/pixel-check-reference-position-2026-10-20.md), read-only analyses
  outside the pipeline that gate nothing; their line references are to commit 295bef4. Their scripts and small
  outputs, byte for byte:
  [`neighbour-epoch-reach-2026-10-20-scripts.tar.gz`](../../results/benchmarks/neighbour-epoch-reach-2026-10-20-scripts.tar.gz)
  (sha256 `32711e99f66e4056ed481643e4f2801a4766754de8b7ea28b993787b4046f00c`): `t13-epoch/` (the measurement, without
  its 41 cached Gaia cones, which `cones.py` fetches again), `pixel-diag/` (the follow-up) and `t13/heavy.sh` (the
  follow-up's memory cap).
