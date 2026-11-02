# 0043: A passed signal gets a preprint and a dataset on Zenodo

- Date: 2026-11-02
- Status: Accepted. Made in the M5 design (section 4.4), approved by the maintainer with the M5 plan on 2026-10-30.
  The design left the packaging to the build; the build's choices are stated under Decision. Two rulings the M5
  build's controller made on 2026-10-30 and 2026-11-02, also stated under Decision, are the controller's, with no
  acceptance by the maintainer recorded: the test of the PDF reads WeasyPrint's laid-out pages, not the written file,
  since the lock holds no PDF reader and only the new dependency group may change it; and
  `results/preprints/author.toml` is committed on its own, once the maintainer approves its text.

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
    the code, not the template, the author line, the claims file or the published runs the paper reads.

  A value the paper needs and its sources lack raises while the paper is rendered, which is also before the run
  starts.
- **The paper.** `preprint.md`, from `results/preprints/preprint.template.md`, and `preprint.pdf`, rendered from it.
  Its sections follow the design: a title naming the star and the period; a summary that calls the signal a planet
  candidate; the star and the signal, with the density-prior fit's period, epoch and duration, their standard
  deviations, the radius with its percentiles and the depth of the search's box; how it was found; how it was vetted,
  with every check's outcome and reason, TRICERATOPS's FPP and NFPP, the pixel check, the literature search and
  ExoFOP, the review, and the call's three sentences quoted; the held-out check and any preregistered result with its
  deposit's DOI; what it can't rule out; when it was made public; data and code availability with the licences; the
  use of LLMs; acknowledgements; and references.
  - Every number is read by key, with `string.Template.substitute`, from the record, its runs' provenance and the
    published runs they lead to: the search run's provenance, its threshold run's `threshold.json`, the triage run's
    `signals.csv` for the signal's SDE, and the injection-recovery run. Numbers are formatted as the dossier and the
    DDT proposal format them. The call's words and the review's are quoted under
    [0037](0037-quoted-text-in-the-dossier.md), with machine paths and the maintainer's name written as the dossier
    writes them ([0038](0038-literature-trim-and-username-scrub.md)). Each note `review-notes.toml` adds beside a
    quoted finding under 0037 is given under that finding, worded as the dossier words it ("Note added on DATE under
    decision 0037, not part of the review or the call").
  - No provenance in a record names the injection-recovery run, so the paper takes the one published production
    `benchmark-inject` run made at the search's threshold run, and refuses unless exactly one is (the build's choice).
  - The claim date and record are `results/claims.toml`'s. Each listing the record's `claims.json` excepts under 0042
    is named with the day ExoFOP first listed it and its dispositions. A `claims.json` that rests on another claim
    than the committed file gives is refused, since the paper states one.
  - The predictions DOI is `results/predictions/dois.toml`'s for the package the record's `prereg.json` names.
  - The summary says "planet candidate" and never "confirmed", "validated" or "discovered a planet".
  - The figures are the record's `transits.png`, `folds.png`, `odd_even.png` and `phase.png`, with the dossier's
    captions. The centroid plots draw Gaia DR3 stars, so they stay in the dataset under Gaia's terms. The paper names
    the star by its TIC number and its other names, never its Gaia DR3 source id, and its own text gives no Gaia
    value, so the paper and its figures are CC BY 4.0 (the build's choice). A Gaia value in the text it quotes from
    the review or the call stays under Gaia's terms, as `results/README.md` says of the reviews' quoted Gaia values,
    and the paper says so.
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
    as the resource type, the creators from the author line the run recorded, the description, both licences (CC BY
    4.0, and CC BY-NC 3.0 IGO for the files holding Gaia DR3 data, which the description names), the related
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

## Limitations

- The prose around the numbers is fixed text, and a test can't check that it claims no more than the record shows.
  The specimen's review checks it once; each real pass's review checks it again.
- A review may quote no Gaia value, but every `review.json` is listed under Gaia's terms, as `results/README.md` lists
  the reviews: when unsure, the narrower licence.
- The paper names the vetting run's commit. The commit that rendered the paper is in its `provenance.json`.

## Evidence

- [tests/test_preprint.py](../../tests/test_preprint.py): `test_preprint_refuses_unless_the_latest_version_is_a_standing_pass`
  (a held record, a passed M3 record with a held r2, a pass `calls.problems` refuses, an uncommitted change),
  `test_every_number_comes_from_the_record` (and a missing value raises), `test_the_paper_says_candidate_not_planet`,
  `test_a_note_0037_added_sits_under_the_quoted_finding`, `test_a_versions_paper_names_its_records`,
  `test_the_paper_names_the_claim_date_and_any_0042_listing` (and a `claims.json` resting on another claim is
  refused), `test_the_paper_gives_the_ephemeris_with_uncertainties`, `test_credits_and_disclosure_are_present`,
  `test_the_dataset_lets_a_reader_recompute` (a file git ignores stays out),
  `test_a_versions_dataset_holds_each_record_up_to_it`, `test_the_author_line_comes_from_author_toml`,
  `test_a_production_run_reads_only_committed_results`, `test_run_refuses_before_starting_without_the_pdf_group`,
  `test_publish_copies_the_package`, `test_zenodo_prints_the_form_from_the_run` (only a production run, and a judged
  result without its depth raises), `test_the_pdf_renders` (the header and footer of every page, and the findings'
  nested list in the HTML).
