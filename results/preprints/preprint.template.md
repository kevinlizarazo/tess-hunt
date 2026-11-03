# A $period_short-day transiting planet candidate around TIC $tic

$author_line

$repository

## Summary

tess-hunt is an independent search for transiting planets in public light curves from NASA's TESS mission. In the
TESS light curves of TIC $tic it found a periodic dip of about $depth_ppm ppm that lasts $duration_h hours and repeats
every $period_short days. A transit-model fit gives the transiting body a radius of $rp_rearth Earth radii, using the
star's radius in the TESS Input Catalog. The signal met every condition tess-hunt sets for a passed signal. Every
check on its light curve passed, TRICERATOPS gives it a false-positive probability of $fpp, and the maintainer
answered every confirmed finding of an adversarial review. This paper's author maintains tess-hunt and makes the call
on each vetted signal: passed, held or killed. This one was called passed on $call_date.$summary_prereg It is a planet
candidate. TESS light curves can't measure its mass or rule out light from every nearby star. Confirming it needs
other observations: photometry that separates the stars near it, high-resolution imaging for companions too close to
resolve, and radial velocities for its mass.

## How tess-hunt works

tess-hunt's search looks for periodic dips in the light curves of a fixed sample of stars. It keeps each signal above
a detection threshold (see "How it was found"). Triage then screens every signal above the threshold:

- the novelty check compares it with published catalogs of known planets, candidates and eclipsing binaries;
- LEO-Vetter (Kunimoto et al. 2025) tests whether it is a false alarm or a false positive at the flux level;
- the pixel check measures where on the sky the dip comes from.

A signal that passes all three is shortlisted. Vetting then runs a fixed, numbered version of tess-hunt's vetting
criteria on each shortlisted signal's light curve. It also runs TRICERATOPS, searches the literature and ExoFOP, and
adds an adversarial review.

Each vetting of a signal is published as a record: the checks' results, the review and the call. The call is the
maintainer's decision: passed, held or killed. A held call names the evidence that would decide it. A held signal can
be vetted again on newer data. Each re-vet is published as a new version of the record (r2, r3 and so on), and the
earlier versions stay as published (decision record 0041).

A signal passes only when all of these hold (decision record 0028):

- every check of the vetting criteria passed, the novelty check included;
- no row of ExoFOP's planet parameters for the star matches its period;
- the literature search was complete, and the maintainer read every paper the review flagged;
- TRICERATOPS and the pixel check passed;
- the maintainer answered every confirmed review finding and answered three fixed questions in a sentence each.

For the novelty check and for ExoFOP's rows, a TOI or CTOI that ExoFOP first listed after tess-hunt made the signal
public does not count (decision record 0042).$bar_promotion

Decision records are numbered documents in `docs/decisions/` in tess-hunt's repository
($repository/tree/$commit/docs/decisions). This paper cites each by its number. A run is one execution of a tess-hunt
command, named by its run id. The section "Data and code availability" lists the runs this paper reads and where
their files are published. A season is a run of TESS sectors with no gap longer than $season_gap_days days between
them.

## The star and the signal

TIC $tic has a TESS magnitude of $tmag, an effective temperature of $teff K and a radius of $radius_sun solar radii in
the TESS Input Catalog v8.2 (Stassun et al. 2019; Paegert et al. 2021). The record holds no uncertainty for that
radius, so the uncertainty on the transiting body's radius below leaves out the star's.

The depth below is from the search's box fit. The other values come from a transit model (batman; Kreidberg 2015)
with Kipping's (2013) limb-darkening parameters, fitted to the light curve with the TIC's stellar density as a prior.
This is the density-prior fit. Each uncertainty is the standard deviation of the fit's posterior. Rp/R*, the impact
parameter and a/R* give the median with its distances to the 16th and 84th percentiles. Times are BTJD (BJD_TDB -
2457000). Because of the prior, b and a/R* partly reflect the TIC's density. The shape, density and radius checks use
a second fit without the density prior, so the density check compares the density the transit implies with the TIC's.

| Quantity | Value |
|---|---|
| Period | $period d (sd $period_sd_s s) |
| Mid-transit time t0 | BTJD $t0 (sd $t0_sd_min min) |
| Duration | $duration_h h |
| Depth | $depth_ppm ppm |
| Planet-to-star radius ratio Rp/R* | $rp_rs |
| Radius | $rp_rearth Earth radii (16th to 84th percentile $rp_lo to $rp_hi, from Rp/R* and the TIC radius alone) |
| Impact parameter | $b |
| Scaled semi-major axis a/R* | $a_rs |

