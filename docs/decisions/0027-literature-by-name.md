# 0027: Literature by every name, NASA ADS and ExoFOP; a search that is not complete is inconclusive

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design)

## Context

Triage searched arXiv, OpenAlex and Zenodo for the phrase "TIC n" (decision 0013). Papers rarely name a star by its
TIC number: TIC 164767175, shortlisted in M2, is HIP 8152 (TOI-266), whose two planets Akana Murphy et al. 2023
(AJ 166, 153) published under that name, and triage's search did not find them. 0013 left NASA ADS, which needs a
token, to a search by hand. The M3 design (section 4.6) searches by every name papers use, adds ADS's object search and
ExoFOP's target page, and records whether the search is complete, so that a search a rate limit cut short never reads
as "nothing published".

## Decision

- **Names.** `literature.simbad_names` asks SIMBAD's TAP service (keyless) for every identifier of the object SIMBAD
  knows as "TIC n": a self-join of the `ident` table on `oidref`, in JSON. `literature.searchable` keeps the forms in
  `[literature] forms` (TIC, TOI, HD, HIP, Gaia DR3, 2MASS, TYC and WDS), with whitespace normalised ("HD  14989"
  becomes "HD 14989"). Other forms (BD, CPD, GSC, HIC, PPM, SAO, RAVE, Gaia DR1 and DR2 and the like) stay in the
  record as SIMBAD gave them and are not searched. Where SIMBAD gave no name of a form (it failed, or does not know the
  star), the TIC name, the Gaia DR3 name from the targets row's `dr3_source_id` and the 2MASS name from a `twomass`
  column are added. A source id that is not an integer is left out: one rounded through a float names another star.
- **Searches.** Each name goes to arXiv (`all:"name"`), OpenAlex (`fulltext.search:"name"`) and Zenodo (`"name"`), as
  triage's phrase search did. ADS takes one query, `object:"TIC n"`, which resolves the star's aliases through SIMBAD
  and so covers the forms the full-text searches skip. ExoFOP's target JSON is read live.
- **Paging.** Each search pages until it holds every hit its service reports, at the most each service serves a page
  without a key (Zenodo refuses more than 25). A search whose reported total exceeds `[literature] max_hits` (200) stops
  at that page and is recorded `too_broad` with the total and no hits: complete, not incomplete, since ADS's object
  search stands for it. A page that comes back empty short of the reported total (arXiv does this now and then) is an
  error, not the end of the hits.
- **Rate limits and failures.** arXiv gets one request per `[literature] arxiv_pause_s` (3.0 s), failed ones included.
  A dropped connection or a server error (5xx) is tried three times, 10 s times the attempt apart. Any other status,
  429 included (arXiv's rate limit, OpenAlex's daily cap of about 100 full-text searches without a key), is not
  retried: no retry's wait outlasts it. Every search records `{status, hits, total, error}` with status `ok`,
  `too_broad`, `error` or `not_searched`. An error names the service and the HTTP status code, or the exception's type
  alone, never a response body or a request header.
- **The ADS token.** The maintainer's NASA ADS token is the project's only secret. `vetting literature` reads it from
  `ADS_API_TOKEN` at run time and passes it down; it is sent only as the `Authorization: Bearer` header of ADS requests
  and never reaches the code, the criteria, a run directory, the provenance, a log line, an exception message or CI.
  The provenance records only `ads_searched` (true or false). Without the token, ADS is recorded `not_searched`. The
  spec's "No secrets" line (`docs/design.md`, section 6.2) gains a sentence for it in M3's spec amendments.
