# 0039: A held signal may go to the DDT ask when 2-min data would supply its deciding evidence

- Date: 2026-10-27
- Status: Accepted. Made in the M4 design and approved by the maintainer with it on 2026-10-27; each ask stays the
  maintainer's call. The proposal's form follows rulings the M4 build's controller made on 2026-10-27, stated in full
  under Decision and put to the maintainer with the proposal: the target list in the TESS office's own shape, its
  proposer and creator lines left as the template's placeholders, the proposal as plain Markdown for want of a LaTeX
  tool, and the template's two questions answered from the record and `facts.toml` alone. Amended 2026-10-28 at the
  maintainer's request that it read as a proposal of its kind: it is written in the first person singular, states
  the record's values in plain words, quotes no review text, shows the record's folded-transit plot, and says the
  code and text were written with LLM assistance; the target list's subject and keywords drop project terms.

## Context

Decision [0028](0028-outcomes-and-calls.md) (with [0026](0026-triceratops.md)) sends a passed signal to the DDT ask
for 2-min data when its next TESS look is full-frame images only, and a held one only on the maintainer's call and
only when the deciding evidence is the transit's shape. A hold on blending does not go, since 2-min data come through
the same 21" pixels. That reason still holds.

The rule leaves out a case M4 found: a hold that needs a season the public products won't deliver. Every held star
with a sector ahead had only FFI data in the sectors fetched, except 423100454 in S12, and the sectors ahead are its
last through S134 (tess-point). QLP on MAST stops at a partial S105, with nothing for S106 or later, and has not
redelivered S99 to S104, whose timestamps are suspect ([0022](0022-vet-without-timing-suspect-sectors.md));
TESS-SPOC's FFI light curves are on MAST only through S85 ([facts.toml](../../results/ddt/241522065-1/facts.toml),
each fact with its source and the date it was read, 2026-10-27). So for these stars the sectors ahead become light
curves only through QLP, which has stalled, through 2-min data, which need a DDT ask, or through the project's own FFI
photometry, which the spec leaves out of scope.

241522065-1 is held only for a third season ([its call](../../results/vetting/241522065-1/call.toml)): its two
seasons with trustworthy timestamps can't test each other, so the held-out check is inconclusive. S112 to S114 would
give each season two training seasons. The held-out check compares depths only within a product family
([0023](0023-product-families.md)), and the star's record has training data only in the PDCSAP family (S38, S64 and
S65, where fetch took TESS-SPOC's light curves over QLP's), so a QLP season could not test the prediction either; with
TESS-SPOC's light curves on MAST only through S85, only SPOC 2-min data can.

## Decision

- **The rule.** A held signal may go to the DDT ask, on the maintainer's call each time, when 2-min data would supply
  its deciding evidence: the transit's shape, or a season no public light curve will otherwise cover. A hold on
  blending still does not go. A passed signal goes as 0028 says, and a killed one does not.
- **"No public light curve will otherwise cover"** means that every product able to test the season (a family with
  training data, 0023) stops before it or has stalled, as a dated `facts.toml` beside the proposal shows.
- **The dossier's DDT note** for a held call states this rule and links here (`dossier._ddt`). Published records never
  change (0028), so the published dossiers keep the note they were published with; the new wording shows in dossiers
  rendered after this decision.
- **Which signals qualify now:** only 241522065-1. Of the other five held signals with a sector ahead:
  - 103312990-1 (S110 to S113): its season would give the held-out check a second testable season, but the hold also
    rests on a nearby eclipsing binary that is not excluded and on an unresolved companion, which 2-min data from the
    same pixels don't decide. And it has QLP training data, so a QLP season could test its prediction if QLP
    resumed; 241522065-1's record has none (fetch took TESS-SPOC for S38, S64 and S65).
  - 296819076-1 (S114): held on blending: the transit's loss may sit on stars west of the target, which takes
    seeing-limited photometry. S114 would also give its held-out check a testable season, but a hold on blending does
    not go.
  - 399023421-1 (S112 to S114): held on blending: three faint background stars that TESS's pixels can't separate from
    the target.
  - 423100454-1 (S113): held on blending: one neighbouring dwarf carries almost all of TRICERATOPS's NFPP, and a pass
    also needs two recorded decisions.
  - 438857197-1 (S112, S114): held on a grazing body that needs radial velocities, a possible bound companion that
    needs imaging and multi-band photometry, and neighbours that need seeing-limited photometry; its call says the
    two sectors sharpen the shape but decide none of these.
