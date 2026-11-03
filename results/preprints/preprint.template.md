# A $period_short-day transiting planet candidate around TIC $tic

$author_line

$repository

## Summary

tess-hunt is an independent search for transiting planets in public light curves from NASA's TESS mission. In the
TESS light curves of TIC $tic it found a periodic dip of about $depth_ppm ppm that lasts $duration_h hours and repeats
every $period_short days. A transit-model fit gives the transiting body a radius of $rp_rearth Earth radii, for the
star's radius in the TESS Input Catalog. The signal met every condition tess-hunt sets for a passed signal: among
them, every check on its light curve passed, TRICERATOPS gives it a false-positive probability of $fpp, and the
maintainer answered each objection an adversarial review raised that no one refuted. The
project's maintainer, this paper's author, makes the call on each vetted signal, passed, held or killed, and called
this one passed on $call_date.$summary_prereg It is a planet candidate. TESS light curves can't measure its mass, and
they don't rule out every other star's light. Whether it is a planet needs other observations: photometry that
separates the stars near it, high-resolution imaging for companions too close to resolve, and radial velocities for
its mass.

## How tess-hunt works

tess-hunt's search looks for periodic dips in the light curves of a fixed sample of stars and keeps each signal above a
detection threshold (How it was found). Triage then screens every signal above the threshold: the novelty check
compares it with published catalogs of known planets, candidates and eclipsing binaries, LEO-Vetter (Kunimoto et al.
2025) tests whether it is a false alarm or a false positive at the flux level, and the pixel check measures where on
the sky the dip comes from. A signal that passes all three is shortlisted. Vetting then runs a fixed set of checks on a
shortlisted signal's light curve, under a numbered version of tess-hunt's vetting criteria, with TRICERATOPS, a search
of the literature and ExoFOP, and an adversarial review.

Each vetting of a signal is published as a record: the checks' results, the review and the call. The call is the
maintainer's decision on the signal: passed; held, when the public data can't decide, and the call names the evidence
that would; or killed. A held signal can be vetted again on newer data, and each re-vet is published as a new version
of the record (r2, r3 and so on) beside the earlier ones, which stay as they were published (decision record 0041).

A signal passes only when (decision record 0028) every check of the vetting criteria passed, the novelty check among
them, with a TOI or CTOI that ExoFOP listed only after tess-hunt made the signal public set aside (decision
record 0042)$bar_promotion; no row of ExoFOP's planet parameters for the star matches its period, a row of a listing
set aside that way apart; the literature search was complete and the maintainer read every paper the review flagged;
TRICERATOPS and the pixel check passed; and the maintainer answered every confirmed review finding and gave one
sentence on each of three questions.

Decision records are numbered documents in `docs/decisions/` in tess-hunt's repository
($repository/tree/$commit/docs/decisions); this paper cites each by its number. A run is one execution of a tess-hunt
command, named by its run id; Data and code availability lists the runs this paper reads and where their files are
published. A season is a run of TESS sectors with no gap longer than $season_gap_days days between them.

## The star and the signal

TIC $tic has a TESS magnitude of $tmag, an effective temperature of $teff K and a radius of $radius_sun solar radii in
the TESS Input Catalog v8.2 (Stassun et al. 2019; Paegert et al. 2021). The record holds no uncertainty for that
radius, so the transiting body's radius below carries none from the star's.

The depth below is that of the box the search fitted. The rest comes from a transit model (batman; Kreidberg 2015),
with limb darkening in Kipping (2013)'s parameters, fitted to the light curve with the TIC's stellar density as a
prior: the density-prior fit. Each uncertainty is the standard deviation of the fit's posterior; Rp/R*, the impact
parameter and a/R* give the median with its distances to the 16th and 84th percentiles; times are BTJD (BJD_TDB -
2457000). Through the prior, b and a/R* partly carry the TIC's density. The shape, density and radius checks under How
it was vetted read a second fit with no prior on the density, so the density check compares the transit's own stellar
density with the TIC's.

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

tess-hunt's search looked for periodic dips of $period_min to $period_max days, with box least squares (BLS;
Kovács et al. 2002), in the light curves of its sample: $sample_stars stars from the TESS Input Catalog with an
effective temperature above $teff_min K and up to $teff_max K, a TESS magnitude of $tmag_max or brighter, a surface
gravity (log g) of $logg_min to $logg_max, a Gaia DR3 log g of at least $flame_logg_min where Gaia gives one
(decision record 0009), and light curves in at least $min_sectors sectors, one of them in Sectors $recent_min to
$recent_max. It found this signal at a signal detection efficiency (SDE) of $sde.

The detection threshold, SDE $threshold, comes from tess-hunt's own null search, which searched each sample star's
light curve again after shuffling the segments between its data gaps within each sector, and then the sectors, so that
no real periodic signal survives. The threshold is the highest SDE in that null search that LEO-Vetter's false-alarm
tests (Kunimoto et al. 2025) do not reject. That one null signal, scaled by the ratio of the sample's $n_sample stars to
the $n_null stars the null search covered, gives an expected $false_alarms false alarms at or above the threshold in
the search. It is an estimate from a single null event; decision record 0019 calls it an upper bound only because the
sample's count includes stars the search could not search.

The injection-recovery run planted $injections synthetic transits in the light curves of $inject_stars sample stars and
searched them at the same threshold. The fraction it recovered at each expected signal-to-noise ratio is in
`results/benchmarks/$inject_run/$completeness` in tess-hunt's repository.

$triage

## How it was vetted

$history

