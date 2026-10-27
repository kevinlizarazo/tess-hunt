# TIC duplicates and artifacts in TRICERATOPS: how far finding F3 reaches

Assembled by the controller from t13-dup's messages (2026-10-21, about 04:00 UTC); the agent could not write report
files. Read-only measurement; scratch in `/tmp/t13-dup/`, published as `t13-dup/` in
`triceratops-tic-duplicates-2026-10-21-scripts.tar.gz` beside this file. TRICERATOPS line numbers refer to
`~/code/tess-hunt-run/.venv/lib/python3.12/site-packages/triceratops/triceratops.py` (1.1.0); wrapper line numbers to
`~/code/tess-hunt-run/src/tess_hunt/tricera.py` (61b5944).

**Short answer.**
- A DUPLICATE row inside the aperture gets its own nearby-star scenarios, so the star it copies is weighed twice.
  ARTIFACT rows do the same for a star that does not exist.
- The extra flux these rows add to the aperture cancels, because the wrapper runs with `dilution_corrected=True`: it
  cancels exactly in one sector and is measured at 6.3e-4 or less (relative) across several sectors.
- Dropping these rows from both `.stars` and `.pix_coords` before `calc_depths` is the whole correction.
- Four judged cases weigh such a row: 399023421-1, 296819076-1, TOI-763.02 and TOI-1058.01. No outcome changes.
- The largest shifts: 399023421-1's mean NFPP 0.0191 goes to about 0.0163; TOI-763.02's two ARTIFACT rows carry
  99.998% of its NFPP, and it stays a pass.
- The promoted second-list run had not finished. Only 1 of its 5 signals was judged (clean). The cone queries suggest
  241522065-1 and 423100454-1 will probably be affected.

## 1. Mechanism

**(a) A separate host scenario: yes.**
- TRICERATOPS builds its star list from the TIC cone and selects `disposition` and `duplicate_id` (lines 124-137, the
  columns at 135). `grep -n "disposition\|duplicate"` over the package finds only line 135, so nothing reads them.
- `calc_depths` gives every row a flux ratio and a tdepth from its pixel position and Tmag (775-818). A DUPLICATE sits
  at the same position with the same Tmag as the star it copies, so it gets the same tdepth. Example: 993417194 and
  399023424 both have tdepth 0.0405.
- `calc_probs` keeps every row with tdepth > 0 (line 924). For each it builds that star's light curve (963-970) and
  runs NTP, NEB and NEBx2P with that row's own mass, radius and Teff (1560-1646).
- NFPP is the sum of rows 15 onward (1699). FPP is 1 - (TP + PTP + DTP) (1697), so the duplicate's share enters both.
- The copy is not exact. A DUPLICATE has no 2MASS photometry, so `estimate_stellar_params` (295-346) gives it a
  different radius. From `pairs.txt`: 993417194 R_s 0.784, prob 0.00275, against its original 399023424 R_s 0.921,
  prob 0.00336; 1132493585 R_s 0.533, prob 0.000994, against its original 296819067 R_s 0.560, prob 0.00127. In
  effect the star gets a second, slightly different model with roughly equal weight.

**(b) Extra flux: real in the `fluxratio` column, but it cancels in everything `calc_probs` uses.**
- Each row's flux is added to the aperture sum (788-799), so every star's `fluxratio` falls.
- The wrapper passes `dilution_corrected=True` to both calls (wrapper lines 469 and 497). Then star i's tdepth =
  depth x fr_target / fr_i (809, 816), and star i's light curve = 1 + (fr_target / fr_i)(flux_0 - 1) (969-970).
- Only ratios enter. Within one aperture the sum cancels exactly, and the target's tdepth is the input depth exactly.
- Across several apertures `fluxratio` is a mean of per-aperture shares (803), so the extra flux only reweights
  sectors: a second-order effect.

Measured with `depths.py`, which rebuilds the target and runs `calc_depths` on the run's own recorded apertures, with
and without the DUPLICATE and ARTIFACT rows. It reproduced the runs' tdepths exactly in all 7 cases.

