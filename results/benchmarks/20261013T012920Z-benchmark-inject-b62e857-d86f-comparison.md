# Replay comparison: OLD 20261009T181208Z-benchmark-inject-0801864-5082 (sha256 4ad757fffc817fb38d18475ebe5d3da5b42a69bb4d2552993aef93f8a497230f), NEW 20261013T012920Z-benchmark-inject-b62e857-d86f (sha256 2ffd913690e97a2a24c9d1b9fb91b2fdfd385ddc29b526ee86ee312eb0eeb1f2)

## Rows

| rows | count |
|---|---|
| OLD bls30 ok | 400 |
| NEW bls30 | 400 |
| joined (NEW ok) | 400 |
| OLD missing from NEW | 0 |
| NEW not ok | 0 |

## Same planets, same data

- pairs with any inj_* value different: 0 of 400
- pairs with expected_snr relative difference above 1e-9: 0 of 400

## Recovery by expected SNR

| bin | n | recovered before | recovered after |
|---|---|---|---|
| [0, 5) | 95 | 0.000 | 0.011 |
| [5, 7) | 14 | 0.000 | 0.000 |
| [7, 10) | 19 | 0.105 | 0.316 |
| [10, 15) | 22 | 0.682 | 0.727 |
| [15, 20) | 15 | 0.800 | 0.867 |
| [20, 50) | 52 | 0.904 | 0.962 |
| [50, inf) | 183 | 0.973 | 0.989 |
| all | 400 | 0.635 | 0.667 |

## Recovery by expected SNR, variable stars: 34 stars, 68 injections

| bin | n | recovered before | recovered after |
|---|---|---|---|
| [0, 5) | 42 | 0.000 | 0.024 |
| [5, 7) | 5 | 0.000 | 0.000 |
| [7, 10) | 9 | 0.000 | 0.111 |
| [10, 15) | 4 | 0.000 | 0.000 |
| [15, 20) | 2 | 0.000 | 0.500 |
| [20, 50) | 3 | 0.000 | 0.667 |
| [50, inf) | 3 | 0.000 | 0.333 |
| all | 68 | 0.000 | 0.088 |

## Losses (recovered before, missed after; search fields from NEW): 0

## Gains (missed before, recovered after; search fields from NEW): 13

| tic | injection | inj_period | inj_rp_rearth | expected_snr | found_period | sde | rank | top_period | top_sde | n_bls | few_transits | budget_exhausted | masked_fraction |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 30403921 | 1 | 26.0114 | 3.34 | 67.01 | 26.01188 | 16.85 | 2 | 1.92712 | 20.19 | 3 | 0 | False | 0.353 |
| 55450286 | 0 | 14.1800 | 2.45 | 10.05 | 14.18018 | 10.09 | 3 | 32.58321 | 13.36 | 3 | 0 | False | 0.041 |
| 142105613 | 1 | 16.3590 | 0.86 | 7.67 | 16.35896 | 9.66 | 1 | 16.35896 | 9.66 | 2 | 0 | False | 0.015 |
| 167163980 | 1 | 23.0287 | 3.08 | 43.39 | 23.02814 | 66.59 | 2 | 1.25163 | 73.19 | 3 | 0 | False | 0.282 |
| 167164775 | 1 | 37.3934 | 6.76 | 52.72 | 37.39443 | 24.24 | 3 | 5.77787 | 21.93 | 3 | 0 | False | 0.136 |
| 177284199 | 1 | 26.8351 | 0.76 | 7.16 | 26.83445 | 10.21 | 1 | 26.83445 | 10.21 | 2 | 0 | False | 0.015 |
| 271807631 | 0 | 25.6798 | 1.40 | 7.14 | 25.68018 | 9.61 | 2 | 14.52113 | 9.72 | 3 | 0 | False | 0.340 |
| 278989077 | 0 | 38.7704 | 2.87 | 21.37 | 38.77103 | 21.27 | 3 | 3.96007 | 18.26 | 3 | 0 | False | 0.246 |
| 300444242 | 1 | 19.4229 | 2.63 | 19.01 | 19.42280 | 15.21 | 1 | 19.42280 | 15.21 | 3 | 0 | False | 0.057 |
| 339633702 | 0 | 11.2606 | 9.92 | 260.12 | 11.26070 | 59.76 | 2 | 2.69308 | 54.38 | 3 | 0 | False | 0.197 |
| 349061976 | 1 | 10.6978 | 2.86 | 27.47 | 10.69764 | 13.26 | 2 | 2.82588 | 15.96 | 3 | 0 | False | 0.350 |
| 350518586 | 1 | 33.0530 | 1.74 | 7.68 | 33.05286 | 10.71 | 1 | 33.05286 | 10.71 | 2 | 0 | False | 0.011 |
| 453100417 | 1 | 17.3334 | 0.80 | 4.56 | 17.33295 | 9.57 | 2 | 2.89113 | 9.99 | 3 | 0 | False | 0.161 |

## Runtime per search (s)

| run | median | p90 |
|---|---|---|
| before | 120.0 | 174.3 |
| after | 117.7 | 163.1 |

## Retries (NEW)

- used retries (few_transits > 0): 5 of 400
- ran out (budget_exhausted): 0 of 400
