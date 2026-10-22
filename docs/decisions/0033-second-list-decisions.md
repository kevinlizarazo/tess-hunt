# 0033: The second list's calls: five rows promoted, one of them past a pixel fail that measured a variable neighbour

- Date: 2026-10-20
- Status: Accepted (the maintainer's calls of 2026-10-20). Ruling W, which item 3 cites, was accepted by the maintainer
  on 2026-10-22 ([decision 0028](0028-outcomes-and-calls.md))

## Context

The second list is the ten signals, of the 466 that triage's novelty matched only to SPOC TCE or ExoMiner rows
([`known_to_spoc.csv`](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/known_to_spoc.csv)), that also passed
LEO-Vetter's flux tests with a normal RUWE. Twelve passed LEO-Vetter; TIC 162892242 (RUWE 2.92) and TIC 327555274 (RUWE
7.05) were left out (the file's `ruwe`). [Decision 0013](0013-novelty-sources.md) leaves such rows for the maintainer to
promote by hand. The M3 design (section 4.10) runs triage's pixel check on the ten, which triage never ran, and a pixel
fail kills a row as it would have in triage; a promoted row becomes a full M3 signal, with a dossier, TRICERATOPS, a
review and a call. The design's section 4.3 says: "A check that fails a confirmed planet is understood, with a decision
record and Kevin's call, before it can kill a candidate."

Triage's pixel check fails 4 of the 20 known planets in the pixel completeness run,
`20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33`
([summary.md](../../results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/summary.md), with
its `pixels.csv`): TOI-144.01, TOI-2011.02, TOI-396.03 and TOI-4307.01. It fails six of the second list's rows. Ruling
AS, the M3 build controller's, read section 4.3 as covering the pixel check where M3 uses it to kill, and had the fails
diagnosed before the second-list calls.
[`pixel-check-diagnosis-2026-10-20.md`](../../results/benchmarks/pixel-check-diagnosis-2026-10-20.md) ("the
diagnosis") refits the check's own fits from the difference images the runs kept, reproducing all 149 recorded offsets,
and adds null images and a fixed-position fit. It is a read-only analysis outside the pipeline and gates nothing. Its
scripts and small outputs are published beside it, byte for byte, in
[`pixel-check-diagnosis-2026-10-20-scripts.tar.gz`](../../results/benchmarks/pixel-check-diagnosis-2026-10-20-scripts.tar.gz).

On 2026-10-20 the maintainer was asked:

> 1. **Second-list calls.** I recommend promoting 241522065, 277774870, 370977908, 438857197, and 423100454 as the
>    exception, and leaving notes on the other five.
> 2. **Ruling G** (TRICERATOPS on phase-binned data): yes or no.
> 3. **Go-ahead for the Task 13 reviews.** All at once, or one at a time.

The reply, the same day: "please go with your recommendations. whats next now?" Item 2 is
[decision 0026](0026-triceratops.md)'s. This record writes down the call on item 1. It is a call made on these results,
not a rule set before them.

## Decision

1. **The known-planet fails are understood**, by the diagnosis (its Summary and section 1). TOI-144.01 and TOI-2011.02
   sit on saturated hosts (Tmag 5.11 and 5.05): the transit's loss shows at the ends of the bleed column, and the
   one-PRF fit follows the column, 1.7 to 3.4 pixels from the star, in 9 of their 10 sectors. TOI-396.03 is a
   saturating host (Tmag 5.91) with a 212 ppm transit its images barely hold. TOI-4307.01 (109 ppm, one transit per
   sector) holds no measurable transit in a sector's difference image, and its fits land on noise around a bright star.
   On these hosts neither outcome means anything: TOI-396.01, on TOI-396.03's star, passed on a sector whose image
   shows no transit at the star.
   - The saturated-host mode can't reach the 19 signals M3 vets: the brightest host is 337885456, at Tmag 8.26 (the
     diagnosis, section 2, where none of the six second-list fails is saturated; every host's `tmag` is in its
     `checks.json` in vetting run `20261020T010149Z-vetting-run-62882b5-c3ee`).
   - Brightness does not rule out the weak-transit mode. It is read sector by sector from the saved difference images,
     with null images and the z the light curve's depth would give: the diagnosis did that for the six second-list
     fails and rated none of them that mode (section 2). It did not discuss the four rows promoted on a pixel pass; its
     per-sector printout for them is `summary_second.txt` in the tarball.
   - The diagnosis also found a failure the known set did not show: a variable star elsewhere in the cutout can capture
     the fit, as it did on 423100454-1 (item 3).
   - Its caveats ("What this could not determine") stand: which of two stars 1" to 3" apart hosts 322826591-1 and
     458290782-1, and which northern star, if any one, hosts 295140687-1; what TIC 423100496 is; whether the second
     list's ephemerides have drifted by the latest sectors; each z's uncertainty of roughly a fifth, from 8 to 16 null
     images per sector, and the nulls hold only their own sector's systematics; and the 3 x 3 box behind the
     aperture-share depths.
2. **The ten rows.** From the second list's `second-list.csv` (run `20261020T012658Z-vetting-second-list-62882b5-3fca`)
   and, for each note, the diagnosis's rating (section 2; section 3 for SPOC's TCE on TIC 1343588382). Pixels is the
   outcome with the best-quality sector's offset; Fails names each vet-v3 check that failed, and the pixel check when
   it failed.

   | Row | TIC | Period (d) | SPOC TCE | ExoMiner row | Pixels | Fails | Decision |
   |---|---|---|---|---|---|---|---|
   | 173369850-1 | 173369850 | 6.487503 | `00173369850-01`, s0103-s0103, ratio 0.5 | `173369850-1-S39`, 0.028 FP | fail, 34.3" | secondary, pixels | noted: off-target source supported, the dip sits on TIC 173369830 (on S93 and S66) |
   | 241522065-1 | 241522065 | 17.436664 | none | `241522065-1-S38`, 0.811 PC | pass, 2.3" | none | promoted |
   | 277774870-1 | 277774870 | 12.819429 | none | `277774870-1-S56-69`, 0.573 PC | pass, 3.0" | none | promoted |
   | 295140687-1 | 295140687 | 2.673337 | none | `295140687-1-S56-69`, 0.028 FP | fail, 19.1" | secondary, pixels | noted: off-target source supported, weakly: the loss sits north of the target, and the pixels can't say on which star |
   | 322826591-1 | 322826591 | 12.725668 | `00322826591-01`, s0001-s0039 | `322826591-1-S1-39`, 0.041 FP | fail, 39.2" | sector_depth, holdout, density, pixels | noted: off-target source supported, the dip sits on TIC 322826642 or TIC 916591876 |
   | 337885456-1 | 337885456 | 1.379783 | none | `337885456-1-S66`, 0.003 FP, ratio 2 | fail, 40.7" | secondary, pixels | noted: off-target source supported, the dip sits on TIC 337885477 |
   | 370977908-1 | 370977908 | 17.091442 | `00370977908-01`, s0001-s0065 | `370977908-1-S1-65`, 0.782 PC | pass, 9.3" | none | promoted |
   | 423100454-1 | 423100454 | 14.186255 | none | `423100454-1-S39`, 0.785 PC | fail, 118.6" | pixels | promoted, the exception (item 3) |
   | 438857197-1 | 438857197 | 3.659160 | none | `438857197-1-S64`, 0.082 FP | pass, 3.6" | none | promoted |
   | 458290782-1 | 458290782 | 1.931605 | `01343588382-01`, s0103-s0103, on TIC 1343588382 | `458290782-1-S39`, 0.152 FP | fail, 25.7" | secondary, sector_depth, holdout, pixels | noted: off-target source supported, the dip sits on TIC 1343588382 or TIC 458290807; SPOC's TCE on TIC 1343588382 shows an eclipsing binary (weak secondary 23,215 ppm) |

   Ratio k: the row's period times k is the signal's, as the second list defines it, so 173369850-1's TCE is at twice
   the period and 337885456-1's ExoMiner row at half. Novelty is inconclusive as `known_to_spoc` on every row; holdout
   is inconclusive on 241522065-1 and 370977908-1, and neighbours on 322826591-1, 370977908-1, 423100454-1 and
   458290782-1.

   SPOC TCE is the second list's lookup in the catalog snapshot's TCE tables, and for 423100454-1 it misses one:
   SPOC's S12 TCE 01 (14.2069 d) and its DV report are on MAST, but the snapshot's S12 TCE table lacks the row (the
   row's review, finding F5, in [results/vetting/423100454-1](../../results/vetting/423100454-1/dossier.md)).
   - **Promoted on the nine's bar.** 241522065-1, 277774870-1, 370977908-1 and 438857197-1 pass the pixel check and
     fail no check. They passed LEO-Vetter's flux tests in triage, as every second-list row did by the list's
     definition, so these four meet the bar the nine shortlisted signals met in triage, with the promotion standing in
     for novelty.
   - **Noted, not promoted.** 173369850-1, 295140687-1, 322826591-1, 337885456-1 and 458290782-1 each fail the pixel
     check, which kills a second-list row (design, section 4.10), and at least one vet-v3 check besides, so none rests
     on pixels alone (the diagnosis, section 4). They stay as 0013 leaves them: matched to SPOC, not shortlisted.
3. **423100454-1, the exception.** Design 4.10's pixel kill ([0028](0028-outcomes-and-calls.md)) is set aside for this
   row only, because its fail measures a neighbour, not the transit (the diagnosis, sections 2 and 4). In S103, S39 and
   S12 the fits sit 5.7" to 8.7" from the target. In S102 and S65 they jump to 118.6" and 115.7", beside TIC 423100496,
   a star 121" away that varies on its own: in each of those sectors a null image lands on the same point with a larger
   loss. The transit sits at the target in all five sectors (box z at the star 4.7, 5.4, 3.2, 1.9 and 1.5 against 3.7,
   6.6, 3.5, 1.6 and 1.4 expected, in S103, S102, S65, S39 and S12). Pixels is its only fail. Like any pixel record,
   this one says nothing about stars within 15" of the target; the neighbour table's possible hosts from 8.42" out
   (corrected in 0034, which also moves Gaia DR3 5836453499849301760 inside 15", from 16.61" to 14.98") are
   TRICERATOPS's question (the diagnosis, section 2).
   - It gets what a promoted row gets: a dossier, TRICERATOPS, a review whose refuters test this finding, and the
     maintainer's call.
   - It can't pass on this record. Every pass needs a pixel pass (Ruling W; [0028](0028-outcomes-and-calls.md),
     [0032](0032-nearby-binary-triceratops.md)), which the maintainer accepted on 2026-10-22. `calls.problems`
     enforces it for every signal, so a pass would also need the code changed, with its own record. The maintainer's
     answer of 2026-10-22: no change in M3. Any change comes later as a rule for every signal in a new criteria
     version, and only if ground-based photometry clears the star that carries the row's NFPP (its call, in
     [results/vetting/423100454-1](../../results/vetting/423100454-1/dossier.md)).
   - Its pixel fail stays in its record as measured: `pixels.json` and `pixels.png` are the second-list run's,
     unchanged.
