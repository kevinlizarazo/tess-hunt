# 0043: A passed signal gets a preprint and a dataset on Zenodo

- Date: 2026-11-02
- Status: Accepted. Made in the M5 design (section 4.4), approved by the maintainer with the M5 plan on 2026-10-30.
  The design left the packaging to the build; the build's choices are stated under Decision. Two rulings the M5
  build's controller made on 2026-10-30 and 2026-11-02, also stated under Decision, are the controller's, with no
  acceptance by the maintainer recorded: the test of the PDF reads WeasyPrint's laid-out pages, not the written file,
  since the lock holds no PDF reader and only the new dependency group may change it; and
  `results/preprints/author.toml` is committed on its own, once the maintainer approves its text. The template's
  changes after the specimen's pre-release review (2026-11-02), which made 60 findings and confirmed 57, follow the
  controller's rulings on those findings, with no acceptance by the maintainer recorded: among them, the refusal of
  a preregistered result whose deposit came on or after the start of the first sector it predicts. Amended on
  2026-11-05 (below): the maintainer asked for the paper to follow journal conventions.

## Context

The design's goal (docs/design.md, section 1) takes a credible candidate as far as an independent researcher can,
and a Zenodo preprint with its dataset is one step of that. No signal has passed yet. The predictions package
([0040](0040-predictions-for-held-signals.md)) covers held signals; a pass needs a short paper that an astronomer
outside the project can read and check against the data behind it. Built before any pass exists, the template can be
reviewed on a specimen and fixed before a real result can shape it.

## Decision

