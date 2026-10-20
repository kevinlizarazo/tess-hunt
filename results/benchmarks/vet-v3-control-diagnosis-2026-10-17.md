# vet-v3 control diagnosis (Task 11)

A read-only analysis made outside the pipeline, with no committed script. It gates nothing:
[decision 0031](../../docs/decisions/0031-known-set-control-fails.md) records the calls made from it.

Read-only diagnosis of the confirmed-planet failures in the control vetting run
`20261017T155223Z-vetting-run-62882b5-4867` (in `$TESS_HUNT_DATA/runs/`, commit 62882b5, criteria vet-v3 and
search-v2), for Kevin's call before any shortlisted signal is vetted. Written 2026-10-17. Nothing in the repo, the run
tree or the cache was changed.

## Summary

None of the seven confirmed-planet failures is a coding error. Each comes from a real property of the planet, a
stale or linear control ephemeris, or a check rule that leaves something out. TOI-107.01 (WASP-94 A b) and
TOI-747.01 (WASP-87 b) show dips at phase 0.5 of 94 ± 26 and 119 ± 37 ppm. WASP-87 b's own thermal emission can
reach 242 ppm in the TESS band, so its dip fits an occultation, and its empirical significance is only about
2.5 sigma. WASP-94 A b's dip is real (none of 2000 scrambled-period trials reached it, and every sector is positive)
but fits an occultation only with a geometric albedo near 0.3, and no published TESS occultation exists to check it
against. A planet-aware rule (fail only when the dip exceeds a physical maximum by 3 sigma) passes both and still
fails TOI-1399.01 by at least 3.9 sigma if the albedo cap is 0.5 or less. With a cap of 1.0, TOI-1399.01 passes once
Rp/R* is read from its depth. TOI-191.01 (WASP-8 b) fails density because its orbit is eccentric (e = 0.304,
ω = 274°). Correcting the TIC density for that brings the tension from 3.5 to 0.4 sigma. TOI-396.01 (HR 858 c) has
transit-time shifts of 0.30 to 0.40 d in 2025 and 2026 against its 2018 to 2020 ephemeris, mirrored by HR 858 b
(-0.20 to -0.28 d), so no linear ephemeris folds all four seasons. The checks did what they are built to do, and
the planet is a poor control. TOI-576.01's season-3 miss comes from one half-covered transit right after a 5.2-hour
data gap. Without that transit the season passes (tension 1.79). The three inconclusives are low SNR as expected
(expected core SNR 3.4, 3.5 and 4.9, against the threshold of 7). They sit on two young stars (125 and 27 Myr)
whose residual variability inflates the errors 2.8 to 5.7 times, and stale TOI periods make TOI-451.03 and
TOI-1097.02 worse. TOI-1175.01's season-1 fail is a real shallower eclipse in S40 and S41, not an ephemeris problem.
For the nine shortlisted signals the planet-aware secondary bound is 0.1 to 8.7 ppm (albedo cap 0.5), so that rule
would vet them almost exactly as vet-v3 does now. The density and depth-tension loosenings would matter mostly for
the deepest, highest-SNR signal, TIC 48010903.

| Item | Signal | Failing check | Cause | Category |
|---|---|---|---|---|
| 1 | TOI-107.01 (WASP-94 A b) | secondary, 94 ppm, 3.6 sigma | real phase-0.5 dip, probably the occultation if Ag is near 0.3; unconfirmed | planet itself; the rule has no planetary allowance |
| 2 | TOI-747.01 (WASP-87 b) | secondary, 119 ppm, 3.2 sigma | half the planet's thermal maximum; empirically about 2.5 sigma | planet itself, plus a check-logic mismatch (beta timescale) |
| 3 | TOI-191.01 (WASP-8 b) | density, 3.5 sigma | eccentric orbit transiting near apoapsis | planet itself; the check assumes a circular orbit |
| 4 | TOI-396.01 (HR 858 c) | sector_depth, holdout, signal_present | transit-timing variations of 0.3 to 0.4 d | planet itself, plus the control's linear input ephemeris |
| 5 | TOI-576.01 (WASP-166 b) | holdout, season 3, tension 3.26 | one half-covered transit after a data gap | check logic (partial transits weigh fully) at a hard threshold |
| 6 | TOI-451.02, 451.03, 1097.02 | holdout and signal_present inconclusive | expected SNR 3.4 to 4.9, red noise on young stars; stale periods | star (noise), plus control input ephemerides |
| 7 | TOI-1175.01 (negative control) | holdout, season 1 | real shallower eclipse in S40 and S41 | real feature of the blend |

## Sources

- **Run evidence:** `$TESS_HUNT_DATA/runs/20261017T155223Z-vetting-run-62882b5-4867/signals/<name>/checks.json`
  (checks, fit, fit_prior, star, sources) and `fit_samples.npz`.
