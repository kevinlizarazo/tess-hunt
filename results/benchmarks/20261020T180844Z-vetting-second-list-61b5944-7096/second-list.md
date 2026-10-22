# Second list (20261020T180844Z-vetting-second-list-61b5944-7096)

The second-list signals of vetting run `20261020T174317Z-vetting-run-61b5944-2d70`: signals triage's novelty matched only to SPOC TCE or ExoMiner rows, which decision 0013 leaves for the maintainer to promote by hand (M3 design, section 4.10). Each row has the vet under vet-v3; triage's pixel check, which triage runs only on novelty passes, run on it as triage runs it (the `[pixels]` of `criteria/triage-v1.toml` as triage run `20261015T155441Z-triage-7b12e25-3f57` read it, an offset limit of 15"); SPOC's DV statistics for the TCE at the signal's period; the ExoMiner score; and the next TESS sectors. Every row is a candidate signal, not a planet.

SPOC and ExoMiner rows match the signal on period alone, within search-v2's `[match]` tolerance at vet-v3's novelty harmonics; ratio k means the row's period times k is the signal's. A row is taken from the signal's star when it has one there, else from a star novelty matched the signal to; of several, from the latest sector run (its last sector, then the longer run). ExoMiner v2's 2-min and FFI catalogs come before v1.

| Signal | TIC | Period (d) | Depth (ppm) | Not passed | Pixels | Offset (arcsec) | ExoMiner | Next sectors |
|---|---|---|---|---|---|---|---|---|
| 173369850-1 | 173369850 | 6.487503 | 734 | novelty inconclusive; secondary fail | fail | 34.3 | 0.028 (FP; ExoMiner-v2 vetting_catalog_FFI, run 39) | none |
| 241522065-1 | 241522065 | 17.436664 | 505 | novelty inconclusive; holdout inconclusive | pass | 2.3 | 0.811 (PC; ExoMiner-v2 vetting_catalog_FFI, run 38) | 112, 113, 114 |
| 277774870-1 | 277774870 | 12.819429 | 586 | novelty inconclusive | pass | 3.0 | 0.573 (PC; ExoMiner-v2 vetting_catalog_FFI, run 56-69) | none |
| 295140687-1 | 295140687 | 2.673337 | 370 | novelty inconclusive; secondary fail | fail | 19.1 | 0.028 (FP; ExoMiner-v2 vetting_catalog_FFI, run 56-69) | 113 |
| 322826591-1 | 322826591 | 12.725668 | 546 | novelty inconclusive; sector_depth fail; holdout fail; density fail; neighbours inconclusive | fail | 39.2 | 0.041 (FP; ExoMiner-v2 vetting_catalog_2-min, run 1-39) | 112, 113, 114 |
| 337885456-1 | 337885456 | 1.379783 | 170 | novelty inconclusive; secondary fail | fail | 40.7 | 0.003 (FP; ExoMiner-v2 vetting_catalog_FFI, run 66, ratio 2) | none |
| 370977908-1 | 370977908 | 17.091442 | 279 | novelty inconclusive; holdout inconclusive; neighbours inconclusive | pass | 9.3 | 0.782 (PC; ExoMiner-v2 vetting_catalog_2-min, run 1-65) | none |
| 423100454-1 | 423100454 | 14.186255 | 448 | novelty inconclusive; neighbours inconclusive | fail | 118.6 | 0.785 (PC; ExoMiner-v2 vetting_catalog_FFI, run 39) | 113 |
| 438857197-1 | 438857197 | 3.659160 | 779 | novelty inconclusive | pass | 3.6 | 0.082 (FP; ExoMiner-v2 vetting_catalog_FFI, run 64) | 112, 114 |
| 458290782-1 | 458290782 | 1.931605 | 1149 | novelty inconclusive; secondary fail; sector_depth fail; holdout fail; neighbours inconclusive | fail | 25.7 | 0.152 (FP; ExoMiner-v2 vetting_catalog_FFI, run 39) | none |

## Checks

| Signal | novelty | odd_even | secondary | sector_depth | holdout | signal_present | shape | density | radius | neighbours |
|---|---|---|---|---|---|---|---|---|---|---|
| 173369850-1 | inconclusive | pass | fail | pass | pass | pass | pass | pass | pass | pass |
| 241522065-1 | inconclusive | pass | pass | pass | inconclusive | pass | pass | pass | pass | pass |
| 277774870-1 | inconclusive | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| 295140687-1 | inconclusive | pass | fail | pass | pass | pass | pass | pass | pass | pass |
| 322826591-1 | inconclusive | pass | pass | fail | fail | pass | pass | fail | pass | inconclusive |
| 337885456-1 | inconclusive | pass | fail | pass | pass | pass | pass | pass | pass | pass |
| 370977908-1 | inconclusive | pass | pass | pass | inconclusive | pass | pass | pass | pass | inconclusive |
| 423100454-1 | inconclusive | pass | pass | pass | pass | pass | pass | pass | pass | inconclusive |
| 438857197-1 | inconclusive | pass | pass | pass | pass | pass | pass | pass | pass | pass |
| 458290782-1 | inconclusive | pass | fail | fail | fail | pass | pass | pass | pass | inconclusive |

## Pixel check

The best-quality sector's centroid offset decides it; each measured sector's offset follows, with its quality.

| Signal | Outcome | Reason | Offset (arcsec) per sector (quality) |
|---|---|---|---|
| 173369850-1 | fail | centroid offset 34.3" exceeds 15" | S103 31.0 (0.12); S102 24.7 (0.41); S100 36.2 (0.16); S93 34.3 (0.64); S66 25.4 (0.32) |
| 241522065-1 | pass | centroid offset 2.3" within 15" | S102 4.2 (0.81); S101 17.3 (0.52); S99 2.3 (0.90); S65 5.8 (0.62); S64 17.3 (0.40) |
| 277774870-1 | pass | centroid offset 3.0" within 15" | S104 6.3 (0.73); S102 9.5 (0.67); S95 2.3 (0.78); S94 3.0 (0.82); S68 8.5 (0.58) |
| 295140687-1 | fail | centroid offset 19.1" exceeds 15" | S99 14.6 (0.64); S65 6.8 (0.54); S64 18.6 (0.59); S38 19.1 (0.74); S37 22.9 (0.34) |
| 322826591-1 | fail | centroid offset 39.2" exceeds 15" | S100 40.2 (0.83); S99 39.2 (0.96); S64 41.3 (0.93); S38 37.8 (0.95); S37 41.0 (0.95) |
| 337885456-1 | fail | centroid offset 40.7" exceeds 15" | S104 40.4 (0.87); S93 40.7 (0.92); S66 42.3 (0.83); S13 41.4 (0.68) |
| 370977908-1 | pass | centroid offset 9.3" within 15" | S103 10.0 (0.61); S102 3.4 (0.75); S65 6.3 (0.41); S38 9.3 (0.76); S11 14.5 (0.39) |
| 423100454-1 | fail | centroid offset 118.6" exceeds 15" | S103 5.7 (0.52); S102 118.6 (0.92); S65 115.7 (0.92); S39 5.8 (0.73); S12 8.7 (0.57) |
| 438857197-1 | pass | centroid offset 3.6" within 15" | S102 2.3 (0.69); S101 3.6 (0.80); S64 8.3 (0.59); S38 5.4 (0.72); S11 19.9 (0.46) |
| 458290782-1 | fail | centroid offset 25.7" exceeds 15" | S103 23.0 (0.10); S93 25.7 (0.85); S66 27.4 (0.69); S39 24.3 (0.70); S12 19.8 (0.42) |

## SPOC DV statistics

MES is `tce_max_mult_ev`; odd/even is `tce_bin_oedp_stat`; the ghost diagnostic's core and halo statistics are `tce_cap_stat` and `tce_hap_stat`; the difference-image centroid offsets are `tce_dicco_msky` (from the out-of-transit centroid) and `tce_ditco_msky` (from the TIC position), each with its `_err`; the weak secondary's depth is `wst_depth`. Each is SPOC's value as the snapshot's raw table gives it.

| Signal | TCE | Ratio | MES | Odd/even | Ghost core | Ghost halo | Offset from OOT centroid (arcsec) | Offset from TIC position (arcsec) | Weak secondary (ppm) | Every TCE that matched (run, TCE, ratio) |
|---|---|---|---|---|---|---|---|---|---|---|
| 173369850-1 | 00173369850-01, run s0103-s0103 | 0.5 | 7.92 | 0.547 | 4.37 | 0.842 | 0.00 (err -1.00) | 0.00 (err -1.00) | 257.1 | s0103-s0103 00173369850-01 ratio 0.5; s0100-s0100 00173369850-01 ratio 0.5 |
| 241522065-1 | no SPOC TCE at the period on this star or a star novelty matched it to |  |  |  |  |  |  |  |  |  |
| 277774870-1 | no SPOC TCE at the period on this star or a star novelty matched it to |  |  |  |  |  |  |  |  |  |
| 295140687-1 | no SPOC TCE at the period on this star or a star novelty matched it to |  |  |  |  |  |  |  |  |  |
| 322826591-1 | 00322826591-01, run s0001-s0039 | 1 | 23.58 | 0.241 | -2.19 | 31.8 | 38.29 (err 2.55) | 38.01 (err 2.59) | 102.7 | s0001-s0039 00322826591-01 ratio 1; s0038-s0038 00322826591-01 ratio 1; s0037-s0037 00322826591-01 ratio 1; s0001-s0013 00322826591-01 ratio 1; s0011-s0011 00322826591-01 ratio 1; s0010-s0010 00322826591-01 ratio 1 |
| 337885456-1 | no SPOC TCE at the period on this star or a star novelty matched it to |  |  |  |  |  |  |  |  |  |
| 370977908-1 | 00370977908-01, run s0001-s0065 | 1 | 7.32 | 0.655 | 6.31 | 0.581 | 2.96 (err 4.23) | 2.36 (err 4.75) | 78.9 | s0001-s0065 00370977908-01 ratio 1; s0001-s0039 00370977908-01 ratio 1 |
| 423100454-1 | no SPOC TCE at the period on this star or a star novelty matched it to |  |  |  |  |  |  |  |  |  |
| 438857197-1 | no SPOC TCE at the period on this star or a star novelty matched it to |  |  |  |  |  |  |  |  |  |
| 458290782-1 | 01343588382-01, run s0103-s0103, on TIC 1343588382 | 1 | 18.45 | 0.625 | 5.3 | 2.8 | 18.18 (err 2.55) | 1.68 (err 2.56) | 23215.1 | s0103-s0103 01343588382-01 ratio 1; s0103-s0103 01343588382-02 ratio 2; s0093-s0093 01343588382-01 ratio 2 |