- **Which record.** `tess-hunt preprint run --name NAME` renders from the signal's latest published record: the M3
  record, or its latest version ([0041](0041-revets-as-versions.md)). It refuses, before any run directory exists:
  - a record with any change git sees under `results/vetting/NAME/`, staged, unstaged or untracked: the paper reads
    the record as it was published and committed;
  - a latest record whose call `calls.problems` refuses, as `vetting publish` would refuse it today (the "passed" bar
    of [0028](0028-outcomes-and-calls.md), novelty read through [0042](0042-listings-after-our-claim.md));
  - a latest record whose call is not passed, even when an earlier version passed: a pass that a later version holds
    or kills no longer stands;
  - a run without WeasyPrint and Markdown importable, with a message naming `uv sync --group preprint`;
  - a missing or malformed `results/preprints/author.toml`;
  - in a production run, any change under `results/` that is not committed (the build's choice). `start_run` checks
    the code, not the template, the author line, the claims file or the published runs the paper reads;
  - a record holding a preregistered result whose deposit Zenodo published on or after the day TESS began observing
    the first sector it predicts (`benchmarks/tess_sectors.csv`): the paper says the prediction came first. Decision
    0040's lock start keeps a real package clear of it;
  - an injection-recovery run without `completeness_snr.csv`, which the paper points to;
  - a triage run whose `signals.csv` holds no row, or more than one, for the signal: the paper gives its SDE and
    triage's steps from that row.

  A value the paper needs and its sources lack raises while the paper is rendered, which is also before the run
  starts.
- **The paper.** `preprint.md`, from `results/preprints/preprint.template.md`, and `preprint.pdf`, rendered from it.
  Its sections follow the design, with the specimen review's additions: a title naming the star and the period; a
  summary that calls the signal a planet candidate, says who makes the call and its three outcomes, and says what the
  light curves leave open; how tess-hunt works, which introduces its steps, the record and its versions, the call,
  the "passed" bar of [0028](0028-outcomes-and-calls.md), decision records, runs and seasons once, in plain words; the
  star and the signal, with the density-prior fit's period, epoch, duration and Rp/R*, their spreads, the radius with
  its percentiles and what they leave out, and the depth of the search's box; how it was found, with the sample, the
  null search's sizes, the injection-recovery run's `completeness_snr.csv` and triage's row for the signal; how it was
  vetted, opening with each earlier record's call and what each re-vet changed, then every check's outcome and reason,
  ModShift, the red-noise factors, TRICERATOPS's FPP and NFPP and any possible host it weighed no scenario on, the
  pixel check's offset in each sector and the sector its outcome rests on, the literature search's hits and ExoFOP's
  listings, the review with each finding's fate, and the call's three sentences quoted; the held-out check, what it
  tests and its season counts, and any preregistered result with its deposit's DOI, its published date against the
  first predicted sector's start, what the result shows and whether the call came before it; what it can't rule out;
  when it was made public, with 0042's rule stated once; data and code availability, with a table of the runs it reads,
  a guide to each record's files and the licences; the use of LLMs; acknowledgements; and references.
  - Every number is read by key, with `string.Template.substitute`, from the record, its runs' provenance and the
    published runs they lead to: the search run's provenance and the criteria file it recorded, its threshold run's
    `threshold.json`, the triage run's `signals.csv` for the signal's row, the injection-recovery run, and
    `benchmarks/tess_sectors.csv` for a predicted sector's start. Numbers are formatted as the dossier and the DDT
    proposal format them. Where the record holds no number a reader would want, such as an uncertainty on the TIC's
    stellar radius, the paper says so in words and computes nothing new. The call's words and the review's are quoted
    under [0037](0037-quoted-text-in-the-dossier.md), in quotation marks, with machine paths and the maintainer's name
    written as the dossier writes them ([0038](0038-literature-trim-and-username-scrub.md)). Every finding is given
    with its fate: confirmed, with the call's answer; refuted, with each refuter's verdict; or rated note. Each note
    `review-notes.toml` adds on a quoted finding under 0037 is given under that finding, after its quoted lines, as
    "Note (DATE)". The paragraph above the findings says once that a note is the maintainer's, added later, and part
    of neither the review nor the call.
  - The prose follows the maintainer's read of the specimen (2026-11-03): one idea per sentence, one word per thing,
    a section named by its quoted heading, counts from one to nine spelled out, each limit stated once, plain verbs,
    and one name per object. A TOI or CTOI from ExoFOP's own rows is named as the novelty check names it (`TOI-266.01`,
    `CTOI-164767175.03`).
  - No provenance in a record names the injection-recovery run, so the paper takes the one published production
    `benchmark-inject` run made at the search's threshold run, and refuses unless exactly one is (the build's choice).
  - The claim date and record are `results/claims.toml`'s. Each listing the record's `claims.json` excepts under 0042
    is named with its period, the day ExoFOP first listed it and its dispositions. 0042 excepts a later listing on
    the star at any period, so only one the novelty check matched (its `evidence["matches"]`) is placed against the
    signal's period: "at this period" at ratio 1, and at the harmonic it matched otherwise ("at twice this period").
    A `claims.json` that rests on another claim than the committed file gives is refused, since the paper states one.
  - The novelty check's outcome is said as a verb, with the listings its evidence matched to the signal by name; where
    its evidence lists no match, its reason is quoted.
  - The predictions DOI is `results/predictions/dois.toml`'s for the package the record's `prereg.json` names.
  - The summary says "planet candidate" and never "confirmed", "validated" or "discovered a planet".
  - The paper and its Zenodo form name no model: the review is "LLM-assisted" and refuters are "separate
    LLM-assisted checks", as the maintainer's Use of LLMs paragraph (2026-11-02) describes them. The maintainer
    chose this on 2026-11-02.
  - The figures are the record's `transits.png`, `folds.png`, `odd_even.png` and `phase.png`, with the paper's own
    captions, which say what each plot draws: the dossier's assume a reader inside the project. The centroid plots
    draw Gaia DR3 stars, so they stay in the dataset under Gaia's terms. The paper names the star by its TIC number
    and its other names, never its Gaia DR3 source id, and its own text gives no Gaia value: it counts the neighbour
    check's possible hosts and leaves their separations and depths to `neighbours.csv`. So the paper and its figures
    are CC BY 4.0 (the build's choice), with two exceptions the paper states. A Gaia value in the text it quotes from
    the review or the call, or in a note beside it, stays under Gaia's terms, as `results/README.md` says of the
    reviews' quoted Gaia values. The ExoFOP listings it names (TOIs, CTOIs, confirmed planets, imaging observations
    and a listing 0042 sets aside) stay under ExoFOP's terms.
