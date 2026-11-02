# A planet candidate with a $period_short-day period on TIC $tic

$author_line

$repository

## Summary

tess-hunt is an independent search for transiting planets in public light curves from NASA's TESS mission. On TIC
$tic it found a periodic dip of about $depth_ppm ppm that lasts $duration_h hours and repeats every $period_short
days. A transit-model fit gives the transiting body a radius of $rp_rearth Earth radii. The signal met tess-hunt's bar
for a passed signal, and the project's maintainer called it passed on $call_date. It is a planet candidate. TESS light
curves can't measure its mass, so whether it is a planet needs other observations, such as radial velocities.

## The star and the signal

TIC $tic has a TESS magnitude of $tmag, an effective temperature of $teff K and a radius of $radius_sun solar radii in
the TESS Input Catalog v8.2 (Stassun et al. 2019; Paegert et al. 2021).

The depth below is that of the box the search fitted. The rest comes from a transit model fitted with the TIC's
stellar density as a prior (the density-prior fit): each uncertainty is the standard deviation of the fit's
posterior, the impact parameter and a/R* give the median with its distances to the 16th and 84th percentiles, and
times are BTJD (BJD_TDB - 2457000).

| Quantity | Value |
|---|---|
| Period | $period d (sd $period_sd_s s) |
| Mid-transit time t0 | BTJD $t0 (sd $t0_sd_min min) |
| Duration | $duration_h h |
| Depth | $depth_ppm ppm |
| Radius | $rp_rearth Earth radii (16th to 84th percentile $rp_lo to $rp_hi) |
| Impact parameter | $b |
| Scaled semi-major axis a/R* | $a_rs |

$upcoming

$figures

## How it was found

tess-hunt's production search, run $search_run, searched its sample's light curves with box least squares (BLS;
Kovács et al. 2002). It found this signal at a signal detection efficiency (SDE) of $sde.

The detection threshold, SDE $threshold, comes from tess-hunt's own null search, run $null_run, which searched every
sample star's light curve again after shuffling the segments between its data gaps within each sector, and then the
sectors. The threshold is the highest SDE in that null search that LEO-Vetter's false-alarm tests (Kunimoto et al.
2025) do not reject (threshold run $threshold_run). From the ratio of the sample's size to the null search's, the
production search expects at most $false_alarms false alarms above it.

Injection-recovery run $inject_run planted $injections synthetic transits in the light curves of $inject_stars sample
stars and searched them at the same threshold. Its tables give the fraction recovered by expected signal-to-noise
ratio.

## How it was vetted

Vetting run $vetting_run applied tess-hunt's vetting criteria, $criteria_version, to the $vetted_products light curves
of $vetted_sectors.$suspect Each check's outcome, with its reason as the vetting record gives it:

$checks

$novelty

The neighbour check lists every Gaia DR3 star near the target whose eclipse could make the dip if all its light fell
in the photometric aperture. TRICERATOPS (Giacalone et al. 2021) then weighed the scenarios that could make the dip,
those stars among them. Over $triceratops_runs its mean false-positive probability (FPP) is $fpp and its mean nearby
false-positive probability (NFPP) is $nfpp, below the limits tess-hunt takes for a likely planet, $fpp_pass and
$nfpp_pass.

The pixel check in the table is $pixel_check: it measures how far the dip's difference-image centroid sits from the
target in each sector.

The literature search looked for the star under each of its names, among them $names, in NASA ADS, arXiv, OpenAlex
and Zenodo, and read ExoFOP's records for the star. None of ExoFOP's planet-parameter rows for the star matches the
signal's period or a harmonic of it$excepted. $hits_read

An adversarial review, written by an AI model ($review_model) on $review_date, looked for reasons the signal is not on
the star, not a planet, or not real and new. A finding it rated kill or hold counts as confirmed unless a refuter, a
separate AI-model session asked to disprove that finding, did so. Of its $findings, $n_confirmed stood as confirmed,
and the maintainer's call answers each confirmed finding (under What it can't rule out).

