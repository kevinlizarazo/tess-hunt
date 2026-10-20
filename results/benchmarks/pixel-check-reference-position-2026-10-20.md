# The pixel check's reference position (pixel-diag's follow-up, 2026-10-20)

Read-only. Scripts and outputs in `/tmp/pixel-diag/`, published as `pixel-diag/` in
`neighbour-epoch-reach-2026-10-20-scripts.tar.gz` beside this file: `epoch_check.py`, `make_jobs_triage.py`,
`epoch_max.py`, `seed_check.py`, `jobs_triage.json`, `epoch_check.txt`, `epoch_check_triage.txt`,
`epoch_check_second_passes.txt`, `seed_check.txt`. Text as the agent sent it (the harness blocks subagent report
files).

## Verdict

The pixel check measures each offset from the target's position at that sector's mean time, not from the J2000 TIC
position. For all four failed known planets that position matches Gaia DR3 carried to the sector within 0.02", so the
epoch error is at most 0.02" in every recorded sector. The rest of each offset is what the diagnosis put down to the
bleed column or the weak transit. The J2000 position only centres the TESScut cutout, which also sets where the fit
starts, and picks the camera and CCD. Restarting the fit from the target instead leaves all four verdicts unchanged.
Nothing changes for the 19 signals' hosts or the six second-list fails. The link to proper motion comes from
brightness: the four fails sit on the four brightest hosts, which are also the nearest.

## Code path (repo .venv)

- `src/tess_hunt/pixels.py:88` passes the TIC J2000 ra and dec. For all 24 stars checked, the star table's ra and dec
  equal the TIC's J2000 values. pixels.py uses them for `observable_sectors` (`:89`) and the star dict (`:105`).