- **Rebuilt light curves:** each signal's `noisy` light curve, rebuilt exactly as `vet_with_fits` builds it (see
  Methods). The rebuild reproduces the run's secondary and signal_present results for all 11 signals examined, for
  example TOI-107.01 at 94 ppm and 3.6 sigma, and TOI-396.01 at 1.2 sigma.
- **Catalogs:** SNAP3 (`$TESS_HUNT_DATA/catalogs/2026-10-17T142814Z`) `raw/TOI/toi.csv` and
  `raw/archive_ps/ps.csv`; live NASA Exoplanet Archive TAP queries on `ps` (2026-10-17), texts in Methods.
- **TESS band:** the TESS response function v2.0 from HEASARC,
  `https://heasarc.gsfc.nasa.gov/docs/tess/data/tess-response-function-v2.0.csv`.
- **Shortlist:** `$TESS_HUNT_DATA/runs/20261015T155441Z-triage-7b12e25-3f57/shortlist.csv`, with TIC Teff and
  density from `$TESS_HUNT_DATA/runs/20261013T031523Z-targets-cce2f6e-b0d4/targets.parquet`.

## Items 1 and 2: secondary at phase 0.5 (TOI-107.01, TOI-747.01)

`secondary` (`checks/photometry.py`) takes the inverse-variance mean of every cadence within one full transit
duration of phase 0.5, over all good-timestamp sectors and both families. Its errors are scaled by each sector's
red-noise beta measured at the core timescale (half the duration). It fails above 3 sigma and has no allowance for a
planet's own occultation.

### Is the dip real?

All rows are from the rebuilt light curves; TOI-1399.01 is shown for comparison.

| | TOI-107.01 | TOI-747.01 | TOI-1399.01 (negative) |
|---|---|---|---|
| Run: depth ± error (sigma) | 94.3 ± 26.0 ppm (3.62) | 119.1 ± 36.9 ppm (3.22) | 277.6 ± 25.0 ppm (11.12) |
| Per sector (ppm) | S1 73 ± 56, S27 112 ± 85, S68 150 ± 52, S95 60 ± 44, S105 112 ± 87 | S10 85 ± 124, S11 130 ± 92, S37 140 ± 77, S99 93 ± 94, S100 143 ± 80, S101 89 ± 94 | S16 254 ± 65, S17 225 ± 58, S57 347 ± 60, S77 182 ± 66, S83 285 ± 52, S84 388 ± 73 |
| Transit held out of the detrend | 94.4 ± 26.2 (3.60) | 119.1 ± 36.8 (3.24) | 285.8 ± 24.2 (11.82) |
| Errors scaled by beta at the full duration | 96.0 ± 27.8 (3.45) | 119.0 ± 44.7 (2.66) | 275.3 ± 31.0 (8.88) |
| Beta, core timescale, by sector | 1.04 to 1.58 | 1.63 to 2.37 | 1.00 to 1.69 |
| Beta, full-duration timescale, by sector | 1.03 to 1.84 | 1.95 to 2.93 | 1.26 to 2.10 |
| Null: sigma of a phase-0.5 box on 2000 scrambled periods, median and sd (held-out detrend) | -0.28, 1.06 | -0.28, 1.27 | -1.64, 1.14 |
| Null trials at or above the observed sigma | 0 of 2000 | 13 of 2000 (0.65%) | 0 of 2000 |

TOI-107.01's dip is real at the level the check reports: no null trial reached it, and every sector is positive
(chi-square about 2 for 4 degrees of freedom). TOI-747.01's dip is marginal: 0.65% of null boxes reach it, about
2.5 sigma one-sided, and its error grows by 21% once beta is measured on the box's own timescale. The secondary
box is twice as long as the core window its errors were scaled for.

### Could they be the planets' own occultations?

The largest occultation an irradiated planet can show is the reflected Ag (Rp/a)² plus the thermal
(Rp/R*)² × B(T_day)/B(Teff), both weighted by the TESS response. T_day = Teff (R*/a)^0.5 (2/3)^0.25 is the hottest
dayside: no heat redistribution and zero Bond albedo. Rp/R* and a/R* are from the flat-prior fit; Teff is the TIC's.

| | TOI-107.01 | TOI-747.01 | TOI-1399.01 |
|---|---|---|---|
| Rp/R* (flat fit) | 0.1048 | 0.0874 | 0.0288 |
| a/R* (flat-fit density and period) | 7.28 | 3.92 | 2.99 |
| TIC Teff (K) | 6073 | 6458 | 6483 |
| Hottest dayside temperature (K) | 2034 | 2946 | 3387 |
| Thermal maximum (ppm) | 30.4 | 241.6 | 57.3 |
| Thermal with full redistribution (ppm) | 3.2 | 46.7 | |
| Reflected at Ag = 1 (ppm) | 207.3 | 496.5 | 92.8 |
| Maximum at Ag 0.3 / 0.5 / 1.0 (ppm) | 92.6 / 134.0 / 237.7 | 390.6 / 489.9 / 738.1 | 85.1 / 103.7 / 150.1 |
| Observed (ppm) | 94.3 ± 26.0 | 119.1 ± 36.9 | 277.6 ± 25.0 |

