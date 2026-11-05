# A $period_short-day Transiting Planet Candidate around TIC $tic

$author_block

## Abstract

We report a transiting planet candidate around TIC $tic, a star with a TESS magnitude of $tmag, an effective
temperature of $teff K and a radius of $radius_sun R⊙ in the TESS Input Catalog. We searched public TESS light curves
and found a periodic transit signal with a period of $period_pm d, a depth of $depth_ppm ppm and a duration of
$duration_h h. A transit-model fit, with the stellar radius from the TESS Input Catalog, gives a radius of $rp_pm R⊕
for the transiting body. $abstract_checks TRICERATOPS gives a mean false-positive probability of $fpp_pm. An
LLM-assisted adversarial review looked for reasons the signal might not be a planet, and we answered every finding
that its refuters did not disprove.$summary_prereg The signal remains a planet candidate. The TESS light curves cannot
measure the transiting body's mass, and they cannot exclude every nearby star as the source of the transit.
Establishing that the signal comes from a planet needs further observations: photometry that resolves the stars near
the target, high-resolution imaging to search for companions too close to resolve, and radial velocities to measure
the mass.

**Keywords:** Exoplanets (498); Transit photometry (1709); Exoplanet detection methods (489); Light curves (918)

## Introduction

The Transiting Exoplanet Survey Satellite (TESS; Ricker et al. 2015) observes the sky in a series of sectors, and its
light curves are public. The TESS Science Office searches them for transits and releases the signals it judges
planetary as TESS Objects of Interest (TOIs; Guerrero et al. 2021). Community members submit their own candidates to
the Exoplanet Follow-up Observing Program (ExoFOP; NExScI 2022) as community TOIs (CTOIs). A candidate found in
photometry alone is not yet a planet: follow-up observations must rule out the false positives that mimic a transit,
such as eclipsing binaries, and measure the companion's mass.

This paper reports a candidate from tess-hunt, an independent search of public TESS light curves. Section 2 describes
the search and how we vet its signals. Sections 3 to 7 give the host star, the detection, the transit parameters, the
vetting, and the held-out and preregistered tests. Section 8 discusses what the data do not rule out, and Section 9
concludes.

## The tess-hunt Search and Vetting

The tess-hunt project is an independent search for transiting planets in public light curves from NASA's TESS mission.
Its search looks for periodic transit signals in the light curves of a fixed sample of stars (Section 4). Each signal at
or above a detection threshold goes to triage, which applies three screens:

- the novelty check compares the signal with published catalogues of known planets, candidates and eclipsing binaries;
- LEO-Vetter (Kunimoto et al. 2025) tests whether the signal is a false alarm or a false positive at the flux level;
- the pixel check measures where on the sky the signal comes from.

The catalogues the novelty check reads include the NASA Exoplanet Archive (Christiansen et al. 2025), ExoMiner++
(Martinho & Valizadegan 2025a, 2025b), TESS-EBs (Prša et al. 2022a, 2022b), the eclipsing-binary candidates of Gaia
DR3 (Gaia Collaboration et al. 2016, 2023; Mowlavi et al. 2023), the eclipsing binaries of Justesen & Albrecht (2021)
and Kostov et al. (2025), read through VizieR (Ochsenbein et al. 2000), and VSX (Watson et al. 2006), matched through
the CDS cross-match service (Boch et al. 2012; Pineau et al. 2020). A signal that passes all three screens is
shortlisted. Vetting then applies a fixed, numbered version of tess-hunt's vetting criteria to the light curve of each
shortlisted signal, runs TRICERATOPS, searches the literature and ExoFOP, and includes an LLM-assisted adversarial
review.

We cite the project's decision records (DRs), numbered documents in the repository at the commit named in Data
Availability, as "DR 0041". The decision records call the author "the maintainer". Each vetting of a signal is
published as a record of the checks' results, the review and the call. The call is our decision on the signal: passed,
held pending further evidence, or killed. A held call names the evidence that would decide the signal, and a held
signal can be vetted again on newer data. Each new vetting is published as a new version of the record (r2, r3 and so
on), and the earlier versions remain published (DR 0041).

We can pass a signal only when all of the following are true (DR 0028):

- every check of the vetting criteria passed, the novelty check included;
- no row of ExoFOP's planet parameters for the star matches the signal's period;
- the literature search was complete, and we read every paper the review flagged;
- TRICERATOPS and the pixel check passed;
- we answered every upheld review finding (Section 6.5) and each of three fixed questions in one sentence.

For the novelty check and the ExoFOP comparison, a TOI or CTOI that ExoFOP first listed after we made the signal public
is not counted as a known object (DR 0042).$bar_promotion

A run is one execution of a tess-hunt command, identified by its run id. Appendix A lists the runs whose outputs this
paper uses. A season is a group of TESS sectors in which no gap between successive sectors exceeds $season_gap_days
days.

## Host Star

TIC $tic has a TESS magnitude of $tmag, an effective temperature of $teff K and a radius of $radius_sun R⊙ in the TESS
Input Catalog v8.2 (Stassun et al. 2019; Paegert et al. 2021; TESS Team 2018). The vetting record carries no
uncertainty for that radius, so the uncertainty on the transiting body's radius in Table 1 omits the stellar-radius
term.

