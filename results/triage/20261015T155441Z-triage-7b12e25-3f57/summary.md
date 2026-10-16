# Triage (20261015T155441Z-triage-7b12e25-3f57)

Search `20261014T205855Z-search-fe29585-cdf2`: 31050 sample signals. Threshold: SDE 20.24 from `20261014T175116Z-threshold-0d6748e-40ac`. Signals at or above it: 2993.

| step | ran | pass | fail | inconclusive |
|---|---|---|---|---|
| novelty | 2993 | 2186 | 302 | 505 |
| leo_flux | 2993 | 57 | 2932 | 4 |
| pixels | 15 | 9 | 6 | 0 |

Pixels ran on the signals that passed novelty and the flux tests.
Novelty inconclusive by category: known_to_spoc 466, stale_catalog_epoch 30, no_period_object 9.
LEO-Vetter tests left unknown, in signals: asymmetric 93, chi 1, non_unique 140, odd_even 24, sinusoidal 23, unphysical_duration 29.
Signals with transits in timing-suspect sectors: 1813.
Known to SPOC only: 466. Shortlisted: 9.

## Shortlist

| tic | rank | period | t0 | duration | depth | sde | timing_suspect_transits | ruwe |
|---|---|---|---|---|---|---|---|---|
| 44926986 | 1 | 24.1145 | 1556.36 | 0.125 | 0.000776382 | 45.5103 | 1 | 0.847611 |
| 48010903 | 1 | 24.9484 | 1566.05 | 0.125 | 0.00457499 | 23.7899 | 0 | 1.01895 |
| 103312990 | 1 | 7.5232 | 1545.94 | 0.0833333 | 0.000363959 | 22.6159 | 2 | 6.20795 |
| 146282666 | 1 | 9.99509 | 1389.32 | 0.1875 | 0.000233411 | 26.0904 | 0 | 1.03945 |
| 164767175 | 1 | 5.83922 | 1387.26 | 0.125 | 0.000180262 | 20.8865 | 0 | 0.825586 |
| 296819076 | 1 | 2.27966 | 1601.01 | 0.0833333 | 0.000390382 | 20.7218 | 35 | 1.0166 |
| 399023421 | 1 | 3.92696 | 1600.85 | 0.125 | 0.000298222 | 30.6353 | 21 | 0.948516 |
| 410399327 | 1 | 34.939 | 1666.75 | 0.25 | 0.000604022 | 27.2505 | 2 | 1.02844 |
| 441010857 | 1 | 24.0539 | 1613.84 | 0.0625 | 0.0013762 | 26.585 | 0 | 1.13092 |

Literature searched for 9 shortlisted stars (`literature/`); incomplete for: TIC 44926986 (zenodo).

## Passed novelty and the flux tests, not pixels

| tic | rank | sde | ruwe | pixels | pixels_reason |
|---|---|---|---|---|---|
| 2962943 | 1 | 29.065 | 1.02087 | fail | centroid offset 19.5" exceeds 15" |
| 18008872 | 1 | 30.0699 | 0.920792 | fail | centroid offset 15.6" exceeds 15" |
| 94738387 | 1 | 32.1639 | 0.999255 | fail | centroid offset 25.9" exceeds 15" |
| 305752375 | 1 | 26.2738 | 0.777716 | fail | centroid offset 92.8" exceeds 15" |
| 423021847 | 1 | 48.3333 | 0.931037 | fail | centroid offset 23.2" exceeds 15" |
| 441269862 | 1 | 20.2531 | 0.744888 | fail | centroid offset 24.6" exceeds 15" |

Every row is a candidate signal, not a confirmed planet.
