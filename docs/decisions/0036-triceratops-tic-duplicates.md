# 0036: TRICERATOPS weighs no TIC duplicate or artifact

- Date: 2026-10-21
- Status: Accepted (a defect fix; no criteria change)

## Context

TRICERATOPS ([decision 0026](0026-triceratops.md)) weighs the transit "on the target, on an unresolved companion, on a
background star, and on each TIC star within 10 pixels". It builds that star list from a TIC cone and selects each
row's `disposition` and `duplicate_id` (`triceratops.py:135`, version 1.1.0), but nothing in the package reads them.
Two of the TIC's dispositions mark rows that are not stars of their own (Paegert et al. 2021, arXiv:2108.04778,
section 3.1):
- DUPLICATE: a second entry for a star already in the TIC, which `duplicate_id` names. The paper flags it "to prevent
  it from being taken into account".
- ARTIFACT: a spurious 2MASS source, usually on a bright star's diffraction spikes. "Stars with this disposition should
  be ignored."

Task 13's adversarial review of 399023421-1 found it (its finding F3): TIC 993417194, a DUPLICATE of TIC 399023424,
6.46" from the target, is weighed as a second star. The M3 design, section 4.8: "A finding that shows a check is wrong
goes to a decision record, never a quiet rerun." This is that record.