The published geometry (Kokori et al. 2023 rows in the archive: a/R* 7.27 and Rp/R* 0.1094 for WASP-94 A b, 3.89
and 0.08746 for WASP-87 b, with archive Teff 6153 and 6450 K) changes little: thermal 35.5 and 247.2 ppm, reflected
at Ag = 1 226.4 and 505.5 ppm.

**Published occultations:** none found. No WASP-94 A b or WASP-87 b row in the archive's `ps` table has a
`pl_occdep` (query 2). A web search found no published TESS occultation depth for either planet. The two TESS
phase-curve surveys it returned (Wong et al. 2020, arXiv:2003.06407; Wong et al. 2021, arXiv:2106.02610) do not
list either planet among their detections. The evidence here is thin.

**Reading:** WASP-87 b's dip is under half its own thermal maximum, and even full heat redistribution gives 47 ppm,
so it fits the planet's occultation. WASP-94 A b's 94 ppm needs Ag of about 0.31 at the point estimate on top of the
30 ppm thermal maximum, or Ag of at least 0.06 at the 2-sigma lower bound (42 ppm). That albedo is on the high side,
and I have no published value to compare it with. Nothing on record explains a dip at exactly phase 0.5 that is the
same in five sectors, so the planet's occultation is the likeliest reading, but it is not confirmed.

### A planet-aware rule

Rule: fail only when (depth - D_max) / error > 3, with D_max the maximum above. Excess sigma by variant (computed
from the run's depth and error):

| Variant | TOI-107.01 | TOI-747.01 | TOI-1399.01 |
|---|---|---|---|
| Thermal only (Ag 0), flat-fit Rp/R* | 2.46, pass | -3.32, pass | 8.82, fail |
| Ag 0.5, flat-fit Rp/R* | -1.52, pass | -10.04, pass | 6.97, fail |
| Ag 1.0, flat-fit Rp/R* | -5.51, pass | -16.76, pass | 5.11, fail |
| Ag 0.5, Rp/R* = sqrt(core depth) | -2.22, pass | -10.90, pass | 3.91, fail |
| Ag 0.5, sqrt(core depth), a/R* from the density-prior fit | -2.28, pass | -10.81, pass | 4.77, fail |
| Ag 1.0, sqrt(core depth) | -6.74, pass | -18.05, pass | 0.68, pass |
| Ag 1.0, sqrt(core depth), a/R* from the density-prior fit | -6.83, pass | -17.94, pass | 1.87, pass |

TOI-1399.01's flat fit reaches its 1442 ppm core depth with Rp/R* = 0.0288 and extreme limb darkening (q1 0.95,
q2 0.985). It fits a V-shaped blend's depth with limb darkening rather than size, so reading Rp/R* from the fit is
the strict choice and reading it from the depth is the lenient one. With an albedo cap of 0.5 or less, TOI-1399.01
fails in every variant (minimum excess 3.91 sigma). With a cap of 1.0 it passes once Rp/R* comes from the depth.

**TOI-188.01** is untouched. Its secondary is -13.4 ± 12.3 ppm (-1.1 sigma) and passes now. It fails odd/even
(7.4 sigma) and density (4.6 sigma), and this rule touches neither. TOI-1058.01 and TOI-1175.01 pass the secondary
now (0.60 and 0.47 sigma) and still would.

**The risk the rule adds:** it passes any eclipse whose secondary is below D_max, including one from a
self-luminous companion cooler than the temperature Tc where (Rp/R*)² B(Tc)/B(Teff) = D_max. That temperature is
high for short periods and small a/R*:

| Geometry | Tc that passes, Ag 0.5 | Tc that passes, Ag 1.0 |
|---|---|---|
| TOI-1399.01 | 3805 K | 4117 K |
| TOI-747.01 | 3333 K | 3604 K |
| TOI-107.01 | 2470 K | 2688 K |
| The nine shortlisted signals | 1499 to 2553 K | 1602 to 2781 K |

On a TOI-1399.01-like geometry, an EB with an M or late-K dwarf companion whose secondary is shallow enough would
pass this check, leaving odd/even, shape, density, radius and TRICERATOPS to catch it.

**The nine shortlisted signals:** D_max from their search depth (Rp/R* = sqrt(depth)), period, TIC density and TIC
Teff:

