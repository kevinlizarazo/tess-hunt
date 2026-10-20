# F3's reach: the neighbour table mixes epochs

2026-10-20. Read-only measurement for Task 13's review of 44926986-1, finding F3. Nothing in the repo, the runs or the drafts was changed; scratch is in `/tmp/t13-epoch/`, published as `t13-epoch/` in `neighbour-epoch-reach-2026-10-20-scripts.tar.gz` beside this file.

**Corrected separation:** the distance from the target's own DR3 position to each star's DR3 position, both at J2016.0. **Corrected cone:** every DR3 star within 60" of the target's DR3 position (`[neighbours] radius_arcmin = 1.0`).

## Answer

- **Tables.**
  - There are 62 tables in three runs: `VET_RUN` (19), `VET_SUSPECT_RUN` (19, identical to `VET_RUN` row for row) and `CONTROL_VET` (24). They cover 41 stars. No other run holds a `neighbours.csv`.
  - In all 62, `checks.json`'s table equals `neighbours.csv`.
  - The archive's `DISTANCE` to the TIC position reproduces every table's stars and `sep_arcsec` exactly (largest difference 0.0").
- **Offsets over 0.5": 24 of 41 stars.**
  - That is 9 of the 19 signals (6 candidates, 3 second-list) and 15 control stars in 16 control tables.
  - Each offset matches the DR3 proper motion times 16 years within 0.013".
- **Line crossings: 156.**
  - 66 in the 19 signals' tables (15": 19, 20": 22, 25": 25).
  - 90 in the controls' tables (20, 29 and 41), 82 of them TOI-2011.02's.
  - 18 are possible hosts.
- **Cone crossings: 205.**
  - The 19 signals' tables: 31 added and 34 dropped, across 11 tables.
  - The controls' tables: 64 added and 76 dropped, across 13 tables (111 of them TOI-2011.02's).
  - 16 are possible hosts, and one added star has no G (458290782-1).
- **What changes besides separations:**
  - Possible-host membership in 103312990-1, 296819076-1, 410399327-1, 423100454-1, 44926986-1, 458290782-1, TOI-652.01 and TOI-755.01.
  - 458290782-1's `no_g` list, from 1 to 2 stars.
  - The "N of M" `reason` in 25 tables.
  - Every `sep_arcsec` in the 24 offset stars' tables.
- **Quotes moved by more than 0.5":**
  - 0026's 12.5" becomes 9.86".
  - 0033's 6.5" becomes 8.42".
  - 280 of the 723 host rows in 8 drafts.
  - 0025/0026/0032's 20.90" and 23.53" stay within 0.05", because they came from the network test. Production's own table has 22.85" for TOI-1175.01's binary, which moves +0.69".
  - The controls summary quotes no separation.

## 1. Offsets over 0.5"

