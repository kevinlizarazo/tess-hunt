# Vetting

One row per published signal the maintainer has called passed, killed or held, whose call stands on its record
([decision 0028](../../docs/decisions/0028-outcomes-and-calls.md)). Each directory holds the signal's dossier
(`dossier.md`), the call (`call.toml`), the review (`review.json`), the review's scripts and outputs
(`review-scripts.tar.gz`) and the run files the dossier is rendered from; [../README.md](../README.md) describes each
file. A passed signal is a planet candidate, not a confirmed planet.

| Signal | Outcome | Date | Reason |
|---|---|---|---|
| [103312990-1](103312990-1/dossier.md) | held | 2026-10-22 | Nothing kills it: the dip is in every season at a steady depth, shows no binary signature on the target, and is not known. It can't pass because the public data can't place it on HD 297321: a nearby eclipsing binary within an arcminute is not excluded, Gaia sees an unresolved companion that no public data identify, and only one season can test the held-out check. |
| [146282666-1](146282666-1/dossier.md) | held | 2026-10-22 | Nothing kills it: the dip is periodic, steady across eight years of transits, U-shaped and new, in a system that already holds TOI-4298.01. It can't pass because the public data can't place it on the target: a background star a few arcseconds away could make it, TESS's pixels can't separate the two, and TRICERATOPS sits just over its pass bar. The held-out check is also inconclusive, for lack of power rather than of transits. |
| [164767175-1](164767175-1/dossier.md) | held | 2026-10-22 | Every other check passes, TRICERATOPS among them, and nothing published or catalogued sits at this period, a third signal on a star with two confirmed planets. But the search found it only just above the threshold, where a false alarm or so is expected across the whole sample, and every held-out season is too weak to test, so TESS can't yet replicate it apart from the search. |
| [241522065-1](241522065-1/dossier.md) | held | 2026-10-22 | Nothing argues against a planet: the dip is real and periodic from 2021 to 2026 at the same depth in both product families, sits on the target in every sector's difference image, and passes TRICERATOPS and every other check. It can't pass only because TESS's two seasons with trustworthy timestamps can't test each other, so the held-out check is inconclusive. |
| [277774870-1](277774870-1/dossier.md) | held | 2026-10-22 | No check fails, but the transit is far too short for a central crossing of this star: on the target it must graze or ride a highly eccentric orbit, and the light curve fits a crossing of a much denser star just as well. TRICERATOPS puts most of its weight on a pair of small stars bound to the target, and Gaia's radial velocities rule out only a stellar companion grazing the target itself. |
| [296819076-1](296819076-1/dossier.md) | held | 2026-10-22 | Nothing failed, but the public data can't place the dip on the target. A reanalysis of triage's difference images puts the transit's loss west of the target, on TIC 296819054 or two fainter stars beside it, but it rests on weak images outside the frozen pixel check and falls short of the project's binary controls, so it holds rather than kills. TRICERATOPS, the neighbour table and the held-out check are inconclusive. |
| [370977908-1](370977908-1/dossier.md) | held | 2026-10-22 | Probably an eclipsing binary, not a planet, though the public data don't show it. A dip about as deep as the transit sits just before the half-orbit point in every orbit with data there, at the target's pixels, which vet-v3's half-orbit check can't see; if real, it is a binary's second eclipse. TRICERATOPS's only blocker is immaterial, and without it its NFPP would fail, though SPOC's difference-image centroid sits well away from every star that carries it. |
| [399023421-1](399023421-1/dossier.md) | held | 2026-10-22 | Every vet-v3 check, the pixel check and the literature search pass, and nothing on the target looks like a binary. TRICERATOPS can't place the dip on the target: three faint background stars a few arcseconds away could make it with deep eclipses, and TESS's pixels can't separate them from the target. |
| [410399327-1](410399327-1/dossier.md) | killed | 2026-10-22 | At the search's period the odd transits are missing: both odd epochs with full data are flat while the even ones dip, so odd and even, the sector depths and the held-out seasons all fail, as they are built to for a wrong period. The dips fit a period twice as long, past the search's period limit; that is a different signal, not vetted here, and goes to the long-period search with M5's slice B as a lead. Sector 114's transit, due on the same date at both periods, is a free check. ExoFOP's note on TOI-7925.01 already names two of these dips. |
| [423100454-1](423100454-1/dossier.md) | held | 2026-10-22 | Every light-curve check passes, the held-out seasons included, and the transit sits on the target in every sector's difference image; the pixel check's fail measured a variable star two arcminutes away (decision 0033). It can't pass because TRICERATOPS can't place the dip on the target: almost all of its NFPP is one dwarf star half an arcminute away, which the pixels argue against but TRICERATOPS can't take in. |
| [438857197-1](438857197-1/dossier.md) | held | 2026-10-22 | The dip is real and not known, and no check fails, but on this star it must be a grazing transit by a body the light curve can't bound from above, and Gaia's flat radial velocities leave only a planet or brown dwarf for that. TRICERATOPS puts most of its weight on an unresolved bound companion, and the pixels can't separate the target from two possible hosts a dozen arcseconds away; SPOC's own sector 64 centroid leans toward one of them. |
| [441010857-1](441010857-1/dossier.md) | killed | 2026-10-22 | The transit is far too short for a planet on this star: on a circular orbit at this period a transit across a star this size lasts several times longer, so the fit implies a star far denser than this F star. A planet escapes only on a highly eccentric orbit seen near its closest approach, which only radial velocities could show; the dip may instead be on a denser neighbour. The held-out check's first-run fail was a defect that decision 0035 fixed; it is now inconclusive and plays no part in the kill. |
| [44926986-1](44926986-1/dossier.md) | killed | 2026-10-22 | Not new: eumemic's public all-sky candidate list holds this signal at the same period and epoch, added before tess-hunt made any public claim. TRICERATOPS also fails it, on a planet on the bound companion TIC 44926982, which TESS's pixels can't separate from the target. |
| [48010903-1](48010903-1/dossier.md) | killed | 2026-10-22 | An eccentric eclipsing binary of stars, not a planet: the real period is longer than the search's, and the search's second signal on the star is the binary's secondary eclipse, too deep and too long for any planet. The shape and radius checks fail too, on a fit that sits near the grazing line, so they are the weaker grounds. The next-look windows in this dossier use the search's period, not the binary's. |