| TIC | P (d) | Depth (ppm) | a/R* (TIC density) | D_max at Ag 0.5 / 1.0 (ppm) | Search depth / SNR (ppm) |
|---|---|---|---|---|---|
| 44926986 | 24.115 | 776 | 30.4 | 0.4 / 0.8 | 46.0 |
| 48010903 | 24.948 | 4575 | 27.4 | 3.1 / 6.1 | 73.7 |
| 103312990 | 7.523 | 364 | 13.6 | 1.0 / 2.0 | 30.4 |
| 146282666 | 9.995 | 233 | 16.7 | 0.4 / 0.8 | 16.1 |
| 164767175 | 5.839 | 180 | 15.0 | 0.4 / 0.8 | 18.8 |
| 296819076 | 2.280 | 390 | 5.5 | 8.7 / 15.2 | 27.9 |
| 399023421 | 3.927 | 298 | 7.3 | 3.8 / 6.6 | 21.8 |
| 410399327 | 34.939 | 604 | 52.1 | 0.1 / 0.2 | 38.6 |
| 441010857 | 24.054 | 1376 | 24.4 | 1.2 / 2.3 | 80.8 |

Their phase-0.5 errors are unknown until they are vetted. The search's depth over SNR (last column) is only a scale,
but it puts the 3-sigma line at roughly 50 to 240 ppm, so a bound of at most 8.7 ppm (Ag 0.5) moves it by a few
percent. A companion cool enough to pass the new rule on these geometries would leave a secondary below the noise
under either rule. For the nine, the rule is close to neutral.

### Cause, category and smallest change

- **TOI-107.01:** the planet itself. The phase-0.5 dip is real and probably the occultation, which vet-v3's rule has
  no allowance for. Unconfirmed.
- **TOI-747.01:** the planet itself (its thermal emission), plus a check-logic mismatch: the box's errors are scaled
  at half its timescale.
- **Smallest change that fixes both:** the planet-aware bound with Ag capped at 0.5, Rp/R* and a/R* from the flat
  fit, and the excess over D_max held to the existing 3 sigma. It needs a decision record and new criteria values.
- **Cheaper, partial:** scale the secondary's errors by beta at one full duration. That passes TOI-747.01
  (2.66 sigma), not TOI-107.01 (3.45), and TOI-1399.01 still fails (8.88). On the controls it raises secondary
  errors by 0.99 to 1.36 times per sector, and the shortlist would see a similar loosening.
- **No change:** record both as understood fails. Since D_max is at most 15 ppm for every shortlisted signal, the
  nine would be vetted almost exactly as under the planet-aware rule.

## Item 3: density, TOI-191.01 (WASP-8 b)

The run's flat fit gives 0.611 g/cm³ (log -0.214, +0.011 / -0.009 dex). The TIC gives 1.408 g/cm³ (0.103 dex),
so the tension is 3.50 sigma (`checks.json`).

**Eccentricity is the cause.** The archive (query 1) gives e = 0.3044, ω = 274.215° (Knutson et al. 2014), and
Bourrier et al. 2017 and Kokori et al. 2023 agree (0.304 to 0.310, 274.2° to 274.3°). A circular fit to a transit
of an eccentric orbit returns ρ_circ = ρ_true g³ with g = (1 + e sin ω) / sqrt(1 - e²). This is the brief's scaling
with the sides swapped. Here g = 0.7311 and g³ = 0.391: the planet transits near apoapsis, moves slowly, and the
long transit reads as a low density.

| ρ_true source | ρ_true (g/cm³) | Expected circular-fit ρ | Tension, circular | Tension, with e |
|---|---|---|---|---|
| TIC (run) | 1.408 | 0.550 | 3.50 | 0.44 |
| Queloz 2010 M = 1.03, R = 0.945 (archive) | 1.718 | 0.672 | 4.34 | 0.40 |
| Stassun 2017 `st_dens` 1.74 ± 0.26 (archive) | 1.740 | 0.680 | 6.91 | 0.71 |
| Borsato 2021 `st_dens` 1.27 ± 0.85 (archive) | 1.269 | 0.496 | 1.10 | 0.31 |

The flat fit's a/R* of 12.91 against the published 18.2 to 18.3 (`pl_ratdor`) is the same factor: 18.25 × 0.731
= 13.3.

**The TIC density is not the cause.** It is lower than the published densities (1.408 against 1.72 to 1.74), so
the published values make the circular tension worse.

**The b-ρ degeneracy is not the cause.** The flat fit's b is 0.645 (+0.009 / -0.012), and b and log ρ correlate at
-0.99 in the samples. At the 2.5th percentile (b 0.32) log ρ reaches only -0.01 (0.98 g/cm³). The 0.1% of samples
near the published b of 0.47 (Borsato 2021) sit at 0.84 g/cm³. No sample reaches the TIC's 1.408.

