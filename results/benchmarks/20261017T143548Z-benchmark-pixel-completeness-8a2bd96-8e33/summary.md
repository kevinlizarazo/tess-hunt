# Pixel completeness (20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33)

The pixel check, with `triage-v1.toml`'s `[pixels]`, on 20 known planets from `known_planets.csv` at their catalog ephemerides: pass 16, fail 4, inconclusive 0. `offset_qual_arcsec` is the best-quality sector's offset.

| toi | tic | period | pixels | offset_qual_arcsec | good_sectors | pixels_reason |
|---|---|---|---|---|---|---|
| 4307.01 | 141186075 | 32.7 | fail | 17.9 | 5 | centroid offset 17.9" exceeds 15" |
| 396.03 | 178155732 | 11.2 | fail | 35.6 | 5 | centroid offset 35.6" exceeds 15" |
| 396.01 | 178155732 | 5.97 | pass | 6.73 | 5 | centroid offset 6.7" within 15" |
| 411.01 | 100990000 | 9.57 | pass | 13.4 | 5 | centroid offset 13.4" within 15" |
| 144.01 | 261136679 | 6.27 | fail | 46.8 | 5 | centroid offset 46.8" exceeds 15" |
| 1052.01 | 317060587 | 9.14 | pass | 14.5 | 5 | centroid offset 14.5" within 15" |
| 652.01 | 22221375 | 3.98 | pass | 1.83 | 5 | centroid offset 1.8" within 15" |
| 4320.01 | 404518509 | 25.1 | pass | 1.2 | 5 | centroid offset 1.2" within 15" |
| 451.02 | 257605131 | 1.86 | pass | 2.17 | 5 | centroid offset 2.2" within 15" |
| 2011.02 | 136916387 | 27.6 | fail | 69 | 5 | centroid offset 69.0" exceeds 15" |
| 755.01 | 73228647 | 2.54 | pass | 4.22 | 5 | centroid offset 4.2" within 15" |
| 1097.02 | 360630575 | 13.9 | pass | 1.26 | 5 | centroid offset 1.3" within 15" |
| 763.02 | 178819686 | 12.3 | pass | 9.93 | 5 | centroid offset 9.9" within 15" |
| 451.03 | 257605131 | 9.19 | pass | 1.69 | 5 | centroid offset 1.7" within 15" |
| 118.01 | 266980320 | 6.03 | pass | 1.17 | 5 | centroid offset 1.2" within 15" |
| 576.01 | 408310006 | 5.44 | pass | 3.59 | 5 | centroid offset 3.6" within 15" |
| 747.01 | 15445551 | 1.68 | pass | 1.29 | 5 | centroid offset 1.3" within 15" |
| 826.01 | 243200602 | 11.6 | pass | 0.832 | 5 | centroid offset 0.8" within 15" |
| 107.01 | 92352620 | 3.95 | pass | 0.743 | 5 | centroid offset 0.7" within 15" |
| 191.01 | 183532609 | 8.16 | pass | 2.23 | 5 | centroid offset 2.2" within 15" |