4. **The promotions reach the record** in each promoted row's `call.toml`: `promotion` names the SPOC TCE or ExoMiner
   row in the table and the maintainer's reason (`calls.py`; 0028), written at Task 14 with the call. Novelty stays
   inconclusive as `known_to_spoc` (0013), and the promotion stands in for it in the pass bar (0028, bar 2).
5. **The check itself** keeps its weaknesses in M3: `pixels.py` is frozen. The diagnosis's findings for a later version
   (section 4): on hosts brighter than about Tmag 6 the check measures the bleed column; the outcome follows one
   sector picked by quality, which measures how PRF-like the image is, not how much transit it holds, while the
   direction of each sector's fit, which `pixels.json` does not keep, separates a real source from noise; the fit
   roams the whole 21 x 21 pixel cutout, so a variable star anywhere in it can capture the fit, which null images
   expose; and in this data a fit that repeats its sky position across sectors and cameras, with nothing at the target
   in a fixed-position fit, marks a real off-target source.

## Evidence

- [The diagnosis](../../results/benchmarks/pixel-check-diagnosis-2026-10-20.md): every cause, rating and pixel
  number above, read-only analysis outside the pipeline. Its scripts and small outputs:
  [`pixel-check-diagnosis-2026-10-20-scripts.tar.gz`](../../results/benchmarks/pixel-check-diagnosis-2026-10-20-scripts.tar.gz)
  (sha256 `1dc96ca3c1a6ccecc4e47d08bfc9d98d7fe5f337c75fa52c3bec104787e43939`).
