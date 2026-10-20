# vet-v3 controls (20261020T082333Z-benchmark-controls-16418d2-f45a)

Vetting run `20261017T155223Z-vetting-run-62882b5-4867` judged 20 controls (known planets, kind `control`) and 4 negative controls under `criteria/vet-v3.toml`. Each row of `controls.csv` holds a signal's checks and neighbour-table outcome from that run, and its TRICERATOPS outcome from the last run given that judged it. A known planet's pixel check comes from pixel-completeness run `20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33`: `criteria/triage-v1.toml`'s `[pixels]` at the catalog ephemeris. `vetting run` takes pixels from triage, and the controls never went through triage. `possible_hosts` counts the neighbour table's possible hosts; `offset_qual_arcsec` is the best-quality sector's centroid offset. `pass_rate` is pass over all the `signals` counted, inconclusives in the denominator. Novelty fails every known planet by design, since each is in the catalogs it checks against.

## Inputs

- Vetting run: `20261017T155223Z-vetting-run-62882b5-4867`
- TRICERATOPS runs, in the order given, with the signals each failed to judge:
  - `20261017T162256Z-vetting-triceratops-62882b5-d0f8`: none
  - `20261018T012940Z-vetting-triceratops-62882b5-e3d7`: none
- Pixel-completeness run: `20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33`

## Pass rates over all 20 controls

| check | signals | pass | fail | inconclusive | pass_rate |
|---|---|---|---|---|---|
| novelty | 20 | 0 | 20 | 0 | 0 |
| odd_even | 20 | 20 | 0 | 0 | 1 |
| secondary | 20 | 18 | 2 | 0 | 0.9 |
| sector_depth | 20 | 19 | 1 | 0 | 0.95 |
| holdout | 20 | 15 | 2 | 3 | 0.75 |
| signal_present | 20 | 16 | 0 | 4 | 0.8 |
| shape | 20 | 20 | 0 | 0 | 1 |
| density | 20 | 19 | 1 | 0 | 0.95 |
| radius | 20 | 20 | 0 | 0 | 1 |
| neighbours | 20 | 20 | 0 | 0 | 1 |
| pixels | 20 | 16 | 4 | 0 | 0.8 |
| triceratops | 20 | 16 | 0 | 4 | 0.8 |

## Pass rates without the left-out controls (19 controls)

| check | signals | pass | fail | inconclusive | pass_rate |
|---|---|---|---|---|---|
| novelty | 19 | 0 | 19 | 0 | 0 |
| odd_even | 19 | 19 | 0 | 0 | 1 |
| secondary | 19 | 17 | 2 | 0 | 0.895 |
| sector_depth | 19 | 19 | 0 | 0 | 1 |
| holdout | 19 | 15 | 1 | 3 | 0.789 |
| signal_present | 19 | 16 | 0 | 3 | 0.842 |
| shape | 19 | 19 | 0 | 0 | 1 |
| density | 19 | 18 | 1 | 0 | 0.947 |
| radius | 19 | 19 | 0 | 0 | 1 |
| neighbours | 19 | 19 | 0 | 0 | 1 |
| pixels | 19 | 15 | 4 | 0 | 0.789 |
| triceratops | 19 | 16 | 0 | 3 | 0.842 |

## Left out

TOI-396.01

## Failed and inconclusive controls, by check

