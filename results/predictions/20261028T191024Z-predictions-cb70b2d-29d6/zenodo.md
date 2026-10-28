# Zenodo metadata

The deposit's fields, to paste into Zenodo's form. Creators and the link to the code are filled in at deposit.

## Title

Preregistered transit predictions for 6 held tess-hunt planet-candidate signals in TESS Sectors 112 to 114

## Resource type

Dataset

## Description

Predictions, fixed before TESS observes them, of where 6 held planet-candidate signals from tess-hunt's search
of public TESS light curves should transit in Sectors 112 to 114, and the test that will judge each
one. Each prediction is the refit that tess-hunt's held-out season check (vet-v3) makes when the season these sectors
make is held out, on the light curve the signal was vetted on, with the training depths that season will be compared
with. The signals are 103312990-1, 241522065-1, 296819076-1, 399023421-1, 423100454-1 and 438857197-1, on TIC 103312990, 241522065, 296819076, 399023421, 423100454 and 438857197. Each is a candidate signal, not a planet.

The package was made by run 20261028T191024Z-predictions-cb70b2d-29d6 at tess-hunt commit cb70b2dc610969c7f5a3f3f7699ac9ddf0d59a33, from the vetting records of run 20261020T174317Z-vetting-run-61b5944-2d70. Zenodo
lets a record's owner open an edit of its files within 30 days of publication and publish it
within 45 days (as read on 2026-10-28), so the files are fixed
45 days after publication; deposited by 2026-11-05, this package's files are fixed by
2026-12-20, and no sector starting earlier is predicted. Each signal is judged once, on its complete new season in a
light curve fetched before 2027-12-31; data fetched on or after that date complete no season, and a season that still
lacks a predicted sector in a re-vet judged as of that date or later stays untested. The README states the test, the
data that can test each signal, when it is judged and what a result means. tess-hunt's code and the package's text
were written with LLM assistance, and the adversarial review of 399023421-1 that the README quotes was written by an AI model.

## Keywords

- TESS
- transiting exoplanets
- planet candidates
- preregistration
- transit timing prediction

## Licence

Creative Commons Attribution 4.0 International (CC BY 4.0)
