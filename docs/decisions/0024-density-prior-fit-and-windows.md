# 0024: vet-v3 fits again with the TIC density as a prior, and predicts the transits in TESS's next sectors

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design). Added on 2026-10-28, by a ruling of the M4 build's
  controller with no acceptance by the maintainer recorded: astropy's bundled leap-second table, which `uv.lock` fixes,
  expires on 2027-06-28, and from 150 days before then astropy tries to download a newer table when it converts a time
  to or from UTC. It checks once per process, at the first such conversion. `predict.btjd` and `predict.seen_utc` turn
  that download off for their own conversions: they keep to the bundled table and warn that it is stale, and the other
  modules keep astropy's default. Every published dossier's windows convert to the same times as before
  (`test_seen_utc_matches_the_dossier` in `tests/test_dossier.py`), and both conversions run offline past the expiry
  (`test_conversions_warn_rather_than_download_once_the_leap_second_table_expires` in `tests/test_predict.py`). A leap
  second announced after the table would be missed: one second, beside windows whose widths run to minutes.

## Context

vet fits each transit with a flat prior on the stellar density, and the density check compares that fit's density with
the TIC's. The check needs the flat prior, or it would only see its own prior (`checks.physical.density` refuses a fit
with a density prior). A flat prior lets the impact parameter and the density trade off, so on a low-SNR signal it can
read a planet as grazing or larger than it is. The dossier, TRICERATOPS and M4 need the planet's parameters on the
assumption that it orbits the target: Rp, b, a/R* and the ephemeris, with its uncertainty carried to each sector TESS
observes next, since those sectors set the dates follow-up has to meet (M3 design, sections 3 and 4.2).

Shape and radius stay on the flat-prior fit, as under vet-v2 (the M3 design's call). Read from a fit with the density
prior, they would assume the signal is on the target, which is one of the things being tested.

## Decision

- Under vet-v3, `vet.vet_with_fits` runs `fit_transit` a second time, on the same light curve as the first (the PDCSAP
  family without timing-suspect sectors, decisions 0022 and 0023), with the same `[fit]` settings and seed and
  `rho_prior = vet.density_prior(star, [density] default_log_rho_error)`: log10 of the TIC `rho` times 1.408 g/cm3, and
  `e_rho / (rho ln 10)` dex, or `default_log_rho_error` when the TIC gives no `e_rho`. Each fit runs on its own, so a
  flat-prior fit that fails does not stop the second.
- `report["fit_prior"]` is the second fit's summary plus `rp_rearth` (the median and 16th and 84th percentiles of
  Rp/R* times the TIC radius times 109.076; null without a TIC radius), `a_rs` (from each sample's density and period)
  and `ephemeris` (t0 and period, each a median and a standard deviation). When there is no second fit,
  `report["fit_prior"]` is null and `report["fit_prior_reason"]` says why: no PDCSAP data to fit, no TIC density, a TIC
  density outside the fit's flat range of log10 rho (-3, 2), where every walker would start outside the prior and the
  fit could say only that they never moved, or the fit's own error. The `vet` command writes the second fit's samples
  to `fit_prior_samples.npz` beside `fit_samples.npz`.
- `shape`, `density` and `radius` read the flat-prior fit. The dossier labels which fit each number comes from.
- `vet_signal` keeps its signature and returns the report and the flat-prior fit; `vet_with_fits` also returns the
  second fit. Under vet-v1 and vet-v2 there is no second fit and the report gains no field, so their vets reproduce.
- `predict.upcoming_sectors` lists every sector from `[predict] first_sector` on in which tess-point places the star on
  a camera.
- `predict.windows` takes the second fit's samples, the sector dates and the upcoming sectors. For each sector with
  dates, and each epoch n whose median mid-time falls between the sector's start and end, it gives the median of the
  posterior's `t0 + n * period` samples in BTJD, their standard deviation in minutes, half-widths of `[predict] sigma`
  standard deviations, and the transit duration. The spread comes from the samples themselves, so a correlation
  between t0 and period carries through, which a propagation of the two errors on their own would miss. A sector with
  no dates in the file is listed with `dates: "unknown"`.
- The sector dates are in `benchmarks/tess_sectors.csv` (`[predict] sectors_file`, a path from the repo root, read the
  same wherever a command runs). The tess.mit.edu sector pages give days, not times, so each start and end is 00:00 UTC
  on its day. They become BTJD through astropy: `Time(utc, scale="utc").tdb.jd - 2457000`.

## Limitations

- With days for sector edges, a transit within about a day of a sector's start or end may fall in the sector before
  or after it. A predicted transit can also fall in a sector's mid-sector downlink gap, which the file does not give.
- The edges are converted to TDB without the barycentric correction, so they can sit up to about 8 minutes off true
  BTJD, small beside a day.
- Future pointings are provisional: tess-point's and the sector pages' plans are those of the dates read, and the
  file is updated by hand.
- The second fit assumes the signal is on the target. For a blend, its parameters describe a planet that is not there,
  which is why no check reads them.
- `rp_rearth` takes the TIC radius as exact; its error is not carried through.
- Like the first fit, the second trusts the light curve's errors (no jitter term), so its posterior widths, and with
  them the windows, can be too narrow where residual red noise remains.

## Evidence

- [tests/test_vet.py](../../tests/test_vet.py):
  - `test_density_prior_units_and_fallback` (solar units to log10 g/cm3, the error in dex, the default error without
    `e_rho`, no prior without a positive `rho`).
  - `test_prior_fit_reported_beside_the_flat_fit` (vet-v3's report has both fits; shape, density and radius evidence
    match the flat-prior fit; the TIC density narrows the second fit's density posterior; `rp_rearth`, `a_rs` and the
    ephemeris come from the second fit's samples).
  - `test_prior_fit_needs_fit_data_and_a_tic_density_inside_the_fit_range` (each reason, including a white dwarf's
    density; vet-v2 fits once and its report gains no field).
  - `test_diluted_qlp_does_not_fail_a_planet` (both fits are given the PDCSAP sectors alone).
- [tests/test_predict.py](../../tests/test_predict.py):
  - `test_windows_follow_the_posterior` (uncorrelated synthetic samples: the standard deviation at each epoch n is
    within 5% of sqrt(sd_t0^2 + n^2 sd_P^2); anti-correlated samples that pivot at one epoch give it almost no spread).
  - `test_sector_without_dates_is_listed_as_unknown` and `test_sectors_file_is_read_from_the_repo_root`.
  - `test_upcoming_sectors_leave_out_observed_sectors_and_a_star_off_the_cameras`, and the network test
    `test_upcoming_sectors_for_44926986` (tess-point's sectors for TIC 44926986 from S110 on), run by hand.
- [benchmarks/tess_sectors.csv](../../benchmarks/tess_sectors.csv), with its source pages and the date read.
