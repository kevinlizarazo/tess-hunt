# 2-minute cadence in Sectors 112, 113 and 114 for a sub-Neptune candidate on HIP 67102 (TIC 241522065)

[proposer name] ([institution] | [contact email])

## DDT Justification

I request 2-minute cadence for TIC 241522065 (HIP 67102) in Sectors 112, 113 and 114 to test a transiting sub-Neptune candidate. The
signal was a SPOC threshold-crossing event in Sector 38 that never became a TOI (Martinho and Valizadegan
2025); my own search recovered it on 2026-10-14, after the previous Guest Investigator call. It cannot wait for the
next call: Sector 112 begins on 2026-12-22, and tess-point (Burke et al. 2020) places the star in no later
sector through Sector 134. As of 2026-10-27 it is on none of the final 2-min and 20-s target lists for Sector 110 or the Guest Investigator priority lists for Sectors 111 to 114, so unless a later
list adds it, TESS will observe it only in full-frame images.

## Scientific Justification

The candidate transits every 17.4 days with a depth of about 505 ppm. A fit with the TIC stellar
density as a prior gives a radius of 3.11 Earth radii (3.00 to 3.22, 16th to 84th percentile) around a
bright star (Tmag 8.34, Teff 6260 K, 1.30 solar radii; Stassun et al. 2019), which suits the high-resolution
imaging and precise radial velocities that would confirm the planet and measure its mass.

In TESS-SPOC PDCSAP light curves (Caldwell et al. 2020) of Sectors 38, 64 and 65 the transit is detected at
11.1 sigma over 5 transits. The fit gives a period of 17.436716 d (sd 8.4 s), a mid-transit time of
BTJD 2340.4325 (sd 4.5 min) and a duration of 4.03 h. Odd and even transits agree in depth, there is no
secondary eclipse, the depth is stable between sectors, the transit is U-shaped, and the stellar density from a fit
without the prior agrees with the TIC value. With TRICERATOPS (Giacalone et al. 2021) the candidate passes as a
likely planet: the mean false-positive probability is 0.0215 and the nearby false-positive probability 0.000148, against
limits of 0.5 and 0.001.

![Figure 1. The transit in each of the star's 2 seasons with reliable timestamps, 2021 and 2023, folded on the fitted period (TESS-SPOC PDCSAP light curves).](../../vetting/241522065-1/plots/folds.png)

One test remains open: whether a fit to some TESS seasons predicts the transit times and depth in a season left out.
It needs at least 2 seasons in each fit, and the star has 2 seasons with reliable
timestamps, 2021 and 2023, so the test cannot run. Its later Sectors 99, 101 and 102 are QLP light curves (Huang et
al. 2020; Kunimoto et al. 2021) with a known barycentric timing error, not yet redelivered with corrected timestamps
for Sectors 99 to 104. With those sectors kept in, the test passes, but I do not count
a pass that rests on suspect timestamps. Another season in Sectors 112, 113 and 114 would leave 2 seasons in every
fit, and the new season would itself test a prediction published in advance.

The search also found a shallower periodic dip at 5.58 d (127 ppm against 505 ppm),
not a harmonic of the main period, which an independent community search (eumemic/exoplanets) also lists. I have not
tested whether it comes from the target; if it does, the star hosts two transiting candidates, and these sectors would
cover both.

## Target Justification and Feasibility

One target, Tmag 8.34; none is brighter than Tmag 7.

The prediction test compares depths only between light curves from one pipeline. The earlier seasons are
TESS-SPOC PDCSAP light curves, so the new season must also be SPOC PDCSAP photometry, from TESS-SPOC or from
SPOC's 2-minute processing (Jenkins et al. 2016). All of the star's light curves so far are full-frame-image products
(QLP and TESS-SPOC). As of 2026-10-27, MAST holds TESS-SPOC light curves only through Sector 85 and
QLP light curves only through part of Sector 105, while SPOC 2-minute light curves of Sectors
105 to 107 reached MAST 24 to 38 days after each sector ended. The 2-minute
data would also sample ingress and egress more finely. I apply the validation thresholds of Giacalone et al. (2021),
as opposed to their likely-planet limits, only to a TRICERATOPS analysis of 2-minute data with a high-resolution
contrast curve.

The fit predicts up to 5 transits in Sectors 112, 113 and 114 (2026-12-22 to 2027-03-14):

| Sector | Epoch | Mid (BTJD) | Mid (UTC, seen from Earth) | sd (min) |
|---|---|---|---|---|
| 112 | 118 | 4397.965 | 2026-12-23 11:12 | 13.3 |
| 112 | 119 | 4415.402 | 2027-01-09 21:40 | 13.5 |
| 113 | 120 | 4432.838 | 2027-01-27 08:07 | 13.6 |
| 114 | 121 | 4450.275 | 2027-02-13 18:34 | 13.8 |
| 114 | 122 | 4467.712 | 2027-03-03 05:01 | 13.9 |

If all fall in the data, the signal should be detected about as strongly as in the earlier sectors. Before Sector
112 begins I will deposit publicly the transit times and depth predicted from the 2021 and 2023 seasons
alone.

## References

- Light curves: Jenkins, J. M., et al. 2016, Proc. SPIE, 9913, 99133E (SPOC); Caldwell, D. A., et al. 2020, RNAAS,
  4, 201 (TESS-SPOC); Huang, C. X., et al. 2020, RNAAS, 4, 204, and Kunimoto, M., et al. 2021, RNAAS, 5, 234 (QLP)
- Giacalone, S., et al. 2021, AJ, 161, 24 (TRICERATOPS); Stassun, K. G., et al. 2019, AJ, 158, 138 (TIC); Burke,
  C. J., et al. 2020, ascl:2003.001 (tess-point)
- Catalogues: Martinho, M., and Valizadegan, H. 2025, ExoMiner++ 2.0, Zenodo, doi:10.5281/zenodo.17707413;
  eumemic/exoplanets, https://github.com/eumemic/exoplanets
- The candidate's vetting record, and the dated source of each archive and target-list fact above:
  results/vetting/241522065-1/ and results/ddt/241522065-1/facts.toml in [repository URL]. The search and vetting code and
  this text were written with LLM assistance.
