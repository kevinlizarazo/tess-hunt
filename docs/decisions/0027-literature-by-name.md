# 0027: Literature by every name, NASA ADS and ExoFOP; a search that is not complete is inconclusive

- Date: 2026-10-17
- Status: Accepted (approved by the maintainer in the M3 design); amended 2026-10-19: ADS's object query goes through
  ADS's object service, since the search endpoint refuses the `object:` field

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
  star), the TIC name and the Gaia DR3 name from the targets row's `dr3_source_id` are added. A source id that is not
  an integer is left out: one rounded through a float names another star. The targets tables carry no 2MASS ID, so a
  2MASS name comes from SIMBAD only.
- **Searches.** Each name goes to arXiv (`all:"name"`), OpenAlex (`fulltext.search:"name"`) and Zenodo (`"name"`), as
  triage's phrase search did. ADS takes one query, `object:"TIC n"`, translated by ADS's object service (a POST to
  `/v1/objects/query` with `{"query": ["object:\"TIC n\""]}`), which resolves the star through SIMBAD and NED. The
  service returns `((=abs:"TIC n" OR simbid:"<SIMBAD id>" OR nedid:"<NED id>") database:astronomy)`, and ADS's
  search pages with it; the translation is made once per star. Within ADS's astronomy collection, that query finds
  the papers SIMBAD or NED tag with the star, under whatever name they use, and the papers whose abstract, title or
  keywords hold the phrase "TIC n". The tagged papers cover the forms the full-text searches skip. The plan sent
  `object:"TIC n"` straight to the search endpoint, which on 2026-10-19 answered HTTP 400 (`undefined field object`);
  ADS's documentation (adsabs-dev-api, `openapi/services/objects.yaml`) gives the object service for expanding an
  object query. The record keeps the translated query and whether SIMBAD or NED resolved the star (an id other than
  "0"). The object service writes "0" for a star a catalog does not hold and also when its own lookup in that catalog
  failed (adsabs/object_service, `get_object_translations`). It asks SIMBAD for "TIC n", the identifier
  `literature.simbad_names` asks SIMBAD's TAP service for, so where the record's SIMBAD answer lists names for the
  star and the query has `simbid:"0"`, ADS's lookup failed: ADS's search is recorded `error` without being made, the
  check is inconclusive and a resumed run asks again. A resumed run also asks ADS again where the earlier answer was
  not resolved through SIMBAD and SIMBAD's answer now lists names for the star (the earlier run's SIMBAD answer failed
  or lacked the star). Where neither catalog resolved the star, ADS searched only the phrase, and the record, the
  check's evidence (`notes`, not the reason) and the dossier say so. Its hits still count and the search is not
  inconclusive for it: the by-name searches cover the star's other names, unless one of them was too broad (below). A
  failed translation, or a 200 without a query (the service answers its own errors with a 200), is ADS's search
  failing. ExoFOP's target JSON is read live.
- **Paging.** Each search pages until it holds every hit its service reports, at the most each service serves a page
  without a key (Zenodo refuses more than 25). A search whose reported total exceeds `[literature] max_hits` (200) stops
  at that page and is recorded `too_broad` with the total and no hits. For a by-name search that is complete, not
  incomplete, since ADS's object search stands for it, but only where a catalog resolved the star: where ADS searched
  the TIC's phrase alone, a too-broad by-name search leaves the search incomplete. Nothing stands for ADS's own, so a
  too-broad ADS search leaves the search incomplete (below). A page that comes back empty short of the reported total
  (arXiv does this now and then) is an error, not the end of the hits.
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
  CTOI's `cnotes`), the confirmed planets ExoFOP lists for the star, its planet parameters (each row's provenance
  heading, name, TOI, period, epoch, duration and disposition), the imaging rows and the names of the files. The TOI
  and CTOI entries carry no period; the planet parameters do, and the "passed" bar compares them with the signal's
  (decision 0028). A failed read, or a page without the planet parameters, is recorded with the same error rule.
- **The check.** `literature.literature_check` (`"literature"`) is inconclusive when SIMBAD, ExoFOP or any search
  failed or was not made (a source missing from the record counts as not made), when ADS's object search was too
  broad, or when a by-name search was too broad for a star ADS searched by its phrase alone, with each listed: a
  rate-limited search is not a negative, and with ADS too broad no search covers the by-name searches it stands for,
  so even a record of too-broad searches only (no hit left to read) can't pass.
  Otherwise it passes, "complete: N hits to screen", with the hits of every `ok` search
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
  for a production run) gives its answered searches (`ok` and `too_broad`) for the same star, source and name; each
  is kept with `from_run` naming the run that made it, and only the rest are made again. An ADS answer not resolved
  through SIMBAD is made again too where SIMBAD's answer now lists names for the star (Searches, above). Each earlier
  file is checked against the sha256 its run recorded and is recorded as an input. SIMBAD and ExoFOP are read again
  every run.

## Limitations

- arXiv's API searches titles, abstracts, comments and authors, not the body of a paper. OpenAlex searches full text
  only for works whose text it holds, and stems its search, so a name like "TOI-266" also matches unrelated text; the
  hits are read, so the noise costs reading time only. On 2026-10-17, a run by hand for TIC 164767175 without the
  token found Akana Murphy et al. 2023 by none of the searched names in arXiv, OpenAlex or Zenodo, while ExoFOP's page
  listed HIP 8152 b and c as confirmed planets and named them in the TOI comments. Without the token, the literature
  control rests on ADS's object search, and the record is inconclusive in any case.