**Category:** the planet itself. The check assumes a circular orbit, and a new candidate has no measured e to
correct with.

**Options:**

| Option | TOI-191.01 | TOI-188.01 (now 4.63) | TOI-1399.01 (now 3.78) | Shortlist |
|---|---|---|---|---|
| No criteria change; record as understood (eccentric, known e) | still fails | fails | fails | unchanged |
| Add 0.11 dex for eccentricity in quadrature | 2.40, pass | 4.34, fails | 2.71, density passes; still fails secondary | tensions about 3 to 30% lower |
| Add 0.379 dex for eccentricity in quadrature | 0.92, pass | 2.85, density passes; still fails odd/even | 1.08, passes | the check loses most of its power |

The 0.11 and 0.379 dex are the standard deviations of 3 log10 g for transiting planets under two eccentricity
priors. Van Eylen et al. 2019's Rayleigh σ = 0.083 for multis gives 0.11; Kipping 2013's Beta(0.867, 3.03) gives
0.379. I quoted both priors' parameters from memory and did not check them against the papers. Under the Kipping
prior, WASP-8 b's 3 log10 g of -0.408 sits at the 3.8th percentile.

How much a shortlisted signal's tension drops depends on its own fit error. On the controls with signal_present SNR
13 to 34, the fit's log-ρ error is 0.08 to 0.44 dex, and 0.11 dex lowers their tensions by 3 to 25%. On a
high-SNR signal like TOI-191.01 (0.011 dex) the drop is about 30%. The SNR-62 signal 48010903 is the shortlisted
one this would move most.

## Item 4: TOI-396.01 (HR 858 c)

### The ephemerides

| Source | P (d) | t0 (BTJD) | σP (d) | σt0 (d) |
|---|---|---|---|---|
| `known_planets.csv`, identical to SNAP3's TOI row 396.01 (ExoFOP, updated 2026-10-05, sectors 4, 30, 31, 97) | 5.973912449 | 3936.89518 | 1.87e-5 | 0.00199 |
| archive `ps`, Bonfanti et al. 2025 (default row) | 5.973865 | 1415.63344 | 1.6e-5 | 0.00099 |
| archive `ps`, Vanderburg et al. 2019 | 5.97293 | 1415.6344 | 6.0e-4 | 0.0022 |

All three HR 858 c rows in SNAP3's `ps.csv` match the live query. Every HR 858 b and c row has `ttv_flag = 1`
(query 3).

### Where the transits are