$upcoming

$figures

## How it was found

The search used box least squares (BLS; Kovács et al. 2002) to look for periodic dips of $period_min to $period_max
days in $sample_stars stars from the TESS Input Catalog. Each star has:

- an effective temperature above $teff_min K and up to $teff_max K;
- a TESS magnitude of $tmag_max or brighter;
- a surface gravity (log g) of $logg_min to $logg_max;
- a Gaia DR3 log g of at least $flame_logg_min, where Gaia gives one (decision record 0009);
- light curves in at least $min_sectors sectors, one of them in Sectors $recent_min to $recent_max.

The search found this signal at a signal detection efficiency (SDE) of $sde.

The detection threshold, SDE $threshold, comes from tess-hunt's own null search. The null search searched each sample
star's light curve again after shuffling the segments between its data gaps within each sector and then shuffling the
sectors, so that no real periodic signal survives. The threshold is the highest SDE in that null search that
LEO-Vetter's false-alarm tests (Kunimoto et al. 2025) do not reject. Scaled by the ratio of the sample's $n_sample
stars to the $n_null stars the null search covered, that one null signal gives an expected $false_alarms false alarms
at or above the threshold. This estimate comes from a single null signal. Decision record 0019 calls it an upper
bound only because the star count includes stars the search couldn't process.

The injection-recovery run planted $injections synthetic transits in the light curves of $inject_stars sample stars and
searched them at the same threshold. The fraction it recovered at each expected signal-to-noise ratio is in
`results/benchmarks/$inject_run/$completeness` in tess-hunt's repository.

$triage

## How it was vetted

$history

The vetting run applied version $criteria_version of tess-hunt's vetting criteria to the $vetted_products light curves
of $vetted_sectors.$suspect The table gives each check's outcome. The first rows are the vetting criteria's checks.
The last four come from other steps: the neighbour table, triage's pixel check, TRICERATOPS and the literature search.
The neighbour table lists the Gaia DR3 stars that could make the dip. It never fails: its pass means only that it
could assess every star near the target (decision record 0025). The literature search passes when every search
completed. What it found is described below.

$checks

$novelty

$modshift

$red_noise

The neighbour check lists every Gaia DR3 star near the target that could make the dip if all its light fell in the
aperture. $hosts TRICERATOPS (Giacalone et al. 2021) then weighed the scenarios that could make the dip: on the
target, on unresolved companions and background stars, and on each nearby TIC star whose light falls in its
apertures.$tdepth_zero

TRICERATOPS ran $tric_times on $tric_data. Its mean false-positive probability (FPP) is $fpp and its mean nearby
false-positive probability (NFPP) is $nfpp. Both are under Giacalone et al.'s (2021) thresholds for a likely planet:
FPP $fpp_pass and NFPP $nfpp_pass. $validated

The pixel check in the table is $pixel_check. It measures how far the dip's difference-image centroid (Bryson et al.
2013) is from the target in each sector, and passes when the offset in the best-quality sector is within $max_offset
arcsec, following LEO-Vetter. $offsets $rests_on The check can't tell the target from a star closer than $max_offset
arcsec: TOI-1399.01's dip comes from a nearby binary inside that limit, and it passes the check (decision record
0032).

The literature search looked up the star's names, including $names, in NASA ADS, arXiv, OpenAlex and Zenodo, and read
ExoFOP's records for the star. It found $papers. $exofop $exofop_rows

An LLM-assisted adversarial review, dated $review_date, looked for reasons the signal might not be on the star, not
be a planet, or not be real and new. It rates each finding kill, hold or note. Kill means the signal is not a planet
candidate if the finding stands. Hold means the signal can't pass until the finding is answered. A note needs no
answer. Each finding also names the question it concerns. A kill or hold finding counts as confirmed unless a refuter
disproves it. Refuters are separate LLM-assisted checks, each asked to disprove one finding. Of the review's
$findings, $fates. The maintainer's call answers each confirmed finding. The answers are quoted under "What it can't
rule out". $hits_read

The call also answers three questions in a sentence each: could the dip be an eclipsing binary on the star, light from
another star, or an artefact or known object? The answers below are quoted from the call. Any number in them is the
maintainer's, not one filled in by tess-hunt's code (decision record 0037).

$sentences

## The held-out seasons and the preregistered test