## Detection

The search ran box least squares (BLS; Kovács et al. 2002) over periods of $period_min to $period_max days on the light
curves of $sample_stars stars from the TESS Input Catalog. Each star has:

- an effective temperature above $teff_min K and no higher than $teff_max K;
- a TESS magnitude of $tmag_max or brighter;
- a surface gravity (log g) of $logg_min to $logg_max;
- a log g of at least $flame_logg_min from the Gaia DR3 FLAME mass and radius (Creevey et al. 2023), where Gaia gives
  them (DR 0009);
- light curves in at least $min_sectors sectors, one of them in Sectors $recent_min to $recent_max.

The search found this signal at a signal detection efficiency (SDE) of $sde.

The detection threshold, SDE $threshold, comes from a null search. In the null search, each sample star's light curve
was searched again after the segments between data gaps had been shuffled within each sector and the sectors then
shuffled, so that no real periodic signal survived. The threshold is the highest SDE among the null-search signals
that LEO-Vetter's false-alarm tests (Kunimoto et al. 2025) do not reject. Scaling the null search's count by the ratio
of the sample's $n_sample stars to the $n_null stars in the null search gives an expected $false_alarms false alarms at
or above the threshold. The estimate rests on a single null-search signal. DR 0019 treats it as an upper bound for one
reason only: the sample count includes stars the search could not process.

For the injection-recovery test, $injections synthetic transits were injected into the light curves of $inject_stars
sample stars, and those light curves were searched at the same threshold. The recovered fraction as a function of
expected signal-to-noise ratio is published with the injection-recovery run (Appendix A).

$triage

## Transit Parameters

Table 1 gives the transit parameters. The depth is that of the search's BLS box model. The other values come from a
transit model (batman; Kreidberg 2015), with limb darkening parametrised as in Kipping (2013), fitted to the light curve
with the TIC stellar density as a prior (the density-prior fit). Because of the prior, b and a/R<sub>⋆</sub> partly
reflect the TIC density. The shape, density and radius checks use a second fit without the density prior, so the
density check compares the density the transit implies with the TIC density.

$parameters

Figure 1 shows each transit in the light curve, and Figure 2 the light curve folded on the ephemeris in each season and
light-curve family. A light-curve family is the flux product a light curve comes from: PDCSAP flux from SPOC or
TESS-SPOC, or QLP flux.

$figure_transits

$figure_folds

## Vetting

$history

The vetting run applied version $criteria_version of tess-hunt's vetting criteria to the $vetted_products light curves
of $vetted_sectors.$suspect Table 2 gives each check's outcome. The vetting criteria's checks come first, and the last
four rows come from other steps: the neighbour check, triage's pixel check, TRICERATOPS and the literature search.
Sections 6.1 to 6.4 discuss them, and Section 6.5 the adversarial review.

$checks

### Light-curve Tests

Figure 3 shows the odd- and even-numbered transits, which the odd-even check compares, and Figure 4 the whole orbit,
where the secondary-eclipse check looks for an eclipse at phase 0.5. $modshift

$figure_odd_even

$figure_phase

$red_noise

### Location of the Signal

The neighbour check lists the possible hosts: every Gaia DR3 star near the target bright enough to produce the
observed depth if all its light fell in the aperture. Gaia DR3 astrometry (Lindegren et al. 2021) and photometry
(Riello et al. 2021) give the stars' positions and brightness. The check has no fail outcome: a pass means only that
every star near the target could be assessed (DR 0025). $hosts

The pixel check in Table 2 is $pixel_check. In each sector, the check measures the offset of the signal's
difference-image centroid (Bryson et al. 2013) from the target. Following LEO-Vetter, it passes when the offset in the
sector of best quality is within $max_offset″. The quality measures how closely the difference image matches the
pixel response function, not how much of the transit it holds (DR 0033). $offsets $rests_on The check cannot
distinguish the target from a star closer than $max_offset″. The signal of TOI-1399.01, for example, comes from a nearby
binary inside that limit, yet TOI-1399.01 passes the check (DR 0032).

### Statistical False-positive Probability

TRICERATOPS (Giacalone et al. 2021) computed the probability of each scenario that could produce the transit: on the
target, on unresolved companions and background stars, and on each nearby TIC star whose light falls in the
photometric apertures.$tdepth_zero

TRICERATOPS ran $tric_times on $tric_data. $tric_probabilities Both are below the thresholds Giacalone et al. (2021)
set for a likely planet, FPP < $fpp_pass and NFPP < $nfpp_pass. $validated

### Literature, Catalogues and Later Listings

The literature search queried Zenodo, arXiv and OpenAlex (Priem et al. 2022) by every name SIMBAD (Wenger et al.
2000) gives the star, including $names, searched NASA ADS by its object search, and retrieved ExoFOP's records for the
star. The search returned $papers, and it passes when all of its queries complete. $exofop

We first made the signal public on $claim_date, $claim_where.$listings

