# 2-minute cadence in Sectors 112, 113 and 114 to test a planet candidate on TIC 241522065

[proposer name] ([institution] | [contact email])

## DDT Justification

We ask for 2-minute cadence on TIC 241522065 (HIP 67102) in Sectors 112, 113 and 114. Our vetting holds back its planet candidate only
because the held-out season test needs another TESS season, which these sectors would give. tess-point places the
star in no later sector through Sector 134, and as of 2026-10-27 it is on none of
the final 2-min and 20-s target lists for Sector 110 or the Guest Investigator priority lists for Sectors 111 to 114. Its fetched light curves are full-frame-image products (QLP and TESS-SPOC), and MAST holds QLP's only through a
partial Sector 105 and TESS-SPOC's only through Sector 85, so without
2-minute data these sectors may never give a testable light curve. We found the candidate in our own search on
2026-10-14, so could not have proposed it in an earlier Guest Investigator call, and it cannot wait for a later
one: Sector 112 starts on 2026-12-22.

## Scientific Justification

If real, it is a planet of 3.11 Earth radii (3.00 to 3.22, 16th to 84th percentile), between Earth and
Neptune in size, on a 17.4-day orbit around a bright star (Tmag 8.34, 6260 K, 1.30 solar radii;
Stassun et al. 2019). A host this bright allows the imaging and radial velocities that would confirm it, once its
ephemeris is tested.

A transit fit with the TIC density as a prior gives period 17.436716 d (sd 8.4 s), mid-time BTJD 2340.4325 (sd
4.5 min) and duration 4.03 h; the search's depth is 505 ppm. Of our 9 vetting checks,
7 pass and the check against known objects and the held-out season test are inconclusive, the first only because the signal matches a SPOC
threshold-crossing event from Sector 38 that never became a TOI (Martinho & Valizadegan 2025). TRICERATOPS
(Giacalone et al. 2021) passes it as a likely planet, with a mean false-positive probability of 0.0215, 0.000148 of it
from nearby stars (bars 0.5 and 0.001). An adversarial review by an AI model (claude-opus-5-5,
2026-10-21) rated all 7 of its findings as notes, none arguing to reject or hold it.

The held-out season test refits the ephemeris without one season and asks whether that season's transits come where,
and as deep as, predicted. With the star's Sectors 99, 101 and 102 left out for suspect QLP timestamps (not
redelivered for Sectors 99 to 104), each of its 2 seasons, 2021 and 2023, has
1 training season where the test needs 2, so it could test none. A season in
Sectors 112, 113 and 114 would give each season 2 to train on.

The test compares depths only between light curves of one kind, and the prediction's reference depths are from
TESS-SPOC's PDCSAP light curves, so only PDCSAP data, from TESS-SPOC or SPOC's 2-minute pipeline (Jenkins et
al. 2016), can test it; a season holding any QLP sector cannot be tested, hence the whole season. A QLP redelivery of
the old sectors could lift the hold without testing a new prediction. 2-minute data would also give a light curve
within 24 to 38 days of each sector's end, the transit's shape at 2-minute cadence, and the
cadence our rule after Giacalone et al. (2021) requires, with a contrast curve, for a "validated planet".

The search also found a shallower dip (127 ppm against 505). Quoted word for word from the
review: "The star carries a second periodic dip at 5.581 d, found by the search (rank 2) and published by eumemic, at a period ratio of 3.124 that is no harmonic and no eclipsing-binary pair; if both are on the target this is a two-candidate system, which by itself lowers the false-positive odds." The finding's evidence gives eumemic's "MES 8.9", in "tier C (MES < 10)", and
ends: "Whether the 5.58 d dip is on the target was not tested here."

## Target Justification and Feasibility

One target, Tmag 8.34; none brighter than TESS magnitude 7. 2-minute cadence is needed for the reasons
above. The fit puts up to 5 transits in Sectors 112, 113 and 114 (2026-12-22 to 2027-03-14), each mid-time with its
standard deviation:

| Sector | Epoch | Mid (BTJD) | Mid (UTC, seen from Earth) | sd (min) |
|---|---|---|---|---|
| 112 | 118 | 4397.965 | 2026-12-23 11:12 | 13.3 |
| 112 | 119 | 4415.402 | 2027-01-09 21:40 | 13.5 |
| 113 | 120 | 4432.838 | 2027-01-27 08:07 | 13.6 |
| 114 | 121 | 4450.275 | 2027-02-13 18:34 | 13.8 |
| 114 | 122 | 4467.712 | 2027-03-03 05:01 | 13.9 |

These windows are for observers; the test judges a refit on the 2021 and 2023 seasons alone, to be deposited publicly
before Sector 112 starts. The vetted light curves (Sectors 38, 64 and 65) show the dip at 11.1 sigma in
5 transits, so up to 5 new ones should show it again.

## References

- Light curves: Jenkins, J. M., et al. 2016, Proc. SPIE, 9913, 99133E (SPOC); Caldwell, D. A., et al. 2020, RNAAS,
  4, 201 (TESS-SPOC); Huang, C. X., et al. 2020, RNAAS, 4, 204, and Kunimoto, M., et al. 2021, RNAAS, 5, 234 (QLP)
- Giacalone, S., et al. 2021, AJ, 161, 24 (TRICERATOPS); Stassun, K. G., et al. 2019, AJ, 158, 138 (TIC); Burke,
  C. J., et al. 2020, ascl:2003.001 (tess-point)
- Catalogues: Martinho, M., & Valizadegan, H. 2025, ExoMiner++ 2.0, Zenodo, doi:10.5281/zenodo.17707413;
  eumemic/exoplanets, https://github.com/eumemic/exoplanets
- The candidate's record and this proposal's sources (archive pages and target lists, read 2026-10-27):
  `results/vetting/241522065-1/` and `results/ddt/241522065-1/facts.toml` in [repository URL]