| case | sectors | dropped rows' flux share per aperture | target fluxratio (with -> without) | target tdepth | largest relative tdepth change, other stars | weighed set |
|---|---|---|---|---|---|---|
| 399023421-1 | 64 | 0.0067 | 0.9132 -> 0.9194 | unchanged | 2.2e-16 | unchanged |
| 296819076-1 | 11, 12 | 0.0036, 0.0021 | 0.7705 -> 0.7727 | unchanged | 6.3e-4 | unchanged |
| 44926986-1 | 36, 62, 63 | 1.2e-5 at most | 0.7308 -> 0.7308 | unchanged | 2.9e-6 | unchanged |
| TOI-763.02 | 10, 37, 64, 101 | 0.016 to 0.017 | 0.9463 -> 0.9619 | unchanged | 1.5e-4 | unchanged |
| TOI-1058.01 | 13, 27, 67, 92, 94 | 0.00098 at most | 0.9519 -> 0.9528 | unchanged | 1.5e-5 | unchanged |
| TOI-107.01 (artifact at 4.9", not weighed) | 5 sectors | 0.0018 at most | 0.6200 -> 0.6210 | unchanged | 3.1e-5 | unchanged |
| TOI-576.01 (artifact at 5.6", not weighed) | 5 sectors | 0.0030 | 0.9921 -> 0.9950 | unchanged | 0 | unchanged |

**Is dropping the rows the whole correction?** Yes, if they are dropped from `.stars` and from every `.pix_coords`
array with one mask, before `calc_depths` and `calc_probs`. Do not use TRICERATOPS's `remove_star` (404-419): it drops
rows from `.stars` but not from `.pix_coords`, while `calc_depths` reads `pix_coords[k][i]` by position (777-778), so
every star after a removed row would take its neighbour's pixel position. `remove_nearby_stars` (443-446) shows the
right pattern. The wrapper calls neither.

**Other dispositions.** Across the 16,820 TIC IDs in these star lists MAST returns only SPLIT (170), DUPLICATE (81)
and ARTIFACT (12). There is no PHANTOM value; "phantom" is the TIC paper's umbrella word (Paegert et al. 2021,
arXiv:2108.04778, sections 2 and 3.1).
- **DUPLICATE: drop.** A second TIC entry for a star already in the TIC. The paper: "We flag TIC ID 2 as DUPLICATE, to
  prevent it from being taken into account"; `duplicate_id` names the kept entry. All 81 share their Gaia DR2 id with
  the entry they name.
- **ARTIFACT: drop.** Spurious 2MASS sources, usually on a bright star's diffraction spikes. The paper: "Stars with
  this disposition should be ignored." Gaia has no source for an artifact, so the neighbour table and `missing_hosts`
  can't see them.
- **SPLIT: keep.** The kept entry, with the brighter Gaia star's position, magnitudes and parameters: a real star, not
  double-counted. Its 2MASS J, H and K are a blend the paper calls "most likely not reliable". TRICERATOPS reads J, H
  and K for neighbours only when estimating missing mass, radius and Teff (320-321), and for the target in DTP, DEB,
  BTP and BEB (976-978, 1351, 1399, 1463, 1512). No M3 target has any disposition.
- **No disposition but a `duplicate_id`: keep.** The fainter Gaia components of a split: real stars with their own
  Gaia DR2 ids (checked for the three weighed: 993417201, 516066139, 1132493790). A filter on `duplicate_id` would
  wrongly drop 993417201, one of F1's three close possible hosts of 399023421-1.

## 2. Reach

Over all star lists: 25,405 rows. Of the rows calc_probs weighs (tdepth > 0): SPLIT 20, DUPLICATE 8, ARTIFACT 3. No
target row has a disposition.

**Weighed DUPLICATE or ARTIFACT rows:**

| run | signal or control | flagged star | disposition | duplicates | separation | Tmag | tdepth |
|---|---|---|---|---|---|---|---|
| 1bbf and e092 | 399023421-1 | 993417194 | DUPLICATE | 399023424 (SPLIT, also weighed) | 6.46" | 15.68 | 0.0405 |
| 1bbf and e092 | 296819076-1 | 1132493514 | DUPLICATE | 296819110 (SPLIT) | 29.28" | 17.30 | 0.344 |
| 1bbf and e092 | 296819076-1 | 1132493618 | DUPLICATE | 296818956 (SPLIT) | 41.45" | 17.47 | 0.964 |
| 1bbf and e092 | 296819076-1 | 1132493585 | DUPLICATE | 296819067 (SPLIT) | 46.96" | 15.67 | 0.204 |
| d0f8 | TOI-763.02 | 178819687 | ARTIFACT | (none) | 5.21" | 15.13 | 0.151 |
| d0f8 | TOI-763.02 | 178819685 | ARTIFACT | (none) | 7.99" | 14.37 | 0.0765 |
| d0f8 | TOI-1058.01 | 31553884 | ARTIFACT | (none) | 15.58" | 16.77 | 0.985 |

(1bbf = 20261020T181658Z-vetting-triceratops-61b5944-1bbf, e092 = 20261020T013408Z-vetting-triceratops-62882b5-e092,
d0f8 = 20261017T162256Z-vetting-triceratops-62882b5-d0f8, e3d7 = 20261018T012940Z-vetting-triceratops-62882b5-e3d7.)

**Flagged but not weighed (tdepth 0)**, affecting only the aperture flux sum (section 1b):
- Signals, the same in 1bbf and e092: 103312990-1 1 ARTIFACT (118"), 1 DUPLICATE (139"); 296819076-1 55 more
  DUPLICATE and 1 ARTIFACT (144"); 44926986-1 3 DUPLICATE (112" and farther); 146282666-1 and 164767175-1 none.
- Controls in d0f8: TOI-1058.01 1 DUPLICATE (116"); TOI-107.01 1 ARTIFACT (4.9"); TOI-1097.02 1 ARTIFACT (127"),
  1 DUPLICATE (143"); TOI-1175.01 3 DUPLICATE (88" and farther); TOI-2011.02 1 ARTIFACT (187"), 10 DUPLICATE (79" and
  farther); TOI-396.01 and TOI-396.03 1 ARTIFACT each (99"); TOI-576.01 1 ARTIFACT (5.6"); TOI-652.01 1 ARTIFACT
  (14"), 2 DUPLICATE (161"); TOI-747.01 1 DUPLICATE (160"); TOI-826.01 1 ARTIFACT (153").
- No DUPLICATE or ARTIFACT rows at all: TOI-1052.01, TOI-118.01, TOI-1399.01, TOI-144.01, TOI-188.01, TOI-191.01,
  TOI-411.01, TOI-4307.01 (d0f8 and e3d7), TOI-4320.01, TOI-451.02, TOI-451.03 and TOI-755.01.

**Promoted rows:** run `20261021T025929Z-vetting-triceratops-61b5944-55f4` was still running; only 277774870-1 was
judged (81 stars, none flagged). For the other four the agent queried the same TIC cone TRICERATOPS queries
(`cone.py`); whether a row is weighed needs the run's apertures, so these are provisional:
- 241522065-1: ARTIFACT 241522064 at 7.43", 1.25% of the target's flux; at depth 0.000505 its tdepth would be about
  0.04, so probably weighed. Also 7 DUPLICATE rows from 70".
- 423100454-1: 61 DUPLICATE rows from 29.7" (each 0.03% to 1.5% of the target's flux) and 1 ARTIFACT at 62.8"; the
  nearest few may be weighed.
- 370977908-1: 10 DUPLICATE rows from 101". 438857197-1: 1 DUPLICATE at 128". Probably neither weighed.
The abandoned run `20261020T140004Z-vetting-triceratops-d039859-f7bc` finished only 277774870-1, which is clean.

## 3. Effect, judged against the bars

Bars: nfpp_pass 0.001, nfpp_fail 0.1, fpp_pass 0.5. `probs.csv` holds only the last run (seed 9). The flagged rows'
probability d is removed and renormalised: X' = (X - d)/(1 - d). Scaled to the 10-run means two ways: "share" (each
seed's d is seed 9's share of that seed's NFPP) and "fixed" (each seed uses seed 9's d). The table shows "share";
"fixed" differs by 1e-4 or less except where noted.

| run | case | flagged rows' share of seed 9 | NFPP seed 9 (with -> without) | FPP seed 9 (with -> without) | mean NFPP (with -> without) | mean FPP (with -> without) | outcome |
|---|---|---|---|---|---|---|---|
| 1bbf | 399023421-1 | 0.00275 (14.8% of NFPP) | 0.01858 -> 0.01588 | 0.06096 -> 0.05836 | 0.01911 -> 0.01632 | 0.06170 -> 0.05903 | inconclusive both ways |
| e092 | 399023421-1 | 0.00275 | 0.01858 -> 0.01587 | 0.06119 -> 0.05860 | 0.01911 -> 0.01632 | 0.06166 -> 0.05899 | inconclusive both ways |
| 1bbf | 296819076-1 | 0.00103 (1.8%) | 0.05627 -> 0.05530 | 0.07098 -> 0.07002 | 0.05543 -> 0.05448 | 0.07072 -> 0.06978 | inconclusive (neighbour-table blocker); inconclusive without it too |
| e092 | 296819076-1 | 0.00103 | 0.05629 -> 0.05533 | 0.07116 -> 0.07021 | 0.05538 -> 0.05443 | 0.07051 -> 0.06957 | same |
| d0f8 | TOI-763.02 | 0.000151 (99.998%) | 1.51e-4 -> 3.6e-9 | 0.01865 -> 0.01850 | 1.63e-4 -> 3.9e-9 ("fixed": 1.2e-5) | 0.01208 -> 0.01192 | pass both ways |
| d0f8 | TOI-1058.01 | 5.3e-67 | unchanged | unchanged | 0.0270 -> 0.0270 | 0.0334 -> 0.0334 | inconclusive both ways |

The flux effect (section 1b): the dropped rows hold 0.67% of the S64 aperture for 399023421-1 and 1.6% to 1.7% per
aperture for TOI-763.02; the target's tdepth does not move, other stars' tdepths move 6.3e-4 or less, and no star
crosses tdepth 1.

**Could any outcome change?** No, in M3 as it stands.
- Removing these rows only lowers NFPP and FPP, so a pass cannot turn.
- 399023421-1, at about 0.016, stays 16 times the pass bar and 6 times below the fail bar.
- The only fail, 44926986-1 (0.167), has no weighed flagged rows, and its flux effect is 2.9e-6.
- The nearest inconclusives to the pass bar have no weighed flagged rows: 146282666-1 (0.00153, no flagged rows at
  all), TOI-1097.02 (0.0064) and TOI-451.03 (0.0081).
- TOI-763.02 shows what could change in principle: an inconclusive just over 0.001 whose NFPP is mostly an artifact's
  would become a pass, and a real planet near the 0.1 fail bar could be failed by a duplicate's share.
- The controls summary and decisions 0026, 0031 and 0032 keep every count and outcome. 0032's TOI-1058.01 NFPP of
  0.027 is unchanged. TOI-763.02's NFPP in `controls.csv` would drop from 1.6e-4 to about 0.

**A single-seed rerun (question 4).** 399023421-1 was over budget (4 h 58 min for 10 seeds, about 30 min per seed).
TOI-763.02 instead, seed 9, under `/tmp/t13/heavy.sh` (its rows are ARTIFACTs, the mechanism the same):
- With the rows it reproduces the run exactly: FPP 0.0186465, NFPP 1.50964e-4, every probability equal (321 s).
- Without them: FPP 0.0184984 (renormalisation predicted 0.0184984) and NFPP 5.8e-9 (predicted 3.6e-9; both
  effectively 0, the gap Monte Carlo noise from the shifted random stream) (254 s).
So the renormalised estimates in the table hold.

## 4. Recommended fix and what to rerun

The fix belongs in the wrapper, `tricera.py`, not TRICERATOPS (`uv.lock` and the dependencies are frozen). In `run`,
after `new_target` (line 447) and before `_stars`, `apertures` and `calc_depths`, drop the DUPLICATE and ARTIFACT rows
from `.stars` and every `.pix_coords` array with one mask:

```python
keep = ~target.stars["disposition"].isin(("DUPLICATE", "ARTIFACT")).to_numpy()
target.stars = target.stars[keep].reset_index(drop=True)
target.pix_coords = [p[keep] for p in target.pix_coords]
```

- The column is already in `target.stars` (line 135), so no new query is needed.
- Keep SPLIT rows and rows with only a `duplicate_id`.
- Record the dropped rows (ID, disposition, `duplicate_id`) in the evidence, and add `disposition` to `STAR_COLUMNS`.
- If the target row itself were flagged, the existing check that the first star is the target (wrapper line 386)
  would block it. Name that case explicitly.
- No threshold changes: a defect fix with a decision record, like 0034.

To rerun after the fix: the current signals run (1bbf: 399023421-1 and 296819076-1 change, 103312990-1 and 44926986-1
only at float level, 146282666-1 and 164767175-1 have no flagged rows); the m3-r2 dossiers that quote these numbers and
F1 in the 399023421-1 review (NFPP 0.0191 and the per-star sums); the promoted run (55f4) if judged before the fix
lands (241522065-1 and 423100454-1 probably affected); controls: TOI-763.02's numbers change but not its outcome, so
rerunning d0f8 and the summary is optional for exactness; e092 is superseded.

## 5. Adjacent, not measured

- **Host matching names DUPLICATE rows.** In 296819076-1 the evidence's `hosts` matches three Gaia DR3 hosts to
  DUPLICATE IDs (1132493618, 1132493585 and 1132491384), because the duplicate comes first in the list and
  `_nearest`'s argmin takes the first. The tdepth is identical, so this is cosmetic; the fix makes them match the
  originals.
- **993417201 is weighed as a solar star.** One of F1's close possible hosts of 399023421-1: `probs.csv` gives it M_s
  1.0 and R_s 1.0, since the TIC has no parameters for it and the photometric estimate gave none.
- **SPLIT neighbours' estimated parameters use blended 2MASS photometry** (399023424 R_s 0.921 against its
  2MASS-less duplicate's 0.784).
- **A galaxy is weighed as a host star in TOI-763.02.** TIC 10000891672 (objType EXTENDED, T 11.63) has tdepth 0.027
  and a share of about 1e-19. The star lists hold 14 EXTENDED rows; only that one is weighed.
- **The input depth may include SPOC's own over-correction.** The wrapper trusts the PDCSAP depth as on-target. If
  SPOC's crowding correction counted DUPLICATE or ARTIFACT flux in some sector, that depth is slightly over-corrected,
  by no more than the flagged flux share (up to 1.7% here).

## 6. Scripts and outputs

Run from `/tmp/t13-dup` with `uv run --project /home/kevin/code/tess-hunt-run --no-sync python`, or `uv run
--no-project --with pandas python` for the pandas-only scripts (running there keeps TESScut and field-star files out
of the repo; cutouts cached in `/tmp/t13-dup/lkcache`).
- `collect.py`: `stars.csv` (every star in every list), `signals.csv`, `collect.txt`.
- `dispositions.py`: MAST `query_criteria` in batches of 1000; `tic.csv`, `dispositions.txt`.
- `reach.py`: `flagged.csv`, `reach.txt`.
- `depths.py`: the flux check; `depths/<signal>.json` and `.log` (the first, 399023421-1, has only the `.json`).
- `effect.py`: `effect.csv`, `effect.txt`.
- `pairs.py`: `pairs.txt`.
- `hosts_check.py`: `hosts_check.txt`.
- `cone.py`: the promoted rows; `cone.csv`, `cone.txt`.
- `rerun.py`: question 4; `rerun/TOI-763.02/rerun.json`, `probs_with.csv`, `probs_without.csv`,
  `rerun-TOI-763.02.log`.
- `paegert2021.pdf` and `.txt`: the TIC 8.2 paper.

The scripts read and write `/tmp/t13-dup/` by that absolute path, so a rerun unpacks the tarball's `t13-dup/` folder
there; `/tmp/t13/heavy.sh` (section 3) is the tarball's `t13/heavy.sh`. The tarball leaves out `lkcache/` (TESScut
cutouts, which `depths.py` and `rerun.py` fetch again), `rerun/TOI-763.02/178819686_gaia_background.csv` (the run's
field-star file, which `rerun.py` copies from the run again) and the paper, which is cited, not republished. The
tarball's sha256 is `2e26c3d72b5cadc86a48690fa2f04f123508930079196db616abeed6fa08153c`.