| check | signal | outcome | reason |
|---|---|---|---|
| novelty | TOI-1052.01 | fail | matches TOI-1052.01 |
| novelty | TOI-107.01 | fail | matches TOI-107.01 |
| novelty | TOI-1097.02 | fail | matches TOI-1097.02 |
| novelty | TOI-118.01 | fail | matches TOI-118.01 |
| novelty | TOI-144.01 | fail | matches TOI-144.01 |
| novelty | TOI-191.01 | fail | matches TOI-191.01 |
| novelty | TOI-2011.02 | fail | matches TOI-2011.02 |
| novelty | TOI-396.01 | fail | matches TOI-396.01 |
| novelty | TOI-396.03 | fail | matches TOI-396.03 |
| novelty | TOI-411.01 | fail | matches TOI-411.01 |
| novelty | TOI-4307.01 | fail | matches TOI-4307.01 |
| novelty | TOI-4320.01 | fail | matches TOI-4320.01 |
| novelty | TOI-451.02 | fail | matches TOI-451.02 |
| novelty | TOI-451.03 | fail | matches TOI-451.03 |
| novelty | TOI-576.01 | fail | matches TOI-576.01 |
| novelty | TOI-652.01 | fail | matches TOI-652.01 |
| novelty | TOI-747.01 | fail | matches TOI-747.01 |
| novelty | TOI-755.01 | fail | matches TOI-755.01 |
| novelty | TOI-763.02 | fail | matches TOI-763.02 |
| novelty | TOI-826.01 | fail | matches TOI-826.01 |
| secondary | TOI-107.01 | fail | dip at phase 0.5 of 94 ppm, 3.6 sigma |
| secondary | TOI-747.01 | fail | dip at phase 0.5 of 119 ppm, 3.2 sigma |
| sector_depth | TOI-396.01 | fail | pdcsap: depths disagree across sectors (p = 1.1e-14) |
| holdout | TOI-396.01 | fail | transits missing where predicted in season(s) [0, 1, 2, 3] |
| holdout | TOI-576.01 | fail | transits missing where predicted in season(s) [3] |
| holdout | TOI-1097.02 | inconclusive | 1 season(s) could be tested; need 2 |
| holdout | TOI-451.02 | inconclusive | 0 season(s) could be tested; need 2 |
| holdout | TOI-451.03 | inconclusive | 1 season(s) could be tested; need 2 |
| signal_present | TOI-1097.02 | inconclusive | combined depth is 1.1 sigma, below 7 |
| signal_present | TOI-396.01 | inconclusive | combined depth is 1.2 sigma, below 7 |
| signal_present | TOI-451.02 | inconclusive | combined depth is 2.7 sigma, below 7 |
| signal_present | TOI-451.03 | inconclusive | combined depth is 3.1 sigma, below 7 |
| density | TOI-191.01 | fail | transit implies 0.611 g/cm3, the TIC gives 1.41 (3.5 sigma) |
| pixels | TOI-144.01 | fail | centroid offset 46.8" exceeds 15" |
| pixels | TOI-2011.02 | fail | centroid offset 69.0" exceeds 15" |
| pixels | TOI-396.03 | fail | centroid offset 35.6" exceeds 15" |
| pixels | TOI-4307.01 | fail | centroid offset 17.9" exceeds 15" |
| triceratops | TOI-1097.02 | inconclusive | mean FPP 0.0689, mean NFPP 0.00643 over 10 run(s): neither likely a planet nor likely a nearby false positive |
| triceratops | TOI-396.01 | inconclusive | mean FPP 1, mean NFPP 1.12e-21 over 10 run(s): neither likely a planet nor likely a nearby false positive |
| triceratops | TOI-451.03 | inconclusive | mean FPP 0.0523, mean NFPP 0.00808 over 10 run(s): neither likely a planet nor likely a nearby false positive |
| triceratops | TOI-747.01 | inconclusive | mean FPP 0.568, mean NFPP 7.73e-76 over 10 run(s): neither likely a planet nor likely a nearby false positive |

## Negative controls

|  | TOI-1058.01 | TOI-1175.01 | TOI-1399.01 | TOI-188.01 |
|---|---|---|---|---|
| tic | 31553893 | 30329585 | 66783360 | 280830734 |
| novelty | fail | fail | fail | fail |
| odd_even | pass | pass | pass | fail |
| secondary | pass | pass | fail | pass |
| sector_depth | pass | pass | pass | pass |
| holdout | pass | fail | pass | pass |
| signal_present | pass | pass | pass | pass |
| shape | pass | pass | pass | pass |
| density | pass | pass | fail | fail |
| radius | pass | pass | pass | pass |
| neighbours | pass | pass | pass | pass |
| possible_hosts | 7 | 13 | 17 | 3 |
| pixels |  |  |  |  |
| offset_qual_arcsec |  |  |  |  |
| triceratops | inconclusive | inconclusive | fail | inconclusive |
| fpp_mean | 0.0334 | 0.148 | 1 | 0.994 |
| fpp_sd | 0.023 | 0.0205 | 0 | 0.00217 |
| nfpp_mean | 0.027 | 0.0341 | 0.99 | 0.0186 |
| nfpp_sd | 0.0217 | 0.0096 | 0.0154 | 0.00181 |
| blockers |  | RUWE 1.48 > 1.4: an unresolved companion the priors don't condition on |  | RUWE 1.47 > 1.4: an unresolved companion the priors don't condition on |
| triceratops_run | 20261017T162256Z-vetting-triceratops-62882b5-d0f8 | 20261017T162256Z-vetting-triceratops-62882b5-d0f8 | 20261017T162256Z-vetting-triceratops-62882b5-d0f8 | 20261017T162256Z-vetting-triceratops-62882b5-d0f8 |
| superseded |  |  |  |  |

## Superseded TRICERATOPS outcomes

| signal | run | outcome | reason | replaced_by |
|---|---|---|---|---|
| TOI-4307.01 | 20261017T162256Z-vetting-triceratops-62882b5-d0f8 | inconclusive | TESScut gave 30 of 31 sectors' cutouts | 20261018T012940Z-vetting-triceratops-62882b5-e3d7 |
