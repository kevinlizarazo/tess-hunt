# Triage completeness (20261017T040740Z-benchmark-triage-completeness-e6719c6-f34c)

Inject run `20261015T131443Z-benchmark-inject-fe29585-8496`: 2000 injections searched, 769 recovered at SDE 20.24 or above (the threshold from `20261014T175116Z-threshold-0d6748e-40ac`). Each recovered injection was planted and searched again as the inject run did it, then judged by novelty and LEO-Vetter's flux tests as triage run `20261015T155441Z-triage-7b12e25-3f57` judged its signals, on the signal the search matched to the injection, with the star's other signals at or above the threshold dropped.

Judged: 769. Not reproduced: 0 (the search did not match the injection at the rank, period and SDE the inject run recorded). Errors: 0. Only judged injections enter the shares below.

| step | pass | fail | inconclusive |
|---|---|---|---|
| novelty | 766 | 0 | 3 |
| leo_flux | 637 | 123 | 9 |

`search` is the inject run's search completeness over the injections it searched. `leo_pc`, `novelty_pass` and `triage_pass` (both passed) are shares of the judged injections; `product` is `search` times `triage_pass`. Pixels are not replayed: an injected transit is not in the pixels, so `benchmark pixel-completeness` measures that step on the known planets.

## By expected SNR

| engine | bin | searched | search | judged | leo_pc | novelty_pass | triage_pass | product |
|---|---|---|---|---|---|---|---|---|
| bls30 | [0.0, 5.0) | 755 | 0 | 0 | nan | nan | nan | nan |
| bls30 | [5.0, 7.0) | 89 | 0 | 0 | nan | nan | nan | nan |
| bls30 | [7.0, 10.0) | 105 | 0 | 0 | nan | nan | nan | nan |
| bls30 | [10.0, 15.0) | 111 | 0.0541 | 6 | 0.833 | 1 | 0.833 | 0.045 |
| bls30 | [15.0, 20.0) | 79 | 0.43 | 34 | 0.824 | 1 | 0.824 | 0.354 |
| bls30 | [20.0, 50.0) | 290 | 0.686 | 199 | 0.844 | 1 | 0.844 | 0.579 |
| bls30 | [50.0, inf) | 571 | 0.928 | 530 | 0.823 | 0.994 | 0.819 | 0.76 |

## By injected period (days)

| engine | bin | searched | search | judged | leo_pc | novelty_pass | triage_pass | product |
|---|---|---|---|---|---|---|---|---|
| bls30 | [1, 2) | 45 | 0.489 | 22 | 0.909 | 0.955 | 0.864 | 0.422 |
| bls30 | [2, 4) | 117 | 0.504 | 59 | 0.932 | 0.983 | 0.915 | 0.462 |
| bls30 | [4, 8) | 232 | 0.474 | 110 | 0.945 | 0.991 | 0.945 | 0.448 |
| bls30 | [8, 16) | 418 | 0.423 | 177 | 0.864 | 1 | 0.864 | 0.366 |
| bls30 | [16, 40) | 1188 | 0.338 | 401 | 0.761 | 1 | 0.761 | 0.257 |

## By injected radius (Earth radii)

| engine | bin | searched | search | judged | leo_pc | novelty_pass | triage_pass | product |
|---|---|---|---|---|---|---|---|---|
| bls30 | [0.5, 1.0) | 402 | 0 | 0 | nan | nan | nan | nan |
| bls30 | [1.0, 2.0) | 400 | 0.0125 | 5 | 1 | 1 | 1 | 0.0125 |
| bls30 | [2.0, 4.0) | 393 | 0.285 | 112 | 0.866 | 1 | 0.866 | 0.247 |
| bls30 | [4.0, 8.0) | 408 | 0.743 | 303 | 0.861 | 1 | 0.861 | 0.64 |
| bls30 | [8.0, 16.0) | 397 | 0.879 | 349 | 0.785 | 0.991 | 0.779 | 0.685 |

## LEO-Vetter tests failed or not judged

| kind | test | injections |
|---|---|---|
| fa_failed | chases | 3 |
| fa_failed | chi | 8 |
| fa_failed | data_gapped | 15 |
| fa_failed | dmm | 5 |
| fa_failed | invalid_transits | 26 |
| fa_failed | non_unique | 20 |
| fa_failed | single_event | 7 |
| fa_failed | sinusoidal | 4 |
| fa_failed | unphysical_duration | 2 |
| fa_failed | weak | 4 |
| fp_failed | odd_even | 36 |
| fp_failed | secondary | 24 |
| unknown | asymmetric | 1 |
| unknown | odd_even | 9 |