- **The proposal** is rendered, never typed: `tess-hunt ddt render --record results/vetting/<name> --template ...
  --facts ... --sectors ... --out results/ddt/<name>` fills `proposal.template.md` with `substitute` from the record
  (`checks.json`, `triceratops.json`, `literature.json` for the star's names, `call.toml`, `review.json`,
  `provenance-checks.json` for the search run's date), from the criteria files the record's runs read
  (`provenance-checks.json` names the vetting run's, for the held-out check's minimum training seasons;
  `provenance-triceratops.json` the TRICERATOPS run's, for its pass bars; each checked against the sha256 the run
  recorded), and from `facts.toml`. A value the record lacks, or holds as null, NaN or an empty list, raises rather
  than rendering (`docs/design.md`, section 5.5). It quotes no review text; a review's text a proposal does quote (a
  finding's claim, and phrases from its evidence, each given only when `review.json` holds it word for word) is
  quoted word for word and says so ([0037](0037-quoted-text-in-the-dossier.md)). It leaves out Gaia DR3 data, the
  star's DR3 source id included, so `results/ddt/` stays CC BY 4.0 whole.
- **The proposal's form** (the controller's rulings of 2026-10-27, above). It follows the DDT template's sections (DDT
  Justification, Scientific Justification, Target Justification and Feasibility, References) as plain Markdown, since
  no LaTeX or pandoc is installed; the maintainer pastes it into the template. Its author line is a placeholder. The
  template asks why the targets can't wait for the next Guest Investigator call and why they weren't in the previous
  one: the proposal answers from the record (the date of the search that found the signal) and from `facts.toml` (the
  sectors are the star's last through S134, and the star is on none of the 2-min or 20-s target lists ahead), and
  names no Guest Investigator deadline, which could not be read from its source. The target list (`targets.csv`)
  follows the office's template: its `#` header block, the `# tic,priority,keywords` line and one row at priority
  1.0, with CRLF line ends; the DDT PI, "Created by" and
  "Created on" lines keep the template's placeholders for the maintainer to fill when sending.

## Limitations

- The ask is public once sent: the DDT page lists proposals, and approved DDT observations have no proprietary period.
- It names the maintainer as PI. Sending it is the maintainer's act, after reading it; nothing in the repository
  contacts anyone.
- Whether it is taken is the TESS team's decision, not ours. S112's final 2-min target list shows it.
- Whether 2-min data would supply a hold's deciding evidence is read from the call by the maintainer; the code can't
  classify it, as 0028 already says of the shape-or-blending question.
- "Will otherwise cover" is true only as of the date `facts.toml` was read. QLP may resume or redeliver; for
  241522065-1 a QLP season could still lift the hold by making its old seasons testable, while the new season itself
  stays untested.

## Evidence

- [tests/test_dossier.py](../../tests/test_dossier.py): `test_ddt_note_follows_0039`,
  `test_seen_utc_matches_the_dossier` (every published windows table renders unchanged with the time from Earth moved
  to `predict.seen_utc`).
- [tests/test_ddt.py](../../tests/test_ddt.py): `test_values_come_from_the_record` (each number as the published
  dossier shows it, the windows of the asked sectors and none other, the sector dates by the sectors asked, the facts
  and their sources, the review's claims word for word, no Gaia DR3 source id), `test_render_fails_on_a_missing_value`
  (no `triceratops.json`, a null `fit_prior`, a NaN, an empty list, a sentence that holds only for some records, an
  unfilled placeholder), `test_criteria_come_from_the_files_the_runs_read` (the TRICERATOPS run's bars, a run naming
  no criteria file, a changed file), `test_the_review_is_quoted_as_the_dossier_quotes_it`, `test_targets_csv`,
  `test_ddt_render_writes_the_proposal_and_the_target_list`, `test_the_committed_proposal_is_its_render` (the
  committed files are exactly the render, quote no finding, use no internal labels, and hold no machine
  path, no one's name and no Gaia DR3 source id).
- [results/ddt/241522065-1/](../../results/ddt/241522065-1/): `facts.toml`, `proposal.template.md`, the rendered
  `proposal.md` and `targets.csv`.
- The six calls: [103312990-1](../../results/vetting/103312990-1/call.toml),
  [241522065-1](../../results/vetting/241522065-1/call.toml),
  [296819076-1](../../results/vetting/296819076-1/call.toml),
  [399023421-1](../../results/vetting/399023421-1/call.toml),
  [423100454-1](../../results/vetting/423100454-1/call.toml),
  [438857197-1](../../results/vetting/438857197-1/call.toml).
