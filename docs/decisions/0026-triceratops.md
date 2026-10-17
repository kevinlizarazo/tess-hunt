# 0026: TRICERATOPS: the false-positive and nearby-false-positive probabilities, inconclusive wherever they mean nothing

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design), except phase binning (`[triceratops] bin_phase`),
  which is Proposed until the maintainer confirms it at the controls stop (M3 plan, Task 11 Step 7), and Rulings N
  (RUWE joined for a star whose targets row lacks it) and S (possible hosts matched at the TIC's epoch), which the M3
  build's controller made after that approval and are Proposed until the maintainer reviews them

## Context

A dip in a TESS light curve can come from the target or from another star whose light falls in the same 21" pixels.
TRICERATOPS (Giacalone et al. 2021, AJ 161, 24; version 1.1.0, locked in `uv.lock`) weighs the transit as on the
target, on an unresolved companion, on a background star, and on each TIC star within 10 pixels, and returns the
false-positive probability (FPP) and the part of it from nearby stars (NFPP). The spec runs it on every signal no check
has failed, ten times, averaged (`docs/design.md`; M3 design, section 4.5). This is the step that decides "not another
star's light", so a number that means nothing has to come out inconclusive, never pass.

Reading TRICERATOPS 1.1.0's source turned up several ways it returns such a number without an error: it skips a
sector whose TESScut cutout fails and carries on with its stars' pixel positions out of step with the sectors; without
the target's mass, radius, Teff or parallax, `calc_probs` stops at the target and reports probabilities from no
scenario; with no target light in the apertures, `calc_depths` leaves the target out and `calc_probs` takes the next
star as the target; without its Gaia field-star population it skips six scenarios and says so only with `verbose=1`;
it flags NaN or infinite scenario evidence in `FPP_degenerate` and still sets an FPP; a numpy float period is read as a
period range and raises; and it reads a contrast curve with `np.interp`, which returns nonsense for a curve whose
delta mag does not increase, as measured curves don't everywhere.

The plan's input (every cadence within two durations of mid-transit, the paper's N) was timed on the machine (pin P2):
calc_probs grows with the number of points, and on that input the controls' ten runs alone would not finish before the
first follow-up deadline. Averaged into phase bins one exposure wide, one run took about a tenth of the time, with FPP
and NFPP within about one run-to-run spread of the unbinned run on the same draws.

## Decision

**Input** (`tess-hunt vetting triceratops`, `tricera.check`)
- The vet's detrended light curve, rebuilt from the vetting run's `checks.json` as the plots rebuild it (its
  `dropped_suspect` sectors out, detrended around its `masked` rows), then only the `[families] fit` family (SPOC and
  TESS-SPOC PDCSAP). QLP publishes no pixel aperture (pin P3).
- Folded on the density-prior fit's median t0 and period, with its full duration (the vetting run's
  `window_duration`); without that fit, on the signal's ephemeris. `ephemeris_from` says which. `calc_probs` gets the
  fold within two durations of mid-transit, in days from it.