The held-out season check leaves out one season at a time and refits the period and epoch with BLS on the rest. It
then measures the left-out season's depth in the cores of the transits the refit predicts there (the central $core of
each transit's duration). The refit only searches near the original period, and the original search used every
season, including the one left out. So this check tests that the seasons agree with each other. It is not a blind
prediction. Only the preregistered test below is. A testable season counts as predicted when its depth is at least
$min_sigma times its error and, for each light-curve product family, within $max_tension sigma of that family's depth
in the other seasons. The check passes when at least two seasons are testable and all of them are predicted.
$holdout

$prereg

## What it can't rule out

Photometry alone does not measure the transiting body's mass. $companions $blends $eccentric The radius depends on
the TIC's stellar radius, which has no uncertainty in the record.

Each confirmed finding is quoted below with the maintainer's answer from the call. tess-hunt never edits quoted text.
Where the maintainer later found a mistake in a quote, a dated note follows it. The note is not part of the review or
the call (decision record 0037).

$answers

$refuted

$notes

## When it was made public

tess-hunt first made this signal public on $claim_date, $claim_where.$listings

## Data and code availability

The TESS light curves come from MAST: $products. tess-hunt's code, under the MIT licence, is at $repository. The
vetting run behind the record this paper reports used commit $commit. This paper's `provenance.json` names the commit
that generated the paper.

The runs this paper reads, each by its run id:

$runs

The dataset deposited with this paper holds the signal's published records and one light curve. $records The light
curve, `dataset/$light_curve`, is the one the vetting run of $rendered_from read. `manifest.json` lists each file of the
dataset with its sha256 and licence. In each record:

$files

Each provenance file names the command and the commit of one run that wrote files in the record. The search,
threshold, injection-recovery and triage runs supply the remaining numbers. They are published in the repository
under `results/`. This paper's text comes from a fixed template. tess-hunt's code filled in every number from those
files and runs, except in quoted text and the dated notes. The notes are the maintainer's, typed by hand and checked
by reading (decision record 0037).

This paper and its figures are licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), with two
exceptions:

- any Gaia value in text quoted from the review or the call, or in a note, stays under ESA's CC BY-NC 3.0 IGO terms
  (https://www.cosmos.esa.int/web/gaia-users/license);
- the ExoFOP listings the paper names stay under ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php).

The dataset is also CC BY 4.0, with two exceptions:

- its files that hold Gaia DR3 data stay under ESA's terms;
- ExoFOP's rows in its `literature.json`, `claims.json` and `dossier.md` files stay under ExoFOP's terms.

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

- TESS: Ricker, G. R., Winn, J. N., Vanderspek, R., et al. 2015, JATIS, 1, 014003
- Light curves: $product_papers$pdcsap_papers
- TESS Input Catalog: Stassun et al. 2019, AJ, 158, 138; Paegert et al. 2021, arXiv:2108.04778$gaia_papers
- BLS: Kovács, G., Zucker, S., & Mazeh, T. 2002, A&A, 391, 369
- LEO-Vetter: Kunimoto, M., Bryson, S., Jaffee, D., et al. 2025, AJ, 170, 280
- ModShift: Rowe, J. F., Coughlin, J. L., Antoci, V., et al. 2015, ApJS, 217, 16; Coughlin, J. L., Mullally, F.,
  Thompson, S. E., et al. 2016, ApJS, 224, 12
- TRICERATOPS: Giacalone, S., Dressing, C. D., Jensen, E. L. N., et al. 2021, AJ, 161, 24, and Giacalone, S., &
  Dressing, C. D. 2020, ascl:2002.004; PyTransit, which it runs: Parviainen, H. 2015, MNRAS, 450, 3233
- Pixel check: difference-image centroids, Bryson, S. T., Jenkins, J. M., Gilliland, R. L., et al. 2013, PASP, 125,
  889; transit-diffImage (Steve Bryson, https://github.com/stevepur/transit-diffImage, commit 2b13199); TESScut,
  through Astrocut: Brasseur, C. E., et al. 2019, ascl:1905.007; SpiceyPy: Annex et al. 2020, JOSS, 5, 2050; SPICE:
  Acton, C. H. 1996, Planetary and Space Science, 44, 65, and Acton, C., Bachman, N., Semenov, B., & Wright, E. 2017,
  Planetary and Space Science (doi:10.1016/j.pss.2017.02.013)
- Transit model: batman, Kreidberg, L. 2015, PASP, 127, 1161; limb darkening, Kipping, D. M. 2013, MNRAS, 435, 2152
- Red noise: Pont, F., Zucker, S., & Queloz, D. 2006, MNRAS, 373, 231
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
