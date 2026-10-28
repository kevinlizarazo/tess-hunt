# 2-minute cadence in Sectors $sectors to test a planet candidate on TIC $tic

[proposer name] ([institution] | [contact email])

## DDT Justification

We ask for 2-minute cadence on TIC $tic ($hip) in Sectors $sectors. Our vetting holds back its planet candidate only
because the held-out season test needs another TESS season, which these sectors would give. tess-point places the
star in no later sector through Sector $fact_last_sector_checked, and as of $facts_read it is on none of
$not_on_lists. Its fetched light curves are full-frame-image products ($products), and MAST holds QLP's only through a
partial Sector $fact_qlp_last_sector and TESS-SPOC's only through Sector $fact_tess_spoc_last_sector, so without
2-minute data these sectors may never give a testable light curve. We found the candidate in our own search on
$search_date, so could not have proposed it in an earlier Guest Investigator call, and it cannot wait for a later
one: Sector $first_sector starts on $first_start.

## Scientific Justification

If real, it is a planet of $rp_rearth Earth radii ($rp_lo to $rp_hi, 16th to 84th percentile), between Earth and
Neptune in size, on a $period_short-day orbit around a bright star (Tmag $tmag, $teff K, $radius_sun solar radii;
Stassun et al. 2019). A host this bright suits follow-up by high-resolution imaging and precise radial velocities.

A transit fit with the TIC density as a prior gives period $period d (sd $period_sd_s s), mid-time BTJD $t0 (sd
$t0_sd_min min) and duration $duration_h h; the search's depth is $depth_ppm ppm. Of our $n_checks vetting checks,
$n_passed pass and $inconclusive are inconclusive, the first only because the signal matches a SPOC
threshold-crossing event from Sector $tce_sectors that never became a TOI (Martinho and Valizadegan 2025). TRICERATOPS
(Giacalone et al. 2021) $tric_pass it as a likely planet, with a mean false-positive probability of $fpp, $nfpp of it
from nearby stars (bars $fpp_pass and $nfpp_pass). An adversarial review by an AI model ($review_model,
$review_date) rated all $review_all_notes of its findings as notes, none arguing to reject or hold it.

The held-out season test refits the ephemeris without one season and asks whether that season's transits come where,
and as deep as, predicted. With the star's Sectors $suspect_sectors left out for suspect QLP timestamps (not
redelivered for Sectors $fact_qlp_suspect_sectors), each of its $n_seasons seasons, $season_years, has
$season_training training season where the test needs $min_training_seasons, so it could test $tested. A season in
Sectors $sectors would give each season $n_seasons to train on.

The test compares depths only between light curves of one kind, and the prediction's reference depths are from
$vetted_products's PDCSAP light curves, so only PDCSAP data, from TESS-SPOC or SPOC's 2-minute pipeline (Jenkins et
al. 2016), can test it; a season holding any QLP sector cannot be tested, hence the whole season. A QLP redelivery of
the old sectors could lift the hold without testing a new prediction. 2-minute data would also give the transit's
shape at 2-minute cadence, and the cadence our rule after Giacalone et al. (2021) requires, with a contrast curve, for
a "validated planet". SPOC's 2-minute light curves of Sectors $fact_spoc_2min_latency_sectors reached MAST
$fact_spoc_2min_latency_days days after each sector ended.

The search also found a shallower dip ($second_depth_ppm ppm against $depth_ppm). Quoted word for word from the
review: "$review_F6" The finding's evidence gives eumemic's "$quote_eumemic_mes", in its "$quote_eumemic_tier", and
ends: "$quote_untested"

## Target Justification and Feasibility

One target, Tmag $tmag; none brighter than TESS magnitude $bright_limit. 2-minute cadence is needed for the reasons
above. The fit puts up to $n_windows transits in Sectors $sectors ($first_start to $last_end), each mid-time with its
standard deviation:

$windows

These windows are for observers; the test judges a refit on the $season_years seasons alone, to be deposited publicly
before Sector $first_sector starts. The vetted light curves (Sectors $vetted_sectors) show the dip at $snr sigma in
$n_transits transits, so up to $n_windows new ones should show it again.

## References

- Light curves: Jenkins, J. M., et al. 2016, Proc. SPIE, 9913, 99133E (SPOC); Caldwell, D. A., et al. 2020, RNAAS,
  4, 201 (TESS-SPOC); Huang, C. X., et al. 2020, RNAAS, 4, 204, and Kunimoto, M., et al. 2021, RNAAS, 5, 234 (QLP)
- Giacalone, S., et al. 2021, AJ, 161, 24 (TRICERATOPS); Stassun, K. G., et al. 2019, AJ, 158, 138 (TIC); Burke,
  C. J., et al. 2020, ascl:2003.001 (tess-point)
- Catalogues: Martinho, M., and Valizadegan, H. 2025, ExoMiner++ 2.0, Zenodo, doi:10.5281/zenodo.17707413;
  eumemic/exoplanets, https://github.com/eumemic/exoplanets
- The candidate's record and this proposal's sources (archive pages and target lists, read $facts_read):
  results/vetting/$signal/ and results/ddt/$signal/facts.toml in [repository URL]
