# 0038: The published literature record keeps identifiers and open sources' titles; the home directory is scrubbed

- Date: 2026-10-26
- Status: Accepted. Decided by the maintainer on 2026-10-26, on findings P2, R1 and P1 of the M3 milestone review.
  Rulings BM, BR, BT and BW, stated in full where they are cited below, are the M3 build controller's of 2026-10-26,
  made in carrying the decision out, and are put to the maintainer with the fix wave.

## Context

Each vetting record's `literature.json` held what the literature search (decision 0027) read: every NASA ADS hit with
its bibcode, title and DOI, and ExoFOP's target page reduced to its TOIs, CTOIs, comments, planet parameters, imaging
rows and file names. The imaging rows name the observer who uploaded each (`imuser`) and carry their notes (`inotes`),
and the dossiers showed every title. `results/README.md` put all of it under CC BY 4.0. ADS's API terms say "You also
shouldn't redistribute any data you obtain from our services to third-parties" (https://adsabs.github.io/help/terms/,
read by the milestone review), and ExoFOP's data-use guidelines treat data as its provider's property. The repository
was private, so nothing had been redistributed.

The review also found the maintainer's home directory, which names him, in machine paths quoted in the reviews
(`review.json`) and in the dossiers that render them.

## Decision

- **What a published `literature.json` keeps.** Every identifier (bibcode, DOI, arXiv id), each paper's `found_by`,
  each search's query, total, status, error and note, SIMBAD's names, the outcome and its reason, and from ExoFOP the
  planet parameters, the confirmed planets, and the TOI, CTOI and imaging rows, each with only the fields an
  allowlist names (`literature.EXOFOP_FIELDS`, Ruling BW):
  - TOI rows: `ctoi`, `date`, `discovery`, `disp_tess`, `disp_tfop`, `editdisp`, `editpri`, `esm`, `predicted_mass`,
    `predicted_rv`, `pri_1a`, `pri_1b`, `pri_2`, `pri_3`, `pri_4`, `pri_5`, `pri_m`, `sector`, `signal`, `source`,
    `toi`, `toidate1`, `toidate2`, `tsm`;
  - CTOI rows: `ctoi`, `discovery`, `cdisp`, `tdisp`, `cdate`, `ctoi_created`, `editctoipri`, `editctoidisp`,
    `cobid`, `ctag`, `cpri_m`, `cpri_1a`, `cpri_1b`, `cpri_2`, `cpri_3`, `cpri_4`, `cpri_5`: the row's ids,
    dispositions, dates and priorities;
  - imaging rows: `icont`, `idate`, `ifilt`, `igroup`, `iinst`, `imid`, `imobid`, `ipix`, `iplname`, `ipsf`, `itag`,
    `itel`, `itoi`, `itype`.

  The TOI and imaging lists are the fields the 14 published records held less those dropped below, so the
  allowlist changed none of them (the trim, run again, wrote byte-identical files). No published record holds a
  CTOI row; ExoFOP's target pages, read on 2026-10-26 for two stars with CTOIs, give each CTOI row a submitter
  (`cuser`), a group, a candidate name, a paper link and notes beside the fields kept, and those stay out. A field
  not on the list, one ExoFOP adds later among them, is dropped, never published unread, and the record's `trim`
  block names it.
- **What it drops** (`literature.DROPPED`): every title ADS gave; ExoFOP's comments and the same text in its TOI and
  CTOI rows (`notes`, `cnotes`); ExoFOP's file names; each imaging row's `imuser` and `inotes`. The TOI and CTOI rows'
  comment fields are the text the comments list was built from, so they go with it (Ruling BR).
- **Titles only from open sources** (`literature.trim`). A paper's title is the search's own arXiv hit's, else its
  OpenAlex hit's, else its Zenodo hit's; failing those, OpenAlex's record for the paper's DOI, or for a paper with only
  an arXiv id, arXiv's DataCite DOI `10.48550/arxiv.<id>`. Each kept title records its source in `title_source`
  (`arxiv`, `openalex`, `zenodo` or `openalex_doi`). Where none of them has the paper, the title is null and the
  dossier's table shows it blank. Bibcodes stay: 27 of the 123 papers ADS found have neither a DOI nor an arXiv id.
