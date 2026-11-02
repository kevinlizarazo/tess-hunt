# Re-vet review brief: listings after our claim (decision 0042)

This brief adds to [review-brief.md](review-brief.md) for the review of a re-vet, a new version `r<N>` of a signal's
record ([decision 0041](../../docs/decisions/0041-revets-as-versions.md)). Everything in that brief holds. This one
covers a single question for the "real and new" lens: how to read a TOI or CTOI listed after the signal was made
public ([decision 0042](../../docs/decisions/0042-listings-after-our-claim.md)). It applies whenever the version's
record holds `claims.json`.

## What you have

The workflow names the version's draft record and its runs. In the record:
- `claims.json`: the signal's claim (the day it was first public and the public record that shows it, from
  `results/claims.toml`), each TOI or CTOI row on the star that decision 0042 excepted, with the day ExoFOP first
  listed it and its dispositions, each row kept as known with the reason, and `novelty`, the novelty check run again
  without the excepted rows.
- `checks.json`: novelty's own result. It still fails on an excepted listing. That is expected, and the dossier says
  so under "Real and new?", one sentence per excepted listing.
- `literature.json`: ExoFOP's rows for the star as the version's literature run read them, which `claims.json` was
  sorted from.
- `provenance-claims.json`: the claims run, with the vetting run, literature run, catalog snapshot and claims file it
  read.

## The rule

A TOI or CTOI does not make the signal known only when all four hold:
1. it is on the signal's own star, the same TIC;
2. it is an ExoFOP TOI or CTOI that the version's literature run found in ExoFOP's record for the star, with the day
   it was first listed (`toidate1` for a TOI, `ctoi_created` for a CTOI);
3. that day is after the signal's claim date. Strictly: a listing made on the claim day counts as known;
4. each of ExoFOP's dispositions for it is PC or empty (`disp_tess` and `disp_tfop` for a TOI, `cdisp` and `tdisp`
   for a CTOI).

Everything else counts as known, as it did before decision 0042: a listing on a neighbour at the same period, a TOI
or CTOI with any other disposition, an archive planet (one others confirmed after our claim included), a row from any
other source (eumemic, RAVEN, Zenodo records and the rest), a SPOC TCE or ExoMiner row, a listing whose first-listed
day can't be read or that ExoFOP's record lacks, lists more than once or gives no disposition field for, every row
when ExoFOP's record was not read, and every row of a signal with no claim. When unsure, a listing counts as known.

## What to test

- Each excepted listing against the four conditions, from `literature.json` and `results/claims.toml`, not from
  `claims.json` alone: the TIC, the first-listed day, the dispositions and the claim date.
- ExoFOP's target page for the star, read live: a disposition given since the literature run (decision 0042 reads the
  dispositions as that run read them), a listing under another name, or a listing on the star from before the claim.
- The claim: the public record it names should show the signal on that day. The four claims that name the repository
  rest on the maintainer's statement, a limitation decision 0042 records; that alone is not a finding.
- The rerun: `novelty` in `claims.json` should follow from the snapshot without the excepted rows, and no row it kept
  should make the signal known.
- What an excepted listing adds. It does not make the signal known, but it is someone else's evidence about the same
  dip: its period, depth and any later disposition can bear on the other two lenses.

## Ratings

As in the brief, with these meanings here:
- **kill:** a listing `claims.json` excepted fails one of the four conditions, or a listing before the claim holds the
  signal: the signal is known. Name the condition and show the evidence. This is also a finding that a check is
  wrong, so it goes to a decision record.
- **hold:** the public data can't say whether one of the four conditions holds. Name what would decide it.
- **note:** anything else a listing shows that is worth the maintainer's eye.

The refuters test each kill or hold finding against the four conditions above as well as the brief's rules.