The call gives one sentence for each of three questions. They are quoted from the record's `call.toml`, in the
maintainer's words; numbers in them are the maintainer's, not rendered from the runs (decision record 0037 in
tess-hunt's repository).

$sentences

## The held-out seasons and the preregistered test

The held-out season check refits the period and epoch on every season of TESS data but one, and measures the left-out
season's depth where the refit predicts its transits. Its outcome for this signal: $holdout.

$prereg

## What it can't rule out

Photometry alone does not measure the transiting body's mass. $companions

The review's confirmed findings, each with the maintainer's answer from the call, both quoted, with any note added
beside a finding later (decision record 0037 in tess-hunt's repository):

$answers

$notes

## When it was made public

tess-hunt first made this signal public on $claim_date, in $claim_record.$listings

## Data and code availability

The TESS light curves come from MAST: $products. tess-hunt's code is at $repository; vetting run $vetting_run ran it
at commit $commit, and this paper's `provenance.json` names the commit that rendered it.

The dataset deposited with this paper holds the signal's published records and one light curve. $records The light
curve, `dataset/$light_curve`, is the one the vetting run of $rendered_from read. `manifest.json` lists each file of
the dataset with its sha256 and licence. The search, threshold, injection-recovery and triage runs named above, from
which the rest of the numbers come, are published in the repository under `results/`.

Every number in this paper outside the quoted text was rendered by tess-hunt's code from those files and runs. The
review and the call are quoted word for word, so their numbers are their authors'.

This paper and its figures are licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), except any
Gaia value in the text quoted from the review or the call, which stays under ESA's CC BY-NC 3.0 IGO terms
(https://www.cosmos.esa.int/web/gaia-users/license). So is the dataset, except its files that hold Gaia DR3 data,
which stay under ESA's terms, and ExoFOP's rows in its `literature.json`, `claims.json` and `dossier.md` files, which
stay under ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php).

## Use of LLMs

tess-hunt's code and this paper's text were written with LLM assistance. Adversarial reviews this paper quotes were
assisted by LLMs. More information on models is available on GitHub.

## Acknowledgements

This paper $tess_credit$qlp_credit It uses stellar parameters from the TESS Input Catalog v8.2 (Stassun et al. 2019;
Paegert et al. 2021), queried through MAST.$gaia_credit

This research has made use of the Exoplanet Follow-up Observation Program (ExoFOP; DOI: 10.26134/ExoFOP5) website,
which is operated by the California Institute of Technology, under contract with the National Aeronautics and Space
Administration under the Exoplanet Exploration Program. This research has made use of the NASA Exoplanet Archive,
which is operated by the California Institute of Technology, under contract with the National Aeronautics and Space
Administration under the Exoplanet Exploration Program.

This research has made use of the SIMBAD database, CDS, Strasbourg Astronomical Observatory, France. This research has
made use of the VizieR catalogue access tool, CDS, Strasbourg Astronomical Observatory, France (DOI :
10.26093/cds/vizier). This research has made use of the CDS cross-match service, Strasbourg Astronomical Observatory,
France. This research has made use of the International Variable Star Index (VSX) database, operated at AAVSO,
Cambridge, Massachusetts, USA. This research has made use of the Astrophysics Data System, funded by NASA under
Cooperative Agreement 80NSSC25M7105. Thank you to arXiv for use of its open access interoperability.

The repository's `ACKNOWLEDGEMENTS.md`, at the commit named above, gives every source tess-hunt reads with its terms
and the citation it asks for.

## References

- Light curves: $product_papers
- TESS Input Catalog: Stassun et al. 2019, AJ, 158, 138; Paegert et al. 2021, arXiv:2108.04778$gaia_papers
- BLS: Kovács, G., Zucker, S., & Mazeh, T. 2002, A&A, 391, 369
- LEO-Vetter: Kunimoto, M., Bryson, S., Jaffee, D., et al. 2025, AJ, 170, 280
- TRICERATOPS: Giacalone, S., Dressing, C. D., Jensen, E. L. N., et al. 2021, AJ, 161, 24, and Giacalone, S., &
  Dressing, C. D. 2020, ascl:2002.004; PyTransit, which it runs: Parviainen, H. 2015, MNRAS, 450, 3233
- Pixel check: transit-diffImage (Steve Bryson, https://github.com/stevepur/transit-diffImage, commit 2b13199);
  TESScut, through Astrocut: Brasseur, C. E., et al. 2019, ascl:1905.007; SpiceyPy: Annex et al. 2020, JOSS, 5, 2050;
  SPICE: Acton, C. H. 1996, Planetary and Space Science, 44, 65, and Acton, C., Bachman, N., Semenov, B., & Wright,
  E. 2017, Planetary and Space Science (doi:10.1016/j.pss.2017.02.013)
- tess-point: Burke, C. J., et al. 2020, ascl:2003.001
- Eclipsing-binary catalogs the novelty check reads: Prša et al. 2022, ApJS, 258, 16 (TESS-EBs,
  doi:10.17909/t9-9gm4-fx30); Kostov, V. B., Powell, B. P., et al. 2025, ApJS, 279, 50; Justesen, A. B., & Albrecht,
  S. 2021, ApJ, 912, 123; VSX: Watson, C., Henden, A. A., & Price, A. 2006, SASS, 25, 47
- Other catalogs the novelty check reads: Martinho, M., & Valizadegan, H. 2025, ExoMiner++
  (doi:10.5281/zenodo.15466293) and ExoMiner++ 2.0 (doi:10.5281/zenodo.17707413); the NASA Exoplanet Archive,
  Christiansen et al. 2025, PSJ (doi:10.3847/PSJ/ade3c2)
- Services: SIMBAD, Wenger et al. 2000, A&AS, 143, 9; VizieR, Ochsenbein et al. 2000, A&AS, 143, 23; the CDS
  cross-match service, Boch et al. 2012, ASPC, 461, 291, and Pineau et al. 2020, ASPC, 522, 125; OpenAlex, Priem, J.,
  Piwowar, H., & Orr, R. 2022, arXiv:2205.01833
- Software: lightkurve (Lightkurve Collaboration 2018); astropy (Astropy Collaboration 2013, 2018, 2022); astroquery,
  which queries MAST and the Gaia archive (Ginsburg et al. 2019); transitleastsquares, whose period grid the search
  uses (Hippke & Heller 2019); wotan (Hippke et al. 2019); emcee (Foreman-Mackey et al. 2013); batman (Kreidberg
  2015); matplotlib (Hunter, J. D. 2007, Computing in Science & Engineering, 9, 90)