The vetting run applied tess-hunt's vetting criteria, version $criteria_version, to the $vetted_products light curves
of $vetted_sectors.$suspect The table gives each check's outcome with its reason as the vetting record gives it. The
vetting criteria's checks come first, then four rows from other steps: the neighbour table, which lists the Gaia DR3
stars that could make the dip and never fails, so that its pass means only that it could judge every star near the
target (decision record 0025); triage's pixel check; TRICERATOPS; and the literature search, which passes when every
search completed (what it found is below).

$checks

$novelty

$modshift

$red_noise

The neighbour check lists every Gaia DR3 star near the target whose eclipse could make the dip if all its light
fell in the photometric aperture: $hosts. TRICERATOPS (Giacalone et al. 2021) then weighed the scenarios that could
make the dip: on the target, on companions and background stars too close to resolve, and on each nearby star in the
TIC whose light its apertures take in.$tdepth_zero Over $triceratops_runs on $tric_data, its mean false-positive
probability (FPP) is $fpp and its mean nearby false-positive probability (NFPP) is $nfpp, both under the thresholds
Giacalone et al. (2021) give for a likely planet, FPP $fpp_pass and NFPP $nfpp_pass. $validated

The pixel check in the table is $pixel_check: it measures how far the dip's difference-image centroid (Bryson et al.
2013) sits from the target in each sector, and passes when the offset in the best-quality sector is within $max_offset
arcsec, LEO-Vetter's rule. Its offsets: $offsets. $rests_on An offset within $max_offset arcsec can't tell the target
from a star closer than that: TOI-1399.01, whose dip comes from a nearby binary inside that limit, passes the
check (decision record 0032).

The literature search looked for the star under each of its names, among them $names, in NASA ADS, arXiv, OpenAlex and
Zenodo, and read ExoFOP's records for the star. It found $papers under those names. $exofop None of ExoFOP's
planet-parameter rows for the star matches the signal's period or a harmonic of it$excepted.

An adversarial review, assisted by an LLM and dated $review_date, looked for reasons the signal is not on the star,
not a planet, or not real and new. It rates each finding kill (if the finding stands, the signal is not a planet
candidate), hold (the signal can't pass until the finding is answered) or note (it needs no answer), and labels it
with the question it bears on. A finding rated kill or hold counts as confirmed unless a refuter, a separate
LLM-assisted check asked to disprove that finding, did so. Of its $findings, $fates. The maintainer's call answers
each confirmed finding (What it can't rule out). $hits_read

The call answers three questions in one sentence each: whether the dip could be an eclipsing binary on the star,
another star's light, or an artefact or a known object. The sentences are quoted from the record's call in the
maintainer's words, so any number in them is the maintainer's, not filled in by tess-hunt's code (decision record
0037).

$sentences

## The held-out seasons and the preregistered test

The held-out season check leaves out one season at a time, refits the period and epoch with BLS on the others, and
measures the left-out season's depth in the cores of the transits the refit predicts there, the central $core of each
transit's duration. The refit searches only near the search's period, which the search found with every season, the
left-out one included, so the check tests that the seasons agree with each other; it is not a blind prediction, which
only the preregistered test below is. A season that could be tested is predicted when its depth there is at least
$min_sigma times its error and, in each light-curve product family, within $max_tension sigma of that family's depth
in the other seasons; the check passes when at least two seasons could be tested and each was predicted. $holdout

$prereg

## What it can't rule out

Photometry alone does not measure the transiting body's mass. $companions $blends $eccentric The radius rests on the
TIC's stellar radius, which the record gives without an uncertainty.

Below, each confirmed finding of the review is quoted with the maintainer's answer from the call. tess-hunt never edits
quoted text: where the maintainer later found a slip in it, a dated note sits beside the quote, and the note is part of
neither the review nor the call (decision record 0037).

$answers

$refuted

$notes

## When it was made public

tess-hunt first made this signal public on $claim_date, $claim_where.$listings

## Data and code availability

The TESS light curves come from MAST: $products. tess-hunt's code, under the MIT licence, is at $repository; the
vetting run that made the record this paper reports ran it at commit $commit, and this paper's `provenance.json` names
the commit that generated the paper.

The runs this paper reads, each by its run id:

$runs

The dataset deposited with this paper holds the signal's published records and one light curve. $records The light
curve, `dataset/$light_curve`, is the one the vetting run of $rendered_from read. `manifest.json` lists each file of the
dataset with its sha256 and licence. In each record:

$files

Each provenance file names the command and the commit that wrote the files beside it. The search, threshold,
injection-recovery and triage runs, from which the rest of the numbers come, are published in the repository under
`results/`.

This paper's text is a fixed template, and tess-hunt's code filled in every number outside the quoted text and the
dated notes from those files and runs. The notes are the maintainer's, typed and checked by reading (decision record
0037).

This paper and its figures are licensed under CC BY 4.0 (https://creativecommons.org/licenses/by/4.0/), with two
exceptions: any Gaia value in the text quoted from the review or the call, or in a note beside it, stays under ESA's CC
BY-NC 3.0 IGO terms (https://www.cosmos.esa.int/web/gaia-users/license), and the ExoFOP listings the paper names stay
under ExoFOP's terms (https://exofop.ipac.caltech.edu/tess/pcp.php). The dataset is also CC BY 4.0, except its files
that hold Gaia DR3 data, which stay under ESA's terms, and ExoFOP's rows in its `literature.json`, `claims.json` and
`dossier.md` files, which stay under ExoFOP's terms.

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