- **The `trim` block.** Each published `literature.json` says what it was cut from: the sha256 of the literature run's
  record (`source_sha256`), this decision (`decision`), the titles run (`titles_run`) and the fields dropped
  (`dropped`).
- **The lookup is a run.** `tess-hunt vetting titles --literature RUN [--production]` asks OpenAlex for the work at
  each DOI a finished literature run's records need, one request at a time through the literature search's HTTP
  client, and writes `titles.json` (by DOI: `ok` with the title, or none when the work has none; `not_found`; `error`)
  into a run directory with its provenance: the literature run, each record it read with its sha256, and the sha256 of
  `titles.json` in its summary. A failed lookup is recorded, never taken for a missing title.
- **Publishing trims.** `vetting publish` takes `--titles RUN`, a titles run made from `--literature`, and refuses a
  record with a `literature.json` without one. It checks that the titles run read this signal's record and that
  `titles.json` is the file the run wrote, refuses a lookup that failed or was never made, and publishes the trimmed
  record with the titles run's provenance as `provenance-titles.json`. The dossier names the titles run among the
  record's runs. Publishing the same runs again changes nothing, as before. Since the review is placed in the record
  by hand, `publish` also refuses a `review.json` that the scrub below would change.
- **The 14 records published before this decision** are trimmed by `tess-hunt vetting trim --name NAME --literature RUN
  --titles RUN`, the narrowest path that changes a published record. It refuses unless the record was published from
  that literature run (`provenance-literature.json` is the run's provenance) and its `literature.json` is the run's file
  for the signal, or already its trim, and refuses a record trimmed with another titles run unless given
  `--replace-titles-run`; then the record's `trim` block names the run it replaced (`replaced_titles_run`), and a later
  trim or `publish` with the new run keeps that name. It writes the trimmed `literature.json` and
  `provenance-titles.json`, scrubs `review.json` (below), and renders `dossier.md` and the vetting README again;
  nothing else in the record changes, and a second run changes nothing. Applied on 2026-10-26 with the literature run
  `20261021T001540Z-vetting-literature-61b5944-07de`, from which all 14 records were published. The first titles run,
  `20261026T155726Z-vetting-titles-0b1deac-1d19`, was made at a commit that the rewrite of the history (below)
  replaced; the backup bundle made before the rewrite keeps that commit. The records were trimmed again the same day
  with `--replace-titles-run` and the titles run `20261026T184940Z-vetting-titles-af322af-9b15`, made at a commit in
  the history, and each names the first run as `replaced_titles_run`. Both runs looked up the same 50 DOIs that the
  literature run's 19 records needed and found a title for each, and no title changed. Of the 14 records' 127 papers,
  9 take their title from the search's own OpenAlex hits, 91 from the lookup, and 27, known only by their bibcodes,
  have none.
- **The home directory is scrubbed (Ruling BM).** One mapping is used everywhere: tess-hunt's own scrub
  (`provenance.scrub`), which writes the data directory as `$TESS_HUNT_DATA` and the home directory as `~`. It covers
  the files first committed at or after the first literature record was published (the publish of 44926986-1 on
  2026-10-22): the 14 `review.json`, changed by `vetting trim` and otherwise left as written; the 14 dossiers, which
  render the review and the call through the same scrub and show a path elsewhere on the machine by its file name
  alone; the review tarballs (`review-scripts.tar.gz`), built with it; and the published review brief
  (`results/vetting/review-brief.md`). Five benchmark notes and three tarballs
  published on 2026-10-20 and 21 stay as published: they were committed no later than cd4e7a2, which with 61b5944 is
  a commit the published records' runs were made at and their provenance names, so a rewrite does not reach them.
  `results/vetting/README.md` says how to read their paths.
- **The maintainer's name is written "the maintainer" (Ruling BT).** The name goes into a generated file only with
  the maintainer's say-so, and the reviews, their scratch files and the review brief name the maintainer in
  places. The same step that rewrites the home directory rewrites the name (`provenance.unname`, after
  `provenance.scrub`): the full name, as `CITATION.cff` gives it, and the given name standing alone become "the
  maintainer" ("The maintainer" opening a sentence); a given name followed by another capitalised word is someone
  else's name and stays. `vetting trim` applies it to `review.json`, the dossier to the review and the call it
  quotes, and the tarballs and the brief were built with it. On 2026-10-26 it changed four `review.json`
  (146282666-1, 164767175-1, 241522065-1, 410399327-1), their dossiers, the brief and 11 files in the tarballs.
- **The history.** The branch's history from the first literature publish is rewritten so that no copy of the
  published record in it keeps the dropped fields, the home directory or the maintainer's name. The review brief and
  the review tarballs are rewritten with it: each copy committed before the name was taken out holds the copy that
  took it out.
- **Licences** (`results/README.md`, `ACKNOWLEDGEMENTS.md`, `README.md`, `CITATION.cff`). ExoFOP's rows stay under
  ExoFOP's terms, not CC BY 4.0. The titles come from arXiv's, OpenAlex's and Zenodo's metadata, which each source's
  page puts under CC0. Bibcodes, DOIs and arXiv ids are identifiers.

## Limitations

- A paper none of the open sources titles shows only its identifier; the reader looks it up by its bibcode or DOI.
- OpenAlex's title for a DOI can differ in wording or case from the journal's.
- The records name no ExoFOP observer; the contrast curves TRICERATOPS read and the imaging rows are credited to their
  contributors through ExoFOP's target page, as ExoFOP's guidelines ask.
- A draft dossier (`vetting dossier`) renders the run's untrimmed record, ADS's titles included, and says so; drafts
  are never committed.

## Evidence

- [tests/test_literature.py](../../tests/test_literature.py):
  `test_trim_keeps_every_identifier_and_takes_titles_only_from_open_sources` (ADS's titles, ExoFOP's comments, files,
  observers and notes out, and a CTOI row's submitter and an unknown user field, and an imaging row's unknown field,
  dropped and named in `trim`; identifiers, `found_by`, every search's query, total and status, the ExoFOP rows'
  allowlisted fields and the outcome kept; a title from arXiv, one from OpenAlex's lookup, none for a paper no open
  source titles; the sha256 and the titles run recorded; a failed or missing lookup refused),
  `test_openalex_title_is_looked_up_by_doi` (a recorded answer, a work without a title, a 404 and a 429, the DOI quoted
  into the path) and `test_vetting_titles_looks_up_only_the_papers_no_open_source_titles` (one lookup for two signals on
  a star, the run's provenance and `titles.json`, a changed literature record refused).
- [tests/test_provenance.py](../../tests/test_provenance.py):
  `test_unname_writes_the_maintainers_name_as_the_maintainer` (the full name across a line break, the given name
  alone, possessive and opening a sentence, other people's names kept, nothing without `CITATION.cff`'s names).
- [tests/test_dossier.py](../../tests/test_dossier.py): `test_publish_refuses_without_a_call` (a literature record
  needs `--titles`; the published record is the trim of the run's),
  `test_publish_refuses_a_review_naming_the_home_directory_or_the_maintainer` (the home directory, the data
  directory, the maintainer's name: each refused with nothing written; the scrubbed text publishes), and
  `test_trim_applies_decision_0038_to_a_record_published_before_it` (only `literature.json`,
  `provenance-titles.json`, `review.json`, the dossier and the README change; `review.json` only where it names the
  home and data directories or the maintainer; the dossier's titles only from open sources, blank where none has
  the paper, and no ExoFOP comment text; a second run changes nothing; another titles run refused, and with
  `--replace-titles-run` taken and the replaced run named, a later trim changing nothing; publishing the same runs
  with the new titles run rendering the dossier again and changing nothing else, and with the replaced run refused; a
  literature record that is neither the run's nor its trim refused),
  `test_the_dossier_shows_no_machine_path_from_the_review_or_the_call`.