Its reach was measured read-only across every M3 TRICERATOPS run, in
[`triceratops-tic-duplicates-2026-10-21.md`](../../results/benchmarks/triceratops-tic-duplicates-2026-10-21.md) ("the
measurement" below):
- A DUPLICATE row sits at the position and TESS magnitude of the star it copies, so `calc_depths` gives it the same
  `tdepth`, and `calc_probs` runs its own NTP, NEB and NEBx2P scenarios with its own mass, radius and Teff. Those are
  estimated from photometry, so they differ a little from the original's: the star is weighed twice, as two slightly
  different models of about equal weight. An ARTIFACT row gets host scenarios for a star that does not exist. Both
  enter NFPP and FPP (its section 1a).
- The flux these rows add to the apertures cancels, because the wrapper runs with `dilution_corrected=True`: exactly
  within one aperture, and to 6.3e-4 relative at most in another star's `tdepth` across several (section 1b).
- Across the 16,820 TIC IDs in the star lists the TIC gives only SPLIT (170), DUPLICATE (81) and ARTIFACT (12). No
  target has a disposition.
- Four judged cases weigh such a row: 399023421-1 (one DUPLICATE), 296819076-1 (three) and the controls TOI-763.02
  (two ARTIFACTs) and TOI-1058.01 (one). Without them, 399023421-1's mean NFPP goes from 0.0191 to about 0.0163 and
  296819076-1's from 0.0554 to about 0.0545. TOI-763.02's two ARTIFACTs carry 99.998% of its NFPP, so 1.6e-4 goes to
  about 0. TOI-1058.01's is unchanged (section 3).
- No outcome changes. A single-seed rerun of TOI-763.02 without its ARTIFACTs matched the renormalised estimate
  (section 3).

## Decision

1. **The fix.** In `tricera.run`, once TRICERATOPS has built its target and before the star list is recorded, the
   target checked, the apertures read and `calc_depths` run, `tricera._drop_flagged` drops every row after the target
   whose `disposition` is DUPLICATE or ARTIFACT (`tricera.DROPPED_DISPOSITIONS`) from `target.stars` and from every
   `target.pix_coords` array with one mask.
   - Not with TRICERATOPS's own `remove_star` (`triceratops.py:404-419`): it drops rows from `.stars` and leaves
     `.pix_coords` alone, while `calc_depths` reads each star's pixel position by row (777-778), so every star after a
     removed row would take its neighbour's position.
   - SPLIT rows stay: a SPLIT row is the entry the TIC keeps, with the brighter Gaia star's position, magnitudes and
     parameters. So do rows with only a `duplicate_id`, the fainter Gaia components of a split, which are real stars
     with their own Gaia DR2 ids. A filter on `duplicate_id` would drop 993417201, one of 399023421-1's three close
     possible hosts (the measurement, section 1).
   - A target the TIC itself flags is not dropped. The check is inconclusive, its reason naming the disposition ("the
     TIC flags the target DUPLICATE, a row it says not to use"), and TRICERATOPS stops before `calc_depths`. No M3
     target is flagged.
   - The record lists the rows dropped (`dropped_stars`: each row's ID, `disposition` and `duplicate_id`), a new field
     of `tricera.RUN_FIELDS`: None before TRICERATOPS has built its star list, a list after. `stars` gains each kept
     row's `disposition`.
   - Nothing that reads the evidence changes shape. `hosts`, `missing_hosts` and `hosts_tdepth_zero` match the
     possible hosts to the stars left. In 296819076-1, `hosts` matched three Gaia DR3 hosts to DUPLICATE rows, which
     sit at their originals' positions but come first in the list; the drop makes it match them to the entries the TIC
     keeps (the measurement, section 5).
   - No criteria change: nothing under `criteria/` changes, and the two dispositions are fixed in the code.
2. **What is redone** (the M3 build controller's Ruling BH). TRICERATOPS is rerun for every signal whose star list
   holds a DUPLICATE or ARTIFACT row: 399023421-1, 296819076-1, 103312990-1 and 44926986-1. It is also rerun for the
   five promoted second-list rows (241522065-1, 277774870-1, 370977908-1, 423100454-1 and 438857197-1): their run,
   `20261021T025929Z-vetting-triceratops-61b5944-55f4`, was stopped unfinished for this fix after judging only
   277774870-1. 146282666-1 and 164767175-1 keep `20261020T181658Z-vetting-triceratops-61b5944-1bbf`: their star lists
   hold no such row, so the fix computes exactly what that run computed. A `triceratops.json` from a run made before
   this record (that run, and the controls' `20261017T162256Z-vetting-triceratops-62882b5-d0f8` and
   `20261018T012940Z-vetting-triceratops-62882b5-e3d7`) has no `dropped_stars` and no `disposition` in its `stars`.
   The dossiers and the affected reviews follow. The controller records the new run ids in a later commit.
   - Done on 2026-10-21 and 22 (UTC), at commit cd4e7a2: the five promoted rows as
     `20261021T044850Z-vetting-triceratops-cd4e7a2-07c3`, and the four as
     `20261021T194348Z-vetting-triceratops-cd4e7a2-7821`.
3. **What must reproduce:** every outcome. NFPP and FPP move as the measurement's section 3 predicts: 399023421-1's
   mean NFPP to about 0.0163 and 296819076-1's to about 0.0545, within Monte Carlo noise. 103312990-1's and
   44926986-1's flagged rows are not weighed (section 2), so the fix reaches them only through the flux those rows
   add to the apertures. For 44926986-1 that moves other stars' `tdepth` by 2.9e-6 relative at most (section 1b);
   103312990-1's rows are 118" and 139" out, and their effect was not measured. Both are expected below the run-to-run
   noise in item 5, so these two signals' numbers should move no more than a rerun without the fix moves them.
   - Result, against 1bbf: all four outcomes reproduced, and every reason but for its digits. 399023421-1's mean NFPP
     went from 0.0191 to 0.0161 (estimated above at about 0.0163) and 296819076-1's from 0.0554 to 0.0545.
     103312990-1's and 44926986-1's means moved by 1.4e-4 relative at most (44926986-1's FPP). That is inside the
     6.6e-4 item 5 saw from a reordered field-star file alone, but above 44926986-1's largest move between the two
     runs before the fix (3.5e-5, its NFPP), so one pair of runs can't separate the fix's effect there from the noise.
     296819076-1's three hosts now name the entries the TIC keeps. 277774870-1, whose star list holds no flagged row,
     matched the stopped 55f4's means to 2.3e-4 relative, with the same outcome.
4. **The controls are not rerun** (Ruling BH, put to the maintainer, who can ask for it). The controls' TRICERATOPS
   runs (`20261017T162256Z-vetting-triceratops-62882b5-d0f8` and `20261018T012940Z-vetting-triceratops-62882b5-e3d7`)
   and the published controls run `20261020T082333Z-benchmark-controls-16418d2-f45a` stand, with this record as their
   note. No outcome, blocker or count in the controls summary changes, and 0032's TOI-1058.01 NFPP of 0.027 is
   unchanged. What does change: in
   [`controls.csv`](../../results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/controls.csv),
   TOI-763.02's NFPP of 1.6e-4 would read about 0, and it passes either way.
   - Rerun on 2026-10-22 and 23 (UTC) at the maintainer's call, at cd4e7a2, as
     `20261023T031548Z-benchmark-controls-cd4e7a2-ca9f`
     ([summary.md](../../results/benchmarks/20261023T031548Z-benchmark-controls-cd4e7a2-ca9f/summary.md)), with
     TOI-118.01 rerun alone after a lost TESScut cutout, as TOI-4307.01 was. Every outcome matches. TOI-763.02's mean
     NFPP reads 3.96e-9. TOI-1058.01's two flagged rows (TIC 31553884, ARTIFACT, and 1827100470, DUPLICATE) were dropped
     and its means moved, FPP 0.0334 to 0.0288 and NFPP 0.0270 to 0.0219, where the renormalised estimate said
     unchanged: the estimate keeps the old draws, and the rerun drew again without the two rows and from its field stars
     in another order (item 5). Its outcome holds, as does 0032's reasoning on it.
5. **A rerun repeats outcomes, not every digit.** TRICERATOPS's own Gaia DR3 query for the field-star population
   returns its rows in no fixed order, so a seeded run on the same inputs need not give the same numbers. 0034's rerun
   of the six signals (`20261020T013408Z-vetting-triceratops-62882b5-e092`, then
   `20261020T181658Z-vetting-triceratops-61b5944-1bbf`) read the same star lists, folds and apertures, and every
   outcome reproduced. The means, in each run's `provenance.json` summary, did not to the digit:
   - 164767175-1's mean FPP went from 0.0220437 to 0.0220438 (1.5e-6 relative), and 146282666-1's from 0.0292511 to
     0.0292514 (1.3e-5).
   - Of the five whose field-star file held the same rows in another order, the largest move was 399023421-1's mean
     FPP, from 0.0616558 to 0.0616965 (6.6e-4).
   - For 296819076-1 the query also returned 13 fewer rows (its field-star files hold 40,074 and then 40,061), and its
     mean FPP went from 0.0705087 to 0.0707155 (2.9e-3).
   - In the controls rerun, every control's field-star file held the same rows in another order. Of the controls with no
     flagged row, TOI-191.01 moved furthest: mean FPP 0.297 to 0.397. Its single runs land at about 0 or about 1 and one
     of the ten flipped, so on such a target the mean moves in steps of about 0.1, and one near the 0.5 bar could cross
     it. It passes in both runs. Of those whose runs spread between, TOI-451.03 moved furthest: mean FPP 0.0523 to
     0.0530 (1.4e-2 relative).
   The comparison after this rerun will show differences of the same kind beside the fix's own.

## Limitations

Adjacent to the defect and not measured (the measurement, section 5):
- Where a SPLIT neighbour's mass, radius or Teff is missing, TRICERATOPS estimates it from 2MASS photometry blended
  over the split, which the TIC paper calls "most likely not reliable"; it reads a neighbour's J, H and K only for that
  estimate. 399023424's estimated radius is 0.921 where its 2MASS-less duplicate's was 0.784.
- 993417201, one of 399023421-1's three close possible hosts, is weighed as a solar star (mass and radius 1.0 in
  `probs.csv`): the TIC has no parameters for it, and the photometric estimate gave none.
- A galaxy is weighed as a host star in TOI-763.02: TIC 10000891672 (objType EXTENDED, T 11.63), with `tdepth` 0.027
  and a share of about 1e-19. The star lists hold 14 EXTENDED rows, and only that one is weighed. The TIC gives it no
  disposition, and this record leaves it in.
- The input depth may carry SPOC's own over-correction. The wrapper takes the PDCSAP depth as on-target; if SPOC's
  crowding correction counted DUPLICATE or ARTIFACT flux in some sector, that depth is over-corrected by no more than
  the flagged rows' share of the aperture (up to 1.7% in these runs).

## Evidence

- [tests/test_tricera.py](../../tests/test_tricera.py):
  - `test_triceratops_weighs_no_tic_duplicate_or_artifact`: after the target, a DUPLICATE row, an ARTIFACT row, a
    SPLIT row and a row with only a `duplicate_id`. `calc_depths` sees the target, the SPLIT row and the
    `duplicate_id` row, each at its own pixel in every sector; the record lists the two rows dropped; and a possible
    host at the SPLIT star's position matches it, not its duplicate listed first.
  - `test_a_target_the_tic_flags_is_inconclusive`: a target flagged DUPLICATE or ARTIFACT stays first in the star
    list, the reason names the disposition, and neither `calc_depths` nor `calc_probs` runs.
  - `test_a_star_list_without_dispositions_runs_as_before`: a star list with no `disposition` column drops nothing.
  - `test_every_path_records_the_same_fields` and `test_a_run_that_raised_keeps_what_it_reached` (`dropped_stars` is
    None before the star list is built and empty when nothing was flagged).
- [The measurement](../../results/benchmarks/triceratops-tic-duplicates-2026-10-21.md), a read-only analysis outside
  the pipeline that gates nothing; its line references are to TRICERATOPS 1.1.0 and to the wrapper at commit 61b5944.
  Its scripts and their outputs, byte for byte:
  [`triceratops-tic-duplicates-2026-10-21-scripts.tar.gz`](../../results/benchmarks/triceratops-tic-duplicates-2026-10-21-scripts.tar.gz)
  (sha256 `2e26c3d72b5cadc86a48690fa2f04f123508930079196db616abeed6fa08153c`): `t13-dup/`, without its TESScut
  cutouts, the field-star file `rerun.py` copies from the run, and the TIC paper, which is cited, not republished; and
  `t13/heavy.sh`, the memory cap the single-seed rerun ran under.