For each season (the holdout's 60-day split), I scanned a shift of the reference epoch and took the core-box SNR
peak. Shifts are in days; the core half-width is 0.033 d.

| Season | Sectors | Epoch | σt, ExoFOP propagated | σt, Bonfanti propagated | Bonfanti minus ExoFOP prediction | c's transit, relative to ExoFOP | c, O-C against Bonfanti | b, O-C against Bonfanti |
|---|---|---|---|---|---|---|---|---|
| 0 | 3, 4 | -421 | 0.0081 | 0.0010 | -0.271 | -0.264 (16.0 sigma, 209 ppm) | +0.007 | -0.004 (18.1 sigma) |
| 1 | 30, 31 | -300 | 0.0059 | 0.0022 | -0.276 | -0.274 (12.5 sigma, 215 ppm) | +0.002 | +0.012 (19.0 sigma) |
| 2 | 97 | 4 | 0.0020 | 0.0069 | -0.291 | +0.004 (8.8 sigma, 231 ppm) | +0.295 | -0.198 (12.2 sigma) |
| 3 | 105 to 107 | 52 | 0.0022 | 0.0076 | -0.293 | +0.102 (7.7 sigma, 149 ppm) | +0.395 | -0.282 (15.4 sigma) |

The ExoFOP ephemeris, which the control uses, places the 2018 and 2020 transits 0.26 to 0.27 d (8 core
half-widths) from where they are. That is 33 to 46 times its own propagated error. Bonfanti's places the 2025 and
2026 transits 0.30 to 0.40 d off, 43 to 52 times its propagated error. HR 858 b moves the other way, by -0.20 and
-0.28 d. The archive's default periods give P_c / P_b = 1.66622, 0.027% below 5:3, with masses of 3.55 and 3.8
Earth masses (Bonfanti 2025, query 4). Anti-correlated shifts on a pair this close to a resonance are what
transit-timing variations look like, and the archive flags them. I have not modelled the TTVs. The peak positions
come from a 0.002-d grid and their precision is not computed, but the shifts are 6 to 12 core half-widths, far
beyond any plausible timing error.

The season-2 dips at the ExoFOP times are separate, clean transits: epochs 1, 5, 7 and 8 at 229, 210, 263 and
192 ± 53 ppm, each more than 1.1 d from HR 858 b. Neither linear ephemeris works. At Bonfanti's, signal_present
passes (18.7 sigma), but sector_depth still fails (p = 2.0e-17) and the holdout misses all four seasons.

**Side effect:** HR 858 b's catalog ephemerides are masked at ±0.104 d, while b's transits now sit 0.20 to 0.28 d
early, so they leak into the TOI-396.01 and TOI-396.03 light curves in S97 to S107. They show as dips at shift
-0.29 at c epochs 3, 6, 48, 51 and 54, where b coincides with c. They do not land on c's catalog phase, and
TOI-396.03 passed everything.

**Cause:** the planet itself (TTVs), plus the control's input: a linear ephemeris anchored in S97. This is not a
check problem. A linear-ephemeris check cannot pass a planet whose transit times wander by several core widths.

**Smallest change:** take TOI-396.01 out of the known-set pass rate as a TTV planet, with a decision record, or
keep it as a documented expected fail of sector_depth and holdout. No criteria change. The negative controls are
unaffected. For the shortlist, nothing changes, but this is a reminder that a candidate whose TTVs exceed a quarter
of its duration would fail sector_depth and holdout, and nothing in vet-v3 recovers that case. The risk is not
quantified.

## Item 5: TOI-576.01 (WASP-166 b), holdout season 3

**Not the ephemeris.** The catalog P is 5.4435354 ± 3e-6 (ExoFOP); the archive rows give 5.4435397 to 5.4435423;
the run's fit gives 5.4435424. At the season-3 transit at epoch 134, the holdout's refit predicts BTJD 3739.9314,
the fit 3739.9304 and the catalog 3739.9286. They are within 0.003 d of each other, against a 0.036 d core
half-width.

**The cause is one partial transit.** The season-3 depth (S89) is 2825 ± 52 ppm against 3023 ± 32 ppm in training,
a tension of 3.26. The other sectors read 2980 to 3054 ppm. Per transit, epoch 134 begins right after a 5.2-hour
gap in S89 (BTJD 3739.706 to 3739.921). It keeps 29 of about 52 core cadences and 54 of 105 transit-window
cadences, and reads 2269 ± 147 ppm, 4.8 sigma below the 2973 ppm mean. The other S89 transits read 2679 to
3056 ppm. Without epoch 134, S89 reads 2903 ± 55 ppm and the holdout passes with a maximum tension of 1.79.
Holding the transit out of the detrend does not help: epoch 134 then reads 2277 ± 148 ppm.

**Category:** check logic. A half-covered, gap-adjacent transit weighs fully in the depth comparison, and a hard
3.0 threshold meets it. High-SNR planets sit close to that line: TOI-747.01's season-0 tension is 2.93 in the run
and 3.02 with the transit held out of the detrend.

**Smallest change:** leave transit epochs whose full-duration window is less than, say, 80% covered out of the depth
comparisons (holdout tension, sector_depth, odd/even). That fixes TOI-576.01.

- **Negative controls:** TOI-1175.01's S40 and S41 eclipses are fully covered (78 to 79 cadences each), so its
  season-1 fail stays. TOI-188.01's odd/even uses many eclipses and would lose little.
- **Shortlist:** signals with few transits (441010857 with 3, 48010903 with 4, 44926986 with 5) could lose one and
  with it holdout or odd/even power. Which ones have partial transits is unknown until they are vetted.

**Blunter alternative:** a fractional depth floor in the tension. At 3% of the depth, TOI-576.01's tension becomes
1.43, but TOI-1175.01's becomes 2.81 and its fail goes away. On 48010903 the floor (137 ppm) would exceed the search
error (74 ppm) and loosen the check a lot. On the shallow signals it is negligible.

## Item 6: the inconclusives (TOI-451.02, TOI-451.03, TOI-1097.02)

The expected SNR is the catalog depth over the run's signal_present error at the catalog ephemeris (core box,
red-noise errors).

| Signal | Host age, rotation (archive) | Catalog depth (ppm) | Error (ppm) | Expected SNR | SNR at catalog ephemeris | SNR at archive ephemeris | Red-noise beta | TOI table SNR |
|---|---|---|---|---|---|---|---|---|
| TOI-451.02 (TOI-451 b) | 125 Myr, 5.10 d | 498 | 147 | 3.4 | 2.7 | 2.7 (Barragán 2026) | 2.8 to 5.1 | 10.0 |
| TOI-451.03 (TOI-451 c) | 125 Myr, 5.10 d | 941 | 269 | 3.5 | 3.1 | 4.1 (Barragán 2026) | 3.2 to 5.7 | 9.8 |
| TOI-1097.02 (HD 109833 c) | 27 Myr, 5.11 d | 647 | 131 | 4.9 | 1.1 | 3.9 (Wood 2023 period, TOI epoch) | 3.4 to 3.9 (S38, S39, S100) | 8.8 |

