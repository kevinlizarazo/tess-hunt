# 2-minute cadence in Sectors $sectors for a held planet candidate on TIC $tic

[proposer name] ([institution] | [contact email])

## DDT Justification

We ask for 2-minute cadence on one star, TIC $tic ($names), in Sectors $sectors. Its planet candidate, $signal, is
held for one reason: the held-out season test needs another TESS season, and these sectors would be it. tess-point
places the star in no later sector through Sector $fact_last_sector_checked. Every sector fetched so far gave only
full-frame-image light curves ($products), and as of $facts_read MAST holds QLP light curves only through a
partial Sector $fact_qlp_last_sector and TESS-SPOC's only through Sector $fact_tess_spoc_last_sector. Without 2-minute
data these sectors may never become a light curve that can test the candidate.

The candidate came out of our own search (run $search_run, $search_date UTC) and was held on $call_date,
so we could not have proposed it in an earlier Guest Investigator call. Nor can it wait for a later call: Sector
$first_sector starts on $first_start, Sector $last_sector ends on $last_end, and after them, through Sector
$fact_last_sector_checked, there is no TESS look at this star to ask for.

## Scientific Justification

TIC $tic has Tmag $tmag, Teff $teff K and a radius of $radius_sun solar radii (TIC). The search found a $depth_ppm ppm
dip. A transit fit with the TIC density as a prior gives period $period d (sd $period_sd d), t0 BTJD $t0 (sd $t0_sd
d), duration $duration_h h and a radius of $rp_rearth Earth radii (16th to 84th percentile $rp_lo to $rp_hi). Of the
$n_checks checks in our vetting criteria, $criteria, $n_passed pass and $inconclusive are inconclusive. Novelty is
inconclusive only because the signal matches $tce, a SPOC TCE that never became a TOI; holdout is the test below.
TRICERATOPS (Giacalone et al. 2021) gives mean FPP $fpp and NFPP $nfpp over $tric_runs runs; its outcome is
$tric_outcome, where a pass ("likely planet") needs them below $fpp_pass and $nfpp_pass. An
adversarial review ($review_date) left $review_confirmed confirmed kill or hold among its $review_findings findings.

The held-out season test refits the ephemeris without one season and asks whether that season's transits appear
where and as deep as the refit predicts. QLP's Sectors $fact_qlp_suspect_sectors carry suspect timestamps and have not
been redelivered, so the star's Sectors $suspect_sectors are left out. That leaves $n_seasons seasons, $season_years.
Held out in turn, each has $season_training training season where the test needs $min_training_seasons, so
$n_tested of them could be tested and the check is $holdout_outcome. A season in Sectors $sectors would give each season
$n_seasons others to train on.

The new season can test the prediction only in the product family its training seasons are in, since the test
compares depths within a family: here $families, from TESS-SPOC's full-frame light curves (stopped, above) or SPOC's
2-minute ones. We ask for the whole season because one mixing a QLP sector with 2-minute ones would be untestable:
QLP has no training data for this star. A QLP redelivery of the old sectors could lift the hold, but would test no
prediction made before its data.

2-minute data would also give a light curve within $fact_spoc_2min_latency_days days of each sector's end, SPOC's
recent latency; the transit's shape at 2-minute cadence; and one condition of our rule, after Giacalone et al.
(2021), for TRICERATOPS's "validated planet" label. The others include a contrast curve from high-resolution imaging,
which would also test a Hipparcos-Gaia acceleration the review notes (its finding F3).

The star may hold a second candidate. Quoted word for word from the review's finding F6: "$review_F6"

Before Sector $first_sector starts we will deposit publicly the prediction the test will judge, refit on the
$season_years seasons alone, so the new season tests a prediction fixed before its data exist.

## Target Justification and Feasibility

One target, TIC $tic, Tmag $tmag; sources brighter than magnitude $bright_tmag: $bright. 2-minute cadence is needed
because it is the only product that can test the new season (above). tess-point places the star in Sectors $sectors
($first_start to $last_end), and the density-prior fit puts $n_windows transits in them:

$windows

Mid (UTC) is when the transit is seen from Earth; sd is the mid-time's standard deviation over the fit's posterior.
These windows are for observers; the test judges the deposited refit. The vetted full-frame light curves (Sectors
$vetted_sectors, at $vetted_cadences s) detect the dip at $snr sigma over $n_transits transits, so the $n_windows
predicted transits should detect it again at 2-minute cadence.

## References

- Burke, C. J., et al. 2020, tess-point, ascl:2003.001
- Caldwell, D. A., et al. 2020, RNAAS, 4, 201 (TESS-SPOC)
- eumemic/exoplanets, https://github.com/eumemic/exoplanets (the second candidate)
- Giacalone, S., et al. 2021, AJ, 161, 24 (TRICERATOPS)
- Huang, C. X., et al. 2020, RNAAS, 4, 204; Kunimoto, M., et al. 2021, RNAAS, 5, 234 (QLP)
- The candidate's record, `results/vetting/$signal/`, and this proposal's sources, `results/ddt/$signal/`, in this
  project's repository: [repository URL]
- Archive state and sector dates, read $facts_read: $fact_sources