- **The dataset.** The run's `dataset/` directory holds `vetting/NAME/`, every file git tracks in each published
  record of the signal from the M3 record to the one the paper is rendered from, as `results/vetting/` holds them (a
  file git ignores, such as macOS's `.DS_Store`, is no part of a record), and
  `lc/<tic>.npz`, the light curve that record's vetting run read, checked against the sha256 that run recorded.
  `manifest.json` lists each file of the dataset with its sha256 and licence, following `results/README.md`: the
  files that hold Gaia DR3 data (`checks.json`, `checks-with-suspect.json`, `neighbours.csv`, `triceratops.json`,
  `plots/centroids.png`, `pixels.png`, `review.json`, `review-scripts.tar.gz` and `dossier.md`) are CC BY-NC 3.0 IGO,
  the rest CC BY 4.0. `literature.json`, `claims.json` and `dossier.md` also say that ExoFOP's rows in them stay under
  ExoFOP's terms (the build's choice, as `results/README.md` says of the records' ExoFOP rows).
- **The commands.**
  - `tess-hunt preprint run --name NAME [--production]` writes the paper, its PDF, the four figures, `dataset/` and
    `manifest.json` into one run directory, and records the author line, the record it read and the predictions DOI
    in the run's `provenance.json`.
  - `tess-hunt preprint publish --run RUN_ID` copies a finished production run's `preprint.md`, `preprint.pdf`,
    `manifest.json`, `provenance.json` and figures into `results/preprints/<run id>/`, and refuses any other run.
    The dataset is not committed: it holds a light curve, which is raw data. The maintainer deposits it from the run
    directory, and the committed `manifest.json` gives the sha256 of each of its files.
  - `tess-hunt preprint zenodo --run RUN_ID` prints the deposit form's text from a finished production run's own
    files, and refuses any other run, since the deposited copy is the committed one: the title, Publication / Preprint
    as the resource type, the creators from the author line the run recorded, the description, the licences (CC BY
    4.0; CC BY-NC 3.0 IGO for the files holding Gaia DR3 data, which the description names; and ExoFOP's terms for
    ExoFOP's rows in the dataset and the listings the paper names), the related
    identifiers (the repository's URL, and the predictions DOI when the record holds a preregistered result) and the
    files to upload, `dataset/` as one zip archive. The form is not a package file.
- **The author line.** The template holds no name. The author line and the repository's URL come from
  `results/preprints/author.toml` (`given_names`, `family_names`, `affiliation` and `repository`, and optionally
  `orcid` and `email`), read when the paper is rendered. The file is the maintainer's: its text changes only with the
  maintainer's approval, and the run refuses without it. The tests render with a placeholder author.
- **The PDF.** WeasyPrint 70.0 renders the Markdown, which Markdown 3.11.1 turns into HTML. Both are pinned in the
  optional `preprint` dependency group (`uv sync --group preprint`); adding them added ten packages to `uv.lock` and
  changed none. `uv sync --locked` doesn't install the group, so CI skips the one test that renders a PDF, and every
  other test of the run replaces the renderer. A specimen's every page reads "SPECIMEN: not a candidate" in its header
  and its footer.
- **The specimen and the two reviews.** The build renders a specimen from a made-up record shaped like a real pass,
  marked on every page, kept outside `results/` and never deposited. A pre-release review reads it as M4's reviews
  read the DDT text and the predictions package: as a reader outside the project, as an astronomer checking that no
  sentence claims more than the record shows, and for AI or agent phrasing. It runs as a workflow on the maintainer's
  go-ahead, and its fixes go into the template before any real result exists. A real pass gets its own pre-release
  review of its rendered text before the maintainer deposits it.
- **What waits.** A preregistration of a passed signal's upcoming sectors (`predictions run` takes held signals
  only), a Research Note of the AAS and a JOSS paper. Each waits for a pass, and the note also for ExoFOP's answer on
  whether it would qualify (docs/design.md, section 1.1).

## Amendment (2026-11-05): journal conventions

The maintainer read the specimen and asked for a paper that reads and looks like a professional paper of its kind. Two
reviews compared it with six published analogues and the AAS rules; the controller's rulings on them are applied.
Where this amendment and the Decision above differ, the amendment holds.

- **Sections and numbering.** The paper has numbered sections in the order the analogues use: 1 Introduction (new
  fixed text: TESS, the TOI and CTOI process, what the paper reports), 2 The tess-hunt Search and Vetting, 3 Host Star,
  4 Detection, 5 Transit Parameters, 6 Vetting with five subsections (light-curve tests, location of the signal, the
  statistical false-positive probability, literature, catalogues and later listings, and the adversarial review and
  the call), 7 Held-out Seasons and the Preregistered Test, 8 Discussion, which quotes the upheld findings with their
  answers, and 9 Conclusions. The unnumbered back matter follows: Acknowledgements, Use of LLMs (word for word),
  Facilities and Software lines, Data Availability as one paragraph, and References, then Appendices A to D (the
  runs, the dataset's files, the refuted findings and the notes, and the licences). The stylesheet numbers the
  headings, and the text refers to sections by number, in place of quoting their headings.
- **Voice.** The body says "we", as single-author papers in the field do, and Section 2 says once that the decision
  records call the author "the maintainer". tess-hunt stays the subject only of what its code does. A finding that
  survives its refuters is "upheld" in the paper's prose; the records keep `confirmed`. Decision records are defined
  once in Section 2 and cited as "DR 0042". Contractions are expanded outside quoted text, and the prose spells
  "catalogue" as British English, beside `neighbours` and "licence".
- **Front matter and abstract.** The title is in title case. The author block gives the name, the affiliation, and
  the ORCID and email when `author.toml` has them, each on its own line, and a "Version of" line with the day the paper
  is rendered; the repository's URL moves to Data Availability. The Summary becomes the Abstract: the period, depth,
  duration, radius and FPP with the errors the record holds, the star's TIC values, what Table 2 shows (every check
  passed, or which did not and why the call still stands), the preregistered result, and that the signal stays a
  candidate and what would establish it as a planet. It still says "planet candidate" and never "confirmed",
  "validated" or "discovered a planet". Who makes the call and its outcomes move to Section 2. UAT keywords follow
  the Abstract. The Zenodo description is the Abstract's first paragraph in plain text.
- **Notation.** Values carry ± or, for asymmetric percentile offsets, a superscript and a subscript with a minus sign,
  in the value's own unit: the period and epoch uncertainties are their posterior standard deviations in days, and
  the radius takes its offsets from the 16th and 84th percentiles. FPP and NFPP are the mean ± the standard deviation
  over TRICERATOPS's runs, as the record holds them. The record holds no uncertainty for the depth (the BLS box depth)
  or the duration (from the density-prior fit's medians), and Table 1's note says so. Symbols follow the AAS (R⊕, R⊙,
  σ, ″), dates in prose read "2027 January 20", and counts of five or more digits take separators. Quoted text and
  the record's reasons in Table 2 stay verbatim.
- **Tables.** Tables 1 to 4 are numbered, captioned above and cited in the text, with notes below. Table 2's novelty
  row carries a lettered footnote when its outcome is not a pass and Section 6.4 sets the listing aside or the call's
  promotion replaces the check.
- **References.** One alphabetical list in AAS form, built and sorted in code, each entry with its DOI where it has
  one, every entry checked in NASA ADS on 2026-11-05 (the MAST and ExoFOP data DOIs, which ADS does not index, in
  DataCite). It adds Guerrero et al. 2021 for the TOI process and full entries for the light-curve products, the TIC,
  TESS-EBs and ExoFOP. Every entry is cited in the text or the Software line. URLs leave the running text for
  footnotes or Data Availability; the acknowledgements' requested credits keep theirs.
- **Figures.** Each figure is cited where its subject is discussed and placed after that citation, with a bold label
  and a caption that opens with no article. `plots.py` draws every future record's plots at the paper's text width with
  text of one size, no titles above the plots, axis labels in sentence case with units, the whole orbit from phase
  −0.25 to 0.75, and 300 dpi, each PNG under 300 KB. Published records keep their plots.
- **Typography.** STIX Two Text, with STIX Two Math for the symbols it lacks, justified and hyphenated text, a centred
  title block, numbered capitalised headings, and tables with horizontal rules only.
- **The specimen.** Its made-up record tells one story: its runs take their ids from a clock of its own, so each run,
  call, listing and deposit comes in order, and the held call names evidence the next version supplies.

## Limitations

- The prose around the numbers is fixed text, and a test can't check that it claims no more than the record shows.
  The specimen's review checked it once; each real pass's review checks it again.
- The paper gives the tension of a preregistered result against the training seasons' depth in words: that depth is
  in the deposited package's `references.json`, which the paper names and does not read.
- A review may quote no Gaia value, but every `review.json` is listed under Gaia's terms, as `results/README.md` lists
  the reviews: when unsure, the narrower licence.
- The paper names the vetting run's commit. The commit that rendered the paper is in its `provenance.json`.

## Evidence

- [tests/test_preprint.py](../../tests/test_preprint.py): `test_preprint_refuses_unless_the_latest_version_is_a_standing_pass`
  (a held record, a passed M3 record with a held r2, a pass `calls.problems` refuses, an uncommitted change),
  `test_every_number_comes_from_the_record` (and a missing value raises), `test_the_paper_says_candidate_not_planet`,
  `test_a_note_0037_added_sits_under_the_quoted_finding`, `test_a_confirmed_finding_no_refuter_ran_on_says_so`,
  `test_a_versions_paper_names_its_records` (an earlier record's call quoted, what the re-vet changed, the runs
  table and the dataset's guide),
  `test_the_paper_names_the_claim_date_and_any_0042_listing` (a later listing at another period named with no claim
  of a match, and a `claims.json` resting on another claim is refused),
  `test_the_paper_gives_the_ephemeris_with_uncertainties`, `test_credits_and_disclosure_are_present`,
  `test_a_deposit_after_its_first_sector_is_refused` (and the pending, untested and missed results),
  `test_the_paper_says_how_the_signal_was_found` (and an injection-recovery run without its completeness file, and a
  triage run without the signal's row, are refused), `test_the_paper_says_what_vetting_leaves_open`,
  `test_triage_and_the_novelty_check_are_said_in_words`, `test_what_a_revet_changed_is_said`,
  `test_how_tess_hunt_works_is_said_once`, `test_the_figures_and_references_are_the_papers_own`,
  `test_the_dataset_lets_a_reader_recompute` (a file git ignores stays out),
  `test_a_versions_dataset_holds_each_record_up_to_it`, `test_the_author_line_comes_from_author_toml`,
  `test_a_production_run_reads_only_committed_results`, `test_run_refuses_before_starting_without_the_pdf_group`,
  `test_numbers_read_as_aas_prints_them`, `test_each_count_reads_as_words`, `test_counts_from_the_record_read_as_words`,
  `test_publish_copies_the_package`, `test_zenodo_prints_the_form_from_the_run` (only a production run, and a judged
  result without its depth raises), `test_the_pdf_renders` (the header and footer of every page, and the findings'
  nested list in the HTML).
- [tests/test_plots.py](../../tests/test_plots.py): `test_each_plot_is_drawn_for_print` (the 2026-11-05 amendment's
  plot style).
