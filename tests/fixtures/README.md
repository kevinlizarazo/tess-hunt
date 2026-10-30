# Test fixtures

Two public light curves of Pi Mensae (TIC 261136679), TESS Sector 1, downloaded unchanged from the public TESS
bucket on AWS (`s3://stpubdata`).

| File | Product | License | DOI | Cite |
|---|---|---|---|---|
| `hlsp_qlp_tess_ffi_s0001-0000000261136679_tess_v01_llc.fits` | QLP | CC BY 4.0 | 10.17909/t9-r086-e880 | Huang et al. 2020a, 2020b |
| `hlsp_tess-spoc_tess_phot_0000000261136679-s0001_tess_v1_lc.fits` | TESS-SPOC | CC BY 4.0 | 10.17909/t9-wpz1-8s54 | Caldwell et al. 2020 |

`m4-refactor/holdout.json` and `m4-refactor/vet.json` hold the held-out check's evidence and vet's report on the
synthetic light curves of `test_holdout.py` and `test_vet.py` (vet's fit stopped before sampling), written by the code
as it stood before M4 lifted vet's light-curve preparation and the held-out judgement out of their functions. The
tests compare to them, so a change to either output fails.