- That J2000 position is used only in three places:
  - `transitDiffImage/tessDiffImage.py:226-227,239-243`: the TESScut request is centred on it.
  - `tessDiffImage.py:493`: the TIC cone query (312" radius) is centred on it.
  - `leo_vetter/pixel.py:93`: tess-point uses it to look up the camera and CCD.
- The target position the offset is measured from comes from `tessDiffImage.py:480-504`:
  - `:484-488` sets the epoch to J2015.5 and takes `dt` from J2015.5 to the mean time of the sector's pixels, divided
    by 365.
  - `:496-504` sets `correctedRa = RA_orig + pmRA*dt/cos(Dec_orig)` and `correctedDec = Dec_orig + pmDEC*dt`, from the
    TIC's `RA_orig`/`Dec_orig` and proper motion.
  - `:506` picks out the target by TIC id.
  - `:528-529` and `:541` turn the corrected positions into pixel positions for the target and every catalogue star.
- `leo_vetter/pixel.py:60-70` computes the offset from `ticColPix[0]` and `correctedRa/Dec[0]`.
- `transitCentroids.py:42-48` starts the fit from the flux centroid of the cutout's central 7 x 7 pixels. That box
  sits on the J2000 position, not the target.

## Measured

`epoch_check.py` reads each pickle's target position, queries MAST TIC and Gaia DR3 for these sources only, and
carries DR3 to each sector's mean time. Every host here has TIC `POSflag tmgaia2` and `PMflag gaia2`, so the code's
J2015.5 assumption holds. Rebuilding the position as `RA_orig + pm*dt` from the TIC row matches the pickle within
0.01" in all 54 + 45 + 20 sectors.

| Planet (DR3 pm, mas/yr) | Sectors | J2000 error at that epoch | Check's position error | Recorded offset |
|---|---|---|---|---|
| TOI-2011.02 (1646.5) | S103, S102, S65, S38, S12 | 43.4, 43.3, 38.5, 35.2, 32.0" | 0.01-0.02" | 64.7, 35.2, 69.0, 60.5, 32.8" |
| TOI-144.01 (1094.2) | S95, S94, S93, S89, S88 | 28.0, 27.9, 27.9, 27.5, 27.4" | 0.01" | 46.8, 59.0, 61.9, 44.3, 60.4" |
| TOI-4307.01 (326.2) | S98, S97, S96, S95, S94 | 8.3-8.5" | 0.00" | 17.9, 23.0, 13.6, 23.8, 16.5" |
| TOI-396.03 (162.7) | S107, S106, S105, S97, S31 | 3.4-4.3" | 0.00" | 35.6, 20.1, 47.0, 30.8, 8.8" |

- Measured from DR3's own position, the offsets are the recorded ones to within 0.1".
- An epoch error would point the same way every sector and grow with time. TOI-2011.02's fits do neither: east, north
  (+27,-59), (-5,-35), (+14,+68), (-19,-57), (-20,-26)".
- The 0.02" that remains comes from the code dividing by 365 days instead of 365.25.

## What the J2000 cutout centre does (`seed_check.py`)

It moves TOI-2011.02's target up to 3 pixels off the cutout centre (S102, S103) and TOI-144.01's up to 2 pixels (S88).
The other two are within 1 pixel. Every sector was refit twice: once starting from a 7 x 7 box centred on the target's
own pixel, once starting at the target's catalogue position. Individual fits shift on the two saturated stars, but the
check's rule still fails all four:
- TOI-2011.02: 32.8" (quality 0.59) in place of 69.0".
- TOI-144.01: 46.8" either way.
- TOI-4307.01: 17.9" either way.
- TOI-396.03: 35.6" either way.

## The 19 hosts and the six second-list fails

- The check's position error is 0.00" in all 45 triage-pixel sectors of the 9 vetted signals not on the second list.
  That includes TIC 44926986: J2000 minus DR3 at J2016 is 2.8", rising to 3.6-4.5" at its sector epochs, yet the
  check's error is 0.00". Its recorded 10.9-12.8" offsets stand.
- The error is also 0.00" in all 29 sectors of the six second-list fails and all 20 of the four second-list passes. No
  rating changes.
- One knock-on for the diagnosis. In its table of stars at the fitted positions, the "From target" distances came from
  `neighbours.csv` `sep_arcsec`, which carry the target's J2000-against-J2016 mismatch: 173369850-1 0.4",
  295140687-1 0.2", 322826591-1 1.7", 337885456-1 0.8", 423100454-1 2.2", 458290782-1 0.4". For example, TIC 322826642
  is listed at 39.1" against 40.1" from the cutout catalogue, which is corrected to each sector's epoch.
  `required_depth` doesn't use separation (`src/tess_hunt/neighbours.py:119`), so possible-host status is unaffected.

## Side finding, not about epoch

The PRF fit depends on where it starts in a few sectors:
- TOI-396.01 S105 goes from 59.0" to 10.6".
- 337885456-1 S66 goes from 42.3" to 18.0" (quality 0.83 to 0.31) when started at the target.
- 423100454-1 S102 and S65 go from 118.6" and 115.7" to 7.3" and 7.0" when started at the target. Their quality drops
  to 0.12 and 0.17, so under the rule the best-quality sector becomes S39 (5.8") and the row would pass. That supports
  reading 423100454-1's fail as the variable neighbour capturing the fit.

## Commands

From Git Bash, `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu-26.04 --cd /tmp/pixel-diag -- bash -l -s`:

```
. ~/.cache/tess-hunt/logs/m3-vars.sh; export CONTROL_VET VET_RUN SECOND_RUN TRIAGE_RUN
P=/home/kevin/code/tess-hunt/.venv/bin/python
/tmp/t13/heavy.sh $P epoch_check.py TOI-2011.02 TOI-144.01 TOI-4307.01 TOI-396.03 TOI-396.01 173369850-1 295140687-1 322826591-1 337885456-1 423100454-1 458290782-1   # epoch_check.txt
JOBS=jobs_triage.json /tmp/t13/heavy.sh $P epoch_check.py $($P make_jobs_triage.py)   # epoch_check_triage.txt
/tmp/t13/heavy.sh $P epoch_check.py 241522065-1 277774870-1 370977908-1 438857197-1   # epoch_check_second_passes.txt
$P epoch_max.py epoch_check*.txt   # largest error: 0.02", 0.00", 0.00"
/tmp/t13/heavy.sh $P seed_check.py <the same 11 labels>   # seed_check.txt
```

The scripts read and write `/tmp/pixel-diag/` by that absolute path, so a rerun unpacks the tarball's `pixel-diag/`
folder there, beside the pixel diagnosis's (`pixel-check-diagnosis-2026-10-20-scripts.tar.gz`): `epoch_check.py` and
`seed_check.py` read its `jobs.json`, `seed_check.py` imports its `sector_detail.py`, and `epoch_check.py` reads its
`detail.json`, which `sector_detail.py` rebuilds. `/tmp/t13/heavy.sh` is the tarball's `t13/heavy.sh`: it runs one
command at a time under a 6 GB memory cap.
