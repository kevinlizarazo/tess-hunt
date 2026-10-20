# Pixel check diagnosis: the four known-planet fails and the six second-list fails

- Date: 2026-10-20. A read-only analysis outside the pipeline. It changes nothing and gates nothing.
- The question: how far a fail of triage-v1's pixel check (`[pixels]`: the best-quality sector's centroid offset over
  15") can be trusted when it kills a second-list row (M3 design, sections 4.3 and 4.10).
- Runs read: pixel completeness `20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33` (published as
  `results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/`; its difference images under
  `~/.cache/tess-hunt/tdi/<run id>/`), second list `20261020T012658Z-vetting-second-list-62882b5-3fca` (its
  `tdi/`), vetting `20261020T010149Z-vetting-run-62882b5-c3ee`, control vet `20261017T155223Z-vetting-run-62882b5-4867`,
  and M2's nearby-binary pixel controls (`results/triage/pixel-controls-2026-10-16.txt`, difference images kept under
  `~/.cache/tess-hunt/pixel-controls-2026-10-16/`).
- Every number below comes from a run file or from a script in `pixel-check-diagnosis-2026-10-20-scripts.tar.gz`
  beside this file (last section).

## Summary

- **None of the four known-planet fails measures where the transit comes from.** They sit on the four brightest hosts
  in the set (Tmag 5.05 to 6.64). TOI-144.01 and TOI-2011.02 are saturated: the transit's loss shows at the ends of the
  bleed column, and the one-PRF fit follows the column, 1.7 to 3.4 pixels from the star, in 9 of their 10 sectors.
  TOI-396.03 is a saturating host with a 212 ppm transit its images barely hold. TOI-4307.01 (109 ppm, one transit per
  sector) holds no measurable transit, and its fits land on noise around a bright star.
- **So the check's outcome means nothing on a host brighter than about Tmag 6, or when a sector's difference image holds
  too little transit.** A pass means nothing there either: TOI-396.01, on the same star as TOI-396.03, passed on a
  sector whose image shows no transit at the star.
- **A real off-target source looks different, and the saved difference images show it.** In M2's nearby-binary
  controls the fit returns to the same sky position sector after sector (scatter 1.7" to 5.9") while its position on
  the detector moves, and a fit with PRFs held at the target and the neighbour finds nothing at the target. No known
  planet does that. `pixels.json` keeps each offset's size but not its direction, so the recorded numbers alone can
  suggest the pattern but can't confirm it; the difference images the runs kept can.
- **Second list.** 322826591-1, 337885456-1, 458290782-1 and 173369850-1 show that pattern, on a catalogued star that
  can host the depth: off-target source supported. 295140687-1 points the same way, more weakly. 423100454-1 is a
  failure of the check: in S102 and S65 a variable star 121" away (TIC 423100496) captured the fit, null images of the
  same sectors land on that star with larger losses, and the transit sits at the target in all five sectors.
- **SPOC's DV statistics** put 322826591-1's source 38.0" ± 2.6" from the target, and 458290782-1's TCE on
  TIC 1343588382, the star our fits land on, 1.7" ± 2.6" from it, with a 23,215 ppm weak secondary. SPOC has no
  difference-image offsets for the other four.

## How the numbers were made

- **The check's own fits, rebuilt.** Each measured sector's transit-diffImage pickle holds the difference image, the
  mean out-of-transit image, the cutout's TIC catalogue, the pixel time series and the ephemeris the check used.
  Refitting the PRF to each saved difference image with LEO-Vetter's calls (`leo_vetter.pixel.prf_fit`) reproduces the
  149 recorded offsets and qualities (100 known-planet sectors, 49 second-list sectors) to within 4e-14, and the 15
  control sectors match the published control printout to its two decimals. Rebuilding each of the 164 difference
  images from its pixel time series with transit-diffImage's `find_transits` reproduces the saved image. So the fitted
  position, which `pixels.json` does not keep, is the check's own.
- **Direction.** For each fit, the offset east and north on the sky, and in CCD column and row from the target. A
  source on the sky keeps its sky position from sector to sector while its detector position turns with the camera; a
  bleed column does the opposite. "Sky scatter" is the RMS distance of the sector fits from their quality-weighted mean
  position, "detector scatter" the same in the CCD frame. "Mean offset in standard errors" is that mean's distance from
  the target over (sky scatter / root of the sector count).
- **Null images.** For each sector, the same difference image made at up to 16 phases with no transit (kept 2.5
  durations clear of the transit and of phase 0.5), fitted the same way. They give the noise of the in-transit loss in
  a 3 x 3 pixel box at the star (median-subtracted image): "z" is the box's loss over the nulls' scatter, beside the z
  the light curve's depth would give ("exp"). They also show how PRF-like a no-transit image gets: "Nulls >= Q" counts
  the nulls whose fit quality reaches the transit image's. transit-diffImage's own SNR image is not used: it divides by
  the error of one cadence, not of the in-transit mean, so it understates the SNR by about the root of the in-transit
  cadence count.
- **Saturation.** The peak pixel of the mean out-of-transit image at the star (e-/s), and the number of pixels in the
  star's CCD column above half that peak ("Col"): 1 or 2 for an unsaturated star, more when charge bleeds.
