# 0037: The dossier quotes the review and the call; numbers in quoted text are their authors'

- Date: 2026-10-26
- Status: Accepted. Decided by the maintainer on 2026-10-26, on finding R2 of the M3 milestone review.

## Context

The design (section 5.5) says no number in a dossier is typed by hand or copied from an agent's summary. M3's dossiers
render two kinds of text word for word: the adversarial review (`review.json`), written by review agents, and the
maintainer's call (`call.toml`). Both hold numbers: the reviews' measurements, and in the calls phrases such as "11 to
14 arcseconds away" (438857197-1) or "precise to about 50 ppm per transit" (164767175-1). Decision 0028 and
`results/README.md` also said `call.toml` "holds no numbers", which is untrue. Every number in that text the
milestone review checked against its record matched but one: 44926986-1's review gives a flux ratio of 0.359 where
the magnitudes it quotes give 0.358.

Two ways out were put to the maintainer: allow quoted, attributed text in a dossier and say which parts are quoted,
or make the call loader refuse digits, which would need new calls for the 14 published signals.

## Decision

- **Section 5.5 is amended** to allow quoted, attributed text. A dossier renders every number of its own from the run
  files beside it. The review and the call are quoted word for word: their numbers are their authors', not rendered
  from the runs, and the code does not check them.
- **The dossier says so.** Its status line says the review and the call are quoted, not rendered, and each of the two
  sections opens with what it quotes: the review "as the reviewer and the refuters wrote it", the call as "the
  maintainer's words" (`dossier.render_review`, `dossier._call`).
- **The published calls stay as they are.** Decision 0028 and `results/README.md` no longer say a call holds no
  numbers.
- **A slip in quoted text is noted beside it, never edited in it.** The record may hold `review-notes.toml`, the
  maintainer's notes on the review, each naming the finding it sits beside, with its date and text:

  ```toml
  [[note]]
  finding = "F2"
  date = 2026-10-26
  text = "..."
  ```

  `calls.load_notes` refuses any other key, a finding the review lacks, a date that is not a TOML date and an empty
  note, and the dossier renders each note under its finding as the maintainer's, dated. `vetting dossier` keeps the
  file in a draft as it keeps the review and the call. 44926986-1's note says that the magnitudes give 0.358, and
  that the call does not rest on the ratio: F2 uses it to check that the depths add up, and the target's share of the
  pair's light is 0.736 at either value, while the kill rests on TRICERATOPS's NFPP and on novelty.

## Limitations

- No code checks a number in quoted text against the record. A slip is found by reading, as the milestone review
  found this one.
- A note is the maintainer's text too, so its numbers are quoted as well.

## Evidence

- [tests/test_calls.py](../../tests/test_calls.py): `test_notes_on_the_review_sit_beside_their_finding`,
  `test_a_notes_file_that_breaks_the_schema_is_refused` (a finding the review lacks, a date that is a string, an
  extra key, an empty note, an unknown table).
- [tests/test_dossier.py](../../tests/test_dossier.py):
  `test_the_review_and_the_call_are_quoted_with_the_maintainers_notes` (both sections open by saying what they
  quote, the status line says so, the note sits under its finding after the refuters, and a draft made again keeps
  the notes file).
- [results/vetting/44926986-1/review-notes.toml](../../results/vetting/44926986-1/review-notes.toml).