- The depth is the one the neighbour table scaled its required depths from (the signals file's), so its possible
  hosts and TRICERATOPS's per-star `tdepth` can be compared. `dilution_corrected` is true in `calc_depths` and
  `calc_probs`: PDCSAP is corrected for crowding.

**The cadence group** (`tricera.cadence_group`; Ruling J, pin P3 for mixed cadences). `calc_probs` takes one exposure
time for every point. Each cadence of the PDCSAP sectors is a candidate exposure E; its group is every sector at E or
faster, the faster ones averaged in time to E (`tricera.to_exposure`: consecutive bins one exposure long from the
sector's first cadence, each kept when it holds at least half the cadences it would hold full; a bin's time and flux
are its cadences' means, its error their errors in quadrature over their number). Among the groups with at least
`[triceratops] min_transits` (3) transits, the one with the most in-transit cadences after averaging wins; a tie goes
to the shorter E. The group's sectors are those with data within the fold's window; every candidate and every sector
left out (slower than E, or no data in the window) is recorded. With no group, the check is inconclusive and says how
many transits each candidate held. 48010903, 410399327 and 441010857 have no single cadence with three transits;
averaged to 600 s, their 120 s and 200 s data become 600 s integrations, which is what one exposure time models.

**Apertures** (`tricera.apertures`). SPOC 2-min sectors take TRICERATOPS's `get_spoc_apertures`. TESS-SPOC sectors
take bit 2 of the `APERTURE` extension of the light-curve file the photometry came from, as CCD (column + `CRVAL1P`,
row + `CRVAL2P`), the conversion TRICERATOPS's own `get_aperture` uses (pin P3). The file is fetched again by its S3 key
into the data directory's `lc_fits/` and must match the sha256 fetch recorded, so the aperture is the one the
photometry used. Each sector records where its aperture came from, its pixel count, the file's sha256, whether the
target's pixel in TRICERATOPS's frame falls inside it, and the pixels themselves as passed to `calc_depths`
(`ccd_pixels`, column and row): SPOC's come from the archive at run time, so the run keeps them to be audited later
(Ruling O).

**Phase binning** (`[triceratops] bin_phase = true`; Ruling G, Proposed). The fold is averaged into phase bins one
exposure wide: the data's own time sampling, one point per bin instead of one per transit. `flux_err_0` is the median
over bins of the median cadence error over the square root of the bin's count. With `bin_phase = false` every point
goes in and `flux_err_0` is the median cadence error, the plan's literal input. If the maintainer chooses the unbinned
input at the controls stop, the controls' TRICERATOPS runs are made again unbinned and this record is amended.

**Runs.** `[triceratops] runs` (10) runs, each after `np.random.seed(i)` for run i from 0, with `N = [triceratops]
draws` (1,000,000, the paper's), `P_orb` as a Python float, `parallel=False` (PyTransit then evaluates every transiting
draw at once, past the run's memory cap; pin P2), `exptime` the group's exposure and `verbose=0`. The evidence keeps
each run's FPP and NFPP, their means and standard deviations, and the last run's scenario table (`probs.csv`).

**Contrast curves** (Ruling K, pin P4). `--contrast` is a CSV `tic,file,filt,source_url` listing ExoFOP's
machine-readable curves as downloaded, never a curve read off a PDF. `filt` is one of TRICERATOPS's `TESS`, `Vis`, `J`,
`H`, `K` (the optical speckle bands are `Vis`, PHARO's Br-gamma is `K`). Each is converted into the run directory as
the two columns TRICERATOPS reads (separation in arcsec, delta mag, comma separated): from the Gemini and WIYN speckle
`.dat` files, the annulus centre and delta mag of the measured annuli (the reduction's fitted curve that follows them
in two columns is not read); from the PHARO `.tbl`, `arcsec` and `dmag`. Rows at zero separation go. A measured curve
dips here and there, and `np.interp` in TRICERATOPS needs delta mag increasing, so the curve is lowered from outside
in: each separation keeps the smallest delta mag reached there or at any wider separation, and of equal values the
widest separation stays (keeping the closest would interpolate from it to the next, deeper point and claim more than
the run measured). The curve then never rules out a companion the data don't. A file in neither layout, a
filter TRICERATOPS lacks, or a missing file refuses the run before it starts. The original's and the converted file's
sha256, the layout, and how many rows the envelope lowered are recorded.

**Outcomes** (`tricera.outcome`, `[triceratops]`, the paper's thresholds):
- **pass** when mean FPP < `fpp_pass` (0.5) and mean NFPP < `nfpp_pass` (0.001): "likely planet";
- **fail** when mean NFPP > `nfpp_fail` (0.1): "likely nearby false positive";
- otherwise **inconclusive**.
- `validated_label` is true only when the check passes, a contrast curve was used, the group is 2-min (120 s), and
  mean FPP < `fpp_validated` (0.015) and mean NFPP < `nfpp_pass`: the paper's "validated planet". It is a label in the
  evidence, never an outcome, and never appears in a public claim as "confirmed".

**Inconclusive whatever the numbers**, each blocker named in the reason:
- RUWE over `[triceratops] max_ruwe` (1.4), or no RUWE for the target: an unresolved companion the priors don't
  condition on (103312990's is 6.21 in the
  [triage shortlist](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/shortlist.csv)). The RUWE is the
  targets row's, or for a star whose row lacks it (the controls' `targets tics` tables join no Gaia DR3 columns), the
  one `vetting run` joins through the TIC's Gaia DR2 id with `gaia.dr3_join`, once per run (Ruling N). `checks.json`'s
  `star` row says where it came from (`dr3_from`: `targets`, `dr3_join` or `missing`) and why it is null
  (`dr3_reason`); the run's provenance records the TICs joined and whether the join worked. A failed join is not fatal:
  those stars have no RUWE, and TRICERATOPS is inconclusive on them;
- an inconclusive neighbour table (decision 0025);
- no cadence group with `min_transits` transits;
- no aperture for a group sector;
- TESScut giving fewer cutouts than sectors, a first star that is not the target, or a target without mass, radius,
  Teff or parallax;
- calc_depths leaving the target no light in the apertures;
- no usable depth (not a fraction between 0 and 1);
- no field-star population (`target.trilegal_fname` not a path): TRICERATOPS skipped DTP, DEB, DEBx2P, BTP, BEB and
  BEBx2P;
- any exception, named;
- a run TRICERATOPS flags degenerate, or any non-finite FPP or NFPP in any run;
- a possible host TRICERATOPS did not weigh: a star the neighbour table says could host the signal with no
  TRICERATOPS star other than the target within `[triceratops] match_arcsec` (2.0") of it, so the NFPP leaves it out
  (M3 design, section 4.4; a close companion the TIC merged or lacks). The target is left out of the match because
  TRICERATOPS weighs it as the target: a companion the TIC merged into it sits nearer the target than any other star
  and would otherwise count as weighed. The evidence lists every possible host beside the TRICERATOPS star matched to
  it and that star's `tdepth`, the cross-check of the two lists.
- The match compares positions at one epoch (Ruling S). TRICERATOPS's stars are TIC v8 positions, at epoch J2000.0;
  the neighbour table's are Gaia DR3's, at J2016.0 (`tricera.TIC_EPOCH`, `tricera.GAIA_DR3_EPOCH`). Each possible
  host is moved back to J2000.0 with its DR3 proper motion before matching (`tricera.at_tic_epoch`: `dec - pmdec * 16
  / 3.6e6` and `ra - pmra * 16 / (3.6e6 cos dec)` in degrees, DR3's `pmra` already carrying cos dec); a host with no
  proper motion (a two-parameter solution) matches at its DR3 position. Without this, a host and its own TIC star read
  as two stars when they move fast: 44926986's 12.5" possible host is TIC 44926982, which TRICERATOPS gave the same
  depth, yet the two positions sit 2.78" apart, beyond `match_arcsec` (the M3 build's smoke runs, Tasks 9 and 10b;
  moved to J2000.0, the host sits 0.001" from TIC 44926982). `match_arcsec` is unchanged. `hosts` keeps each host's proper motion, its position at J2000.0 (`ra_2000`, `dec_2000`) and its distance
  there from the nearest TRICERATOPS star.

**A possible host TRICERATOPS gave no depth** (Ruling M) is evidence, not a blocker. When a possible host matches a
TIC star whose TRICERATOPS `tdepth` is 0, TRICERATOPS judged that star unable to make the dip and weighed no scenario
on it. The neighbour table counts the star's whole light in the aperture, an upper bound on its flux there that
ignores the aperture, so its required depth is the least the star could need; TRICERATOPS's depth comes from the light
its PSF model puts in the apertures actually used, the better-informed of the two. This departs from the M3 design,
section 4.4, which says the two must agree on which neighbours are possible. The cost: TRICERATOPS can pass while a
star it put outside the apertures could host the signal by the table. The review's on-the-star lens and the pixel
check's per-sector centroid offsets cover that case, and each such host is listed in `hosts_tdepth_zero` (and, with
its TIC match and `tdepth`, in `hosts`) so the review sees it.

Where TRICERATOPS can still run (RUWE, the neighbour table, the field-star population, a missing host), it runs and its
numbers are kept as evidence for the review; where it cannot give a meaningful number (no group, no aperture, a target
it can't weigh), it stops before `calc_probs`. On every path the evidence holds every field `run` records
(`tricera.RUN_FIELDS`). `run` fills each as it gets there, in a dict `check` keeps when `run` raises, so a run that
raised keeps what it reached (the cadence group, the fold, the star list and its host match, the apertures, the
`calc_probs` runs that finished) and names the exception in `raised`. None marks a step it never reached, and
`hosts_tdepth_zero` is None until `calc_depths` has given depths. The record says how far TRICERATOPS got, and the
dossier says only that (decision 0028).

**The stage.** `tess-hunt vetting triceratops --run VETTING_RUN [--signals NAME ...] [--contrast CSV]
[--criteria-search ...] [--criteria-vet ...] [--workers N] [--production]` runs one job per signal no check failed in
the vetting run, or the named ones. Before its run starts it refuses an unfinished or evidence-only vetting run, a
non-production one under `--production`, search or vet criteria whose sha256 differs from the vetting run's (one run,
one criteria file), a signal the run did not vet, a light curve changed since the vetting run, and any contrast file it
can't read. Each signal gets `signals/<name>/triceratops.json`, `probs.csv` and TRICERATOPS's Gaia field-star file
`<tic>_gaia_background.csv`; the provenance records the vetting run, each signal's `checks.json`, the light curves,
the contrast CSV and each original curve.

**Controls** (M3 design, section 4.3). TOI-1058.01 and TOI-1175.01, eclipsing binaries 20.90" and 23.53" from their
targets (decision 0025), must fail (NFPP > 0.1). If either does not, TRICERATOPS can't gate and the build stops for the
maintainer. TOI-1399.01, a nearby eclipsing binary inside the pixel rule's 15" (`benchmarks/README.md`), must not pass.
If it passes, a TRICERATOPS pass does not cover a blend inside 15", and the build stops before 44926986 is judged
(its triage centroid offset is 10.9" in the
[triage shortlist](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/shortlist.csv)).

**The DDT ask** (M4; M3 design, section 4.5) is for passed signals whose next TESS look is FFI-only: the TRICERATOPS
paper's own caveat that 30-minute data cannot validate is the case for 2-min data. A held signal whose deciding
evidence is the transit's shape may go to the DDT ask on the maintainer's call; one held on blending may not, since
2-min data have the same 21" pixels.

**Licence.** RUWE, the neighbour table's positions and the Gaia field-star file are Gaia DR3 data or computed from it
(credit ESA/Gaia/DPAC) and stay under ESA's CC BY-NC 3.0 IGO terms (decision 0025); `results/README.md` says so for
`triceratops.json` and the field-star file when they are published.

## Limitations

- A possible host without a DR3 proper motion is matched at its DR3 position, so one that moved more than
  `match_arcsec` between the epochs reads as missing; that leaves the check inconclusive, the safe direction. The
  propagation is linear in RA and Dec and leaves out the change in proper motion from radial velocity, far below
  `match_arcsec` over 16 years. The match is still to the nearest star, not one to one: two hosts can match one TIC
  star.
- Binning assumes the model changes little across a bin. Each binned point is a one-exposure integration averaged over
  a bin one exposure wide, so the transit's edges are smoothed over up to two exposures where the model sees one.
- A faster sector averaged to E keeps bins with half their cadences or more, so a bin's integration can be shorter
  than E; 120 s data averaged to 200 s sit one or two cadences to a bin. The group leaves out slower sectors and their
  transits, which the evidence lists.
- The lowered contrast curve gives up sensitivity at a separation where a wider annulus measured less.
- The depth is the signals file's, from the search's light curve, which mixes product families; on a crowded star a
  diluted QLP sector makes it shallower than the PDCSAP depth TRICERATOPS fits.
- The field-star population comes from Gaia DR3, TRICERATOPS 1.1.0's default, not a TRILEGAL simulation.
- TRICERATOPS fills a missing TIC mass, radius or Teff from photometry (`estimate_missing_params`); only the target's
  parallax has no stand-in, and its absence is a blocker.
- The runs share one target (the TIC query, TESScut and the field-star population), so their spread measures only the
  Monte Carlo noise.
- A star without a RUWE is inconclusive: one whose DR3 join failed or found no source, or whose DR3 source has no
  RUWE.

## Evidence

- [tests/test_tricera.py](../../tests/test_tricera.py):
  - `test_outcome_pass_fail_and_between` (pass, fail, the cases between, NFPP at the fail line, blockers), and
    `test_a_non_finite_or_missing_run_is_inconclusive`.
  - `test_missing_field_population_is_inconclusive`, `test_nan_or_raise_is_inconclusive` (a NaN FPP, an infinite
    NFPP, an exception named, a degenerate run), `test_missing_aperture_is_inconclusive` (a SPOC sector without one,
    and a QLP sector), `test_high_ruwe_is_inconclusive` (6.21, and none),
    `test_a_possible_host_triceratops_did_not_weigh_is_inconclusive` (a Gaia star 30" out with no TIC star near it,
    and one 1.5" from the target with only the target near it),
    `test_an_inconclusive_neighbour_table_is_inconclusive`, and
    `test_a_target_triceratops_cannot_weigh_is_inconclusive` (a missing TESScut cutout, a target without a parallax,
    a first star that is not the target, no target light in the apertures).
  - `test_a_host_triceratops_gave_no_depth_is_evidence_not_a_blocker` (Ruling M: the check passes and lists the host
    in `hosts_tdepth_zero`).
  - `test_a_host_is_matched_at_the_tic_epoch` (Ruling S: a host 2.78" from its TIC star at J2016.0 whose motion brings
    it within 0.03" at J2000.0 is matched; without a proper motion it stays missing, as does one whose motion takes it
    away; `hosts` keeps the position at J2000.0 and the distance there).
  - `test_every_path_records_the_same_fields` (a finished run and one that raised hold the same fields) and
    `test_a_run_that_raised_keeps_what_it_reached` (a raise in TESScut after the fold, and on the second seed's
    `calc_probs`, which keeps the first run, the star list and the host match); in
    `test_a_target_triceratops_cannot_weigh_is_inconclusive`, `hosts_tdepth_zero` is None before `calc_depths`.
- [tests/test_vetting.py](../../tests/test_vetting.py): `test_a_star_without_dr3_values_gets_them_from_the_join`
  (Ruling N: one join, a row with both values never joined again) and
  `test_a_star_the_join_gives_nothing_keeps_nulls_and_the_reason` (a failed join, and none found: null values, the
  reason, and the run finishes).
- [tests/test_dossier.py](../../tests/test_dossier.py): `test_a_triceratops_record_from_any_path_renders` (each
  sentence true to the record: a raise before the group, after the fold, and on a later seed; each stop).
  - `test_validated_label_needs_contrast_and_2min` and `test_runs_are_seeded_and_averaged` (seeds 0 to runs - 1, a
    float period from a numpy one, `parallel=False`, the group's exposure, `dilution_corrected`, and each sector's
    `ccd_pixels` equal to what `calc_depths` got).
  - `test_cadence_group_picks_the_richest_group`, `test_cadence_group_averages_faster_sectors_to_the_slower_exposure`
    (two transits at 600 s and one at 200 s make a 600 s group of three) and
    `test_faster_sectors_are_averaged_to_the_exposure` (the half-full rule).
  - `test_phase_bins_keep_one_exposure_sampling` (both settings of `bin_phase`).
  - `test_tess_spoc_aperture_comes_from_the_light_curve_file` (bit 2 and the CCD offsets, the cache, a file that is
    not the one fetch read).
  - `test_contrast_curves_convert_to_triceratops_two_columns` (both layouts, read back by TRICERATOPS's own reader;
    interpolated as TRICERATOPS interpolates, the curve never exceeds the measured delta mag at a measured separation)
    and
    `test_a_contrast_file_in_neither_layout_is_refused`, on small synthetic files in ExoFOP's layouts.
  - `test_triceratops_runs_on_the_signals_no_check_failed` (with each sector's `ccd_pixels` in `triceratops.json`),
    `test_contrast_curves_are_converted_into_the_run`,
    `test_triceratops_refuses_what_it_cannot_stand_behind` and `test_triceratops_refuses_an_evidence_only_run`.
- The network controls `test_nearby_eb_controls_fail_triceratops` (TOI-1058.01, TOI-1175.01) and
  `test_toi_1399_does_not_pass_triceratops`, one run each, and the controls' production runs at ten runs (M3 plan,
  Task 11).