Low SNR is expected on all three: under vet-v3's noise model even the expected SNR is below 7. The TOI SNRs are
SPOC's (full duration, its own detrend). The core box uses half the duration, and on these two young stars the
residual variability left by the 1.2-day biweight inflates the errors 2.8 to 5.7 times. HD 109833's S11 and S12
are 30-minute FFI data with 9 core cadences in all.

Two of the TOI periods are stale:

| Signal | Archive minus catalog prediction, by season | Core half-width | Effect |
|---|---|---|---|
| TOI-451.02 | -0.009, +0.006, +0.053 d | 0.021 d | only S106 and S107 affected, where the error is 535 ppm anyway |
| TOI-451.03 | -0.004, +0.104 (S31), +0.420 (S106, S107) d | 0.032 d | TOI P 9.191079 against Barragán 9.192463 ± 1.7e-5; later transits missed |
| TOI-1097.02 | +0.140 (S11, S12, epoch -52), 0, -0.336 (S100, epoch 125) d, from the period difference | 0.022 d | TOI P 13.902839 ± 0.00139 against Wood 13.900148 ± 5.7e-5; the run's density-prior fit gives 13.900193 |

For TOI-1097.02, the scan finds the S11 and S12 transit at +0.132 d (4.0 sigma), matching the predicted +0.140. The
archive's Wood 2023 t0 (BJD 2456440.7567, query 3) puts the S38 and S39 transits 1.4 d from where they are in the
data, so I used Wood's period with the TOI epoch. That archive t0 looks wrong; I did not check it against the paper.

The holdout's per-season expected SNRs in the run:

| Signal | Season 0 | Season 1 | Season 2 |
|---|---|---|---|
| TOI-451.02 | 3.2, underpowered | 0.9, underpowered | 0.8, underpowered |
| TOI-451.03 | 7.3, missed | 0.9, underpowered | 1.2, underpowered |
| TOI-1097.02 | 4.4, predicted | 1.9, underpowered | 1.4, underpowered |

TOI-451.03's season-0 "missed" comes from a refit on two training seasons with expected SNR near 1. BLS takes the
best noise peak, so the training depth that sets the expected SNR is biased up. Only one season was testable, so the
outcome was inconclusive.

**Cause:** low SNR from the star's red noise, plus stale control ephemerides for 451.03 and 1097.02. Not a
threshold problem: at the corrected ephemerides they reach 4.1 and 3.9, still under 7.

**Smallest change:** none to vet-v3. Updating the two ephemerides gives cleaner controls but leaves them
inconclusive. A shortlisted signal on an equally active star would likewise come out inconclusive, not failed.

## Item 7: TOI-1175.01 (negative control), holdout season 1

This is a real feature of the blend, not the ephemeris issue. Season 1 (S40, S41) is detected at 15.0 sigma at the
refit ephemeris, but its depth is 1260 ± 84 ppm against 1644 ± 88 ppm from training, a tension of 3.16. At the
catalog ephemeris S40 and S41 read 1247 ± 169 and 1277 ± 95 ppm. The later sectors read S54 1463 ± 253, S74
1495 ± 175, S80 1622 ± 285 and S81 1785 ± 190 ppm; S14 reads 1899 ± 137 ppm from six 30-minute cadences. Every S40
and S41 eclipse is fully covered (78 to 79 window cadences) and shallow (918 to 1779 ppm), so no single event drives
it.