- The pixel completeness run's
  [summary.md](../../results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/summary.md) and
  [`pixels.csv`](../../results/benchmarks/20261017T143548Z-benchmark-pixel-completeness-8a2bd96-8e33/pixels.csv): the
  pixel check on the 20 known planets and its four fails.
- The second list's table, `second-list.csv` and `second-list.md` of run
  `20261020T012658Z-vetting-second-list-62882b5-3fca`, not yet under `results/`: each row's checks, pixel check, SPOC
  TCE and ExoMiner row. Each host's Tmag is in its `checks.json` in vetting run
  `20261020T010149Z-vetting-run-62882b5-c3ee`, not yet under `results/` either.
- The triage run's
  [`known_to_spoc.csv`](../../results/triage/20261015T155441Z-triage-7b12e25-3f57/known_to_spoc.csv): the 466 rows,
  with the LEO-Vetter flux outcomes and RUWE that pick the ten.
- [tests/test_calls.py](../../tests/test_calls.py): `test_promotion_stands_in_for_known_to_spoc` (a promotion stands
  in for a `known_to_spoc` novelty on a second-list row only), `test_a_second_list_pass_needs_the_pixel_check_to_pass`
  (a missing, failed or inconclusive `pixels.json` refuses the pass), `test_a_candidate_pass_needs_triages_pixel_pass`
  (Ruling W) and `test_a_kill_may_rest_on_a_failed_pixel_check`.
