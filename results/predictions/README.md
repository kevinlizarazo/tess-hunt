# Predictions

Each directory here is one package of preregistered transit predictions for held signals
([decision 0040](../../docs/decisions/0040-predictions-for-held-signals.md)). A package is made by one production
run of `tess-hunt predictions run` and copied unchanged from its run directory by `tess-hunt predictions publish`.
Its `README.md` says what is predicted, the test that will judge it, and when.

The maintainer deposits each package directory as one Zenodo record, with the form text that
`tess-hunt predictions zenodo --run RUN_ID` prints. Zenodo lets a record's owner open an edit of its files within
30 days of publishing and publish it within 45 days
(as read on 2026-10-28); after that the files are fixed. Published packages are never edited: a correction is a
new package.

[facts.toml](facts.toml) holds the facts the packages state, each with its source and the date it was read.
`dois.toml` holds the DOI and publication date Zenodo gave each deposited package.

| Package | Made | Signals | DOI |
|---|---|---|---|
| [`20261028T204003Z-predictions-98bf417-0ef5`](20261028T204003Z-predictions-98bf417-0ef5/README.md) | 2026-10-28 | 103312990-1, 241522065-1, 296819076-1, 399023421-1, 423100454-1 and 438857197-1 | [10.5281/zenodo.23745923](https://doi.org/10.5281/zenodo.23745923), published 2026-10-28 |

## Credits

The packages are derived from TESS light curves from MAST and from stellar parameters in the TESS Input Catalog.
Reuse of a package must carry the acknowledgements and citations in [ACKNOWLEDGEMENTS.md](../../ACKNOWLEDGEMENTS.md)
that apply to it: the TESS acknowledgement, QLP's if the package was trained on QLP light curves, the light-curve
products it used with their sectors, and the TIC's papers. Each deposited package's Zenodo record carries them in
its description.