$novelty

$exofop_rows

### Adversarial Review and the Call

An LLM-assisted adversarial review, dated $review_date, looked for reasons the signal might not be on the star, not be
a planet, or not be real and new. The review rates each finding kill, hold or note. Kill means the signal is not a
planet candidate if the finding stands. Hold means the signal cannot pass until the finding is answered. A note needs
no answer. Each finding also names the question it concerns. Refuters are separate LLM-assisted checks, each asked to
disprove one finding. A kill or hold finding is upheld unless a refuter disproves it. $fates Our call answers each
upheld finding. Section 8 quotes the upheld findings with their answers, and Appendix C gives the refuted findings and
the notes. $hits_read

The call also answers three fixed questions in one sentence each: is the target itself an eclipsing binary, does the
transit come from another star, and is it an artefact or a known object? We quote the answers from the call. Any
number in them was written by us and is not filled in from the records (DR 0037).

$sentences

## Held-out Seasons and the Preregistered Test

The held-out season check leaves out one season at a time and refits the period and epoch with BLS on the rest. The
check then measures the held-out season's depth in the cores of the transits the refit predicts in that season (the
central $core of each transit's duration). Because the refit searches only near the original period, and the original
search used every season including the held-out one, the check tests whether the seasons agree with each other. The
preregistered test in this section is the paper's only blind prediction. A season is not testable when, for example,
the depth expected there is too small against its error or too few cadences fall in the predicted cores. A testable
season counts as predicted when its depth is at least ${min_sigma}σ and, for each light-curve family, within
${max_tension}σ of that family's depth in the other seasons. The check passes when at least two seasons are testable
and all of them are predicted. $holdout

$upcoming $prereg

## Discussion

Photometry alone does not measure the transiting body's mass. $companions $blends $eccentric The radius depends on
the TIC stellar radius, which has no uncertainty in the record.

Each upheld finding is quoted below with our answer from the call, and quoted text is reproduced without edits. Where
we later found a mistake in a quote, a dated note follows it. The note is not part of the review or the call (DR 0037).

$answers

## Conclusions

We report a planet candidate around TIC $tic with a period of $period_pm d and a radius of $rp_pm R⊕. It passed our
vetting, and TRICERATOPS gives it a mean false-positive probability of $fpp_pm.$conclusion_prereg It remains a
candidate until photometry that resolves the stars near the target, high-resolution imaging and radial velocities show
whether it is a planet and measure its mass.

## Acknowledgements

This paper $tess_credit$qlp_credit This work uses stellar parameters from the TESS Input Catalog v8.2 (Stassun et al.
2019; Paegert et al. 2021), queried through MAST.$gaia_credit

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

The repository's `ACKNOWLEDGEMENTS.md`, at the commit named in Data Availability, gives every source tess-hunt reads
with its terms and the citation it asks for.

## Use of LLMs

tess-hunt's code and this paper's text were written with LLM assistance. Adversarial reviews this paper quotes were
assisted by LLMs. More information on models is available on GitHub.

**Facilities:** $facilities

**Software:** $software

## Data Availability

The TESS light curves come from MAST: $products. tess-hunt's code, under the MIT licence, is at $repository. The
vetting run for the record reported here used commit $commit, and the commit that generated this paper is named in its
`provenance.json`. The decision records are in the repository's `docs/decisions/` directory at that commit. The
dataset deposited with this paper holds the signal's published records and the light curve that was the input to the
vetting run of $rendered_from. Appendix B describes its files and Appendix D their licences. The remaining numbers
come from the search, threshold, injection-recovery and triage runs listed in Appendix A, published in the repository
under `results/`. The text of this paper is generated from a fixed template, and tess-hunt's code filled in every
number from those files and runs, except in quoted text and the dated notes. We typed the notes by hand and proofread
them (DR 0037).

## References

$references

## Appendix A. Runs

$runs

## Appendix B. Dataset Files

The dataset deposited with this paper holds the signal's published records and one light curve. $records The light
curve, `dataset/$light_curve`, is the input to the vetting run of $rendered_from. `manifest.json` lists each file in
the dataset with its SHA-256 hash and licence. Table 4 lists what each record holds.

$files

## Appendix C. Refuted Findings and Notes

The rules of Section 8 on quoted text and dated notes apply here too.

$refuted

$notes

## Appendix D. Licences

This paper and its figures are licensed under CC BY
4.0<span class="footnote">https://creativecommons.org/licenses/by/4.0/</span>, with two exceptions:

- any Gaia value in text quoted from the review or the call, or in a note, stays under ESA's CC BY-NC 3.0 IGO
  terms<span class="footnote">https://www.cosmos.esa.int/web/gaia-users/license</span>;
- the ExoFOP listings the paper names stay under ExoFOP's
  terms<span class="footnote">https://exofop.ipac.caltech.edu/tess/pcp.php</span>.

The dataset is also CC BY 4.0, with two exceptions:

- its files that hold Gaia DR3 data stay under ESA's terms;
- ExoFOP's rows in its `literature.json`, `claims.json` and `dossier.md` files stay under ExoFOP's terms.