## Reading the reviews

Each review (`review.json`, quoted in `dossier.md`) cites its evidence by the names it had on the machine the reviews
ran on: scratch directories, draft records and shell variables holding run ids. This key says what each stands for.

- `/tmp/t13/<name>/` was the review's scratch directory. Its scripts and their small outputs are in
  `<name>/review-scripts.tar.gz`, under `t13/<name>/`, with a `MANIFEST.txt` listing each file left out and why (fetched
  from a service, 1 MB (1,000,000 bytes) or over, a copy of a published file, and so on). `/tmp/t13/` itself, the
  scripts every review shared, is in [review-scripts.tar.gz](review-scripts.tar.gz), under `t13/`: among them
  `heavy.sh`, which ran each memory-heavy command one at a time once 6 GB were free and under a 6 GB cap, `assemble.py`,
  which made `review.json` from a review workflow's output, and `compare_runs.py` and `cmp_control_vet.py`, which
  compared runs for decisions 0034 and 0036. `/tmp/pixel-diag/` was the pixel check's diagnosis, published as
  [pixel-check-diagnosis-2026-10-20-scripts.tar.gz](../benchmarks/pixel-check-diagnosis-2026-10-20-scripts.tar.gz).
- "The brief" is the review brief every reviewer and refuter was given: [review-brief.md](review-brief.md). "M3
  design, section N" in it and in the reviews is the milestone's design, kept outside the repository, from which
  [docs/design.md](../../docs/design.md) was amended. The brief's `/mnt/c/code/docs/tess-hunt-m3-design.md` and the
  reviews' `C:\code\docs\tess-hunt-m3-design.md` are both that private design on the maintainer's machine (the
  dossiers show it as `tess-hunt-m3-design.md`); it is not published, and the public spec is
  [docs/design.md](../../docs/design.md).
- `~` is the maintainer's home directory and `$TESS_HUNT_DATA` the data directory (by default `~/.cache/tess-hunt`);
  `~/code/tess-hunt` is the maintainer's checkout of this repository. A run id names a directory under
  `$TESS_HUNT_DATA/runs/`. `review.json` keeps every other path as the review wrote it; `dossier.md` shows a path
  elsewhere on the maintainer's machine by its file name alone.
- "The maintainer" in the reviews, the brief and the tarballs stands where they gave the maintainer's name, rewritten
  by the same step that rewrites the home directory
  ([decision 0038](../../docs/decisions/0038-literature-trim-and-username-scrub.md)).
