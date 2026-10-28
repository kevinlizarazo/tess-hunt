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
`dois.toml`, once the maintainer writes it, holds the DOI and publication date Zenodo gave each package.

| Package | Made | Signals | DOI |
|---|---|---|---|
| [`20261028T191024Z-predictions-cb70b2d-29d6`](20261028T191024Z-predictions-cb70b2d-29d6/README.md) | 2026-10-28 | 103312990-1, 241522065-1, 296819076-1, 399023421-1, 423100454-1 and 438857197-1 | DOI pending |