- **Fixed-position fit.** PRFs held at the target's and one neighbour's catalogue positions, plus a constant, fitted to
  the difference image; each amplitude's z comes from the same fit to the null images. It asks which of the two stars
  carries the loss. This is not the check, which fits one PRF anywhere in the cutout. Its false-alarm rate on the known
  planets: the neighbour (there, the brightest star within 60") got z 3 or more, and more than the target, in 1 of 75
  sectors on the unsaturated hosts (TOI-4320.01 S3, a Tmag 17.0 star 57" out, z 6.3) and in 4 of 20 on the saturated
  ones (the bleed). On the controls it did so in 10 of 15 sectors: every sector of TOI-1175.01 and TOI-1399.01, none of
  TOI-1058.01, whose neighbour reached z 2.9 at most while the target stayed within 0.4 of zero.
- **Not used: a pooled position.** `locate.py` tried a least-squares map of the source position on a sky grid, summing
  the sectors with each sector's pixel variance from its nulls. Single sectors with large systematics dominated its
  statistic (TOI-576.01's S8, TOI-4320.01's S3, TOI-107.01's S105), so it was stopped after 22 signals and nothing
  below rests on it (`locate.txt` holds what it printed).
- **Neighbours.** The star at the fitted position comes from the cutout's TIC catalogue and is matched by position to
  the vet run's Gaia DR3 neighbour table (`neighbours.csv`), whose `required_depth` takes the neighbour's whole flux to
  be in the aperture. "Aperture share" also counts how much of the neighbour's PRF falls in a 3 x 3 aperture on the
  target, with the TIC's Tmag, a rough stand-in for SPOC's and QLP's apertures.
- **Network.** Nothing beyond what the imports do: importing transit-diffImage contacts the Gaia archive, and the PRF
  model files it opens by URL all came from astropy's download cache (no cache file was written during these runs). No
  TESScut cutout was fetched.

## 1. The four known planets

| Planet | Tmag | Depth | Transits per sector | Offsets | Best sector | Col | Along column | Cause |
|---|---|---|---|---|---|---|---|---|
| TOI-144.01 | 5.11 | 321 ppm | 3 to 5 | 44.3 to 61.9" | S95, 46.8" | 5 to 6 | 5 of 5 | saturated, bleed column |
| TOI-2011.02 | 5.05 | 555 ppm | 1 | 32.8 to 69.0" | S65, 69.0" | 5 to 7 | 4 of 5 | saturated, bleed column |
| TOI-396.03 | 5.91 | 212 ppm | 1 to 3 | 8.8 to 47.0" | S107, 35.6" | 2 to 4 | 3 of 5 | short bleed, little signal |
| TOI-4307.01 | 6.64 | 109 ppm | 1 | 13.6 to 23.8" | S98, 17.9" | 1 to 2 | 1 of 5 | too little signal |

"Along column": sectors whose fit sits more than 1 pixel up or down the star's CCD column and less than half that
across it.
Crowding plays no part: CROWDSAP is 0.995 to 1.0 in every SPOC sector of these stars and the TIC contamination ratio
0.006 at most. Cutout size plays none either: every fit lies inside the 21 x 21 pixel cutout (441", the target at its
centre), 70" out at most.

- **TOI-144.01 (Pi Men c, TIC 261136679).** The peak pixel is 103,032 to 111,234 e-/s and 5 or 6 pixels of the star's
  column sit above half that peak: the star bleeds. All five fits lie on the column, 2.18 to 3.04 pixels along it and
  0.66 at most across it: up the column in S93 to S95, down it in S88 and S89. On the sky the same fits scatter by
  26.8". A PRF held at the star finds no loss (fixed-fit z -0.8 to 1.6), yet the transit images are more PRF-like than
  their nulls (0 to 6 of 16 nulls reach their quality): the loss is there, at the ends of the bleed column, where a
  saturated star's charge shows the change. A one-PRF model can't fit a bleed column, so the offset measures the bleed's
  length.
- **TOI-2011.02 (TIC 136916387).** Peak 108,180 to 125,794 e-/s, 5 to 7 column pixels above half peak. Four of five
  fits lie along the column, 1.67 to 3.42 pixels from the star. One transit per sector (period 27.6 d). Fixed-fit z at
  the star 0.9 at most. The same cause as TOI-144.01.
- **TOI-396.03 (HR 858, TIC 178155732).** Peak 84,934 to 102,485 e-/s, 2 to 4 column pixels above half peak: at the
  edge of saturation, with a short bleed. Three of five fits lie along the column. The 212 ppm transit gives an expected
  z of 0.6 to 3.8 per sector at the star; measured, -0.2 to 2.4 in the box and -0.3 to 1.3 in the fixed fit (3.8 in
  S31). In S105, 12 of 16 null images fit as well as the transit image. The fits scatter on the sky by 26.6".
- **TOI-4307.01 (TIC 141186075).** Peak 64,982 to 80,463 e-/s with 1 or 2 column pixels above half peak: no visible
  bleed. A 109 ppm transit, once per sector, gives an expected z of 0.1 to 1.8; the fixed fit finds 0.9 at most at the
  star. In four of five sectors 3 to 9 of the 12 to 16 null images fit as well as the transit image, and the nulls'
  median quality is 0.53 to 0.61: around a bright star any difference image looks fairly like a PRF. The offset sizes
  stay similar (13.6 to 23.8") while the directions point every way (east, north: -14, +12; -12, +20; -14, -1; +19,
  +15; +16, +5"), a sky scatter of 16.6". The fail rests on S98, the sector whose noise looked most like a PRF (0.91).
- **TOI-396.01 passed, on no evidence.** Same star. The pass rests on S31 (6.7", quality 0.73), where the box z at the
  star is -1.2 (1.8 expected) and 2 of 13 nulls fit as well; the other sectors sit 26.2 to 59.0" out. Decision 0031
  found transit-timing variations of 0.30 to 0.40 d on this planet, longer than its 3.1-hour in-transit window, so the
  catalog ephemeris's windows can miss its transits outright.

Per sector. Off: the check's offset; Q: its quality; E, N: the fit east and north of the target; dcol, drow: the fit
minus the target in CCD pixels; Tr: transits used of those in the sector (LEO-Vetter's `n_bad = 0` keeps only the
transits with the fewest flagged cadences); Peak in e-/s; Fixed z: the fixed-position fit's z at the star / at the
neighbour (here the brightest star within 60").

| Signal | S | Cam | Off | Q | E, N (") | dcol, drow | Tr | Peak | Col | z (exp) | Fixed z | Nulls >= Q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TOI-144.01 | 95 | 3.3 | 46.8" | 0.77 | -41, -22 | +0.66, +2.42 | 3/3 | 111234 | 5 | -0.8 (2.4) | -0.5/3.5 | 0/16 |
| TOI-144.01 | 94 | 3.3 | 59.0" | 0.70 | -30, -51 | +0.32, +2.91 | 4/4 | 105692 | 6 | 0.0 (0.8) | -0.2/0.2 | 0/16 |
| TOI-144.01 | 93 | 3.4 | 61.9" | 0.76 | +6, -62 | -0.34, +3.03 | 4/4 | 104861 | 6 | 0.1 (0.8) | 0.0/0.7 | 0/16 |
| TOI-144.01 | 89 | 4.4 | 44.3" | 0.44 | -43, -11 | -0.08, -2.18 | 5/5 | 109321 | 6 | 1.7 (9.1) | -0.8/3.8 | 2/16 |
| TOI-144.01 | 88 | 4.4 | 60.4" | 0.42 | -45, -41 | -0.10, -3.04 | 4/4 | 103032 | 6 | 3.3 (7.2) | 1.6/3.3 | 6/16 |
| TOI-2011.02 | 103 | 1.4 | 64.7" | 0.50 | +27, -59 | +0.04, +3.08 | 1/1 | 109206 | 7 | 1.2 (4.2) | 0.5/0.7 | 0/12 |
| TOI-2011.02 | 102 | 2.3 | 35.2" | 0.40 | -5, -35 | +1.31, +1.24 | 1/1 | 108585 | 5 | -0.1 (0.4) | -0.1/-0.1 | 6/14 |
| TOI-2011.02 | 65 | 1.2 | 69.0" | 0.78 | +14, +68 | -0.17, +3.42 | 1/1 | 111821 | 5 | 0.4 (2.2) | 0.9/1.1 | 0/14 |
| TOI-2011.02 | 38 | 1.2 | 60.5" | 0.39 | -19, -57 | -0.20, -3.09 | 1/1 | 108180 | 6 | 2.5 (6.9) | 0.4/4.1 | 5/13 |
| TOI-2011.02 | 12 | 1.1 | 32.8" | 0.59 | -20, -26 | -0.57, -1.67 | 1/1 | 125794 | 5 | 0.0 (1.0) | 0.0/1.3 | 0/10 |
| TOI-396.03 | 107 | 2.2 | 35.6" | 0.73 | -35, -3 | -0.17, +1.76 | 2/3 | 84934 | 4 | 2.4 (3.8) | -0.3/0.6 | 0/16 |
| TOI-396.03 | 106 | 3.4 | 20.1" | 0.57 | -10, +18 | +0.96, +0.13 | 2/2 | 100491 | 3 | 1.8 (2.8) | -0.2/0.5 | 4/16 |
| TOI-396.03 | 105 | 4.1 | 47.0" | 0.39 | -26, -39 | +0.60, -2.14 | 2/3 | 87371 | 3 | -0.2 (0.8) | 0.1/-0.6 | 12/16 |
| TOI-396.03 | 97 | 2.2 | 30.8" | 0.68 | +15, -27 | -0.04, -1.47 | 3/5 | 90125 | 3 | 0.8 (2.6) | 1.3/-0.9 | 0/16 |
| TOI-396.03 | 31 | 2.1 | 8.8" | 0.43 | -9, +0 | -0.42, +0.11 | 1/2 | 102485 | 2 | 2.2 (0.6) | 3.8/-4.6 | 4/8 |
| TOI-4307.01 | 98 | 4.3 | 17.9" | 0.91 | -14, +12 | -0.59, +0.64 | 1/2 | 77961 | 1 | 2.5 (1.8) | 0.9/-0.2 | 0/16 |
| TOI-4307.01 | 97 | 4.3 | 23.0" | 0.57 | -12, +20 | +0.62, +0.94 | 1/1 | 75570 | 2 | 1.8 (1.7) | 0.1/0.0 | 7/16 |
| TOI-4307.01 | 96 | 4.2 | 13.6" | 0.52 | -14, -1 | -0.10, -0.66 | 1/1 | 64982 | 2 | 0.1 (0.1) | 0.1/0.2 | 9/12 |
| TOI-4307.01 | 95 | 4.2 | 23.8" | 0.61 | +19, +15 | -0.05, +1.19 | 1/1 | 78606 | 2 | 0.0 (0.1) | -0.0/-0.2 | 3/12 |
| TOI-4307.01 | 94 | 4.2 | 16.5" | 0.59 | +16, +5 | +0.57, +0.58 | 1/1 | 80463 | 2 | 0.2 (0.3) | 0.1/0.0 | 8/13 |
| TOI-396.01 | 107 | 2.2 | 26.3" | 0.46 | +24, -11 | -0.50, -1.20 | 2/5 | 84965 | 4 | 0.2 (2.6) | 0.8/-0.7 | 9/16 |
| TOI-396.01 | 106 | 3.4 | 26.2" | 0.52 | -26, +6 | +0.69, +1.05 | 2/4 | 100412 | 3 | 0.1 (9.1) | -1.3/1.3 | 10/16 |
| TOI-396.01 | 105 | 4.1 | 59.0" | 0.30 | -37, -46 | +0.52, -2.74 | 4/5 | 87372 | 3 | -0.8 (1.1) | 0.3/-1.5 | 10/16 |
| TOI-396.01 | 97 | 2.2 | 28.9" | 0.63 | -21, +20 | -0.38, +1.34 | 7/9 | 90168 | 3 | 5.5 (7.5) | 1.0/-0.4 | 2/16 |
| TOI-396.01 | 31 | 2.1 | 6.7" | 0.73 | -6, +4 | -0.23, +0.23 | 2/2 | 102239 | 2 | -1.2 (1.8) | -0.6/0.1 | 2/13 |

### Failure modes a reader can recognize

From the recorded numbers alone (`pixels.json`'s offset sizes and qualities, with the star's Tmag, the depth and the
period):

- **Saturated host.** Tmag about 6 or brighter (here 5.05 to 5.91), offsets up to 70" (3.5 pixels) that change by 18"
  to 38" between sectors, qualities 0.39 to 0.78. Neither outcome means anything. The four fails sit on the four
  brightest hosts in the set; the one planet on those hosts that passed (TOI-396.01) passed by chance.
- **Too little transit in the images.** A shallow transit, one or two per sector, on a bright star (TOI-4307.01). The
  sizes can look steady (13.6 to 23.8") while the directions point every way, so the recorded numbers can't tell this
  from a real source at that distance; the saved difference images can. The same scatter sits behind many passes: 10 of
  the 16 known-planet passes have a sector beyond 15" (TOI-1097.02 at 41.8", TOI-576.01 at 44.9", TOI-396.01 at 59.0")
  and pass because their best-quality sector fell near the star.
- **A variable star elsewhere in the cutout** (no known planet shows it; 423100454-1 does). The offsets split into two
  groups: a few arcseconds in some sectors, one large, repeated offset at high quality in the others.
- **A real off-target source** (TOI-1175.01, TOI-1399.01, and TOI-1058.01 outside S13): offset sizes within 4" of each
  other in every sector, qualities 0.42 to 0.96. Confirming it takes the saved images: the sky position repeats (scatter
  1.7" to 5.9") while the detector position moves (10.6" to 20.5"), and the mean offset sits 7.8 to 26.6 standard errors
  from the target, where no unsaturated known planet exceeds 1.4.

## 2. The six second-list rows

None of the six targets is saturated (Tmag 8.26 to 10.38, peak pixel 2,185 to 22,789 e-/s), so the bleed mode can't
apply to any of them.

| Row | Tmag | Depth | Offsets | Sky scatter | Mean offset (std errors) | Rating |
|---|---|---|---|---|---|---|
| 173369850-1 | 10.18 | 734 ppm | 24.7 to 36.2" | 5.0" | 30.1" (13.5) | off-target source supported |
| 295140687-1 | 10.18 | 370 ppm | 6.8 to 22.9" | 10.3" | 13.7" (3.0) | off-target source supported, weakly |
| 322826591-1 | 9.15 | 546 ppm | 37.8 to 41.3" | 1.8" | 39.8" (48.8) | off-target source supported |
| 337885456-1 | 8.26 | 170 ppm | 40.4 to 42.3" | 2.8" | 41.1" (29.4) | off-target source supported |
| 423100454-1 | 8.62 | 448 ppm | 5.7 to 118.6" | two groups | two groups | a check failure, not an off-target source |
| 458290782-1 | 10.38 | 1149 ppm | 19.8 to 27.4" | 2.8" | 24.7" (19.5) | off-target source supported |

423100454-1's rating is none of the known planets' modes: a variable neighbour captured the fit (below).

The stars at the fitted positions, each matched within 0.1" to a Gaia DR3 star that the vet run's neighbour table
calls a possible host (Tmag and distance from the target are the table's; distance from the mean fit uses the TIC
position; the cutout's TIC lists TIC 322826642 a second time as TIC 916591898):

| Row | Star (Gaia DR3) | Tmag | From target | From mean fit | Depth needed: table; aperture share |
|---|---|---|---|---|---|
| 173369850-1 | TIC 173369830 (5915858610302704384) | 15.35 | 31.3" | 1.3" | 8.6%; 10 to 15% |
| 295140687-1 | TIC 295140710 (5235195633516208128) | 15.76 | 17.6" | 4.0" | 6.3%; 6 to 10% |
| 295140687-1 | TIC 295140717 (5235195633516931072) | 14.48 | 23.4" | 11.5" | 2.0%; 2 to 4% |
| 322826591-1 | TIC 322826642 (5332801342310848256) | 12.35 | 39.1" | 0.7" | 1.0%; 3.4 to 7.4% |
| 322826591-1 | TIC 916591876 (5332801342299236864) | 12.87 | 37.9" | 1.0" | 1.7%; 9 to 21% (TIC Tmag 13.64) |
| 337885456-1 | TIC 337885477 (6726411611586612352) | 15.62 | 40.7" | 0.5" | 15%; 30 to 57% |
| 423100454-1 | TIC 423100496 (past the table's 1') | 9.96 (TIC) | 120.8" | 2.2" (S102), 5.2" (S65) | none; 28 to 111% |
| 458290782-1 | TIC 1343588382 (5971009774267118464) | 13.41 | 24.2" | 0.3" | 1.9%; 2.0 to 3.7% |
| 458290782-1 | TIC 458290807 (5971009769967461632) | 11.80 | 27.1" | 3.2" | 0.43%; 0.5 to 1.0% |

- **322826591-1: off-target source supported.** The fit lands within 3" of one sky point in all five sectors (S37,
  S38, S64 and S100 on camera 3, S99 on camera 4), a sky scatter of 1.8" against a detector scatter of 28.7". Quality
  0.83 to 0.96, and no null image reaches it (0 of 16 in every sector). The fixed fit gives the neighbour z 5.0 to 21.0
  and the target -0.4 to 0.7, where the transit on the target would give a box z of 1.9 to 7.1. The point sits on two
  stars within 2" of each other, TIC 322826642 and TIC 916591876; 21" pixels can't choose between them (with
  TIC 916591876 as the neighbour the fixed fit gives 4.8 to 18.3), and either can host the depth.
- **337885456-1: off-target source supported.** Four sectors on camera 1 (S13, S66, S93, S104), offsets 40.4 to
  42.3", sky scatter 2.8" against a detector scatter of 15.4". Quality 0.68 to 0.92, no null reaches it. The fixed fit
  gives the neighbour z 11.6, 24.0, 8.4 and 2.9 and the target 1.1, -0.2, 0.3 and -0.4, where the transit on the target
  would give 3.1 to 7.7. The point is 0.5" from TIC 337885477. It would need a 15% eclipse if all its light were in the
  aperture, 30 to 57% counting its PRF share: deep, but within an eclipsing binary's reach.
- **458290782-1: off-target source supported.** Five sectors on camera 1, offsets 19.8 to 27.4", sky scatter 2.8".
  The sectors share a camera, so the detector frame barely turns (detector scatter 8.3") and the sky-against-detector
  test is weak here; the fixed fit and SPOC carry it. The fixed fit gives the neighbour z 10.6 to 23.4 and the target
  -2.5 to 1.7, where the transit on the target would give 7.8 to 20.1. The mean fit is 0.3" from TIC 1343588382 and
  3.2" from TIC 458290807 (with it as the neighbour, z 11.5 to 22.7); SPOC's TCE sits on TIC 1343588382 (section 3).
- **173369850-1: off-target source supported.** Five sectors on cameras 2 and 4, offsets 24.7 to 36.2", sky scatter
  5.0" against a detector scatter of 26.5". The qualities are low (0.12 to 0.64), and S100, S102 and S103 hold little
  transit (expected z 1.1 to 2.0; fixed fit within 0.5 of zero at both stars), so the case rests on S93 and S66: there
  the transit on the target would give z 11.5 and 6.8, and the fixed fit gives the target -0.5 and -1.4 and
  TIC 173369830 11.8 and 3.9. TIC 173369830 is 1.3" from the mean fit and would need an 8.6% eclipse (10 to 15% counting
  its PRF share).
- **295140687-1: off-target source supported, weakly.** Four of five fits lie 14.5" to 21.0" north of the target (S37,
  S38 and S64 on camera 3, S99 on camera 4); S65's points 6.8" south-east. The sky scatter (10.3") is close to the
  detector scatter (13.6"), so that test can't separate them, and the quality-weighted mean position is 13.7" out,
  inside 15", at 3.0 standard errors: above every unsaturated known planet (1.4 at most), below every control (7.8 at
  least). The fail rests on S38 alone (19.1", quality 0.74). The fixed fit is clearer. With TIC 295140710 as the
  neighbour it gives z 5.0, 0.5, 8.6, 3.0 and 3.9 against the target's 0.6, 2.1, -0.7, -0.4 and -1.1 (S99, S65, S64,
  S38, S37), where the transit on the target would give 4.1 to 9.6; with TIC 295140717, 5.6, 1.2, 9.9, 3.1 and 5.7
  against 2.6, 4.1, 1.0, 0.2 and 0.4. That is four sectors of five with the neighbour at z 3 or more and above the
  target, against 1 of 75 on the unsaturated known planets. So the loss sits north of the target rather than on it, but
  the pixels can't say on which star, and this rests on a measurement outside the check at separations of about one
  pixel.
- **423100454-1: a failure of the check, not an off-target source.** In S103, S39 and S12 the fits sit 5.7" to 8.7"
  from the target. In S102 and S65 they jump to 118.6" and 115.7" at quality 0.92, both on one sky point (east 114" to
  117", north 17") seen from two different CCDs, beside TIC 423100496. That star varies on its own: in each of those
  sectors one null image lands on the same point with a larger loss and quality 0.94 to 0.97 (S102 at phase 0.625:
  amplitude 385.5 e-/s against the transit image's 202.9; S65 at phase 0.375: 170.1 against 119.9). The transit itself
  is at the target in every sector: box z at the star 4.7, 5.4, 3.2, 1.9 and 1.5 against 3.7, 6.6, 3.5, 1.6 and 1.4
  expected (S103, S102, S65, S39, S12), and the fixed fit gives the target 4.0, 3.7, 1.5, 0.6 and 1.2 and TIC 423100496
  -0.2, 2.0, 2.8, -0.1 and 0.4. TIC 423100496 sits 5.7 pixels out, and 0.1 to 0.4% of its PRF falls in a 3 x 3
  aperture on the target, so it would need a 28 to 111% eclipse to make the 448 ppm dip; its own 0.8% loss in the S102
  and S65 windows (from the fixed fit) puts at most 14 ppm into that aperture. Like any pixel record, this one says
  nothing about stars within 15" of the target (TOI-1399.01's binary at 12" passes the rule); the neighbour table lists
  possible hosts from 6.5" out, which is TRICERATOPS's question, not this one.

Per sector, as in section 1; the fixed fit's neighbour is the first star named for the row above (TIC 423100496 for
423100454-1).

| Signal | S | Cam | Off | Q | E, N (") | dcol, drow | Tr | Peak | Col | z (exp) | Fixed z | Nulls >= Q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 173369850-1 | 103 | 2.3 | 31.0" | 0.12 | +23, -21 | -0.02, +1.51 | 2/4 | 3744 | 2 | 1.2 (1.9) | -0.3/0.4 | 2/16 |
| 173369850-1 | 102 | 2.2 | 24.7" | 0.41 | +21, -14 | -0.08, -1.26 | 2/4 | 2185 | 2 | 0.9 (1.1) | 0.0/0.2 | 1/16 |
| 173369850-1 | 100 | 4.4 | 36.2" | 0.16 | +26, -25 | -1.53, -0.94 | 2/4 | 3597 | 2 | 1.0 (2.0) | -0.3/0.5 | 6/16 |
| 173369850-1 | 93 | 2.4 | 34.3" | 0.64 | +26, -23 | -1.38, +0.94 | 4/4 | 4507 | 1 | 6.0 (11.5) | -0.5/11.8 | 2/16 |
| 173369850-1 | 66 | 2.4 | 25.4" | 0.32 | +20, -16 | -1.04, +0.67 | 3/5 | 3710 | 2 | 3.3 (6.8) | -1.4/3.9 | 0/16 |
| 295140687-1 | 99 | 4.2 | 14.6" | 0.64 | -2, +14 | -0.42, -0.60 | 7/8 | 3191 | 2 | 8.5 (7.4) | 0.6/5.0 | 0/16 |
| 295140687-1 | 65 | 3.2 | 6.8" | 0.54 | +6, -4 | -0.28, -0.18 | 9/10 | 2658 | 2 | 7.0 (8.8) | 2.1/0.5 | 0/16 |
| 295140687-1 | 64 | 3.1 | 18.6" | 0.59 | -3, +18 | +0.72, -0.52 | 8/10 | 3709 | 2 | 7.5 (7.0) | -0.7/8.6 | 0/16 |
| 295140687-1 | 38 | 3.2 | 19.1" | 0.74 | -8, +17 | +0.92, -0.03 | 9/9 | 4421 | 1 | 3.8 (4.1) | -0.4/3.0 | 0/16 |
| 295140687-1 | 37 | 3.1 | 22.9" | 0.34 | -9, +21 | +0.99, -0.48 | 8/8 | 3041 | 2 | 6.9 (9.6) | -1.1/3.9 | 0/16 |
| 322826591-1 | 100 | 3.2 | 40.2" | 0.83 | +35, +20 | -1.97, -0.04 | 1/2 | 8408 | 2 | 4.6 (5.7) | -0.4/16.5 | 0/16 |
| 322826591-1 | 99 | 4.2 | 39.2" | 0.96 | +32, +22 | -1.91, +0.57 | 1/1 | 9662 | 2 | 4.4 (6.7) | 0.4/21.0 | 0/16 |
| 322826591-1 | 64 | 3.1 | 41.3" | 0.93 | +34, +23 | -0.59, -2.00 | 1/2 | 7972 | 2 | 6.1 (7.1) | 0.4/5.0 | 0/16 |
| 322826591-1 | 38 | 3.2 | 37.8" | 0.95 | +31, +22 | +0.20, -1.88 | 2/2 | 6729 | 2 | 2.1 (2.1) | 0.7/6.1 | 0/16 |
| 322826591-1 | 37 | 3.1 | 41.0" | 0.95 | +35, +22 | -0.80, -1.90 | 2/2 | 6563 | 2 | 1.3 (1.9) | 0.6/5.1 | 0/16 |
| 337885456-1 | 104 | 1.3 | 40.4" | 0.87 | +34, +22 | -1.89, +0.49 | 16/19 | 19267 | 2 | 3.7 (4.1) | 1.1/11.6 | 0/16 |
| 337885456-1 | 93 | 1.3 | 40.7" | 0.92 | +33, +24 | -1.72, -0.99 | 16/19 | 22094 | 1 | 6.4 (7.7) | -0.2/24.0 | 0/16 |
| 337885456-1 | 66 | 1.3 | 42.3" | 0.83 | +33, +26 | -1.75, -1.09 | 12/21 | 16849 | 2 | 2.9 (3.6) | 0.3/8.4 | 0/16 |
| 337885456-1 | 13 | 1.4 | 41.4" | 0.68 | +30, +28 | -1.46, -1.34 | 14/20 | 22789 | 1 | 1.7 (3.1) | -0.4/2.9 | 0/16 |
| 423100454-1 | 103 | 1.1 | 5.7" | 0.52 | +4, +4 | +0.27, +0.08 | 1/2 | 10831 | 2 | 4.7 (3.7) | 4.0/-0.2 | 0/14 |
| 423100454-1 | 102 | 2.2 | 118.6" | 0.92 | +117, +17 | +4.50, -3.57 | 2/2 | 12320 | 2 | 5.4 (6.6) | 3.7/2.0 | 1/15 |
| 423100454-1 | 65 | 2.3 | 115.7" | 0.92 | +114, +17 | -5.74, -1.54 | 2/2 | 10852 | 2 | 3.2 (3.5) | 1.5/2.8 | 1/16 |
| 423100454-1 | 39 | 2.4 | 5.8" | 0.73 | +4, -5 | -0.25, +0.15 | 2/2 | 15518 | 3 | 1.9 (1.6) | 0.6/-0.1 | 0/16 |
| 423100454-1 | 12 | 2.4 | 8.7" | 0.57 | +3, -8 | -0.26, +0.34 | 1/2 | 12488 | 4 | 1.5 (1.4) | 1.2/0.4 | 0/16 |
| 458290782-1 | 103 | 1.3 | 23.0" | 0.10 | -21, +8 | +0.55, -0.98 | 10/13 | 2964 | 2 | 9.6 (15.4) | -0.5/15.2 | 0/16 |
| 458290782-1 | 93 | 1.4 | 25.7" | 0.85 | -23, +12 | +1.24, -0.36 | 11/12 | 2660 | 2 | 18.2 (20.1) | -2.5/23.4 | 0/16 |
| 458290782-1 | 66 | 1.4 | 27.4" | 0.69 | -25, +11 | +1.34, -0.34 | 9/14 | 3237 | 3 | 9.9 (15.0) | -1.0/21.7 | 0/16 |
| 458290782-1 | 39 | 1.4 | 24.3" | 0.70 | -23, +8 | +1.14, -0.23 | 10/13 | 4227 | 3 | 7.7 (12.2) | -0.1/10.6 | 0/16 |
| 458290782-1 | 12 | 1.3 | 19.8" | 0.42 | -18, +8 | +0.90, -0.25 | 9/14 | 4366 | 2 | 10.8 (7.8) | 1.7/11.1 | 0/16 |

The controls, for comparison (`pixel_controls.csv` gives no depth, so no expected z):

| Signal | S | Cam | Off | Q | E, N (") | dcol, drow | Tr | Peak | Col | z (exp) | Fixed z | Nulls >= Q |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| TOI-1058.01 | 94 | 1.4 | 24.4" | 0.90 | +16, +18 | -0.89, -0.79 | 2/2 | 5599 | 2 | 2.1 (-) | 0.1/1.4 | 0/16 |
| TOI-1058.01 | 92 | 2.4 | 21.5" | 0.96 | +15, +15 | -0.73, +0.91 | 2/2 | 5947 | 2 | 1.9 (-) | -0.1/0.7 | 0/16 |
| TOI-1058.01 | 67 | 1.4 | 24.2" | 0.91 | +19, +15 | -1.01, -0.61 | 2/3 | 6303 | 2 | 2.1 (-) | -0.1/0.4 | 0/16 |
| TOI-1058.01 | 27 | 1.4 | 22.3" | 0.90 | +13, +18 | -0.73, -0.81 | 2/2 | 5740 | 1 | 4.2 (-) | -0.4/2.9 | 0/16 |
| TOI-1058.01 | 13 | 1.3 | 10.6" | 0.81 | +4, +10 | -0.28, -0.45 | 2/2 | 6633 | 2 | 2.3 (-) | 0.4/0.9 | 0/16 |
| TOI-1175.01 | 81 | 2.2 | 26.8" | 0.83 | -1, +27 | -0.34, -1.28 | 4/4 | 2847 | 2 | 5.2 (-) | -0.5/4.6 | 0/16 |
| TOI-1175.01 | 80 | 2.1 | 23.5" | 0.67 | +1, +24 | -0.07, -1.23 | 3/4 | 3381 | 3 | 7.8 (-) | 0.1/5.9 | 0/16 |
| TOI-1175.01 | 74 | 4.4 | 24.8" | 0.81 | -3, +25 | +0.06, +1.20 | 4/4 | 3315 | 2 | 6.7 (-) | 0.0/13.3 | 0/16 |
| TOI-1175.01 | 54 | 2.2 | 23.1" | 0.73 | -3, +23 | -0.13, -1.15 | 1/2 | 2622 | 3 | 5.9 (-) | 0.1/5.8 | 1/16 |
| TOI-1175.01 | 41 | 1.2 | 25.1" | 0.86 | -4, +25 | -0.34, -1.17 | 4/4 | 3517 | 2 | 14.7 (-) | -0.2/14.6 | 0/16 |
| TOI-1399.01 | 84 | 2.2 | 10.3" | 0.48 | -4, +9 | -0.17, -0.47 | 15/17 | 2691 | 2 | 20.7 (-) | 0.7/4.1 | 0/10 |
| TOI-1399.01 | 83 | 2.1 | 11.6" | 0.95 | -4, +11 | -0.06, -0.59 | 14/18 | 2746 | 1 | 29.4 (-) | 0.5/11.3 | 0/10 |
| TOI-1399.01 | 77 | 4.3 | 13.4" | 0.52 | -6, +12 | +0.22, +0.63 | 11/13 | 2911 | 2 | 28.1 (-) | -1.1/9.0 | 0/10 |
| TOI-1399.01 | 57 | 2.2 | 11.1" | 0.42 | -3, +11 | -0.28, -0.46 | 16/17 | 2762 | 2 | 48.8 (-) | 1.2/9.9 | 0/10 |
| TOI-1399.01 | 17 | 2.2 | 13.1" | 0.60 | -2, +13 | -0.39, -0.51 | 12/16 | 2096 | 2 | 5.5 (-) | 0.0/5.6 | 0/10 |

## 3. SPOC's DV statistics and the other checks

| Row | SPOC TCE at the period | MES | Ghost core; halo | Weak secondary | ExoMiner | Other vet-v3 fails |
|---|---|---|---|---|---|---|
| 173369850-1 | target, FFI S100, S103, twice the period | 7.92 | 4.37; 0.84 | 257 ppm | 0.028 FP | secondary |
| 295140687-1 | none | | | | 0.028 FP | secondary |
| 322826591-1 | target, 2-min S1 to S39 | 23.58 | -2.19; 31.79 | 103 ppm | 0.041 FP | sector_depth, holdout, density |
| 337885456-1 | none | | | | 0.003 FP, half the period | secondary |
| 423100454-1 | none | | | | 0.785 PC | none |
| 458290782-1 | TIC 1343588382, S103 | 18.45 | 5.30; 2.80 | 23,215 ppm | 0.152 FP | secondary, sector_depth, holdout |

Novelty is inconclusive on all six by design (`known_to_spoc`); neighbours is inconclusive on 322826591-1,
423100454-1 and 458290782-1 because one Gaia DR3 star within 1' has no G magnitude.

- **322826591-1.** SPOC's own difference images, from 2-minute data over S1 to S39, put the source 38.01" ± 2.59"
  from the TIC position (38.29" ± 2.55" from the out-of-transit centroid), 15 standard errors out, where our fits put it
  (37.8" to 41.3"). Its ghost diagnostic's halo statistic (31.79) far exceeds the core's (-2.19), which in SPOC's terms
  points to a signal from outside the optimal aperture. With three vet-v3 fails and ExoMiner's 0.041, everything points
  the same way.
- **458290782-1.** SPOC found the signal, at the same period, as a TCE on the neighbour TIC 1343588382, placed it 1.68"
  ± 2.56" from that star's catalogue position, and measured a 23,215 ppm weak secondary on it: an eclipsing binary 24"
  from our target. Its 18.18" ± 2.55" offset from the out-of-transit centroid is the pull of the brighter stars around
  it. At that error SPOC can't separate TIC 1343588382 from TIC 458290807, about 3" away, either.
- **173369850-1.** SPOC's TCEs are single-sector FFI runs at twice our period with no difference-image offsets (0.00
  with error -1), so they add nothing on position. A TCE at twice the period, with our secondary fail, fits an
  eclipsing binary with similar eclipses.
- **295140687-1, 337885456-1 and 423100454-1** have no SPOC TCE at the period. ExoMiner calls the first two false
  positives (0.028 and 0.003; 337885456-1's row is at half our period) and 423100454-1 a planet candidate (0.785), which
  matches its checks: every vet-v3 check passes but novelty (by design) and neighbours (inconclusive).

## 4. What it means for the second-list decisions

- **322826591-1, 337885456-1, 458290782-1 and 173369850-1.** Each fail is a real off-target source by every test here,
  so a kill on pixels stands on firm ground. 173369850-1's rests on two sectors (S93, S66); its other three hold too
  little transit to say anything. Each of the four also fails another vet-v3 check (secondary for three; sector_depth,
  holdout and density for 322826591-1), so none of these kills rests on pixels alone.
- **295140687-1.** On this evidence the fail points the right way, but the check's own number is marginal: one sector at
  19.1", a quality-weighted mean of 13.7". A kill on pixels alone would rest on S38. Its secondary fail and ExoMiner's
  0.028 are separate grounds.
- **423100454-1.** Its pixel fail is not evidence against the signal: in two sectors the check measured a variable star
  2' away, and in the other three it measured the target. Pixels is its only fail. The approved rule (M3 design,
  section 4.10; decision 0028) kills a second-list row on a pixel fail, and the proposed Ruling W would bar a pass
  without a pixel pass, so on this record the row is killed by rule; what this diagnosis adds is that the kill measures
  the neighbour, which the call's reason can say. Setting the rule aside for this row would be the maintainer's call,
  with its own record. Its next TESS look is S113 (`upcoming_sectors`).
- **Findings for the maintainer.** The check is frozen; these argue for a later version, not a change now.
  1. On hosts brighter than about Tmag 6 the check measures the bleed column, and neither outcome says where the
     transit is. No second-list row is that bright.
  2. The outcome follows one sector, picked by quality, and quality measures how PRF-like the image is, not how much
     transit it holds: on TOI-4307.01's star the null images' median quality is 0.53 to 0.61. The direction of each
     sector's fit, which `pixels.json` doesn't keep, is what separates a real source from noise, and the saved
     difference images keep it.
  3. The fit roams the whole 21 x 21 pixel cutout (441"), so a variable star anywhere in it can capture the fit
     (423100454-1, 121" out). Null images expose it.
  4. In this data a fit that repeats its sky position across sectors and cameras, with nothing at the target in a
     fixed-position fit, marks a real off-target source, and nothing else here does that.

## What this could not determine

- Which of two stars 1" to 3" apart hosts 322826591-1 (TIC 322826642 or TIC 916591876) and 458290782-1
  (TIC 1343588382 or TIC 458290807); which northern star, if any one, hosts 295140687-1.
- What TIC 423100496 is (no variability catalogue was read), beyond the losses its pixels show.
- Whether the second-list ephemerides have drifted by the latest sectors; no shifted-ephemeris images were made.
- Each z rests on 8 to 16 null images per sector, so each is uncertain by roughly a fifth, and the nulls hold only
  their own sector's systematics.
- The aperture-share depths use a 3 x 3 box, not the SPOC or QLP apertures.

## Scripts

The scripts and their small outputs are in `pixel-check-diagnosis-2026-10-20-scripts.tar.gz` beside this file
(sha256 `1dc96ca3c1a6ccecc4e47d08bfc9d98d7fe5f337c75fa52c3bec104787e43939`), byte for byte as they ran in
`/tmp/pixel-diag/`. 14 of the 19 scripts read and write by that absolute path, so a rerun unpacks the tarball there.
They ran from Git Bash as
`MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-26.04 --cd /tmp/pixel-diag -- bash -l -s` with, inside:

```
. ~/.cache/tess-hunt/logs/m3-vars.sh; export PIXEL_COMPLETENESS SECOND_RUN VET_RUN CONTROL_VET
P=/home/kevin/code/tess-hunt/.venv/bin/python
CAP="systemd-run --user --scope -p MemoryMax=6G -p MemorySwapMax=0 nice -n 10"
$P make_jobs.py                                  # jobs.json: 33 signals, their sectors, depths, recorded offsets
$CAP $P sector_detail.py detail.json jobs.json   # refits, nulls, saturation, stars at each fit
$P verify_refit.py                               # refits against the record, rebuilt images against the saved
$P report.py; $P summary.py detail.json           # per-sector and per-signal printouts
$P make_pairs.py                                 # pairs.json and pairs_alt.json: the fixed fit's neighbours
$CAP $P two_star.py two_star.json jobs.json pairs.json
$CAP $P two_star.py two_star_alt.json jobs.json pairs_alt.json
$P fixed_fit_rates.py                            # how often the fixed fit flags a neighbour, per group
$P gaia_match.py; $CAP $P aperture_share.py; $P crowding.py; $P nulls_423.py
$P tables.py; $P persec.py LABEL ...             # the tables above
```

| Script | What it does |
|---|---|
| `make_jobs.py` | Lists each signal's saved difference images, measured sectors, depth and recorded offsets. |
| `sector_detail.py` | Per sector: the refit, sky and detector offsets, box z, saturation, stars at the fit, nulls. |
| `verify_refit.py` | Checks the refits against the recorded offsets and the rebuilt images against the saved ones. |
| `report.py`, `summary.py` | Per-sector and per-signal printouts: scatter, nulls, stars at the mean fit. |
| `make_pairs.py`, `two_star.py` | The fixed-position fit (target, one neighbour, constant) with null-image z. |
| `fixed_fit_rates.py` | The fixed fit's neighbour hits per group (known planets, controls, second list). |
| `gaia_match.py`, `aperture_share.py` | Neighbour-table rows for the stars at the fits; aperture-share depths. |
| `crowding.py`, `nulls_423.py` | Tmag and CROWDSAP from the vet runs; 423100454-1's null-image fits. |
| `tables.py`, `persec.py` | The summary and per-sector tables in this file. |
| `locate.py` | The pooled-position map, stopped and not used (above). |
| `dump_second_list.py`, `peek_checks.py` | Read-only looks at `second-list.csv` and `checks.json`. |
| `peek_neighbours.py`, `assemble.py` | A look at `neighbours.csv`; puts the per-sector tables into this file. |

Outputs in the tarball: `two_star.json`, `two_star_alt.json`, and the printouts `two_star.txt`, `two_star_alt.txt`,
`summary_known.txt`, `summary_second.txt`, `locate.txt` and `persec_*.md`, with `jobs.json`, `pairs.json` and
`pairs_alt.json`. Left out: `detail.json` (26 MB), which `sector_detail.py` rebuilds (the second command above).