- `drafts/m3/<name>/` and `drafts/m3-r2/<name>/`, under `$TESS_HUNT_DATA`, are draft records `tess-hunt vetting
  dossier` laid out: `drafts/m3` from the first runs (`VET_RUN`, `VET_SUSPECT_RUN`, `TRIC_RUN`, `LIT_RUN`,
  `SECOND_RUN`), `drafts/m3-r2` from the reruns after decisions 0034 to 0036 (`VET2_RUN`, `VET2_SUSPECT_RUN`,
  `TRIC2_RUN`, `TRIC3A_RUN`, `TRIC3B_RUN`, `LIT3_RUN`, `SECOND2_RUN`). Each published record holds its runs' files as
  `drafts/m3-r2` held them, and its `provenance-*.json` files name its runs.
- The shell variables, set by files under `$TESS_HUNT_DATA/logs/` that are not published, each hold a run id (or,
  for `SNAP3`, a catalog snapshot under `$TESS_HUNT_DATA/catalogs/`):

| Variable | Run | What it is |
|---|---|---|
| `SEARCH_RUN` | [`20261014T205855Z-search-fe29585-cdf2`](../benchmarks/20261014T205855Z-search-fe29585-cdf2) | M2's production search |
| `THRESHOLD_RUN` | [`20261014T175116Z-threshold-0d6748e-40ac`](../benchmarks/20261014T175116Z-threshold-0d6748e-40ac) | M2's detection threshold |
| `TRIAGE_RUN` | [`20261015T155441Z-triage-7b12e25-3f57`](../triage/20261015T155441Z-triage-7b12e25-3f57) | M2's triage, with LEO-Vetter and the pixel check |
| `SNAP3` | `2026-10-17T142814Z` | the catalog snapshot novelty used (not published) |
| `CONTROLS_RUN` | [`20261020T082333Z-benchmark-controls-16418d2-f45a`](../benchmarks/20261020T082333Z-benchmark-controls-16418d2-f45a) | vet-v3's controls |
| `VET_RUN` | `20261020T010149Z-vetting-run-62882b5-c3ee` | vet-v3 on the 19 signals, first run |
| `VET_SUSPECT_RUN` | `20261020T011247Z-vetting-run-62882b5-d92b` | the same with the timing-suspect sectors kept in, evidence only |
| `SECOND_RUN` | `20261020T012658Z-vetting-second-list-62882b5-3fca` | the second list, first run |
| `TRIC_RUN` | `20261020T013408Z-vetting-triceratops-62882b5-e092` | TRICERATOPS, first run |
| `LIT_RUN` | `20261020T091938Z-vetting-literature-2315775-066c` | the literature search, first run |
| `VET2_RUN` | `20261020T174317Z-vetting-run-61b5944-2d70` | vet-v3 on the 19 signals, rerun after decisions 0034 and 0035 |
| `VET2_SUSPECT_RUN` | `20261020T175536Z-vetting-run-61b5944-7f4e` | its evidence-only twin |
| `SECOND2_RUN` | [`20261020T180844Z-vetting-second-list-61b5944-7096`](../benchmarks/20261020T180844Z-vetting-second-list-61b5944-7096) | the second list, rerun |
| `TRIC2_RUN` | `20261020T181658Z-vetting-triceratops-61b5944-1bbf` | TRICERATOPS on the rerun, before decision 0036 |
| `LIT3_RUN` | `20261021T001540Z-vetting-literature-61b5944-07de` | the literature search on the rerun |
| `TRIC3A_RUN` | `20261021T044850Z-vetting-triceratops-cd4e7a2-07c3` | TRICERATOPS on the five promoted second-list rows, after decision 0036 |
| `TRIC3B_RUN` | `20261021T194348Z-vetting-triceratops-cd4e7a2-7821` | TRICERATOPS on 399023421-1, 296819076-1, 103312990-1 and 44926986-1, after decision 0036 |

Five benchmark notes and three tarballs under `../benchmarks/`, published on 2026-10-20 and 21 before the scrub of
[decision 0038](../../docs/decisions/0038-literature-trim-and-username-scrub.md), still give the maintainer's home
directory in full. Read it as `~`, its `.cache/tess-hunt` as `$TESS_HUNT_DATA`, and its `code/tess-hunt-run` as a
second checkout of this repository.