The ephemeris is fine. The TOI period, 7.5022708 ± 3.68e-5, against the fit's 7.502172 drifts by at most 0.014 d
over epochs -100 to +145, and season 1 holds the TOI epoch itself (the fit's t0 is 0.0036 d from it). The holdout's
prediction is 0.008 d from the fit there, against a 0.027 d core half-width. Holding the eclipse out of the detrend
leaves the tension at 3.07. A nearby EB's leaked depth depends on each sector's aperture, which fits this pattern.
CROWDSAP (0.84 to 0.90) does not order the depths by itself, so the mechanism is a guess. A negative control failing
a check is not a stop condition, and the design gates TOI-1175.01 on TRICERATOPS.

## Other observations

- **The vet does not hold the transit out of the detrend.** `vet_with_fits` calls `detrend(lc, ..., others)`
  without `hold_out`; triage's LEO `prepare` holds out 2 durations. On short-period or deep signals this lifts the
  out-of-transit flux: 162 ppm above 1 for TOI-1399.01 (51 with the hold-out) and 42 ppm for TOI-747.01 (14). The
  phase-0.5 depths barely move (94 to 94, 119 to 119, 278 to 286 ppm), so this caused none of the items. It does
  lower combined depths, though: TOI-1399.01 reads 1442 against 1542 ppm with the hold-out, and TOI-1175.01 1487
  against 1579. With the hold-out, TOI-747.01's holdout season 0 goes from 2.93 to 3.02 and fails. The shortlisted
  depths are small, so the effect on them should be small.
- **Masks trust catalog ephemerides.** HR 858 b's stale ephemeris leaks its transits (item 4). A shortlisted star
  with a known planet on a drifted ephemeris would see the same.
- **The holdout's expected SNR is biased up** when the training seasons are noise-dominated (item 6).

## Changes and their reach

| Change | Fixes | Negative controls | Shortlist |
|---|---|---|---|
| None; record each item as understood (decision records) | nothing | unchanged | unchanged |
| Planet-aware secondary bound, Ag cap 0.5, flat-fit Rp/R* and a/R* | 107.01, 747.01 | 1399.01 still fails (3.9 sigma or more over the bound); 188.01, 1058.01, 1175.01 unchanged | the 3-sigma line moves by 8.7 ppm at most |
| Secondary errors scaled by beta at the full duration | 747.01 | 1399.01 still fails (8.88) | secondary errors 0.99 to 1.36 times larger (control range) |
| Eccentricity term of 0.11 dex in the density tension | 191.01 | 188.01 still fails (4.34); 1399.01's density passes (2.71), its secondary still fails | tensions 3 to 30% lower, most for 48010903 |
| Partially covered transits left out of depth comparisons | 576.01 | 1175.01's holdout fail stays | may cost holdout or odd/even power on signals with 3 to 5 transits |
| TOI-396.01 out of the pass rate (TTV planet) | 396.01 | none | none |
| Archive ephemerides for 451.03 and 1097.02 | nothing (they stay inconclusive at 4.1 and 3.9) | none | none |

## Methods

- **Rebuild:** `good_timestamps(LightCurve.load(...))`; then `other_known_transits(eph, load_known(SNAP3), tic,
  harmonics, search-v2, vet-v3 [masks] sources)`; then `detrend(lc, search-v2 [detrend], others)`; then
  `red_noise_beta` at 0.5 × duration and `with_red_noise`. The checks were rerun with the repo's own functions
  (`secondary`, `signal_present`, `sector_depths` through `per_family`, `holdout`) at commit 62882b5.
- **Held-out detrend:** the same, with `hold_out=in_transit(time, eph, 2.0)`.
- **Full-duration beta:** `red_noise_beta` with the timescale set to one duration.
- **Secondary null:** cadences within one duration of each transit and of phase 0.5 removed; then `box_depth`
  (width 1.0) at phase 0.5 of 2000 random periods (0.7 to 1.3 P, random epoch, numpy seed 1).
- **Occultation maxima:** star and planet as blackbodies, integrated over the TESS response × wavelength (photon
  weighting); a/R* = `a_rs_from_density(10**log_rho_median, period)` from the flat fit. Tc solves
  (Rp/R*)² B(Tc)/B(Teff) = D_max.
- **Transit-position scans:** per holdout season, the core-box SNR (`box_depth`, width 0.5) at epoch shifts from
  -0.6 to +0.6 d in 0.002-d steps (±0.8 d for TOI-451.03 and TOI-1097.02). HR 858 b was rebuilt the same way with
  its Bonfanti ephemeris as the signal, so c and d were masked.
- **Eccentricity prior widths:** e drawn from each prior, ω uniform, kept with probability proportional to
  (1 + e sin ω) / (1 - e²); standard deviation of 3 log10 g over 2,000,000 draws.
- **Archive queries** (TAP sync, `format=csv`, 2026-10-17):
  1. `select pl_name,default_flag,pl_orbeccen,...,pl_orblper,...,st_dens,...,st_mass,st_rad,pl_ratdor,pl_imppar,pl_refname from ps where pl_name='WASP-8 b'`
  2. `select pl_name,default_flag,pl_occdep,...,pl_ratdor,pl_ratror,pl_eqt,st_teff,pl_orbeccen,pl_refname from ps where pl_name in ('WASP-87 b','WASP-94 A b')`
  3. `select pl_name,default_flag,pl_orbper,pl_orbpererr1,pl_orbpererr2,pl_tranmid,pl_tranmiderr1,pl_tranmiderr2,pl_trandur,ttv_flag,pl_refname from ps where pl_name in ('HR 858 c','HR 858 b','TOI-451 b','TOI-451 c','HD 109833 c','WASP-166 b')`
  4. `select pl_name,st_age,...,st_rotp,pl_refname from ps where default_flag=1 and pl_name in (...)` and
     `select pl_name,pl_orbper,pl_orbeccen,pl_bmasse,pl_refname from ps where default_flag=1 and hostname='HR 858'`
- **Scratch:** all scripts and rebuilt light curves were kept in `/tmp/t11-diag/` and deleted afterwards.