| signal | kind | TIC | Gaia DR3 id | offset (") | DR3 pm (mas/yr) | pm x 16 yr (") | tables | rows | max shift (") |
|---|---|---|---|---|---|---|---|---|---|
| TOI-2011.02 | control | 136916387 | 5902750168276592256 | 26.357 | 1646.5 | 26.344 | CONTROL_VET | 202 | 26.357 |
| TOI-144.01 | control | 261136679 | 4623036865373793408 | 17.505 | 1094.2 | 17.507 | CONTROL_VET | 8 | 17.219 |
| TOI-4307.01 | control | 141186075 | 4648266774581927296 | 5.222 | 326.2 | 5.219 | CONTROL_VET | 44 | 5.222 |
| TOI-118.01 | control | 266980320 | 6492940453524576128 | 5.033 | 314.6 | 5.033 | CONTROL_VET | 3 | 1.219 |
| TOI-652.01 | control | 22221375 | 5660492297395345408 | 2.931 | 183.3 | 2.933 | CONTROL_VET | 11 | 2.909 |
| 44926986-1 | candidate | 44926986 | 5431607545961330560 | 2.752 | 171.9 | 2.750 | VET_RUN, VET_SUSPECT_RUN | 29 | 2.737 |
| TOI-396.01, TOI-396.03 | control | 178155732 | 5064574724769475968 | 2.599 | 162.7 | 2.603 | CONTROL_VET | 8 | 2.522 |
| 164767175-1 | candidate | 164767175 | 5140454049422547200 | 2.254 | 141.0 | 2.256 | VET_RUN, VET_SUSPECT_RUN | 0 | no rows |
| 423100454-1 | second | 423100454 | 5836452847014268800 | 2.204 | 137.8 | 2.205 | VET_RUN, VET_SUSPECT_RUN | 774 | 2.204 |
| TOI-411.01 | control | 100990000 | 4848767461548943104 | 1.953 | 122.0 | 1.952 | CONTROL_VET | 1 | 0.314 |
| 146282666-1 | candidate | 146282666 | 4967249906845494144 | 1.846 | 115.2 | 1.844 | VET_RUN, VET_SUSPECT_RUN | 7 | 1.795 |
| TOI-763.02 | control | 178819686 | 6140553127216043648 | 1.832 | 114.3 | 1.829 | CONTROL_VET | 14 | 1.829 |
| TOI-191.01 | control | 183532609 | 2312679845530628096 | 1.760 | 110.0 | 1.760 | CONTROL_VET | 2 | 1.572 |
| 322826591-1 | second | 322826591 | 5332801170510042880 | 1.723 | 107.8 | 1.724 | VET_RUN, VET_SUSPECT_RUN | 191 | 1.723 |
| 103312990-1 | candidate | 103312990 | 5365550158677776896 | 1.187 | 74.1 | 1.185 | VET_RUN, VET_SUSPECT_RUN | 54 | 1.187 |
| TOI-1052.01 | control | 317060587 | 6357524189130820992 | 1.014 | 63.3 | 1.013 | CONTROL_VET | 14 | 1.005 |
| 441010857-1 | candidate | 441010857 | 6122183689530591488 | 0.966 | 60.2 | 0.962 | VET_RUN, VET_SUSPECT_RUN | 16 | 0.955 |
| 296819076-1 | candidate | 296819076 | 5877911685214643072 | 0.948 | 59.2 | 0.948 | VET_RUN, VET_SUSPECT_RUN | 539 | 0.948 |
| TOI-576.01 | control | 408310006 | 5664957444179338240 | 0.899 | 56.2 | 0.899 | CONTROL_VET | 14 | 0.872 |
| TOI-107.01 | control | 92352620 | 6780546169634170496 | 0.834 | 52.2 | 0.835 | CONTROL_VET | 12 | 0.834 |
| TOI-188.01 | negative_control | 280830734 | 4645797134023714688 | 0.815 | 51.1 | 0.818 | CONTROL_VET | 8 | 0.814 |
| TOI-1097.02 | control | 360630575 | 5838450865699668736 | 0.813 | 50.9 | 0.815 | CONTROL_VET | 80 | 0.813 |
| 337885456-1 | second | 337885456 | 6726411577226875136 | 0.770 | 48.2 | 0.772 | VET_RUN, VET_SUSPECT_RUN | 233 | 0.770 |
| TOI-1175.01 | negative_control | 30329585 | 2039904204830244096 | 0.744 | 47.1 | 0.753 | CONTROL_VET | 84 | 0.743 |

"offset" is the distance from the TIC position to the star's own DR3 position. "rows" is the table's neighbour count. "max shift" is the largest change in any row's separation.

The other 17 stars, offset in arcsec: 48010903-1 0.494, 399023421-1 0.449, 241522065-1 0.439, 173369850-1 0.413, 410399327-1 0.387, 458290782-1 0.384, TOI-4320.01 0.367, TOI-1399.01 0.289, 370977908-1 0.280, TOI-451.02 0.267, TOI-1058.01 0.266, TOI-755.01 0.227, 277774870-1 0.170, 295140687-1 0.166, TOI-826.01 0.100, 438857197-1 0.078, TOI-747.01 0.067.

## 2. Crossings

### Possible hosts across 15", 20" or 25"

| table | signal | line | Gaia DR3 id | table sep (") | corrected (") |
|---|---|---|---|---|---|
| 19 | 103312990-1 | 15" | 5365550193037516288 | 14.47 | 15.37 |
| 19 | 173369850-1 | 25" | 5915858816461169536 | 24.93 | 25.04 |
| 19 | 296819076-1 | 15" | 5877910929300396928 | 14.40 | 15.23 |
| 19 | 296819076-1 | 15" | 5877910929300393728 | 14.84 | 15.37 |
| 19 | 296819076-1 | 15" | 5877911650821097216 | 15.24 | 14.40 |
| 19 | 296819076-1 | 25" | 5877911646525818240 | 25.86 | 24.98 |
| 19 | 322826591-1 | 25" | 5332800964351873152 | 24.69 | 26.40 |
| 19 | 322826591-1 | 25" | 5332801170500496256 | 25.18 | 23.51 |
| 19 | 322826591-1 | 25" | 5332801166188339584 | 25.76 | 24.20 |
| 19 | 423100454-1 | 15" | 5836453499849301760 | 16.61 | 14.98 |
| 19 | 423100454-1 | 20" | 5836452846953412992 | 19.13 | 20.82 |
| 19 | 423100454-1 | 20" | 5836452847014262400 | 19.16 | 20.25 |
| 19 | 423100454-1 | 25" | 5836453598527876480 | 24.10 | 25.04 |
| 19 | 423100454-1 | 25" | 5836452847014269824 | 24.28 | 26.37 |
| 19 | 423100454-1 | 25" | 5836453499849304576 | 26.39 | 24.92 |
| 19 | 438857197-1 | 25" | 6083427107255911936 | 24.95 | 25.02 |
| controls | TOI-2011.02 | 20" | 5902750202619292672 | 15.40 | 39.67 |
| controls | TOI-2011.02 | 25" | 5902750202619292672 | 15.40 | 39.67 |

"19" is VET_RUN's tables and "controls" is CONTROL_VET's. VET_SUSPECT_RUN's tables are identical to VET_RUN's. A row that crosses two lines is listed once per line.

None of these 18 changes a host's status, because `possible` depends on magnitudes only. The 15" rows matter when reasoning about triage's pixel rule, since a blend inside 15" can pass it. 423100454-1's host 5836453499849301760 moves inside 15". 103312990-1's 5365550193037516288 and two of 296819076-1's hosts move outside it.

### Cone changes that touch a possible host or a star without G

| table | signal | change | Gaia DR3 id | table sep (") | corrected (") | G | required depth | possible |
|---|---|---|---|---|---|---|---|---|
| 19 | 103312990-1 | added | 5365550055598557056 | 60.70 | 59.83 | 17.10 | 0.215 | True |
| 19 | 296819076-1 | added | 5877911719540705408 | 60.05 | 59.73 | 18.89 | 0.347 | True |
| 19 | 296819076-1 | added | 5877911719540657024 | 60.69 | 59.94 | 19.14 | 0.526 | True |
| 19 | 296819076-1 | dropped | 5877910929266500992 | 59.96 | 60.22 | 19.01 | 0.389 | True |
| 19 | 296819076-1 | dropped | 5877911749605067264 | 60.00 | 60.31 | 19.00 | 0.409 | True |
| 19 | 296819076-1 | dropped | 5877910924970222464 | 59.91 | 60.53 | 18.84 | 0.436 | True |
| 19 | 410399327-1 | added | 6434209107919208064 | 60.20 | 59.89 | 18.43 | 0.559 | True |
| 19 | 423100454-1 | added | 5836452739533401088 | 60.11 | 58.84 | 17.73 | 0.940 | True |
| 19 | 423100454-1 | dropped | 5836452778233699456 | 60.00 | 60.04 | 17.60 | 0.871 | True |
| 19 | 423100454-1 | dropped | 5836453598524522240 | 58.57 | 60.11 | 16.91 | 0.467 | True |
| 19 | 423100454-1 | dropped | 5836452808248808320 | 58.88 | 60.26 | 12.70 | 0.013 | True |
| 19 | 423100454-1 | dropped | 5836452881313190784 | 59.52 | 61.67 | 17.19 | 0.604 | True |
| 19 | 44926986-1 | dropped | 5431607644742487424 | 59.04 | 61.50 | 17.65 | 0.860 | True |
| 19 | 458290782-1 | added | 5971009602474720768 | 60.06 | 59.68 | none | none | False |
| 19 | 458290782-1 | added | 5971009602504628608 | 60.20 | 59.84 | 17.00 | 0.258 | True |
| controls | TOI-652.01 | dropped | 5660492086942048384 | 58.50 | 61.41 | 15.58 | 0.493 | True |
| controls | TOI-755.01 | added | 6133384204027888128 | 60.00 | 59.88 | 11.94 | 0.003 | True |

"added" means the star is in the corrected cone but not in the table. "dropped" means the reverse. Required depth and `possible` are as `required_depths` computes them.

For 44926986-1:
- The companion Gaia DR3 5431607545963652864 (TIC 44926982) moves from 12.50" to 9.86" and crosses no line.
- The possible host 5431607644742487424 leaves the cone (59.04" to 61.50").
- The non-host 5431607610382753536 crosses 15" (17.32" to 14.77").
- Its triage centroid offset is 10.9" (0026), which is now closer to the companion's 9.86" than to the table's 12.50".

Every line crossing is in appendix A and every cone change is in appendix B.

## 3. Outcomes, possible hosts, blockers and TRICERATOPS

I rebuilt every table on the corrected cone and ran it through the repo's own `neighbours.required_depths` and `neighbours.neighbour_check`, unchanged, with each table's recorded depth and TESS magnitude. The table below lists every table where the corrected cone changes the neighbour record's `reason` or its possible hosts. VET_SUSPECT_RUN's 7 match VET_RUN's and are left out.

| table | signal | outcome | reason now | reason corrected | possible hosts added | possible hosts dropped |
|---|---|---|---|---|---|---|
| 19 | 103312990-1 | pass (unchanged) | 20 of 54 neighbours could host the signal | 21 of 55 neighbours could host the signal | 5365550055598557056 | none |
| 19 | 173369850-1 | pass (unchanged) | 39 of 143 neighbours could host the signal | 39 of 144 neighbours could host the signal | none | none |
| 19 | 296819076-1 | inconclusive (unchanged) | 10 Gaia DR3 star(s) within the radius have no G magnitude | same | 5877911719540657024 5877911719540705408 | 5877910924970222464 5877910929266500992 5877911749605067264 |
| 19 | 337885456-1 | pass (unchanged) | 40 of 233 neighbours could host the signal | 40 of 237 neighbours could host the signal | none | none |
| 19 | 399023421-1 | pass (unchanged) | 53 of 83 neighbours could host the signal | 53 of 82 neighbours could host the signal | none | none |
| 19 | 410399327-1 | pass (unchanged) | 11 of 23 neighbours could host the signal | 12 of 24 neighbours could host the signal | 6434209107919208064 | none |
| 19 | 423100454-1 | inconclusive (unchanged) | 1 Gaia DR3 star(s) within the radius have no G magnitude | same | 5836452739533401088 | 5836452778233699456 5836452808248808320 5836452881313190784 5836453598524522240 |
| 19 | 44926986-1 | pass (unchanged) | 7 of 29 neighbours could host the signal | 6 of 28 neighbours could host the signal | none | 5431607644742487424 |
| 19 | 458290782-1 | inconclusive (unchanged) | 1 Gaia DR3 star(s) within the radius have no G magnitude | 2 Gaia DR3 star(s) within the radius have no G magnitude | 5971009602504628608 | none |
| controls | TOI-1052.01 | pass (unchanged) | 3 of 14 | 3 of 16 | none | none |
| controls | TOI-1058.01 | pass (unchanged) | 7 of 92 | 7 of 91 | none | none |
| controls | TOI-1175.01 | pass (unchanged) | 13 of 84 | 13 of 82 | none | none |
| controls | TOI-1399.01 | pass (unchanged) | 17 of 60 | 17 of 61 | none | none |
| controls | TOI-2011.02 | pass (unchanged) | 2 of 202 | 2 of 193 | none | none |
| controls | TOI-396.01 | pass (unchanged) | 1 of 8 | 1 of 7 | none | none |
| controls | TOI-396.03 | pass (unchanged) | 1 of 8 | 1 of 7 | none | none |
| controls | TOI-4307.01 | pass (unchanged) | 2 of 44 | 2 of 41 | none | none |
| controls | TOI-652.01 | pass (unchanged) | 3 of 11 | 2 of 11 | none | 5660492086942048384 |
| controls | TOI-755.01 | pass (unchanged) | 9 of 38 | 10 of 39 | 6133384204027888128 | none |
| controls | TOI-763.02 | pass (unchanged) | 2 of 14 | 2 of 15 | none | none |

In the control rows, "N of M" is short for "N of M neighbours could host the signal".

**What TRICERATOPS takes from the table.** It doesn't read `neighbours.csv` itself. `vetting triceratops` reads the same table from `checks.json` (`checks["neighbours"]["evidence"]["table"]`, `vetting.py:653`) and keeps the rows with `possible` true (`vetting.py:654`). From those it uses two things:
- The neighbour record's outcome: anything but pass is a blocker (`tricera.py:531-533`).
- Each possible host's DR3 `ra`, `dec`, `pmra` and `pmdec`, moved back to J2000 (`at_tic_epoch`, `tricera.py:140-148`). It looks for a TRICERATOPS star within `match_arcsec` (2"), and a host with none is a blocker (`tricera.py:567-572`).

`sep_arcsec` is only copied into `hosts` as evidence (`tricera.py:198`). The depth TRICERATOPS folds at is the neighbour record's `depth` (`vetting.py:627`), which is the signals file's depth and isn't touched by the fix. The star list, and everything `calc_probs` sees, comes from TRICERATOPS's own TIC query. So FPP and NFPP can't move, and the outcome could move only through a new blocker.

None appears. I re-ran `tricera.missing_hosts` on the corrected possible hosts against the star list stored by every finished run: TRIC_RUN's 6 signals (103312990-1, 146282666-1, 164767175-1, 296819076-1, 399023421-1, 44926986-1), CONTROL_TRIC's 24 controls and CONTROL_TRIC_4307. All 31 have no missing hosts before and after. Every added host in a judged signal matches a TRICERATOPS star at J2000:

| table | signal | TRICERATOPS run | outcome | added host: matched TIC star, distance (") |
|---|---|---|---|---|
| 19 | 103312990-1 | 20261020T013408Z | inconclusive | 5365550055598557056: TIC 103313020, 0.002 |
| 19 | 296819076-1 | 20261020T013408Z | inconclusive | 5877911719540705408: TIC 1132493713, 0.174; 5877911719540657024: TIC 1132493694, 0.029 |
| controls | TOI-755.01 | 20261017T162256Z | pass | 6133384204027888128: TIC 73228631, 0.002 |

Three signals that no finished TRICERATOPS run has judged gain possible hosts nobody has checked against a star list: 410399327-1 (1 added), 423100454-1 (1 added, 4 dropped) and 458290782-1 (1 added).

A TRICERATOPS run on VET_RUN is in progress: `20261020T140004Z-vetting-triceratops-d039859-f7bc`. It started at 14:00 UTC and was still running at 14:31 UTC (`ps`; no `ended_at` in its provenance). It covers 241522065-1, 277774870-1, 370977908-1, 438857197-1 and 423100454-1. Of those, only 423100454-1's possible hosts change.

The drafts' `centroids.png` draws a line at each possible host's `sep_arcsec` (`plots.py:229-254`), so those plots move with the table.

## 4. Quoted separations

### Decision records

| Where | Quote | Star | Table value (") | Corrected (") | Moved (") |
|---|---|---|---|---|---|
| 0026, Ruling S | 44926986's "12.5" possible host" | Gaia DR3 5431607545963652864 (TIC 44926982) | 12.504 | 9.859 | -2.645 |
| 0033, item 3 | 423100454-1's "possible hosts from 6.5" out" | Gaia DR3 5836452846954130944 | 6.549 | 8.415 | +1.867 |
| 0025, 0026, 0032 | TOI-1058.01's binary "20.90"" | Gaia DR3 6757952648798471040 | 20.808 in CONTROL_VET; 20.899 from the network test's centre | 20.947 | +0.139; +0.048 |
| 0025, 0026, 0032 | TOI-1175.01's binary "23.53"" | Gaia DR3 2039904204830247296 | 22.850 in CONTROL_VET; 23.527 from the network test's centre | 23.544 | +0.693; +0.017 |

The two binaries' quotes come from `test_nearby_eb_controls_show_a_possible_host`. That test centres its cone on `benchmarks/pixel_controls.csv`'s `ra` and `dec`, which sit 0.277" and 0.705" from the targets table's TIC positions. Those centres happen to land near the DR3 positions, so the quotes hold within 0.05". Production's own table read 22.85" for TOI-1175.01's binary.

In 0033's item 3, 423100454-1's corrected nearest possible host is at 8.42". 5836453499849301760 (16.61" to 14.98") becomes the second nearest and is now inside 15".

The fix doesn't move these:
- 0026's "2.78" apart". It measures a host's DR3 position against its own TIC star's position, which is the gap Ruling S closes, not a separation from the target.
- The centroid offsets in 0026 (10.9"), 0032 (21.5", 25.1", 11.6") and 0033 (the pixel column, and item 3's 5.7" to 8.7", 118.6", 115.7" and 121"). These come from LEO-Vetter's centroid test.
- 0031, which quotes no separation.

### Dossier drafts

All 19 drafts are rendered from VET_RUN (`provenance-checks.json`). Each lists its possible hosts with the table's separation to 0.1", and all 723 quoted rows match the table to that rounding. 280 of them move by more than 0.5", across 8 drafts; appendix C lists every row. The dossier sorts hosts by separation, so the order changes too.

| draft | rows moved > 0.5" | largest shift (") |
|---|---|---|
| 103312990-1 | 13 | 1.19 |
| 146282666-1 | 3 | 1.79 |
| 296819076-1 | 118 | 0.95 |
| 322826591-1 | 35 | 1.72 |
| 337885456-1 | 23 | 0.77 |
| 423100454-1 | 80 | 2.20 |
| 441010857-1 | 3 | 0.96 |
| 44926986-1 | 5 | 2.69 |

### Controls summary

`results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md` quotes no neighbour separation; its only arcsec values are pixel-check centroid offsets. Its possible-host row for the four negative controls (line 112: 7, 13, 17, 3) is unchanged. In `controls.csv`, `possible_hosts` changes for TOI-652.01 (3 to 2) and TOI-755.01 (9 to 10). The neighbour pass rates don't change, because every control's table passes either way.

## 5. The fix and what it forces

**Fix.** When the target has a DR3 source id, centre the cone on its DR3 row. Every M3 target has one. One query does it:

```sql
SELECT g.source_id, g.ra, g.dec, g.phot_g_mean_mag, g.bp_rp,
       DISTANCE(POINT('ICRS', g.ra, g.dec), POINT('ICRS', t.ra, t.dec)) * 3600 AS sep_arcsec,
       g.pmra, g.pmdec, g.ref_epoch
FROM gaiadr3.gaia_source AS t, gaiadr3.gaia_source AS g
WHERE t.source_id = {source_id}
  AND 1 = CONTAINS(POINT('ICRS', g.ra, g.dec), CIRCLE('ICRS', t.ra, t.dec, {radius_deg}))
```

I tried it read-only (`selfjoin.py`) on 44926986, TOI-2011.02 and 423100454. It returns exactly the corrected cone: 29, 194 and 770 rows including the target, with separations within 3e-10" of the offline values. One try got an HTTP 500 that a second try cleared; `gaia_cone` already retries.

With the fix, every position and separation is DR3's at J2016.0 with no propagation, and stars without a proper motion need none. Without a source id, the TIC-centred cone and the 1" match stay as they are. 16 of the 41 stars sit more than 1" from their TIC position, so that path remains the weaker one that 0025's Limitations describe. Ruling S's match needs no change, because it never read `sep_arcsec`.

The alternatives are harder:
- Moving the TIC position to J2016 needs the TIC's proper motion, and `checks.json`'s star row doesn't carry it.
- Moving every DR3 star back to J2000 can't move the two-parameter ones, which is Ruling S's own limitation.
- A wider TIC-centred cone recut around the DR3 row needs a margin set before the offset is known, and TOI-2011.02's offset is 26.36".

The change touches `gaia_cone`'s query and its caller in `vetting._neighbours`. The fakes in `test_vetting.py` (lines 80, 151, 377, 455 and 465) take `neighbours.gaia_cone(ra, dec, radius_arcmin)`, so a new signature means updating them. In the docs, 0025's first Decision bullet and first Limitation, 0026's 12.5" and 0033's 6.5" need updating.

**What it forces to rerun.** A corrected table means a new `checks.json` in a new vetting run, and the tools that build on a vetting run refuse anything made from another one:
- `vetting dossier` and `vetting publish` take their runs through `_record_runs` (`vetting.py:1061`). Each TRICERATOPS, literature and second-list run must be made from the vetting run given (`vetting.py:1086-1087`).
- `_signal_files` refuses a run that read a different `checks.json` from the one that vetting run holds (`vetting.py:1122-1126`).
- `benchmark controls` refuses a TRICERATOPS run made on another vetting run (`controls.py:163-166`).

Durations are each run's `ended_at` minus its `started_at`.

| Run now | What reruns | Why | Last took |
|---|---|---|---|
| VET_RUN (`20261020T010149Z-vetting-run-62882b5-c3ee`) | `vetting run --production` on the 19 | the table lives in its `checks.json` | 11 min |
| VET_SUSPECT_RUN (`20261020T011247Z-vetting-run-62882b5-d92b`) | the evidence-only `vetting run` | `_record_runs` would still accept the old one (it checks only the evidence-only flag, the criteria and the ephemeris: `vetting.py:1084, 1088-1089, 1133`), but its `checks-with-suspect.json` would keep the old table | 11 min |
| TRIC_RUN (`20261020T013408Z-vetting-triceratops-62882b5-e092`), 6 signals | `vetting triceratops` | made from VET_RUN; checks.json sha256 | 6.5 h |
| `20261020T140004Z-vetting-triceratops-d039859-f7bc`, 5 signals | `vetting triceratops` | made from VET_RUN; in progress | running |
| LIT_RUN (`20261020T091938Z-vetting-literature-2315775-066c`) | `vetting literature` | made from VET_RUN | 8 min |
| SECOND_RUN (`20261020T012658Z-vetting-second-list-62882b5-3fca`) | `vetting second-list` | made from VET_RUN | 7 min |
| the 19 drafts | `vetting dossier` | rendered from the runs above; `review.json` and `call.toml` survive `_clear` (`vetting.py:1157`) but were written against the old dossiers | |
| CONTROL_VET (`20261017T155223Z-vetting-run-62882b5-4867`) | `vetting run --production` on the 24 controls | its tables carry the defect too | 29 min |
| CONTROL_TRIC (`20261017T162256Z-vetting-triceratops-62882b5-d0f8`), 24 controls | `vetting triceratops` | made from CONTROL_VET | 9.1 h |
| CONTROL_TRIC_4307 (`20261018T012940Z-vetting-triceratops-62882b5-e3d7`) | `vetting triceratops` on TOI-4307.01 | made from CONTROL_VET | 1.3 h |
| CONTROLS_RUN (`20261020T082333Z-benchmark-controls-16418d2-f45a`, published; cited by 0026, 0031 and 0032) | `benchmark controls` | refuses TRICERATOPS runs made on another vetting run | seconds |

TRICERATOPS seeds each of its runs (`tricera.py:482-483`), so with the same inputs its FPP and NFPP should come back the same. Its field-star population comes from TRICERATOPS itself (`tricera.py:448-450`), and I didn't check whether a rerun gets the same one.

One choice is the maintainer's. On the controls, the corrected tables change no outcome, no blocker and no count that the summary publishes. Leaving CONTROL_VET and the published controls run as they stand, with this reach recorded, saves about 10.5 h of TRICERATOPS and keeps the run that 0026, 0031 and 0032 cite. The cost is that the controls' published tables keep the mixed-epoch separations, with TOI-2011.02's off by up to 26.36". The 19 signals' chain can't be left the same way, because the drafts quote the separations.

## Adjacent, not measured

The pixel check (triage-v1: LEO-Vetter through transit-diffImage) is also handed the TIC's `ra` and `dec` (`pixels.py:88, 105`). The controls summary lists four known planets failing it: TOI-144.01 (46.8"), TOI-2011.02 (69.0"), TOI-396.03 (35.6") and TOI-4307.01 (17.9"). Among the 22 control stars, they rank 2nd, 1st, 6th and 3rd by DR3 proper motion:

| control | DR3 pm (mas/yr) |
|---|---|
| TOI-2011.02 | 1646.5 |
| TOI-144.01 | 1094.2 |
| TOI-4307.01 | 326.2 |
| TOI-118.01 | 314.6 |
| TOI-652.01 | 183.3 |
| TOI-396.01, TOI-396.03 | 162.7 |
| TOI-411.01 | 122.0 |
| TOI-763.02 | 114.3 |

I didn't check whether the centroid test compares against a position at another epoch. 0031 leaves these fails to Task 15.

## Commands

Each block ran from Git Bash inside `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-26.04 --cd /home/kevin/code/tess-hunt -- bash -l -s`, with the block passed as a quoted here-document:

```sh
. ~/.cache/tess-hunt/logs/m3-vars.sh       # VET_RUN, VET_SUSPECT_RUN, CONTROL_VET, TRIC_RUN, CONTROL_TRIC, CONTROL_TRIC_4307
cd ~/.cache/tess-hunt/runs && find . -name neighbours.csv | awk -F/ '{print $2}' | sort | uniq -c   # 24, 19, 19 in three runs
uv run python /tmp/t13-epoch/gather.py     # manifest.json: 62 tables, 41 stars, csv == checks.json in all
uv run python /tmp/t13-epoch/cones.py      # cones/<tic>.csv: 41 Gaia cones of 90" around the TIC positions
uv run python /tmp/t13-epoch/analyse.py    # targets.csv, rows.csv, changes.csv, repro.csv
uv run python /tmp/t13-epoch/outcomes.py   # outcomes.json: neighbour_check and missing_hosts on the corrected cones
uv run python /tmp/t13-epoch/quotes.py     # decision quotes, dossier_moved.csv
uv run python /tmp/t13-epoch/counts.py     # crossing counts
uv run python /tmp/t13-epoch/selfjoin.py   # the fix's query on 44926986, then 136916387 and 423100454
uv run python /tmp/t13-epoch/tables.py     # tables/*.md
grep -n -E '[0-9]"|arcsec|separation' docs/decisions/0026-triceratops.md docs/decisions/0033-second-list-decisions.md
grep -n -i "possible\|neighbour" results/benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a/summary.md
grep -n 'table = pd.DataFrame(checks\["neighbours"\]\|made\["vetting_run"\] != run_id\|inputs.get(f"checks_{name}"' src/tess_hunt/vetting.py
ps -eo pid,etime,args | grep -i triceratops
```

The scripts follow as run (appended by the assembly command). They read and write `/tmp/t13-epoch/` by that absolute path, so a rerun unpacks the tarball's `t13-epoch/` folder there. The tarball leaves out `cones/`, which `cones.py` fetches again.

## Appendix A: every line crossing

| table | signal | line | Gaia DR3 id | table sep (") | corrected (") | possible |
|---|---|---|---|---|---|---|
| 19 | 103312990-1 | 15" | 5365550193037516288 | 14.47 | 15.37 | True |
| 19 | 173369850-1 | 25" | 5915858816461169536 | 24.93 | 25.04 | True |
| 19 | 296819076-1 | 15" | 5877910929300396928 | 14.40 | 15.23 | True |
| 19 | 296819076-1 | 15" | 5877910929300393728 | 14.84 | 15.37 | True |
| 19 | 296819076-1 | 15" | 5877911650821097216 | 15.24 | 14.40 | True |
| 19 | 296819076-1 | 15" | 5877911646542274944 | 15.34 | 14.42 | False |
| 19 | 296819076-1 | 15" | 5877911650855276032 | 15.88 | 14.95 | False |
| 19 | 296819076-1 | 20" | 5877910929268072960 | 19.34 | 20.26 | False |
| 19 | 296819076-1 | 25" | 5877911685180890112 | 24.90 | 25.66 | False |
| 19 | 296819076-1 | 25" | 5877911646525818240 | 25.86 | 24.98 | True |
| 19 | 322826591-1 | 15" | 5332801166194591616 | 15.15 | 14.01 | False |
| 19 | 322826591-1 | 15" | 5332801166188339456 | 15.98 | 14.29 | False |
| 19 | 322826591-1 | 15" | 5332801170512152064 | 16.69 | 14.97 | False |
| 19 | 322826591-1 | 20" | 5332801170500521472 | 20.64 | 19.85 | False |
| 19 | 322826591-1 | 20" | 5332801170502687488 | 21.06 | 19.40 | False |
| 19 | 322826591-1 | 25" | 5332800964344443392 | 23.65 | 25.31 | False |
| 19 | 322826591-1 | 25" | 5332801170502875392 | 24.13 | 25.56 | False |
| 19 | 322826591-1 | 25" | 5332800964351873152 | 24.69 | 26.40 | True |
| 19 | 322826591-1 | 25" | 5332801170500496256 | 25.18 | 23.51 | True |
| 19 | 322826591-1 | 25" | 5332801166188339584 | 25.76 | 24.20 | True |
| 19 | 337885456-1 | 20" | 6726411783358057984 | 19.68 | 20.29 | False |
| 19 | 337885456-1 | 25" | 6726411783360573312 | 24.95 | 25.47 | False |
| 19 | 423100454-1 | 15" | 5836452846953389440 | 14.12 | 16.08 | False |
| 19 | 423100454-1 | 15" | 5836452847023469312 | 14.69 | 16.84 | False |
| 19 | 423100454-1 | 15" | 5836452846953351680 | 14.92 | 16.74 | False |
| 19 | 423100454-1 | 15" | 5836452743874119040 | 16.03 | 14.21 | False |
| 19 | 423100454-1 | 15" | 5836452743876800000 | 16.21 | 14.20 | False |
| 19 | 423100454-1 | 15" | 5836452743874119168 | 16.23 | 14.25 | False |
| 19 | 423100454-1 | 15" | 5836452743874119552 | 16.42 | 14.34 | False |
| 19 | 423100454-1 | 15" | 5836453499849301760 | 16.61 | 14.98 | True |
| 19 | 423100454-1 | 20" | 5836452846954541056 | 18.31 | 20.46 | False |
| 19 | 423100454-1 | 20" | 5836452847014276992 | 18.37 | 20.35 | False |
| 19 | 423100454-1 | 20" | 5836453602867660416 | 18.76 | 20.04 | False |
| 19 | 423100454-1 | 20" | 5836452846954540928 | 18.92 | 21.05 | False |
| 19 | 423100454-1 | 20" | 5836452846953412992 | 19.13 | 20.82 | True |
| 19 | 423100454-1 | 20" | 5836452846953342080 | 19.14 | 20.74 | False |
| 19 | 423100454-1 | 20" | 5836452847014262400 | 19.16 | 20.25 | True |
| 19 | 423100454-1 | 20" | 5836452846953405440 | 19.31 | 21.19 | False |
| 19 | 423100454-1 | 20" | 5836452846953318656 | 19.57 | 20.06 | False |
| 19 | 423100454-1 | 20" | 5836452846955445888 | 19.58 | 21.79 | False |
| 19 | 423100454-1 | 20" | 5836452846953341952 | 19.75 | 21.44 | False |
| 19 | 423100454-1 | 20" | 5836452743874123776 | 20.51 | 18.31 | False |
| 19 | 423100454-1 | 20" | 5836453499849301504 | 20.57 | 18.80 | False |
| 19 | 423100454-1 | 20" | 5836452743874914560 | 20.64 | 18.51 | False |
| 19 | 423100454-1 | 20" | 5836453499788426880 | 20.81 | 19.72 | False |
| 19 | 423100454-1 | 20" | 5836452743935235712 | 21.75 | 19.57 | False |
| 19 | 423100454-1 | 20" | 5836452743875348224 | 21.99 | 19.98 | False |
| 19 | 423100454-1 | 25" | 5836452846956469504 | 22.95 | 25.08 | False |
| 19 | 423100454-1 | 25" | 5836452846953382144 | 23.75 | 25.92 | False |
| 19 | 423100454-1 | 25" | 5836453598527876480 | 24.10 | 25.04 | True |
| 19 | 423100454-1 | 25" | 5836453602868781312 | 24.14 | 25.57 | False |
| 19 | 423100454-1 | 25" | 5836452847014269824 | 24.28 | 26.37 | True |
| 19 | 423100454-1 | 25" | 5836453602870675712 | 24.29 | 25.41 | False |
| 19 | 423100454-1 | 25" | 5836452846953423744 | 24.36 | 26.27 | False |
| 19 | 423100454-1 | 25" | 5836452847014263680 | 24.45 | 26.04 | False |
| 19 | 423100454-1 | 25" | 5836453499788432000 | 25.57 | 24.32 | False |
| 19 | 423100454-1 | 25" | 5836453499788417152 | 25.90 | 24.27 | False |
| 19 | 423100454-1 | 25" | 5836452743874101504 | 26.05 | 23.94 | False |
| 19 | 423100454-1 | 25" | 5836452743874088192 | 26.26 | 24.39 | False |
| 19 | 423100454-1 | 25" | 5836453499849304576 | 26.39 | 24.92 | True |
| 19 | 438857197-1 | 25" | 6083427107255911936 | 24.95 | 25.02 | True |
| 19 | 44926986-1 | 15" | 5431607610382753536 | 17.32 | 14.77 | False |
| 19 | 458290782-1 | 15" | 5971009774273598208 | 15.00 | 15.35 | False |
| 19 | 458290782-1 | 20" | 5971009808633262464 | 20.07 | 19.72 | False |
| 19 | 458290782-1 | 25" | 5971009602471510400 | 25.08 | 24.73 | False |
| 19 | 458290782-1 | 25" | 5971009804310482304 | 25.10 | 24.98 | False |
| controls | TOI-1175.01 | 20" | 2039904200523844352 | 20.09 | 19.87 | False |
| controls | TOI-1175.01 | 25" | 2039904204823524992 | 24.59 | 25.33 | False |
| controls | TOI-144.01 | 25" | 4623036899732204032 | 23.95 | 35.95 | False |
| controls | TOI-191.01 | 20" | 2312678363766427264 | 19.85 | 21.42 | False |
| controls | TOI-2011.02 | 15" | 5902750168280019712 | 4.24 | 22.14 | False |
| controls | TOI-2011.02 | 15" | 5902750202625303680 | 4.63 | 30.79 | False |
| controls | TOI-2011.02 | 15" | 5902750202625303808 | 5.75 | 31.63 | False |
| controls | TOI-2011.02 | 15" | 5902750202625304064 | 7.18 | 33.12 | False |
| controls | TOI-2011.02 | 15" | 5902750202625303552 | 8.08 | 29.03 | False |
| controls | TOI-2011.02 | 15" | 5902750202622988800 | 11.52 | 35.28 | False |
| controls | TOI-2011.02 | 15" | 5902750202625226368 | 12.31 | 38.67 | False |
| controls | TOI-2011.02 | 15" | 5902750168280018816 | 12.39 | 18.98 | False |
| controls | TOI-2011.02 | 15" | 5902750202625661952 | 12.87 | 35.86 | False |
| controls | TOI-2011.02 | 15" | 5902750168280022144 | 13.03 | 24.09 | False |
| controls | TOI-2011.02 | 15" | 5902750168280018688 | 13.55 | 18.45 | False |
| controls | TOI-2011.02 | 15" | 5902750168265333888 | 14.88 | 29.83 | False |
| controls | TOI-2011.02 | 15" | 5902750168280238976 | 16.21 | 13.00 | False |
| controls | TOI-2011.02 | 15" | 5902750168280238592 | 23.80 | 10.80 | False |
| controls | TOI-2011.02 | 15" | 5902750168280238720 | 25.29 | 14.64 | False |
| controls | TOI-2011.02 | 15" | 5902750236999497984 | 27.04 | 9.86 | False |
| controls | TOI-2011.02 | 15" | 5902750236999729408 | 32.09 | 10.08 | False |
| controls | TOI-2011.02 | 15" | 5902750236996397312 | 34.73 | 13.16 | False |
| controls | TOI-2011.02 | 20" | 5902750168280019712 | 4.24 | 22.14 | False |
| controls | TOI-2011.02 | 20" | 5902750202625303680 | 4.63 | 30.79 | False |
| controls | TOI-2011.02 | 20" | 5902750202625303808 | 5.75 | 31.63 | False |
| controls | TOI-2011.02 | 20" | 5902750202625304064 | 7.18 | 33.12 | False |
| controls | TOI-2011.02 | 20" | 5902750202625303552 | 8.08 | 29.03 | False |
| controls | TOI-2011.02 | 20" | 5902750202622988800 | 11.52 | 35.28 | False |
| controls | TOI-2011.02 | 20" | 5902750202625226368 | 12.31 | 38.67 | False |
| controls | TOI-2011.02 | 20" | 5902750202625661952 | 12.87 | 35.86 | False |
| controls | TOI-2011.02 | 20" | 5902750168280022144 | 13.03 | 24.09 | False |
| controls | TOI-2011.02 | 20" | 5902750168265333888 | 14.88 | 29.83 | False |
| controls | TOI-2011.02 | 20" | 5902750202619323648 | 15.24 | 35.97 | False |
| controls | TOI-2011.02 | 20" | 5902750202619292672 | 15.40 | 39.67 | True |
| controls | TOI-2011.02 | 20" | 5902750202639760640 | 15.86 | 27.36 | False |
| controls | TOI-2011.02 | 20" | 5902750168276934656 | 17.92 | 20.46 | False |
| controls | TOI-2011.02 | 20" | 5902750202624651136 | 19.00 | 44.81 | False |
| controls | TOI-2011.02 | 20" | 5902750163957965312 | 19.01 | 25.55 | False |
| controls | TOI-2011.02 | 20" | 5902750168280238592 | 23.80 | 10.80 | False |
| controls | TOI-2011.02 | 20" | 5902750168280238720 | 25.29 | 14.64 | False |
| controls | TOI-2011.02 | 20" | 5902750236999497984 | 27.04 | 9.86 | False |
| controls | TOI-2011.02 | 20" | 5902750168265909248 | 29.01 | 16.71 | False |
| controls | TOI-2011.02 | 20" | 5902750236982278912 | 29.89 | 18.80 | False |
| controls | TOI-2011.02 | 20" | 5902750236999729408 | 32.09 | 10.08 | False |
| controls | TOI-2011.02 | 20" | 5902750168276964608 | 33.36 | 16.26 | False |
| controls | TOI-2011.02 | 20" | 5902750236996397312 | 34.73 | 13.16 | False |
| controls | TOI-2011.02 | 20" | 5902750236996068608 | 41.71 | 16.26 | False |
| controls | TOI-2011.02 | 20" | 5902750236996438912 | 44.29 | 17.93 | False |
| controls | TOI-2011.02 | 25" | 5902750202625303680 | 4.63 | 30.79 | False |
| controls | TOI-2011.02 | 25" | 5902750202625303808 | 5.75 | 31.63 | False |
| controls | TOI-2011.02 | 25" | 5902750202625304064 | 7.18 | 33.12 | False |
| controls | TOI-2011.02 | 25" | 5902750202625303552 | 8.08 | 29.03 | False |
| controls | TOI-2011.02 | 25" | 5902750202622988800 | 11.52 | 35.28 | False |
| controls | TOI-2011.02 | 25" | 5902750202625226368 | 12.31 | 38.67 | False |
| controls | TOI-2011.02 | 25" | 5902750202625661952 | 12.87 | 35.86 | False |
| controls | TOI-2011.02 | 25" | 5902750168265333888 | 14.88 | 29.83 | False |
| controls | TOI-2011.02 | 25" | 5902750202619323648 | 15.24 | 35.97 | False |
| controls | TOI-2011.02 | 25" | 5902750202619292672 | 15.40 | 39.67 | True |
| controls | TOI-2011.02 | 25" | 5902750202639760640 | 15.86 | 27.36 | False |
| controls | TOI-2011.02 | 25" | 5902750202624651136 | 19.00 | 44.81 | False |
| controls | TOI-2011.02 | 25" | 5902750163957965312 | 19.01 | 25.55 | False |
| controls | TOI-2011.02 | 25" | 5902750168259543168 | 21.26 | 40.25 | False |
| controls | TOI-2011.02 | 25" | 5902750168276894848 | 21.43 | 31.33 | False |
| controls | TOI-2011.02 | 25" | 5902750168259542528 | 21.45 | 38.93 | False |
| controls | TOI-2011.02 | 25" | 5902750202625646976 | 21.52 | 33.48 | False |
| controls | TOI-2011.02 | 25" | 5902750168259541248 | 22.50 | 38.19 | False |
| controls | TOI-2011.02 | 25" | 5902750202624653056 | 22.58 | 48.93 | False |
| controls | TOI-2011.02 | 25" | 5902750202619326720 | 22.83 | 43.75 | False |
| controls | TOI-2011.02 | 25" | 5902750168259541120 | 23.93 | 43.35 | False |
| controls | TOI-2011.02 | 25" | 5902750163955467648 | 24.07 | 26.86 | False |
| controls | TOI-2011.02 | 25" | 5902750168280238720 | 25.29 | 14.64 | False |
| controls | TOI-2011.02 | 25" | 5902750236999497984 | 27.04 | 9.86 | False |
| controls | TOI-2011.02 | 25" | 5902750236982279168 | 28.61 | 21.34 | False |
| controls | TOI-2011.02 | 25" | 5902750168265909248 | 29.01 | 16.71 | False |
| controls | TOI-2011.02 | 25" | 5902750236982278912 | 29.89 | 18.80 | False |
| controls | TOI-2011.02 | 25" | 5902750168265333760 | 30.39 | 22.49 | False |
| controls | TOI-2011.02 | 25" | 5902750236999729408 | 32.09 | 10.08 | False |
| controls | TOI-2011.02 | 25" | 5902750168276964608 | 33.36 | 16.26 | False |
| controls | TOI-2011.02 | 25" | 5902750236996397312 | 34.73 | 13.16 | False |
| controls | TOI-2011.02 | 25" | 5902750232673990912 | 38.35 | 24.93 | False |
| controls | TOI-2011.02 | 25" | 5902750168265903360 | 40.96 | 23.48 | False |
| controls | TOI-2011.02 | 25" | 5902750236996068608 | 41.71 | 16.26 | False |
| controls | TOI-2011.02 | 25" | 5902750168263245312 | 43.43 | 21.35 | False |
| controls | TOI-2011.02 | 25" | 5902750236996438912 | 44.29 | 17.93 | False |
| controls | TOI-2011.02 | 25" | 5902750236984961920 | 44.55 | 22.81 | False |
| controls | TOI-2011.02 | 25" | 5902750236984809984 | 47.93 | 21.71 | False |
| controls | TOI-4307.01 | 25" | 4648266774578578560 | 25.04 | 24.77 | False |
| controls | TOI-576.01 | 15" | 5664957448475434752 | 14.49 | 15.32 | False |
| controls | TOI-755.01 | 20" | 6133385032957541760 | 19.91 | 20.14 | False |
| controls | TOI-763.02 | 15" | 6140553195935876096 | 15.54 | 14.08 | False |

## Appendix B: every cone change

| table | signal | change | Gaia DR3 id | table sep (") | corrected (") | G | required depth | possible |
|---|---|---|---|---|---|---|---|---|
| 19 | 103312990-1 | added | 5365550055598557056 | 60.70 | 59.83 | 17.10 | 0.215 | True |
| 19 | 173369850-1 | added | 5915857343290158976 | 60.13 | 59.96 | 21.19 | 11.905 | False |
| 19 | 296819076-1 | added | 5877911719540705408 | 60.05 | 59.73 | 18.89 | 0.347 | True |
| 19 | 296819076-1 | added | 5877911719540657024 | 60.69 | 59.94 | 19.14 | 0.526 | True |
| 19 | 296819076-1 | dropped | 5877911753903746944 | 59.96 | 60.04 | 20.95 | 3.198 | False |
| 19 | 296819076-1 | dropped | 5877910929266500992 | 59.96 | 60.22 | 19.01 | 0.389 | True |
| 19 | 296819076-1 | dropped | 5877911749605067264 | 60.00 | 60.31 | 19.00 | 0.409 | True |
| 19 | 296819076-1 | dropped | 5877910860547037056 | 59.94 | 60.40 | 20.68 | 1.813 | False |
| 19 | 296819076-1 | dropped | 5877911788260146176 | 59.60 | 60.44 | 19.93 | 1.069 | False |
| 19 | 296819076-1 | dropped | 5877910924970222464 | 59.91 | 60.53 | 18.84 | 0.436 | True |
| 19 | 296819076-1 | dropped | 5877911032347335680 | 59.97 | 60.92 | 20.43 | 1.830 | False |
| 19 | 322826591-1 | added | 5332801204869766784 | 60.41 | 58.91 | 18.77 | 1.651 | False |
| 19 | 322826591-1 | added | 5332801239229523200 | 61.02 | 59.30 | 18.13 | 1.045 | False |
| 19 | 322826591-1 | added | 5332801204871884032 | 60.76 | 59.35 | 19.17 | 1.797 | False |
| 19 | 322826591-1 | added | 5332801548457706368 | 60.93 | 59.87 | 18.88 | 2.013 | False |
| 19 | 322826591-1 | dropped | 5332800929984038528 | 58.73 | 60.28 | 21.17 | 11.581 | False |
| 19 | 322826591-1 | dropped | 5332800925670174720 | 59.17 | 60.74 | 20.37 | 5.687 | False |
| 19 | 322826591-1 | dropped | 5332801342299205376 | 59.51 | 61.13 | 19.97 | 5.001 | False |
| 19 | 322826591-1 | dropped | 5332800964345018496 | 59.98 | 61.66 | 21.13 | 21.086 | False |
| 19 | 337885456-1 | added | 6726411474120367872 | 60.03 | 59.31 | 19.79 | 4.296 | False |
| 19 | 337885456-1 | added | 6726411508482582400 | 60.26 | 59.54 | 20.70 | 10.477 | False |
| 19 | 337885456-1 | added | 6726411508507389568 | 60.14 | 59.60 | 18.45 | 1.082 | False |
| 19 | 337885456-1 | added | 6726411474122876672 | 60.27 | 59.62 | 20.53 | 6.609 | False |
| 19 | 337885456-1 | added | 6726411474122897920 | 60.23 | 59.76 | 20.99 | 16.607 | False |
| 19 | 337885456-1 | dropped | 6726411817717794176 | 60.00 | 60.65 | 19.93 | 5.634 | False |
| 19 | 370977908-1 | dropped | 5900598080399246464 | 59.95 | 60.00 | 20.81 | 8.036 | False |
| 19 | 399023421-1 | dropped | 6080509518778854016 | 59.89 | 60.21 | 20.70 | 1.852 | False |
| 19 | 410399327-1 | added | 6434209107919208064 | 60.20 | 59.89 | 18.43 | 0.559 | True |
| 19 | 423100454-1 | added | 5836453465429871872 | 60.06 | 57.85 | 21.02 | 13.446 | False |
| 19 | 423100454-1 | added | 5836453465429416064 | 60.28 | 58.12 | 20.26 | 8.486 | False |
| 19 | 423100454-1 | added | 5836452739533401088 | 60.11 | 58.84 | 17.73 | 0.940 | True |
| 19 | 423100454-1 | added | 5836452743944242560 | 60.56 | 58.86 | 19.56 | 3.491 | False |
| 19 | 423100454-1 | added | 5836452709514253440 | 60.89 | 58.90 | 20.58 | 8.898 | False |
| 19 | 423100454-1 | added | 5836453465428717312 | 60.52 | 58.93 | 20.09 | 7.076 | False |
| 19 | 423100454-1 | added | 5836453465429857024 | 61.06 | 59.14 | 20.97 | 12.757 | False |
| 19 | 423100454-1 | added | 5836453465429678080 | 60.90 | 59.18 | 20.97 | 12.736 | False |
| 19 | 423100454-1 | added | 5836453465489724800 | 61.08 | 59.41 | 20.12 | 6.858 | False |
| 19 | 423100454-1 | added | 5836453499790480640 | 60.90 | 59.42 | 20.68 | 9.755 | False |
| 19 | 423100454-1 | added | 5836453465429415936 | 61.60 | 59.45 | 20.32 | 7.014 | False |
| 19 | 423100454-1 | added | 5836453461109681024 | 61.39 | 59.52 | 18.68 | 2.206 | False |
| 19 | 423100454-1 | added | 5836453465429677568 | 61.50 | 59.80 | 20.71 | 10.097 | False |
| 19 | 423100454-1 | added | 5836452709575284992 | 61.95 | 59.99 | 18.50 | 1.791 | False |
| 19 | 423100454-1 | dropped | 5836452778235977216 | 59.48 | 60.04 | 21.00 | 13.105 | False |
| 19 | 423100454-1 | dropped | 5836452778233699456 | 60.00 | 60.04 | 17.60 | 0.871 | True |
| 19 | 423100454-1 | dropped | 5836452778236333440 | 58.87 | 60.05 | 20.38 | 7.417 | False |
| 19 | 423100454-1 | dropped | 5836452881313155072 | 57.89 | 60.09 | 19.20 | 3.320 | False |
| 19 | 423100454-1 | dropped | 5836453598524522240 | 58.57 | 60.11 | 16.91 | 0.467 | True |
| 19 | 423100454-1 | dropped | 5836452808248808320 | 58.88 | 60.26 | 12.70 | 0.013 | True |
| 19 | 423100454-1 | dropped | 5836452778234640640 | 59.27 | 60.39 | 19.63 | 3.720 | False |
| 19 | 423100454-1 | dropped | 5836452881313191168 | 58.69 | 60.84 | 20.15 | 5.999 | False |
| 19 | 423100454-1 | dropped | 5836452876994129920 | 58.72 | 60.93 | 18.86 | 2.204 | False |
| 19 | 423100454-1 | dropped | 5836452881313116416 | 58.88 | 60.98 | 19.94 | 6.927 | False |
| 19 | 423100454-1 | dropped | 5836453602868766464 | 59.93 | 61.06 | 20.89 | 18.271 | False |
| 19 | 423100454-1 | dropped | 5836452881313100416 | 59.04 | 61.08 | 19.34 | 3.860 | False |
| 19 | 423100454-1 | dropped | 5836452881313136128 | 59.01 | 61.18 | 20.08 | 7.169 | False |
| 19 | 423100454-1 | dropped | 5836452876994130432 | 59.37 | 61.57 | 19.71 | 4.013 | False |
| 19 | 423100454-1 | dropped | 5836452881313190784 | 59.52 | 61.67 | 17.19 | 0.604 | True |
| 19 | 423100454-1 | dropped | 5836452881315177856 | 59.60 | 61.71 | 20.94 | 12.384 | False |
| 19 | 423100454-1 | dropped | 5836453637227475840 | 59.84 | 61.72 | 19.67 | 4.770 | False |
| 19 | 423100454-1 | dropped | 5836452881313874176 | 59.66 | 61.85 | 20.18 | 8.476 | False |
| 19 | 423100454-1 | dropped | 5836452881316131200 | 59.78 | 61.96 | 21.12 | 14.725 | False |
| 19 | 44926986-1 | dropped | 5431607644742487424 | 59.04 | 61.50 | 17.65 | 0.860 | True |
| 19 | 458290782-1 | added | 5971009602474720768 | 60.06 | 59.68 | none | none | False |
| 19 | 458290782-1 | added | 5971009602504628608 | 60.20 | 59.84 | 17.00 | 0.258 | True |
| 19 | 458290782-1 | added | 5971009602468249856 | 60.36 | 59.99 | 19.61 | 2.699 | False |
| controls | TOI-1052.01 | added | 6357524395289818624 | 60.26 | 59.50 | 20.35 | 7.955 | False |
| controls | TOI-1052.01 | added | 6357523772517808128 | 60.14 | 59.63 | 19.83 | 4.579 | False |
| controls | TOI-1058.01 | dropped | 6757952747585514624 | 59.85 | 60.09 | 19.07 | 3.588 | False |
| controls | TOI-1097.02 | added | 5838450758317206144 | 60.16 | 59.49 | 19.00 | 4.589 | False |
| controls | TOI-1097.02 | added | 5838450762620761088 | 60.50 | 59.71 | 20.98 | 43.125 | False |
| controls | TOI-1097.02 | added | 5838439011589913344 | 60.29 | 59.99 | 17.85 | 1.569 | False |
| controls | TOI-1097.02 | dropped | 5838439041647387008 | 59.66 | 60.14 | 18.41 | 2.484 | False |
| controls | TOI-1097.02 | dropped | 5838450900054953344 | 59.74 | 60.38 | 20.85 | 21.633 | False |
| controls | TOI-1097.02 | dropped | 5838439149023182464 | 59.77 | 60.52 | 18.44 | 3.025 | False |
| controls | TOI-1175.01 | added | 2039904136102398848 | 60.48 | 59.90 | 20.43 | 13.665 | False |
| controls | TOI-1175.01 | dropped | 2039904234883665024 | 59.48 | 60.05 | 20.42 | 10.629 | False |
| controls | TOI-1175.01 | dropped | 2039904410980402432 | 59.81 | 60.23 | 20.31 | 8.777 | False |
| controls | TOI-1175.01 | dropped | 2039904406682381312 | 59.90 | 60.42 | 19.23 | 4.114 | False |
| controls | TOI-1399.01 | added | 1988764441541889664 | 60.12 | 59.92 | 18.64 | 2.057 | False |
| controls | TOI-144.01 | added | 4623036964157027072 | 75.31 | 59.38 | 18.26 | 42.530 | False |
| controls | TOI-144.01 | dropped | 4623036831012291072 | 51.73 | 64.34 | 17.97 | 21.439 | False |
| controls | TOI-2011.02 | added | 5902744357158641536 | 60.01 | 34.09 | 18.58 | 76.086 | False |
| controls | TOI-2011.02 | added | 5902744361463793024 | 61.88 | 36.18 | 19.19 | 135.598 | False |
| controls | TOI-2011.02 | added | 5902744361469702016 | 62.59 | 36.62 | 20.85 | 382.423 | False |
| controls | TOI-2011.02 | added | 5902744361463780352 | 60.49 | 36.66 | 17.04 | 20.985 | False |
| controls | TOI-2011.02 | added | 5902744361467824768 | 63.64 | 37.29 | 20.49 | 640.486 | False |
| controls | TOI-2011.02 | added | 5902744361480496640 | 65.40 | 39.05 | 17.77 | 38.078 | False |
| controls | TOI-2011.02 | added | 5902744361463814144 | 65.49 | 39.40 | 19.67 | 174.530 | False |
| controls | TOI-2011.02 | added | 5902750236983090304 | 61.23 | 40.28 | 20.23 | 347.595 | False |
| controls | TOI-2011.02 | added | 5902744292749686528 | 61.69 | 41.19 | 20.54 | 443.784 | False |
| controls | TOI-2011.02 | added | 5902744357159219712 | 66.93 | 41.22 | 18.93 | 109.205 | False |
| controls | TOI-2011.02 | added | 5902750236984396672 | 64.33 | 42.80 | 20.66 | 787.782 | False |
| controls | TOI-2011.02 | added | 5902744361469827456 | 70.50 | 44.49 | 20.99 | 788.996 | False |
| controls | TOI-2011.02 | added | 5902744357159223040 | 70.30 | 44.86 | 19.05 | 127.579 | False |
| controls | TOI-2011.02 | added | 5902744361469906176 | 67.70 | 45.61 | 20.97 | 425.536 | False |
| controls | TOI-2011.02 | added | 5902750236979103744 | 67.22 | 45.66 | 20.87 | 388.026 | False |
| controls | TOI-2011.02 | added | 5902750236979103872 | 67.47 | 46.26 | 19.98 | 268.412 | False |
| controls | TOI-2011.02 | added | 5902744292744273152 | 63.52 | 46.60 | 20.03 | 262.461 | False |
| controls | TOI-2011.02 | added | 5902750236984391680 | 66.13 | 47.20 | 20.64 | 404.172 | False |
| controls | TOI-2011.02 | added | 5902744357158641664 | 73.65 | 47.35 | 18.20 | 47.987 | False |
| controls | TOI-2011.02 | added | 5902744361480686848 | 71.07 | 47.51 | 20.03 | 235.041 | False |
| controls | TOI-2011.02 | added | 5902744361467821696 | 69.72 | 47.93 | 20.13 | 240.180 | False |
| controls | TOI-2011.02 | added | 5902744288439238144 | 60.11 | 49.50 | 20.71 | 426.427 | False |
| controls | TOI-2011.02 | added | 5902744361463827328 | 74.71 | 49.63 | 19.38 | 126.748 | False |
| controls | TOI-2011.02 | added | 5902744361463821824 | 75.52 | 49.70 | 18.89 | 106.514 | False |
| controls | TOI-2011.02 | added | 5902750236984721280 | 63.14 | 50.45 | 20.83 | 499.239 | False |
| controls | TOI-2011.02 | added | 5902744361469160192 | 77.08 | 51.15 | 20.79 | 702.838 | False |
| controls | TOI-2011.02 | added | 5902744361484235136 | 76.37 | 51.36 | 19.92 | 295.337 | False |
| controls | TOI-2011.02 | added | 5902744361469462656 | 78.41 | 52.25 | 20.87 | 625.575 | False |
| controls | TOI-2011.02 | added | 5902744292744257408 | 64.95 | 53.05 | 18.29 | 64.181 | False |
| controls | TOI-2011.02 | added | 5902744361480499584 | 79.96 | 53.84 | 17.39 | 27.005 | False |
| controls | TOI-2011.02 | added | 5902744361463764096 | 76.67 | 54.03 | 19.86 | 270.895 | False |
| controls | TOI-2011.02 | added | 5902744292764755584 | 72.28 | 54.67 | 19.58 | 183.682 | False |
| controls | TOI-2011.02 | added | 5902744357158640128 | 78.88 | 54.90 | 18.01 | 42.664 | False |
| controls | TOI-2011.02 | added | 5902750443137541376 | 77.50 | 55.31 | 18.53 | 72.978 | False |
| controls | TOI-2011.02 | added | 5902750236984377856 | 62.42 | 55.32 | 20.58 | 484.720 | False |
| controls | TOI-2011.02 | added | 5902750232676900608 | 67.00 | 55.35 | 18.66 | 85.745 | False |
| controls | TOI-2011.02 | added | 5902744288439237888 | 60.42 | 55.40 | 18.31 | 53.876 | False |
| controls | TOI-2011.02 | added | 5902744361480494848 | 81.49 | 55.44 | 14.47 | 2.043 | False |
| controls | TOI-2011.02 | added | 5902750236983093888 | 70.60 | 55.44 | 20.20 | 281.851 | False |
| controls | TOI-2011.02 | added | 5902744567628129536 | 79.80 | 55.62 | 20.74 | 660.336 | False |
| controls | TOI-2011.02 | added | 5902744288441047168 | 66.29 | 55.66 | 17.65 | 32.090 | False |
| controls | TOI-2011.02 | added | 5902744563327140224 | 81.26 | 56.28 | 19.14 | 124.483 | False |
| controls | TOI-2011.02 | added | 5902744292760999424 | 62.04 | 56.47 | 18.66 | 83.531 | False |
| controls | TOI-2011.02 | added | 5902750168262789120 | 61.26 | 57.50 | 19.92 | 261.033 | False |
| controls | TOI-2011.02 | added | 5902744292750227200 | 76.08 | 57.50 | 20.76 | 561.357 | False |
| controls | TOI-2011.02 | added | 5902750443154500352 | 79.94 | 57.75 | 17.93 | 46.288 | False |
| controls | TOI-2011.02 | added | 5902744292744253056 | 71.07 | 57.84 | 18.53 | 78.181 | False |
| controls | TOI-2011.02 | added | 5902744567627568256 | 80.69 | 57.88 | 20.81 | 1066.651 | False |
| controls | TOI-2011.02 | added | 5902744357158640512 | 82.72 | 57.98 | 18.48 | 65.930 | False |
| controls | TOI-2011.02 | added | 5902744563320610944 | 83.55 | 58.25 | 17.97 | 43.303 | False |
| controls | TOI-2011.02 | added | 5902744567628334080 | 83.49 | 59.01 | 21.04 | 1324.555 | False |
| controls | TOI-2011.02 | dropped | 5902703232871898752 | 52.69 | 60.43 | 21.02 | 445.268 | False |
| controls | TOI-2011.02 | dropped | 5902703232847993088 | 44.53 | 60.54 | 20.65 | 597.169 | False |
| controls | TOI-2011.02 | dropped | 5902703232871742976 | 54.58 | 61.04 | 14.84 | 2.915 | False |
| controls | TOI-2011.02 | dropped | 5902750198317704576 | 36.86 | 61.64 | 17.98 | 37.917 | False |
| controls | TOI-2011.02 | dropped | 5902703267207958272 | 37.93 | 62.22 | 20.43 | 409.570 | False |
| controls | TOI-2011.02 | dropped | 5902703267207171712 | 39.50 | 62.46 | 20.24 | 318.715 | False |
| controls | TOI-2011.02 | dropped | 5902703232848229248 | 53.61 | 62.48 | 21.04 | 657.576 | False |
| controls | TOI-2011.02 | dropped | 5902750271355808384 | 52.47 | 63.25 | 17.48 | 29.377 | False |
| controls | TOI-2011.02 | dropped | 5902750202622534272 | 36.92 | 63.28 | 20.01 | 232.600 | False |
| controls | TOI-2011.02 | dropped | 5902750202624643712 | 37.79 | 63.50 | 20.72 | 338.883 | False |
| controls | TOI-2011.02 | dropped | 5902750271342474368 | 57.41 | 63.72 | 20.36 | 365.568 | False |
| controls | TOI-2011.02 | dropped | 5902750202623357440 | 47.82 | 63.91 | 20.46 | 477.485 | False |
| controls | TOI-2011.02 | dropped | 5902750202602729344 | 38.22 | 64.51 | 19.98 | 303.816 | False |
| controls | TOI-2011.02 | dropped | 5902750202636330368 | 39.25 | 64.69 | 17.74 | 38.334 | False |
| controls | TOI-2011.02 | dropped | 5902750271344547712 | 56.96 | 64.73 | 20.85 | 530.347 | False |
| controls | TOI-2011.02 | dropped | 5902750202619320960 | 40.21 | 64.73 | 19.98 | 303.868 | False |
| controls | TOI-2011.02 | dropped | 5902703232847416704 | 49.67 | 65.43 | 18.57 | 81.011 | False |
| controls | TOI-2011.02 | dropped | 5902750202622993920 | 45.18 | 67.42 | 20.19 | 407.407 | False |
| controls | TOI-2011.02 | dropped | 5902750202619350656 | 50.73 | 67.69 | 20.13 | 196.739 | False |
| controls | TOI-2011.02 | dropped | 5902750202619350784 | 50.57 | 67.88 | 19.80 | 217.664 | False |
| controls | TOI-2011.02 | dropped | 5902750202619327488 | 44.83 | 68.26 | 19.04 | 120.204 | False |
| controls | TOI-2011.02 | dropped | 5902703267207193216 | 42.65 | 68.99 | 18.91 | 117.607 | False |
| controls | TOI-2011.02 | dropped | 5902750202624629760 | 52.51 | 69.21 | 20.70 | 331.410 | False |
| controls | TOI-2011.02 | dropped | 5902703232848226944 | 53.38 | 69.23 | 20.42 | 454.266 | False |
| controls | TOI-2011.02 | dropped | 5902703232847410048 | 55.64 | 70.02 | 18.83 | 98.694 | False |
| controls | TOI-2011.02 | dropped | 5902750202619312256 | 46.22 | 71.71 | 19.58 | 215.921 | False |
| controls | TOI-2011.02 | dropped | 5902750202636330752 | 47.29 | 71.81 | 17.30 | 23.032 | False |
| controls | TOI-2011.02 | dropped | 5902750202619340928 | 51.36 | 72.25 | 19.51 | 178.243 | False |
| controls | TOI-2011.02 | dropped | 5902703267231481856 | 54.43 | 72.29 | 16.69 | 14.487 | False |
| controls | TOI-2011.02 | dropped | 5902703267207158784 | 51.59 | 72.67 | 18.97 | 67.233 | False |
| controls | TOI-2011.02 | dropped | 5902750202619368192 | 58.99 | 72.71 | 19.78 | 259.804 | False |
| controls | TOI-2011.02 | dropped | 5902703267207193088 | 46.91 | 73.25 | 18.40 | 69.970 | False |
| controls | TOI-2011.02 | dropped | 5902703267207181952 | 47.27 | 73.28 | 17.63 | 33.555 | False |
| controls | TOI-2011.02 | dropped | 5902750202619303808 | 47.26 | 73.43 | 19.60 | 174.132 | False |
| controls | TOI-2011.02 | dropped | 5902703267231489920 | 47.73 | 73.69 | 19.38 | 98.086 | False |
| controls | TOI-2011.02 | dropped | 5902703267207958528 | 49.87 | 73.77 | 20.73 | 455.013 | False |
| controls | TOI-2011.02 | dropped | 5902750202623355392 | 48.77 | 73.95 | 20.61 | 477.235 | False |
| controls | TOI-2011.02 | dropped | 5902703267207158272 | 53.07 | 74.41 | 18.00 | 45.435 | False |
| controls | TOI-2011.02 | dropped | 5902750202623359104 | 59.55 | 74.47 | 20.33 | 319.339 | False |
| controls | TOI-2011.02 | dropped | 5902703267207182208 | 49.21 | 75.21 | 19.86 | 153.866 | False |
| controls | TOI-2011.02 | dropped | 5902703267207181824 | 49.28 | 75.36 | 19.70 | 131.985 | False |
| controls | TOI-2011.02 | dropped | 5902703267231490944 | 49.18 | 75.43 | 18.89 | 104.261 | False |
| controls | TOI-2011.02 | dropped | 5902750305703852544 | 50.45 | 75.47 | 20.37 | 414.292 | False |
| controls | TOI-2011.02 | dropped | 5902703267208119680 | 50.37 | 75.48 | 20.96 | 602.767 | False |
| controls | TOI-2011.02 | dropped | 5902750202624640896 | 49.96 | 75.94 | 20.75 | 604.349 | False |
| controls | TOI-2011.02 | dropped | 5902750305703844480 | 55.76 | 76.62 | 20.32 | 362.644 | False |
| controls | TOI-2011.02 | dropped | 5902703267208437760 | 53.34 | 77.28 | 20.92 | 772.170 | False |
| controls | TOI-2011.02 | dropped | 5902703267208116992 | 52.27 | 78.24 | 20.92 | 483.538 | False |
| controls | TOI-2011.02 | dropped | 5902703370286411776 | 53.26 | 79.44 | 20.16 | 322.175 | False |
| controls | TOI-2011.02 | dropped | 5902703267207187840 | 53.45 | 79.79 | 19.15 | 137.925 | False |
| controls | TOI-2011.02 | dropped | 5902750305703844096 | 58.08 | 79.89 | 20.66 | 589.167 | False |
| controls | TOI-2011.02 | dropped | 5902750305715545600 | 55.02 | 80.49 | 17.59 | 33.097 | False |
| controls | TOI-2011.02 | dropped | 5902703267207959552 | 57.96 | 80.71 | 20.84 | 707.195 | False |
| controls | TOI-2011.02 | dropped | 5902703370310709632 | 54.51 | 80.74 | 20.12 | 317.845 | False |
| controls | TOI-2011.02 | dropped | 5902703370286415872 | 54.94 | 80.84 | 18.13 | 52.502 | False |
| controls | TOI-2011.02 | dropped | 5902750305701754496 | 57.05 | 80.86 | 19.69 | 234.974 | False |
| controls | TOI-2011.02 | dropped | 5902703267207162752 | 57.75 | 81.58 | 19.58 | 181.777 | False |
| controls | TOI-2011.02 | dropped | 5902750305698554496 | 59.72 | 81.92 | 19.11 | 126.407 | False |
| controls | TOI-2011.02 | dropped | 5902750305703847168 | 57.61 | 81.98 | 20.82 | 718.962 | False |
| controls | TOI-2011.02 | dropped | 5902703267207175808 | 56.34 | 82.06 | 20.06 | 306.005 | False |
| controls | TOI-396.01 | dropped | 5064574621685240192 | 58.50 | 60.73 | 20.03 | 52.769 | False |
| controls | TOI-396.03 | dropped | 5064574621685240192 | 58.50 | 60.73 | 20.03 | 48.106 | False |
| controls | TOI-4307.01 | added | 4648265292816711936 | 61.59 | 56.62 | 18.81 | 4.800 | False |
| controls | TOI-4307.01 | added | 4648263819642768128 | 60.87 | 58.67 | 20.94 | 50.478 | False |
| controls | TOI-4307.01 | dropped | 4648266808942941312 | 57.12 | 61.17 | 20.97 | 35.078 | False |
| controls | TOI-4307.01 | dropped | 4648266907731167616 | 56.55 | 61.68 | 19.18 | 6.468 | False |
| controls | TOI-4307.01 | dropped | 4648266907723424128 | 57.78 | 62.98 | 18.31 | 2.858 | False |
| controls | TOI-4307.01 | dropped | 4648263957080576384 | 59.63 | 63.56 | 20.16 | 11.261 | False |
| controls | TOI-4307.01 | dropped | 4648266912018752256 | 58.58 | 63.73 | 20.82 | 34.310 | False |
| controls | TOI-652.01 | added | 5660491988156749568 | 61.42 | 58.98 | 20.03 | 21.037 | False |
| controls | TOI-652.01 | dropped | 5660492086942048384 | 58.50 | 61.41 | 15.58 | 0.493 | True |
| controls | TOI-755.01 | added | 6133384204027888128 | 60.00 | 59.88 | 11.94 | 0.003 | True |
| controls | TOI-763.02 | added | 6140365454324822144 | 60.48 | 59.71 | 20.78 | 13.880 | False |

## Appendix C: draft rows moved by more than 0.5"

| draft | Gaia DR3 id | quoted (") | corrected (") | shift (") |
|---|---|---|---|---|
| 103312990-1 | 5365550188738551040 | 8.2 | 9.4 | +1.18 |
| 103312990-1 | 5365550193037516288 | 14.5 | 15.4 | +0.89 |
| 103312990-1 | 5365553109321276160 | 19.3 | 18.6 | -0.67 |
| 103312990-1 | 5365550158677773568 | 35.7 | 34.6 | -1.04 |
| 103312990-1 | 5365550158677773312 | 36.4 | 35.2 | -1.19 |
| 103312990-1 | 5365550193037517312 | 37.1 | 38.1 | +1.04 |
| 103312990-1 | 5365553113615274752 | 39.6 | 39.0 | -0.59 |
| 103312990-1 | 5365550193037518720 | 49.2 | 50.3 | +1.10 |
| 103312990-1 | 5365550124318040960 | 50.1 | 51.0 | +0.90 |
| 103312990-1 | 5365553109313739776 | 50.2 | 49.7 | -0.50 |
| 103312990-1 | 5365553006234492288 | 53.7 | 52.5 | -1.18 |
| 103312990-1 | 5365550497973622784 | 54.3 | 55.3 | +0.96 |
| 103312990-1 | 5365550566693107584 | 56.5 | 57.6 | +1.12 |
| 146282666-1 | 4967249906843757568 | 5.5 | 6.0 | +0.54 |
| 146282666-1 | 4967249872486553600 | 34.3 | 32.5 | -1.79 |
| 146282666-1 | 4967249872484022400 | 35.0 | 33.2 | -1.79 |
| 296819076-1 | 5877911650854905600 | 8.8 | 8.0 | -0.86 |
| 296819076-1 | 5877911685180870272 | 11.9 | 12.7 | +0.81 |
| 296819076-1 | 5877911650821093120 | 12.2 | 11.7 | -0.54 |
| 296819076-1 | 5877911646527548800 | 14.3 | 13.5 | -0.74 |
| 296819076-1 | 5877910929300396928 | 14.4 | 15.2 | +0.83 |
| 296819076-1 | 5877910929300393728 | 14.8 | 15.4 | +0.53 |
| 296819076-1 | 5877911650821097216 | 15.2 | 14.4 | -0.84 |
| 296819076-1 | 5877910929266587008 | 15.3 | 15.9 | +0.56 |
| 296819076-1 | 5877911685214648320 | 15.4 | 16.0 | +0.66 |
| 296819076-1 | 5877910929266592896 | 18.5 | 19.3 | +0.79 |
| 296819076-1 | 5877910929266589312 | 19.2 | 20.0 | +0.74 |
| 296819076-1 | 5877911650854902272 | 19.7 | 18.7 | -0.94 |
| 296819076-1 | 5877911650821133824 | 21.1 | 20.3 | -0.79 |
| 296819076-1 | 5877910929266582272 | 21.4 | 22.1 | +0.65 |
| 296819076-1 | 5877910894906830208 | 22.1 | 21.5 | -0.58 |
| 296819076-1 | 5877911650854902400 | 22.4 | 21.4 | -0.95 |
| 296819076-1 | 5877911650854908160 | 22.8 | 22.1 | -0.69 |
| 296819076-1 | 5877911685180895744 | 22.8 | 23.4 | +0.60 |
| 296819076-1 | 5877910924970227456 | 23.0 | 23.9 | +0.91 |
| 296819076-1 | 5877911650821133696 | 23.2 | 22.6 | -0.62 |
| 296819076-1 | 5877911650821138560 | 23.7 | 23.0 | -0.76 |
| 296819076-1 | 5877911685214652032 | 23.8 | 24.5 | +0.63 |
| 296819076-1 | 5877911646525818240 | 25.9 | 25.0 | -0.88 |
| 296819076-1 | 5877910929266623104 | 27.1 | 28.1 | +0.94 |
| 296819076-1 | 5877911650821080960 | 27.3 | 26.4 | -0.85 |
| 296819076-1 | 5877911650860731264 | 27.3 | 26.6 | -0.67 |
| 296819076-1 | 5877911650821146496 | 27.7 | 27.0 | -0.69 |
| 296819076-1 | 5877911650821109760 | 27.9 | 26.9 | -0.94 |
| 296819076-1 | 5877910894906817408 | 27.9 | 27.3 | -0.55 |
| 296819076-1 | 5877911646527546752 | 28.3 | 27.4 | -0.94 |
| 296819076-1 | 5877911685180907008 | 28.7 | 29.3 | +0.60 |
| 296819076-1 | 5877910929300400384 | 28.9 | 29.8 | +0.95 |
| 296819076-1 | 5877911650821112320 | 29.3 | 28.4 | -0.94 |
| 296819076-1 | 5877911650854904320 | 29.4 | 28.4 | -0.94 |
| 296819076-1 | 5877910929300397184 | 30.2 | 31.1 | +0.90 |
| 296819076-1 | 5877911646524736384 | 30.8 | 30.2 | -0.60 |
| 296819076-1 | 5877910929300401408 | 31.3 | 32.3 | +0.95 |
| 296819076-1 | 5877910924973046528 | 32.3 | 33.1 | +0.82 |
| 296819076-1 | 5877910894940647808 | 32.6 | 32.0 | -0.59 |
| 296819076-1 | 5877911650821074560 | 33.4 | 32.5 | -0.85 |
| 296819076-1 | 5877910929266560896 | 34.1 | 34.7 | +0.61 |
| 296819076-1 | 5877910929266573568 | 34.4 | 35.1 | +0.76 |
| 296819076-1 | 5877910894906813056 | 34.6 | 33.9 | -0.68 |
| 296819076-1 | 5877911650854901760 | 34.8 | 33.8 | -0.95 |
| 296819076-1 | 5877910929266612352 | 35.1 | 36.0 | +0.94 |
| 296819076-1 | 5877911685180920832 | 35.1 | 35.7 | +0.62 |
| 296819076-1 | 5877911650822529152 | 36.7 | 35.9 | -0.74 |
| 296819076-1 | 5877911650821139328 | 37.1 | 36.2 | -0.85 |
| 296819076-1 | 5877910894906797952 | 38.2 | 37.7 | -0.51 |
| 296819076-1 | 5877911650821095168 | 38.6 | 37.7 | -0.94 |
| 296819076-1 | 5877911650854898688 | 39.0 | 38.1 | -0.93 |
| 296819076-1 | 5877911650821147008 | 40.8 | 40.0 | -0.81 |
| 296819076-1 | 5877910929300393600 | 41.2 | 42.1 | +0.86 |
| 296819076-1 | 5877910929266599040 | 41.6 | 42.5 | +0.91 |
| 296819076-1 | 5877911650821138688 | 41.8 | 41.0 | -0.85 |
| 296819076-1 | 5877910929266617344 | 41.9 | 42.8 | +0.94 |
| 296819076-1 | 5877910929266586752 | 42.1 | 43.0 | +0.88 |
| 296819076-1 | 5877911680885570176 | 42.3 | 43.2 | +0.91 |
| 296819076-1 | 5877911680885574144 | 42.6 | 43.4 | +0.79 |
| 296819076-1 | 5877911650821147392 | 42.8 | 42.0 | -0.82 |
| 296819076-1 | 5877910929266604928 | 43.2 | 44.1 | +0.93 |
| 296819076-1 | 5877910929266584832 | 44.1 | 45.0 | +0.86 |
| 296819076-1 | 5877911650854892032 | 44.5 | 43.7 | -0.82 |
| 296819076-1 | 5877911646539880064 | 45.0 | 44.1 | -0.89 |
| 296819076-1 | 5877911650854911232 | 45.2 | 44.3 | -0.83 |
| 296819076-1 | 5877911719540657280 | 45.2 | 44.6 | -0.61 |
| 296819076-1 | 5877910929266548864 | 45.5 | 46.1 | +0.65 |
| 296819076-1 | 5877911685180918528 | 45.9 | 46.8 | +0.82 |
| 296819076-1 | 5877911646525800448 | 46.4 | 45.5 | -0.91 |
| 296819076-1 | 5877911650854904064 | 46.9 | 46.0 | -0.94 |
| 296819076-1 | 5877910890610480384 | 47.0 | 46.4 | -0.57 |
| 296819076-1 | 5877911650854912640 | 47.3 | 46.5 | -0.81 |
| 296819076-1 | 5877910924971314176 | 47.4 | 48.3 | +0.90 |
| 296819076-1 | 5877911788260121984 | 47.7 | 48.6 | +0.88 |
| 296819076-1 | 5877910890613185920 | 47.9 | 47.2 | -0.70 |
| 296819076-1 | 5877911032345847040 | 48.3 | 49.2 | +0.95 |
| 296819076-1 | 5877911719574391168 | 48.5 | 47.7 | -0.78 |
| 296819076-1 | 5877911032379620736 | 49.4 | 50.3 | +0.93 |
| 296819076-1 | 5877910929266531712 | 49.4 | 49.9 | +0.52 |
| 296819076-1 | 5877910924987792896 | 49.5 | 50.4 | +0.84 |
| 296819076-1 | 5877911719540658176 | 49.6 | 49.0 | -0.63 |
| 296819076-1 | 5877910929266571264 | 49.8 | 50.6 | +0.82 |
| 296819076-1 | 5877911719540658304 | 49.8 | 49.2 | -0.66 |
| 296819076-1 | 5877911719574752256 | 49.8 | 49.0 | -0.81 |
| 296819076-1 | 5877911650854908032 | 49.9 | 49.0 | -0.90 |
| 296819076-1 | 5877911788260137344 | 50.8 | 51.7 | +0.83 |
| 296819076-1 | 5877911719540643456 | 51.2 | 50.5 | -0.75 |
| 296819076-1 | 5877911685214664832 | 51.2 | 51.8 | +0.58 |
| 296819076-1 | 5877911032379616384 | 51.7 | 52.7 | +0.95 |
| 296819076-1 | 5877911650821093504 | 52.1 | 51.2 | -0.95 |
| 296819076-1 | 5877910929266567680 | 52.3 | 53.1 | +0.84 |
| 296819076-1 | 5877911715244570112 | 52.4 | 51.7 | -0.66 |
| 296819076-1 | 5877911650821128192 | 52.5 | 51.6 | -0.91 |
| 296819076-1 | 5877910894940642560 | 53.1 | 52.4 | -0.74 |
| 296819076-1 | 5877911719574396672 | 53.2 | 52.5 | -0.66 |
| 296819076-1 | 5877910929266567808 | 53.3 | 54.1 | +0.82 |
| 296819076-1 | 5877911646524732800 | 53.4 | 52.5 | -0.87 |
| 296819076-1 | 5877910890625671680 | 53.4 | 52.8 | -0.66 |
| 296819076-1 | 5877911788260136960 | 54.2 | 55.1 | +0.86 |
| 296819076-1 | 5877911715259317120 | 54.6 | 54.1 | -0.54 |
| 296819076-1 | 5877911788293878528 | 54.8 | 55.5 | +0.70 |
| 296819076-1 | 5877910894906771072 | 55.1 | 54.6 | -0.53 |
| 296819076-1 | 5877911032345827328 | 55.2 | 56.1 | +0.94 |
| 296819076-1 | 5877911788260127744 | 55.2 | 56.1 | +0.88 |
| 296819076-1 | 5877910924971310720 | 56.0 | 56.8 | +0.84 |
| 296819076-1 | 5877911646525810688 | 56.7 | 55.8 | -0.93 |
| 296819076-1 | 5877911719540627328 | 57.1 | 56.2 | -0.85 |
| 296819076-1 | 5877910929300384768 | 57.2 | 57.9 | +0.68 |
| 296819076-1 | 5877911788260154240 | 57.4 | 58.1 | +0.79 |
| 296819076-1 | 5877911032345814272 | 57.5 | 58.4 | +0.92 |
| 296819076-1 | 5877911028052263040 | 57.9 | 58.7 | +0.87 |
| 296819076-1 | 5877911032345860736 | 58.1 | 59.0 | +0.94 |
| 296819076-1 | 5877911028050545024 | 58.5 | 59.4 | +0.92 |
| 296819076-1 | 5877911788260170112 | 59.1 | 59.8 | +0.71 |
| 296819076-1 | 5877911719574392192 | 59.6 | 58.8 | -0.79 |
| 296819076-1 | 5877911719540662016 | 59.6 | 58.9 | -0.71 |
| 296819076-1 | 5877910924970222464 | 59.9 | 60.5 | +0.61 |
| 296819076-1 | 5877911715259291392 | 59.9 | 59.1 | -0.88 |
| 322826591-1 | 5332801170510051456 | 14.5 | 13.9 | -0.61 |
| 322826591-1 | 5332801166182036096 | 18.3 | 17.2 | -1.16 |
| 322826591-1 | 5332800964351873152 | 24.7 | 26.4 | +1.71 |
| 322826591-1 | 5332801170500496256 | 25.2 | 23.5 | -1.67 |
| 322826591-1 | 5332801166188339584 | 25.8 | 24.2 | -1.56 |
| 322826591-1 | 5332800964351623808 | 26.0 | 27.1 | +1.16 |
| 322826591-1 | 5332800960024777088 | 27.4 | 28.9 | +1.43 |
| 322826591-1 | 5332801166182041856 | 29.9 | 28.8 | -1.14 |
| 322826591-1 | 5332801166188339328 | 30.2 | 28.6 | -1.62 |
| 322826591-1 | 5332801548467180928 | 30.7 | 30.1 | -0.65 |
| 322826591-1 | 5332801136140680704 | 32.8 | 33.9 | +1.05 |
| 322826591-1 | 5332801166182031744 | 36.2 | 34.5 | -1.63 |
| 322826591-1 | 5332801548467182592 | 37.7 | 36.7 | -1.00 |
| 322826591-1 | 5332801342299236864 | 37.9 | 38.6 | +0.71 |
| 322826591-1 | 5332801342310848256 | 39.1 | 39.8 | +0.66 |
| 322826591-1 | 5332801544139169536 | 41.6 | 40.3 | -1.30 |
| 322826591-1 | 5332800960023589632 | 42.9 | 44.6 | +1.72 |
| 322826591-1 | 5332800964351872896 | 43.0 | 44.7 | +1.70 |
| 322826591-1 | 5332800964342027904 | 44.4 | 46.2 | +1.71 |
| 322826591-1 | 5332801136150283776 | 45.4 | 44.4 | -0.95 |
| 322826591-1 | 5332801131822287616 | 46.6 | 45.3 | -1.28 |
| 322826591-1 | 5332801342308745472 | 47.5 | 49.0 | +1.53 |
| 322826591-1 | 5332800925665021184 | 47.7 | 49.0 | +1.28 |
| 322826591-1 | 5332800964351608320 | 48.6 | 50.3 | +1.72 |
| 322826591-1 | 5332801548467188480 | 48.9 | 48.0 | -0.96 |
| 322826591-1 | 5332801170500513152 | 48.9 | 47.3 | -1.68 |
| 322826591-1 | 5332800964351605888 | 53.0 | 54.7 | +1.72 |
| 322826591-1 | 5332801548467187200 | 53.1 | 51.9 | -1.20 |
| 322826591-1 | 5332801166183219840 | 54.0 | 52.3 | -1.72 |
| 322826591-1 | 5332801548457690368 | 54.8 | 53.7 | -1.13 |
| 322826591-1 | 5332801136150563456 | 54.9 | 55.9 | +1.00 |
| 322826591-1 | 5332801204869776512 | 56.0 | 54.4 | -1.66 |
| 322826591-1 | 5332801548459331712 | 57.1 | 56.2 | -0.96 |
| 322826591-1 | 5332801544145462912 | 57.4 | 56.6 | -0.79 |
| 322826591-1 | 5332801033071055232 | 57.7 | 58.3 | +0.58 |
| 337885456-1 | 6726411577202112256 | 7.7 | 7.2 | -0.57 |
| 337885456-1 | 6726411474147658752 | 24.2 | 23.5 | -0.70 |
| 337885456-1 | 6726411572904933248 | 26.7 | 26.0 | -0.66 |
| 337885456-1 | 6726411577226871808 | 26.8 | 26.3 | -0.54 |
| 337885456-1 | 6726411474120382080 | 30.4 | 29.7 | -0.71 |
| 337885456-1 | 6726411783385309056 | 37.7 | 38.4 | +0.70 |
| 337885456-1 | 6726411783385314560 | 39.7 | 40.3 | +0.61 |
| 337885456-1 | 6726411577226870912 | 40.0 | 39.2 | -0.77 |
| 337885456-1 | 6726411577199579648 | 41.1 | 40.3 | -0.77 |
| 337885456-1 | 6726411783385314688 | 41.5 | 42.1 | +0.69 |
| 337885456-1 | 6726411577226868992 | 43.9 | 43.1 | -0.73 |
| 337885456-1 | 6726411783358063616 | 44.9 | 45.6 | +0.74 |
| 337885456-1 | 6726411607264611840 | 45.7 | 46.4 | +0.61 |
| 337885456-1 | 6726411504187237504 | 48.9 | 48.3 | -0.66 |
| 337885456-1 | 6726411611559356544 | 49.6 | 50.2 | +0.61 |
| 337885456-1 | 6726411607269499776 | 51.8 | 52.3 | +0.54 |
| 337885456-1 | 6726411474147655552 | 51.9 | 51.1 | -0.76 |
| 337885456-1 | 6726411779065164928 | 51.9 | 52.7 | +0.74 |
| 337885456-1 | 6726411469827497856 | 54.0 | 53.4 | -0.57 |
| 337885456-1 | 6726411779063379712 | 56.2 | 56.9 | +0.75 |
| 337885456-1 | 6726411817745049216 | 58.2 | 58.9 | +0.68 |
| 337885456-1 | 6726411813423120768 | 58.7 | 59.5 | +0.73 |
| 337885456-1 | 6726411779065167232 | 58.9 | 59.7 | +0.77 |
| 423100454-1 | 5836452846954130944 | 6.5 | 8.4 | +1.87 |
| 423100454-1 | 5836452846953362560 | 16.1 | 18.1 | +2.03 |
| 423100454-1 | 5836453499849301760 | 16.6 | 15.0 | -1.63 |
| 423100454-1 | 5836453495454849792 | 18.1 | 17.2 | -1.00 |
| 423100454-1 | 5836452739540607232 | 18.2 | 16.8 | -1.37 |
| 423100454-1 | 5836453602867660544 | 18.7 | 19.9 | +1.17 |
| 423100454-1 | 5836452846953412992 | 19.1 | 20.8 | +1.69 |
| 423100454-1 | 5836452847014262400 | 19.2 | 20.2 | +1.08 |
| 423100454-1 | 5836452846953304832 | 19.6 | 19.0 | -0.63 |
| 423100454-1 | 5836452842610260608 | 20.4 | 21.6 | +1.17 |
| 423100454-1 | 5836452842634396800 | 22.1 | 21.3 | -0.76 |
| 423100454-1 | 5836452743935048832 | 22.6 | 20.4 | -2.20 |
| 423100454-1 | 5836453598527876480 | 24.1 | 25.0 | +0.94 |
| 423100454-1 | 5836452847014269824 | 24.3 | 26.4 | +2.09 |
| 423100454-1 | 5836453499849304576 | 26.4 | 24.9 | -1.47 |
| 423100454-1 | 5836452846953307648 | 26.6 | 27.5 | +0.94 |
| 423100454-1 | 5836452847014259840 | 29.2 | 30.4 | +1.19 |
| 423100454-1 | 5836452743874071168 | 29.8 | 28.0 | -1.81 |
| 423100454-1 | 5836453495445289856 | 30.0 | 28.2 | -1.79 |
| 423100454-1 | 5836452743935035264 | 30.5 | 29.7 | -0.87 |
| 423100454-1 | 5836452743935038848 | 30.7 | 28.9 | -1.81 |
| 423100454-1 | 5836452739555181824 | 33.1 | 31.7 | -1.47 |
| 423100454-1 | 5836452842610251520 | 33.4 | 33.9 | +0.52 |
| 423100454-1 | 5836453598534065792 | 34.0 | 35.7 | +1.73 |
| 423100454-1 | 5836453499849295360 | 34.0 | 31.9 | -2.12 |
| 423100454-1 | 5836452847014261120 | 34.9 | 36.4 | +1.55 |
| 423100454-1 | 5836453499849306752 | 35.6 | 34.1 | -1.45 |
| 423100454-1 | 5836453499849310720 | 36.2 | 35.4 | -0.77 |
| 423100454-1 | 5836453602867693312 | 37.8 | 39.5 | +1.78 |
| 423100454-1 | 5836453602928528512 | 37.9 | 39.7 | +1.81 |
| 423100454-1 | 5836452846953373056 | 37.9 | 40.0 | +2.10 |
| 423100454-1 | 5836453602928532480 | 39.1 | 39.9 | +0.81 |
| 423100454-1 | 5836452847014270848 | 39.5 | 41.6 | +2.14 |
| 423100454-1 | 5836452743935040896 | 40.6 | 38.4 | -2.16 |
| 423100454-1 | 5836453499849291264 | 41.6 | 39.4 | -2.20 |
| 423100454-1 | 5836452881374009344 | 42.2 | 44.3 | +2.11 |
| 423100454-1 | 5836452881374011648 | 43.4 | 45.5 | +2.14 |
| 423100454-1 | 5836453499849437952 | 43.9 | 42.3 | -1.63 |
| 423100454-1 | 5836453499849290240 | 43.9 | 41.7 | -2.20 |
| 423100454-1 | 5836452847014259584 | 44.1 | 45.6 | +1.56 |
| 423100454-1 | 5836453499788350976 | 44.2 | 42.0 | -2.20 |
| 423100454-1 | 5836452743935043584 | 44.9 | 42.7 | -2.20 |
| 423100454-1 | 5836452743935024384 | 45.2 | 43.8 | -1.31 |
| 423100454-1 | 5836452876970003456 | 46.1 | 48.1 | +2.01 |
| 423100454-1 | 5836453602928530176 | 46.4 | 48.4 | +1.93 |
| 423100454-1 | 5836453495454847488 | 46.7 | 44.8 | -1.90 |
| 423100454-1 | 5836452743874081920 | 46.9 | 44.8 | -2.18 |
| 423100454-1 | 5836452847014259072 | 47.0 | 48.5 | +1.59 |
| 423100454-1 | 5836452743935040640 | 47.2 | 45.0 | -2.19 |
| 423100454-1 | 5836452743935024256 | 47.2 | 45.9 | -1.29 |
| 423100454-1 | 5836452743935030400 | 47.6 | 45.7 | -1.90 |
| 423100454-1 | 5836452846953273856 | 47.9 | 49.1 | +1.18 |
| 423100454-1 | 5836453499849296896 | 48.2 | 46.2 | -2.08 |
| 423100454-1 | 5836452743935190144 | 48.7 | 47.7 | -1.02 |
| 423100454-1 | 5836453598526915712 | 48.8 | 49.8 | +1.05 |
| 423100454-1 | 5836452743935024000 | 49.0 | 47.5 | -1.48 |
| 423100454-1 | 5836452778294770688 | 49.1 | 50.0 | +0.96 |
| 423100454-1 | 5836452778233792256 | 49.6 | 50.8 | +1.18 |
| 423100454-1 | 5836452876970010880 | 50.7 | 52.9 | +2.20 |
| 423100454-1 | 5836453499849307136 | 50.8 | 49.1 | -1.69 |
| 423100454-1 | 5836452743935034368 | 51.5 | 49.4 | -2.11 |
| 423100454-1 | 5836452743935019776 | 51.5 | 50.9 | -0.62 |
| 423100454-1 | 5836452881374013696 | 51.6 | 53.8 | +2.17 |
| 423100454-1 | 5836452876972411392 | 52.6 | 54.7 | +2.16 |
| 423100454-1 | 5836452739540605184 | 52.7 | 50.5 | -2.16 |
| 423100454-1 | 5836453465428629120 | 53.0 | 50.8 | -2.14 |
| 423100454-1 | 5836452881374001792 | 53.0 | 54.9 | +1.84 |
| 423100454-1 | 5836453602928541440 | 55.1 | 55.9 | +0.79 |
| 423100454-1 | 5836452705171282432 | 55.1 | 52.9 | -2.13 |
| 423100454-1 | 5836453495445288192 | 55.2 | 54.3 | -0.89 |
| 423100454-1 | 5836452743935017984 | 55.2 | 54.3 | -0.93 |
| 423100454-1 | 5836453499788482688 | 55.7 | 54.6 | -1.07 |
| 423100454-1 | 5836452709575294208 | 56.0 | 53.9 | -2.11 |
| 423100454-1 | 5836452881313202432 | 56.9 | 58.9 | +2.09 |
| 423100454-1 | 5836452709514286592 | 56.9 | 54.8 | -2.09 |
| 423100454-1 | 5836453598524522240 | 58.6 | 60.1 | +1.54 |
| 423100454-1 | 5836453465428651008 | 58.6 | 56.5 | -2.06 |
| 423100454-1 | 5836452709575291776 | 58.6 | 56.5 | -2.10 |
| 423100454-1 | 5836452808248808320 | 58.9 | 60.3 | +1.38 |
| 423100454-1 | 5836452881313190784 | 59.5 | 61.7 | +2.15 |
| 441010857-1 | 6122183689530020736 | 10.4 | 9.8 | -0.62 |
| 441010857-1 | 6122183689530020480 | 21.4 | 20.4 | -0.96 |
| 441010857-1 | 6122183758249498240 | 48.9 | 49.9 | +0.95 |
| 44926986-1 | 5431607545963652864 | 12.5 | 9.9 | -2.65 |
| 44926986-1 | 5431607614680563456 | 30.7 | 28.0 | -2.69 |
| 44926986-1 | 5431607507305797760 | 52.5 | 51.0 | -1.47 |
| 44926986-1 | 5431607335504795136 | 54.9 | 56.0 | +1.18 |
| 44926986-1 | 5431607644742487424 | 59.0 | 61.5 | +2.47 |

## Scripts

### gather.py

```python
"""Every M3 neighbour table: each signal's star row, its neighbours.csv and checks.json's neighbour record."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd

RUNS = ("VET_RUN", "VET_SUSPECT_RUN", "CONTROL_VET")
rows = []
for label in RUNS:
    run = Path(os.environ[label])
    for d in sorted((run / "signals").iterdir()):
        c = json.loads((d / "checks.json").read_text())
        s, nb = c["star"], c["neighbours"]
        csv = d / "neighbours.csv"
        t = pd.read_csv(csv) if csv.is_file() else None
        ev = nb["evidence"].get("table")
        same = None
        if t is not None and ev is not None and len(ev) == 0:
            same = len(t) == 0
        elif t is not None and ev is not None:
            e = pd.DataFrame(ev)
            same = bool(
                list(e["source_id"]) == list(t["source_id"])
                and np.allclose(e["sep_arcsec"], t["sep_arcsec"], rtol=0, atol=1e-9)
                and list(e["possible"].astype(bool)) == list(t["possible"].astype(bool))
            )
        rows.append(
            dict(
                run=label, run_id=run.name, name=d.name, kind=c["signal"]["kind"], tic=int(s["tic"]),
                ra=float(s["ra"]), dec=float(s["dec"]), source_id=s.get("dr3_source_id"),
                dr3_from=s.get("dr3_from"), tmag=s.get("tmag"),
                depth=nb["evidence"].get("depth"), outcome=nb["outcome"], reason=nb["reason"],
                csv=str(csv) if t is not None else None, n_rows=None if t is None else len(t),
                csv_equals_checks=same,
                possible=[h["source_id"] for h in nb["evidence"].get("possible_hosts") or []],
            )
        )
Path("/tmp/t13-epoch/manifest.json").write_text(json.dumps(rows, indent=1))
m = pd.DataFrame(rows)
print(m[["run", "name", "kind", "tic", "dr3_from", "outcome", "n_rows", "csv_equals_checks"]].to_string())
print("tables:", len(m), "unique TICs:", m.tic.nunique())
# One TIC position per star across runs?
print("positions per TIC:", m.groupby("tic")[["ra", "dec"]].nunique().max().to_dict())
print("no source id:", m[m.source_id.isna()][["run", "name"]].to_dict("records"))
```

### cones.py

```python
"""A 90" Gaia DR3 cone around each target's TIC position, with the archive's own DISTANCE to that position (the
quantity neighbours.gaia_cone records as sep_arcsec), and each target's own DR3 row. Cached per TIC."""
import json
from pathlib import Path
import pandas as pd
from tess_hunt.gaia import launch_gaia

RADIUS_ARCSEC = 90.0
QUERY = """
SELECT source_id, ra, dec, phot_g_mean_mag, bp_rp, pmra, pmdec, parallax, ref_epoch,
       DISTANCE(POINT('ICRS', ra, dec), POINT('ICRS', {ra:.10f}, {dec:.10f})) * 3600 AS sep_tic
FROM gaiadr3.gaia_source
WHERE 1 = CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra:.10f}, {dec:.10f}, {r:.10f}))
"""
m = json.loads(Path("/tmp/t13-epoch/manifest.json").read_text())
stars = {r["tic"]: r for r in m}
for tic, r in sorted(stars.items()):
    out = Path(f"/tmp/t13-epoch/cones/{tic}.csv")
    if out.is_file():
        continue
    raw = launch_gaia(QUERY.format(ra=r["ra"], dec=r["dec"], r=RADIUS_ARCSEC / 3600), None)
    raw.columns = [str(c).lower() for c in raw.columns]
    raw.sort_values("sep_tic").to_csv(out, index=False)
    print(tic, len(raw), "target in cone:", int(r["source_id"]) in set(raw.source_id), flush=True)
```

### analyse.py

```python
"""Each M3 neighbour table against the epoch-consistent one: separations from the target's own DR3 position (J2016)
to each DR3 star (J2016), and the 60" cone centred there."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from tess_hunt.neighbours import tess_mag, tess_mag_bright

RADIUS = 60.0  # criteria/vet-v3.toml [neighbours] radius_arcmin = 1.0
LINES = (15.0, 20.0, 25.0)
CFG = {"bp_rp_range": [0.0, 3.0], "max_required_depth": 1.0}


def sep(ra1, dec1, ra2, dec2):
    ra1, dec1, ra2, dec2 = (np.radians(np.asarray(v, dtype=float)) for v in (ra1, dec1, ra2, dec2))
    h = np.sin((dec2 - dec1) / 2) ** 2 + np.cos(dec1) * np.cos(dec2) * np.sin((ra2 - ra1) / 2) ** 2
    return np.degrees(2 * np.arcsin(np.sqrt(np.clip(h, 0, 1)))) * 3600


def judge(row, depth, t_target):
    g, c = row["phot_g_mean_mag"], row["bp_rp"]
    if pd.isna(g):
        return np.nan, np.nan, False, "none"
    t = tess_mag(g, c) if pd.notna(c) else tess_mag_bright(g, CFG["bp_rp_range"])
    rd = depth * 10 ** (0.4 * (t - t_target))
    return t, rd, bool(rd <= CFG["max_required_depth"]), "colour" if pd.notna(c) else "g_only"


manifest = json.loads(Path("/tmp/t13-epoch/manifest.json").read_text())
targets, rows, changes, repro = [], [], [], []
for m in manifest:
    cone = pd.read_csv(f"/tmp/t13-epoch/cones/{m['tic']}.csv")
    sid = int(m["source_id"])
    tgt = cone[cone.source_id == sid].iloc[0]
    others = cone[cone.source_id != sid].copy()
    others["sep_new"] = sep(tgt.ra, tgt.dec, others.ra, others.dec)
    old = others[others.sep_tic <= RADIUS]
    new = others[others.sep_new <= RADIUS]
    table = pd.read_csv(m["csv"]) if m["csv"] else None
    # The archive's DISTANCE to the TIC position must reproduce the table's sep_arcsec, star for star.
    t_ids = set() if table is None else set(table.source_id)
    merged = table.merge(old[["source_id", "sep_tic", "sep_new"]], on="source_id", how="left") if table is not None else None
    repro.append(dict(run=m["run"], name=m["name"], table_rows=len(t_ids), cone_rows=len(old),
                      same_stars=t_ids == set(old.source_id),
                      max_sep_diff=float((merged.sep_arcsec - merged.sep_tic).abs().max()) if merged is not None and len(merged) else 0.0,
                      target_self_sep=float(sep(tgt.ra, tgt.dec, tgt.ra, tgt.dec))))
    pm = float(np.hypot(tgt.pmra, tgt.pmdec)) if pd.notna(tgt.pmra) else np.nan
    targets.append(dict(run=m["run"], name=m["name"], kind=m["kind"], tic=m["tic"], source_id=sid,
                        offset=float(tgt.sep_tic), pm_masyr=pm, pm_x16=pm * 16 / 1000,
                        n_old=len(old), n_new=len(new), outcome=m["outcome"]))
    if merged is not None:
        for r in merged.itertuples():
            rows.append(dict(run=m["run"], name=m["name"], tic=m["tic"], source_id=r.source_id,
                             sep_old=r.sep_arcsec, sep_new=r.sep_new, possible=bool(r.possible),
                             g=r.phot_g_mean_mag))
    for kind, ids in (("added", set(new.source_id) - set(old.source_id)), ("dropped", set(old.source_id) - set(new.source_id))):
        for s in ids:
            r = others[others.source_id == s].iloc[0]
            t, rd, possible, frm = judge(r, m["depth"], m["tmag"])
            if kind == "dropped" and table is not None:
                tr = table[table.source_id == s].iloc[0]
                assert bool(tr.possible) == possible, (m["name"], s)
            changes.append(dict(run=m["run"], name=m["name"], tic=m["tic"], change=kind, source_id=int(s),
                                sep_old=float(r.sep_tic), sep_new=float(r.sep_new), g=r.phot_g_mean_mag,
                                bp_rp=r.bp_rp, tmag=t, tmag_from=frm, required_depth=rd, possible=possible))

T, R, C, P = map(pd.DataFrame, (targets, rows, changes, repro))
R["delta"] = R.sep_new - R.sep_old
for name, df in (("targets", T), ("rows", R), ("changes", C), ("repro", P)):
    df.to_csv(f"/tmp/t13-epoch/{name}.csv", index=False)
pd.set_option("display.width", 250)
print("== reproduction: stars equal in all tables:", P.same_stars.all(), " max |sep diff| arcsec:", P.max_sep_diff.max())
print(P[~P.same_stars].to_string())
print("== targets by offset (unique stars)")
u = T.drop_duplicates("tic").sort_values("offset", ascending=False)
print(u[["name", "kind", "tic", "source_id", "offset", "pm_masyr", "pm_x16", "n_old", "n_new"]].to_string(index=False))
print("== over 0.5\":", (u.offset > 0.5).sum(), "of", len(u), "stars;", (T.offset > 0.5).sum(), "of", len(T), "tables")
print("== cone changes")
print(C.sort_values(["run", "name"]).to_string(index=False))
print("== line crossings")
for line in LINES:
    x = R[(R.sep_old < line) != (R.sep_new < line)]
    print(f"-- {line}\"")
    print(x.to_string(index=False) if len(x) else "none")
print("== max |delta| per table vs offset")
mx = R.groupby(["run", "name"]).delta.apply(lambda d: d.abs().max()).rename("max_abs_delta").reset_index()
print(mx.merge(T[["run", "name", "offset"]]).query("offset > 0.5").to_string(index=False))
```

### outcomes.py

```python
"""The neighbour check and TRICERATOPS's host cross-check rerun, offline, on the corrected cone: the stored cone's
stars re-centred on the target's DR3 position, through the repo's own required_depths, neighbour_check and
missing_hosts."""
import json, os
from pathlib import Path
import numpy as np
import pandas as pd
from tess_hunt import neighbours, tricera
import tomllib

cfg_all = tomllib.loads(Path("criteria/vet-v3.toml").read_text())
CFG, TCFG = cfg_all["neighbours"], cfg_all["triceratops"]
R = CFG["radius_arcmin"] * 60
TRIC = {"VET_RUN": [os.environ["TRIC_RUN"]], "CONTROL_VET": [os.environ["CONTROL_TRIC"], os.environ["CONTROL_TRIC_4307"]]}


def sep(ra1, dec1, ra2, dec2):
    return tricera._separation_arcsec(ra1, dec1, ra2, dec2)


out = []
for m in json.loads(Path("/tmp/t13-epoch/manifest.json").read_text()):
    cone = pd.read_csv(f"/tmp/t13-epoch/cones/{m['tic']}.csv")
    sid = int(m["source_id"])
    tgt = cone[cone.source_id == sid].iloc[0]
    cone["sep_arcsec"] = sep(tgt.ra, tgt.dec, cone.ra, cone.dec)
    fixed = cone[cone.sep_arcsec <= R][neighbours.COLUMNS].sort_values("sep_arcsec").reset_index(drop=True)
    table = neighbours.required_depths(fixed, m["depth"], m["tmag"], sid, CFG)
    new = neighbours.neighbour_check(table, None).to_dict()
    checks = json.loads((Path(os.environ[m["run"]]) / "signals" / m["name"] / "checks.json").read_text())
    old = checks["neighbours"]
    old_hosts = {h["source_id"] for h in old["evidence"]["possible_hosts"]}
    new_hosts = {h["source_id"] for h in new["evidence"]["possible_hosts"]}
    row = dict(run=m["run"], name=m["name"], old_outcome=old["outcome"], new_outcome=new["outcome"],
               old_reason=old["reason"], new_reason=new["reason"],
               old_no_g=len(old["evidence"].get("no_g") or []), new_no_g=len(new["evidence"].get("no_g") or []),
               hosts_old=len(old_hosts), hosts_new=len(new_hosts),
               hosts_added=sorted(new_hosts - old_hosts), hosts_dropped=sorted(old_hosts - new_hosts))
    # TRICERATOPS's cross-check on the corrected possible hosts, against the star list each run stored.
    for run in TRIC.get(m["run"], []):
        f = Path(run) / "signals" / m["name"] / "triceratops.json"
        if not f.is_file():
            continue
        t = json.loads(f.read_text())
        stars = t["evidence"]["stars"]
        if stars is None:
            continue
        stars = pd.DataFrame(stars)
        possible = table[table["possible"]]
        row[f"tric {Path(run).name[:16]}"] = dict(
            outcome=t["outcome"], missing_old=t["evidence"]["missing_hosts"],
            missing_new=tricera.missing_hosts(possible, stars, TCFG["match_arcsec"]),
            added_hosts_matched={int(h["source_id"]): (h["tic"], round(h["distance_arcsec"], 3))
                                 for h in tricera._hosts(possible, stars, TCFG["match_arcsec"])
                                 if h["source_id"] in row["hosts_added"]},
        )
    out.append(row)
Path("/tmp/t13-epoch/outcomes.json").write_text(json.dumps(out, indent=1, default=str))
for r in out:
    changed = (r["old_outcome"] != r["new_outcome"] or r["old_reason"] != r["new_reason"]
               or r["hosts_added"] or r["hosts_dropped"])
    tric = {k: v for k, v in r.items() if k.startswith("tric")}
    if changed or any(v["missing_old"] != v["missing_new"] for v in tric.values()):
        print(json.dumps(r, default=str))
print("tables:", len(out), " outcome changes:", sum(r["old_outcome"] != r["new_outcome"] for r in out),
      " reason changes:", sum(r["old_reason"] != r["new_reason"] for r in out))
```

### quotes.py

```python
"""Separations quoted in decisions 0025, 0026, 0032, 0033 and in the dossier drafts, old and corrected."""
import json, re
from pathlib import Path
import pandas as pd
from tess_hunt.tricera import _separation_arcsec as sep

R = pd.read_csv("/tmp/t13-epoch/rows.csv")
T = pd.read_csv("/tmp/t13-epoch/targets.csv")


def row(run, name, sid):
    x = R[(R.run == run) & (R.name == name) & (R.source_id == sid)]
    return None if x.empty else x.iloc[0]


print("== decisions")
for run, name, sid, quoted, where in (
    ("CONTROL_VET", "TOI-1058.01", 6757952648798471040, 20.90, "0025, 0026, 0032"),
    ("CONTROL_VET", "TOI-1175.01", 2039904204830247296, 23.53, "0025, 0026, 0032"),
    ("VET_RUN", "44926986-1", 5431607545963652864, 12.5, "0026"),
):
    r = row(run, name, sid)
    print(f"{name} {sid} quoted {quoted} ({where}): table {r.sep_old:.4f}  corrected {r.sep_new:.4f}  moved {r.sep_new - r.sep_old:+.4f}")
# The network test centres on benchmarks/pixel_controls.csv's ra and dec, not the targets table's TIC position.
pc = pd.read_csv("benchmarks/pixel_controls.csv", dtype={"toi": str}).set_index("toi")
for toi, tic, eb in (("1058.01", 31553893, 6757952648798471040), ("1175.01", 30329585, 2039904204830247296)):
    cone = pd.read_csv(f"/tmp/t13-epoch/cones/{tic}.csv").set_index("source_id")
    m = next(x for x in json.loads(Path("/tmp/t13-epoch/manifest.json").read_text()) if x["tic"] == tic)
    e = cone.loc[eb]
    print(f"TOI-{toi}: pixel_controls.csv centre {pc.loc[toi].ra}, {pc.loc[toi].dec}; targets table {m['ra']}, {m['dec']};"
          f" the two {float(sep(pc.loc[toi].ra, pc.loc[toi].dec, m['ra'], m['dec'])):.3f}\" apart;"
          f" EB from pixel_controls centre {float(sep(pc.loc[toi].ra, pc.loc[toi].dec, e.ra, e.dec)):.4f}")
# 0033 item 3: 423100454-1's possible hosts "from 6.5\" out".
x = R[(R.run == "VET_RUN") & (R.name == "423100454-1") & R.possible].sort_values("sep_old").head(3)
print("423100454-1 nearest possible hosts:\n", x[["source_id", "sep_old", "sep_new"]].to_string(index=False))
x = R[(R.run == "VET_RUN") & (R.name == "423100454-1") & R.possible].sort_values("sep_new").head(3)
print("423100454-1 nearest possible hosts, corrected order:\n", x[["source_id", "sep_old", "sep_new"]].to_string(index=False))

print("== dossier drafts")
moved = []
quoted_rows = 0
for d in sorted(Path.home().joinpath(".cache/tess-hunt/drafts/m3").iterdir()):
    text = (d / "dossier.md").read_text()
    for sid, s in re.findall(r"^\| Gaia DR3 (\d+) \| ([0-9.]+) \|", text, re.M):
        quoted_rows += 1
        r = row("VET_RUN", d.name, int(sid))
        assert abs(float(s) - r.sep_old) <= 0.05 + 1e-9, (d.name, sid, s, r.sep_old)
        if abs(r.sep_new - r.sep_old) > 0.5:
            moved.append(dict(draft=d.name, source_id=int(sid), quoted=float(s), corrected=round(r.sep_new, 1),
                              moved=round(r.sep_new - r.sep_old, 2)))
M = pd.DataFrame(moved)
print("host rows quoted in drafts:", quoted_rows, " moved > 0.5\":", len(M))
print(M.groupby("draft").agg(rows=("source_id", "size"), max_moved=("moved", lambda v: v.abs().max())).to_string())
M.to_csv("/tmp/t13-epoch/dossier_moved.csv", index=False)
print(M.to_string(index=False))
```

### counts.py

```python
"""Counts for the report: line and cone crossings per run, and the suspect run against the main one."""
import pandas as pd

R = pd.read_csv("/tmp/t13-epoch/rows.csv")
C = pd.read_csv("/tmp/t13-epoch/changes.csv")
T = pd.read_csv("/tmp/t13-epoch/targets.csv")
a = R[R.run == "VET_RUN"].drop(columns="run").reset_index(drop=True)
b = R[R.run == "VET_SUSPECT_RUN"].drop(columns="run").reset_index(drop=True)
print("VET_SUSPECT_RUN tables identical to VET_RUN's:", a.equals(b))
print("changes identical:", C[C.run == "VET_RUN"].drop(columns="run").reset_index(drop=True).equals(
    C[C.run == "VET_SUSPECT_RUN"].drop(columns="run").reset_index(drop=True)))
for run in ("VET_RUN", "CONTROL_VET"):
    x = R[R.run == run]
    print(f"== {run}: tables {T[T.run == run].shape[0]}, over 0.5\" {(T[T.run == run].offset > 0.5).sum()}, rows {len(x)}")
    for line in (15, 20, 25):
        c = x[(x.sep_old < line) != (x.sep_new < line)]
        print(f"  {line}\": {len(c)} rows ({int(c.possible.sum())} possible hosts) in {c.name.nunique()} tables:",
              c.groupby("name").size().to_dict())
    cc = C[C.run == run]
    print(f"  60\" cone: added {int((cc.change == 'added').sum())} ({int(cc[cc.change == 'added'].possible.sum())} possible),"
          f" dropped {int((cc.change == 'dropped').sum())} ({int(cc[cc.change == 'dropped'].possible.sum())} possible),"
          f" in {cc.name.nunique()} tables:", cc.groupby("name").size().to_dict())
    print("  rows moved > 0.5\":", int((x.delta.abs() > 0.5).sum()), "of", len(x),
          "| possible hosts moved > 0.5\":", int(((x.delta.abs() > 0.5) & x.possible).sum()), "of", int(x.possible.sum()))
# Stars by offset over 0.5", unique stars
u = T.drop_duplicates("tic")
print("unique stars:", len(u), "over 0.5\":", int((u.offset > 0.5).sum()))
print(u[u.offset > 0.5].groupby("kind").size().to_dict())
```

### selfjoin.py

```python
"""The fix's query shape, tried read-only: a cone centred on the target's own DR3 row, in one ADQL self-join,
against the corrected cone computed offline."""
import json
from pathlib import Path
import numpy as np
import pandas as pd
from tess_hunt.gaia import launch_gaia
from tess_hunt.tricera import _separation_arcsec as sep

QUERY = """
SELECT g.source_id, g.ra, g.dec, g.phot_g_mean_mag, g.bp_rp,
       DISTANCE(POINT('ICRS', g.ra, g.dec), POINT('ICRS', t.ra, t.dec)) * 3600 AS sep_arcsec,
       g.pmra, g.pmdec, g.ref_epoch
FROM gaiadr3.gaia_source AS t, gaiadr3.gaia_source AS g
WHERE t.source_id = {sid}
  AND 1 = CONTAINS(POINT('ICRS', g.ra, g.dec), CIRCLE('ICRS', t.ra, t.dec, {r:.10f}))
"""
m = {x["tic"]: x for x in json.loads(Path("/tmp/t13-epoch/manifest.json").read_text())}
for tic in (136916387, 423100454):
    sid = int(m[tic]["source_id"])
    got = launch_gaia(QUERY.format(sid=sid, r=1.0 / 60), None)
    got.columns = [str(c).lower() for c in got.columns]
    cone = pd.read_csv(f"/tmp/t13-epoch/cones/{tic}.csv")
    t = cone[cone.source_id == sid].iloc[0]
    cone["sep_new"] = sep(t.ra, t.dec, cone.ra, cone.dec)
    want = cone[cone.sep_new <= 60]
    j = got.merge(want[["source_id", "sep_new"]], on="source_id", how="outer", indicator=True)
    print(tic, "rows", len(got), "offline", len(want), "same stars:", set(got.source_id) == set(want.source_id),
          "max |sep diff|:", float((j.sep_arcsec - j.sep_new).abs().max()))
```

### tables.py

```python
"""The report's tables, written from the analysis CSVs so no number is copied by hand."""
import json
from pathlib import Path
import pandas as pd

D = Path("/tmp/t13-epoch")
T, R, C = (pd.read_csv(D / f) for f in ("targets.csv", "rows.csv", "changes.csv"))
O = json.loads((D / "outcomes.json").read_text())
M = pd.read_csv(D / "dossier_moved.csv")
R["delta"] = R.sep_new - R.sep_old


def md(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(str(v) for v in row) + " |" for row in df.itertuples(index=False)]
    return "\n".join(out) + "\n"


def f(x, n=2):
    return "" if pd.isna(x) else f"{x:.{n}f}"


# 1. Every star over 0.5", one row per star with the signals and runs that carry it.
t = T[T.offset > 0.5].copy()
t["runs"] = t.run
g = t.groupby("tic")
rows = []
for tic, x in g:
    first = x.iloc[0]
    rr = R[(R.tic == tic) & R.run.isin(["VET_RUN", "CONTROL_VET"])]
    rows.append(dict(
        signal=", ".join(sorted(set(x.name))), kind=first.kind, TIC=tic, **{"Gaia DR3 id": first.source_id},
        **{"offset (\")": f(first.offset, 3), "DR3 pm (mas/yr)": f(first.pm_masyr, 1), "pm x 16 yr (\")": f(first.pm_x16, 3)},
        **{"tables": ", ".join(sorted(set(x.run))), "rows": int(first.n_old),
           "max shift (\")": f(rr.groupby("name").delta.apply(lambda d: d.abs().max()).max(), 3) if len(rr) else "no rows"},
    ))
(D / "tables/offsets.md").write_text(md(pd.DataFrame(rows).sort_values("offset (\")", key=lambda s: s.astype(float), ascending=False)))
under = T[T.offset <= 0.5].drop_duplicates("tic").sort_values("offset", ascending=False)
(D / "tables/under.md").write_text(", ".join(f"{n} {o:.3f}" for n, o in zip(under.name, under.offset)) + "\n")

# 2. Line crossings and cone changes, VET_RUN and CONTROL_VET (VET_SUSPECT_RUN repeats VET_RUN exactly).
x = R[R.run.isin(["VET_RUN", "CONTROL_VET"])]
lines = []
for line in (15, 20, 25):
    c = x[(x.sep_old < line) != (x.sep_new < line)].copy()
    c["line"] = f'{line}"'
    lines.append(c)
L = pd.concat(lines)
L = L.assign(table=L.run.map({"VET_RUN": "19", "CONTROL_VET": "controls"}))
L = L.sort_values(["table", "name", "line", "sep_old"])
(D / "tables/lines_all.md").write_text(md(pd.DataFrame({
    "table": L.table, "signal": L.name, "line": L.line, "Gaia DR3 id": L.source_id,
    "table sep (\")": L.sep_old.map(f), "corrected (\")": L.sep_new.map(f), "possible": L.possible})))
P = L[L.possible]
(D / "tables/lines_possible.md").write_text(md(pd.DataFrame({
    "table": P.table, "signal": P.name, "line": P.line, "Gaia DR3 id": P.source_id,
    "table sep (\")": P.sep_old.map(f), "corrected (\")": P.sep_new.map(f)})))
c = C[C.run.isin(["VET_RUN", "CONTROL_VET"])].copy()
c["table"] = c.run.map({"VET_RUN": "19", "CONTROL_VET": "controls"})
c = c.sort_values(["table", "name", "change", "sep_new"])
cone = pd.DataFrame({"table": c.table, "signal": c.name, "change": c.change, "Gaia DR3 id": c.source_id,
                     "table sep (\")": c.sep_old.map(f), "corrected (\")": c.sep_new.map(f),
                     "G": c.g.map(lambda v: f(v, 2) or "none"), "required depth": c.required_depth.map(lambda v: f(v, 3) or "none"),
                     "possible": c.possible})
(D / "tables/cone_all.md").write_text(md(cone))
key = cone[(cone.possible) | (cone.G == "none")]
(D / "tables/cone_key.md").write_text(md(key))

# 3. Outcome rows that change anything (VET_RUN and CONTROL_VET).
rows = []
for o in O:
    if o["run"] == "VET_SUSPECT_RUN":
        continue
    if o["old_reason"] == o["new_reason"] and not o["hosts_added"] and not o["hosts_dropped"]:
        continue
    rows.append({"table": {"VET_RUN": "19", "CONTROL_VET": "controls"}[o["run"]], "signal": o["name"],
                 "outcome": o["old_outcome"] + (" (unchanged)" if o["old_outcome"] == o["new_outcome"] else " -> " + o["new_outcome"]),
                 "reason now": o["old_reason"], "reason corrected": o["new_reason"],
                 "possible hosts added": " ".join(map(str, o["hosts_added"])) or "none",
                 "possible hosts dropped": " ".join(map(str, o["hosts_dropped"])) or "none"})
(D / "tables/outcomes.md").write_text(md(pd.DataFrame(rows)))
tri = []
for o in O:
    for k, v in o.items():
        if k.startswith("tric"):
            tri.append({"table": {"VET_RUN": "19", "CONTROL_VET": "controls"}[o["run"]], "signal": o["name"], "TRICERATOPS run": k[5:],
                        "outcome": v["outcome"], "missing hosts now": v["missing_old"] or "none",
                        "missing hosts corrected": v["missing_new"] or "none",
                        "added hosts matched (TIC, distance at J2000 in \")": "; ".join(f"{s}: TIC {t} {d}" for s, (t, d) in v["added_hosts_matched"].items()) or "no host added"})
(D / "tables/tric.md").write_text(md(pd.DataFrame(tri)))

# 4. Draft rows moved by more than 0.5".
(D / "tables/drafts_summary.md").write_text(md(M.groupby("draft").agg(
    **{"rows moved > 0.5\"": ("source_id", "size"), "largest shift (\")": ("moved", lambda v: f"{v.abs().max():.2f}")}).reset_index()))
(D / "tables/drafts_all.md").write_text(md(pd.DataFrame({"draft": M.draft, "Gaia DR3 id": M.source_id,
    "quoted (\")": M.quoted.map(lambda v: f"{v:.1f}"), "corrected (\")": M.corrected.map(lambda v: f"{v:.1f}"),
    "shift (\")": M.moved.map(lambda v: f"{v:+.2f}")})))
# Controls by proper motion, for the adjacent pixel-check note.
cs = T[T.run == "CONTROL_VET"].drop_duplicates("tic").sort_values("pm_masyr", ascending=False)
(D / "tables/controls_pm.md").write_text(md(pd.DataFrame({"control": [", ".join(sorted(T[(T.run == 'CONTROL_VET') & (T.tic == t)].name)) for t in cs.tic],
    "DR3 pm (mas/yr)": cs.pm_masyr.map(lambda v: f"{v:.1f}")}).head(8)))
for p in sorted((D / "tables").iterdir()):
    print(p.name, len(p.read_text().splitlines()))
```