- SIMBAD is asked by the TIC identifier. A star SIMBAD holds without that identifier gets only the names from the
  targets row, and ADS's object search for the TIC may not resolve it either.
- A NED "0" from ADS's object service can't be told from a failed NED lookup on ADS's side for any star. A SIMBAD
  "0" can't be told from a failed lookup where SIMBAD does not know the star or SIMBAD's own answer failed (with
  SIMBAD's answer failed, the search is incomplete anyway). A star is searched by its phrase alone only when both ids
  are "0".
- A mismatch that never clears, ADS never resolving a star whose SIMBAD answer lists names, keeps the star's
  literature search inconclusive on every resume. The way out is the maintainer's call, recorded with the signal.
- The control tables carry no `dr3_source_id`, so for a star SIMBAD lacks, the search may run on the TIC name alone.
- A star ADS lists more than `max_hits` papers for never gets a complete search under vet-v3, so its signal can't be
  passed (M3 design, section 4.9) until the maintainer reads ADS for it by hand and a decision record says how that
  counts, or `max_hits` changes through one. A resumed run asks ADS again only if the earlier answer failed or SIMBAD
  now knows a star the earlier answer was not resolved through; the same criteria give the same too-broad answer.
- A resumed search is kept as it was found, whatever its age; `from_run` names the run, and so the date, it came from.

## Evidence

- [tests/test_literature.py](../../tests/test_literature.py):
  - `test_simbad_names_reads_every_identifier` (SIMBAD's identifiers as served; an unknown star is an empty list; a
    server error is retried and raises; a bad request is recorded, not retried).
  - `test_searchable_forms_and_fallback_names` (the forms kept from SIMBAD's identifiers for TIC 164767175, whitespace
    normalised; the TIC and Gaia DR3 names from the targets row when SIMBAD gave none; a missing or float source id
    adds nothing).
  - `test_paging_stops_at_max_hits_as_too_broad` (two Zenodo pages for 30 hits; a total over `max_hits` stops at the
    first page as too broad, and the check still passes).
  - `test_ads_too_broad_leaves_the_search_incomplete` (every search too broad, ADS's included: inconclusive, with ADS
    listed and nothing standing for it).
  - `test_a_failed_source_leaves_the_search_incomplete` (OpenAlex's 429 is not retried, a server error is tried three
    times, arXiv paced; an empty page short of the total is an error; a failed SIMBAD or ExoFOP, a missing source, or
    an empty record is inconclusive).
  - `test_ads_without_a_token_is_not_searched` (no request to ADS, inconclusive; with the token, the object service's
    POST body, the search paging with the translated query, the bearer header on both, and the query and the
    catalogs that resolved the star in the record).
  - `test_a_star_no_catalog_resolves_is_searched_by_its_phrase` (ids "0" from both catalogs for a star SIMBAD does not
    know: the record and the check's `notes` say ADS searched only the phrase, the reason does not, and the search
    still passes); `test_real_and_new_says_when_ads_searched_only_the_phrase` in `tests/test_dossier.py` (the
    dossier's line).
  - `test_an_unresolved_star_leaves_a_too_broad_name_uncovered` (a too-broad by-name search passes where ADS's search
    was resolved through SIMBAD, and is incomplete where ADS searched the phrase alone).
  - `test_ads_not_resolving_a_star_simbad_knows_is_ads_failing` (SIMBAD names the star, ADS's query has
    `simbid:"0"`: `error`, no search made, inconclusive; with SIMBAD's own answer failed, the phrase is searched) and
    `test_resume_asks_ads_again_after_its_lookup_failed` (a resumed run makes only ADS's search again, and it passes).
  - `test_resume_asks_ads_again_once_simbad_knows_the_star` (a phrase-only answer from a run whose SIMBAD answer
    failed is not kept once SIMBAD names the star: ADS is asked again, a "0" again is `error` and inconclusive, and a
    working lookup passes).
  - `test_a_failed_translation_is_ads_failing` (the object service's HTTP 400, or a 200 without a query: ADS recorded
    `error`, the search never made, no token text in the record).
  - `test_the_token_never_reaches_the_record` (the object service or the search echoes the request's headers in a 401
    body or a 200 body, or raises naming them: no token text in the record or the check).
  - `test_exofop_record_keeps_comments_and_imaging` (also the planet parameters with their periods; a page without
    them is a failed read), `test_hits_are_deduplicated_by_doi_arxiv_id_or_title`.
  - `test_vetting_literature_writes_one_record_per_signal`, `test_resume_fills_only_what_the_earlier_run_left_incomplete`
    (only the incomplete searches are made again; no file of the run holds the token; a changed earlier record is
    refused), `test_literature_refuses_what_it_cannot_stand_behind`, `test_literature_refuses_an_evidence_only_run`.
- The network test `test_hip_8152_finds_akana_murphy_2023` (skipped without `ADS_API_TOKEN`): SIMBAD names TIC
  164767175 HIP 8152, and ADS's object search itself, resolved through SIMBAD, returns Akana Murphy et al. 2023. Until
  2026-10-19 arXiv's hit by HIP 8152 also passed it, which hid an ADS search that failed for every star.
