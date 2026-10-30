# 2-minute cadence in Sectors $sectors for a sub-Neptune candidate on $hip (TIC $tic)

[proposer name] ([institution] | [contact email])

## DDT Justification

I request 2-minute cadence for TIC $tic ($hip) in Sectors $sectors to test a transiting sub-Neptune candidate. The
signal was a SPOC threshold-crossing event in Sector $tce_sectors that never became a TOI (Martinho and Valizadegan
2025); my own search recovered it on $search_date, after the previous Guest Investigator call. It cannot wait for the
next call: Sector $first_sector begins on $first_start, and tess-point (Burke et al. 2020) places the star in no later
sector through Sector $fact_last_sector_checked. As of $facts_read it is on none of $not_on_lists, so unless a later
list adds it, TESS will observe it only in full-frame images.

## Scientific Justification

The candidate transits every $period_short days with a depth of about $depth_ppm ppm. A fit with the TIC stellar
density as a prior gives a radius of $rp_rearth Earth radii ($rp_lo to $rp_hi, 16th to 84th percentile) around a
bright star (Tmag $tmag, Teff $teff K, $radius_sun solar radii; Stassun et al. 2019), which suits the high-resolution
imaging and precise radial velocities that would confirm the planet and measure its mass.

In $vetted_products PDCSAP light curves (Caldwell et al. 2020) of Sectors $vetted_sectors the transit is detected at
$snr sigma over $n_transits transits. The fit gives a period of $period d (sd $period_sd_s s), a mid-transit time of
BTJD $t0 (sd $t0_sd_min min) and a duration of $duration_h h. Odd and even transits agree in depth, there is no
secondary eclipse, the depth is stable between sectors, the transit is U-shaped, and the stellar density from a fit
without the prior agrees with the TIC value. With TRICERATOPS (Giacalone et al. 2021) the candidate $tric_pass as a
likely planet: the mean false-positive probability is $fpp and the nearby false-positive probability $nfpp, against
limits of $fpp_pass and $nfpp_pass.

![Figure 1. The transit in each of the star's $n_seasons seasons with reliable timestamps, $season_years, folded on the fitted period ($vetted_products PDCSAP light curves).](../../vetting/$signal/plots/folds.png)

One test remains open: whether a fit to some TESS seasons predicts the transit times and depth in a season left out.
It needs at least $min_training_seasons seasons in each fit, and the star has $n_seasons seasons with reliable
timestamps, $season_years, so the test cannot run. Its later Sectors $suspect_sectors are QLP light curves (Huang et
al. 2020; Kunimoto et al. 2021) with a known barycentric timing error, not yet redelivered with corrected timestamps
for Sectors $fact_qlp_suspect_sectors. With those sectors kept in, the test $holdout_with_suspect, but I do not count
a pass that rests on suspect timestamps. Another season in Sectors $sectors would leave $n_seasons seasons in every
fit, and the new season would itself test a prediction published in advance.

The search also found a shallower periodic dip at $second_period d ($second_depth_ppm ppm against $depth_ppm ppm),
not a harmonic of the main period, which an independent community search (eumemic/exoplanets) also lists. I have not
tested whether it comes from the target; if it does, the star hosts two transiting candidates, and these sectors would
cover both.

## Target Justification and Feasibility

One target, Tmag $tmag; none is brighter than Tmag $bright_limit.

The prediction test compares depths only between light curves from one pipeline. The earlier seasons are
$vetted_products PDCSAP light curves, so the new season must also be SPOC PDCSAP photometry, from TESS-SPOC or from
SPOC's 2-minute processing (Jenkins et al. 2016). All of the star's light curves so far are full-frame-image products
($products). As of $facts_read, MAST holds TESS-SPOC light curves only through Sector $fact_tess_spoc_last_sector and
QLP light curves only through part of Sector $fact_qlp_last_sector, while SPOC 2-minute light curves of Sectors
$fact_spoc_2min_latency_sectors reached MAST $fact_spoc_2min_latency_days days after each sector ended. The 2-minute
data would also sample ingress and egress more finely. I apply the validation thresholds of Giacalone et al. (2021),
as opposed to their likely-planet limits, only to a TRICERATOPS analysis of 2-minute data with a high-resolution
contrast curve.

The fit predicts up to $n_windows transits in Sectors $sectors ($first_start to $last_end):

$windows

If all fall in the data, the signal should be detected about as strongly as in the earlier sectors. Before Sector
$first_sector begins I will deposit publicly the transit times and depth predicted from the $season_years seasons
alone.

## References

- Light curves: Jenkins, J. M., et al. 2016, Proc. SPIE, 9913, 99133E (SPOC); Caldwell, D. A., et al. 2020, RNAAS,
  4, 201 (TESS-SPOC); Huang, C. X., et al. 2020, RNAAS, 4, 204, and Kunimoto, M., et al. 2021, RNAAS, 5, 234 (QLP)
- Giacalone, S., et al. 2021, AJ, 161, 24 (TRICERATOPS); Stassun, K. G., et al. 2019, AJ, 158, 138 (TIC); Burke,
  C. J., et al. 2020, ascl:2003.001 (tess-point)
- Catalogues: Martinho, M., and Valizadegan, H. 2025, ExoMiner++ 2.0, Zenodo, doi:10.5281/zenodo.17707413;
  eumemic/exoplanets, https://github.com/eumemic/exoplanets
- The candidate's vetting record, and the dated source of each archive and target-list fact above:
  results/vetting/$signal/ and results/ddt/$signal/facts.toml in [repository URL]. The search and vetting code and
  this text were written with LLM assistance.
