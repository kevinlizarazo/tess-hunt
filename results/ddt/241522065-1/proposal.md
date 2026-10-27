# 2-minute cadence in Sectors 112, 113 and 114 for a held planet candidate on TIC 241522065

<proposer name> (<institution> | <contact email>)

## DDT Justification

We ask for 2-minute cadence on one star, TIC 241522065 (HIP 67102, HD 119555, TYC 8663-626-1, 2MASS J13451278-5318310), in Sectors 112, 113 and 114. Its planet candidate, 241522065-1, is
held for one reason: the held-out season test needs a third TESS season, and these sectors are that season.
tess-point places the star in no later sector through Sector 134. Every sector fetched so far
has only full-frame-image light curves of it (QLP at 600 and 200 s; TESS-SPOC at 600 and 200 s), and as of 2026-10-27 MAST holds QLP light curves only
through a partial Sector 105 and TESS-SPOC's only through Sector 85.
Without 2-minute data these sectors may never become a light curve that can test the candidate.

The candidate came out of this project's own search (run 20261014T205855Z-search-fe29585-cdf2, 2026-10-14 UTC) and was held on 2026-10-22,
so we could not have proposed it in an earlier Guest Investigator call. Nor can it wait for a later call: Sector
112 starts on 2026-12-22, Sector 114 ends on 2027-03-14, and after them, through Sector
134, there is no TESS look at this star to ask for.

## Scientific Justification

TIC 241522065 has Tmag 8.34, Teff 6260 K and a radius of 1.30 solar radii (TIC). The search found a 505 ppm
dip. A transit fit with the TIC density as a prior gives period 17.436716 d (sd 9.7e-05 d), t0 BTJD 2340.4325 (sd 0.0031
d), duration 4.03 h and a radius of 3.11 Earth radii (16th to 84th percentile 3.00 to 3.22). Of
vet-v3's 9 checks, all pass but novelty (inconclusive: matches only SPOC TCE or ExoMiner rows) and holdout (inconclusive: 0 season(s) could be tested; need 2); novelty is inconclusive only because the signal matches ExoMiner vetting_catalog_FFI 241522065-1-S38, a
SPOC TCE that never became a TOI. TRICERATOPS (Giacalone et al. 2021): pass, mean FPP 0.0215 < 0.5 and mean NFPP 0.000148 < 0.001 over 10 run(s): likely a planet. An adversarial review
(2026-10-21) left no confirmed kill or hold among its 7 findings.

The held-out season test refits the ephemeris without one season and asks whether that season's transits appear
where and as deep as the refit predicts. QLP's Sectors 99 to 104 carry suspect timestamps and have not
been redelivered, so the star's Sectors 99, 101 and 102 are left out. That leaves the seasons of 2021 and 2023, and
with either held out the record reads "1 training season(s), need 2: one season can't predict a season a year away". A third season gives each season two others to train on.

The new season can test the prediction only in the product family its training seasons are in, since the test
compares depths within a family: here PDCSAP, from TESS-SPOC's full-frame light curves (stopped, above) or SPOC's
2-minute ones. We ask for the whole season because one mixing a QLP sector with 2-minute ones would be untestable:
QLP has no training data for this star. A QLP redelivery of the old sectors could lift the hold, but would
test no prediction made before its data.

2-minute data would also give a light curve within 24 to 38 days of each sector's end, SPOC's
recent latency; the transit's shape at 2-minute cadence; and one condition of our rule, after Giacalone et al.
(2021), for TRICERATOPS's "validated planet" label. The others include a contrast curve from high-resolution imaging,
which would also test a Hipparcos-Gaia acceleration the review notes (its finding F3).

The star may hold a second candidate. Quoted word for word from the review's finding F6: "The star carries a second periodic dip at 5.581 d, found by the search (rank 2) and published by eumemic, at a period ratio of 3.124 that is no harmonic and no eclipsing-binary pair; if both are on the target this is a two-candidate system, which by itself lowers the false-positive odds."

Before Sector 112 starts we will deposit publicly the prediction the test will judge, refit on the
2021 and 2023 seasons alone, so the new season tests a prediction fixed before its data exist.

## Target Justification and Feasibility

One target, TIC 241522065, Tmag 8.34; sources brighter than magnitude 7: 0. 2-minute cadence is needed
because it is the only product that can test the new season (above). tess-point places the star in Sectors 112, 113 and 114
(2026-12-22 to 2027-03-14), and the density-prior fit puts 5 transits in them:

| Sector | Epoch | Mid (BTJD) | Mid (UTC) | sd (min) |
|---|---|---|---|---|
| 112 | 118 | 4397.965 | 2026-12-23 11:12 | 13.3 |
| 112 | 119 | 4415.402 | 2027-01-09 21:40 | 13.5 |
| 113 | 120 | 4432.838 | 2027-01-27 08:07 | 13.6 |
| 114 | 121 | 4450.275 | 2027-02-13 18:34 | 13.8 |
| 114 | 122 | 4467.712 | 2027-03-03 05:01 | 13.9 |

Mid (UTC) is when the transit is seen from Earth; sd is the mid-time's standard deviation over the fit's posterior.
These windows are for observers; the test judges the deposited refit. The vetted full-frame light curves (Sectors
38, 64 and 65, at 600 and 200 s) detect the dip at 11.1 sigma over 5 transits, so the 5
predicted transits should detect it again at 2-minute cadence.

## References

- Burke, C. J., et al. 2020, tess-point, ascl:2003.001
- Caldwell, D. A., et al. 2020, RNAAS, 4, 201 (TESS-SPOC)
- eumemic/exoplanets, https://github.com/eumemic/exoplanets (the second candidate)
- Giacalone, S., et al. 2021, AJ, 161, 24 (TRICERATOPS)
- Huang, C. X., et al. 2020, RNAAS, 4, 204; Kunimoto, M., et al. 2021, RNAAS, 5, 234 (QLP)
- The candidate's record, `results/vetting/241522065-1/`, and this proposal's sources, `results/ddt/241522065-1/`, in this
  project's repository: <repository URL>
- Archive state and sector dates, read 2026-10-27: https://archive.stsci.edu/hlsps/qlp/; https://archive.stsci.edu/hlsp/qlp; https://archive.stsci.edu/hlsp/tess-spoc; https://archive.stsci.edu/missions/tess/download_scripts/sector/; https://tess.mit.edu/observations/sector-112/; https://tess.mit.edu/observations/sector-113/; https://tess.mit.edu/observations/sector-114/; https://github.com/tessgi/tess-point