- **ExoFOP.** The target JSON is reduced to its TOIs and CTOIs (each entry whole), their comments (a TOI's `notes`, a
  CTOI's `cnotes`), the confirmed planets ExoFOP lists for the star, the imaging rows and the names of the files. A
  failed read is recorded with the same error rule.
- **The check.** `literature.literature_check` (`"literature"`) is inconclusive when SIMBAD, ExoFOP or any search
  failed or was not made (a source missing from the record counts as not made), with each listed: a rate-limited
  search is not a negative. Otherwise it passes, "complete: N hits to screen", with the hits of every `ok` search
  merged into one entry per paper: hits that share a DOI, an arXiv id or a title (lowercase letters and digits) are
  the same paper, and an arXiv DOI (10.48550/arXiv.X) gives the arXiv id X. Each entry lists the searches that found
  it. Too-broad searches are listed with their totals.
- **It never fails.** This is an exception to the spec's rule that every check ships a negative control that makes it
  fail (`docs/design.md`, section 5.2), as for `signal_present` (0017) and the neighbour table (0025). A hit is a paper
  that names the star, not one that reports this signal: a star with known planets or a known variability can still
  host a new signal, and a paper can name the star for an unrelated reason. Deciding that takes reading, which is the
  review's "real and new" lens and the maintainer's (M3 design, section 4.6). What the check guards is that an
  incomplete search can't pass, and the "passed" bar requires a pass (section 4.9). Its control is that the search
  finds the paper triage missed: `test_hip_8152_finds_akana_murphy_2023` (M3 design, section 4.3).
- **The run.** `tess-hunt vetting literature --run VETTING_RUN [--signals NAME ...] [--resume-from RUN]` refuses what
  the TRICERATOPS stage refuses: an unfinished or evidence-only vetting run, a `--criteria-search` or `--criteria-vet`
  whose sha256 differs from the vetting run's, and a non-production vetting run under `--production`. It takes each
  star's targets row from the vetting run's `checks.json` and searches one star at a time (arXiv's pace and OpenAlex's
  cap are per client), once for all of a star's signals, and writes `signals/<name>/literature.json`: the signal, the
  vetting run, the whole search (SIMBAD's answer, the names searched, every search, ExoFOP) and the check. The
  provenance's summary records each file's sha256.
- **Resuming.** With `--resume-from RUN`, an earlier finished literature run on the same criteria (a production run
  for a production run) gives its complete searches (`ok` and `too_broad`) for the same star, source and name; each
  is kept with `from_run` naming the run that made it, and only the rest are made again. Each earlier file is checked
  against the sha256 its run recorded and is recorded as an input. SIMBAD and ExoFOP are read again every run.

## Limitations

- arXiv's API searches titles, abstracts, comments and authors, not the body of a paper. OpenAlex searches full text
  only for works whose text it holds, and stems its search, so a name like "TOI-266" also matches unrelated text; the
  hits are read, so the noise costs reading time only. On 2026-10-17, a run by hand for TIC 164767175 without the
  token found Akana Murphy et al. 2023 by none of the searched names in arXiv, OpenAlex or Zenodo, while ExoFOP's page
  listed HIP 8152 b and c as confirmed planets and named them in the TOI comments. Without the token, the literature
  control rests on ADS's object search, and the record is inconclusive in any case.
- SIMBAD is asked by the TIC identifier. A star SIMBAD holds without that identifier gets only the names from the
  targets row, and ADS's object search for the TIC may not resolve it either.
- The targets tables M2 built carry no 2MASS ID, and the control tables carry no `dr3_source_id`, so for a star SIMBAD
  lacks, the search may run on the TIC name alone.
- If ADS's object search itself is too broad, nothing stands for it. It is recorded with its total, and a star with
  that many papers is one the review reads closely anyway.
- A resumed search is kept as it was found, whatever its age; `from_run` names the run, and so the date, it came from.

## Evidence

- [tests/test_literature.py](../../tests/test_literature.py):
  - `test_simbad_names_reads_every_identifier` (SIMBAD's identifiers as served; an unknown star is an empty list; a
    server error is retried and raises; a bad request is recorded, not retried).
  - `test_searchable_forms_and_fallback_names` (the forms kept from SIMBAD's identifiers for TIC 164767175, whitespace
    normalised; the TIC, Gaia DR3 and 2MASS names from the targets row when SIMBAD gave none; a missing or float
    source id adds nothing).
  - `test_paging_stops_at_max_hits_as_too_broad` (two Zenodo pages for 30 hits; a total over `max_hits` stops at the
    first page as too broad, and the check still passes).
  - `test_a_failed_source_leaves_the_search_incomplete` (OpenAlex's 429 is not retried, a server error is tried three
    times, arXiv paced; an empty page short of the total is an error; a failed SIMBAD or ExoFOP, a missing source, or
    an empty record is inconclusive).
  - `test_ads_without_a_token_is_not_searched` (no request to ADS, inconclusive; with the token, the object search by
    TIC with the bearer header).
  - `test_the_token_never_reaches_the_record` (an ADS that echoes the request's headers in a 401 body or a 200 body, or
    raises naming them: no token text in the record or the check).
  - `test_exofop_record_keeps_comments_and_imaging`, `test_hits_are_deduplicated_by_doi_arxiv_id_or_title`.
  - `test_vetting_literature_writes_one_record_per_signal`, `test_resume_fills_only_what_the_earlier_run_left_incomplete`
    (only the incomplete searches are made again; no file of the run holds the token; a changed earlier record is
    refused), `test_literature_refuses_what_it_cannot_stand_behind`, `test_literature_refuses_an_evidence_only_run`.
- The network test `test_hip_8152_finds_akana_murphy_2023` (skipped without `ADS_API_TOKEN`): SIMBAD names TIC
  164767175 HIP 8152, and ADS's object search or arXiv by HIP 8152 returns Akana Murphy et al. 2023 (arXiv
  2306.16587).
