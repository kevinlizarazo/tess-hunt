# tess-hunt

An independent search for transiting planets in public NASA TESS light curves. Every signal it reports is a candidate,
not a confirmed planet, until other observers confirm it.

## Results

The search covered 30,195 Sun-like dwarfs in the southern ecliptic hemisphere. Of its 2,993 signals above the
detection threshold, triage shortlisted 9, and 5 more were added from signals whose only catalog match was a SPOC
threshold-crossing event or an ExoMiner row. All 14 have been vetted:

- **Passed:** none.
- **Killed:** 4. One is an eclipsing binary, one was already published, one was found at the wrong period, and one
  transits too briefly for a planet around its star.
- **Held:** 10. Nothing in the public data rules them out, but none can pass yet, most often because the data can't
  place the dip on the target star.

[results/vetting/README.md](results/vetting/README.md) gives the reason for each call and links each signal's dossier:
every check, an adversarial review and the runs behind them.

In progress ([pull request #1](https://github.com/kevinlizarazo/tess-hunt/pull/1)): transit predictions for the six
held signals that TESS observes again in Sectors 112 to 114 (December 2026 to March 2027), preregistered on Zenodo
on 2026-10-28 ([doi:10.5281/zenodo.23745923](https://doi.org/10.5281/zenodo.23745923)), before those sectors start.
A request for 2-minute cadence on one of them, TIC 241522065, went to the TESS office the same day.

## How it works

1. **Targets.** Stars from the TESS Input Catalog with a Gaia DR3 dwarf cut: 5300 to 6500 K, TESS magnitude 10.5 or
   brighter, observed in at least four sectors including at least one of Sectors 97 to 107.
2. **Search.** Periodic dips between 1 and 40 days in the SPOC, TESS-SPOC and QLP light curves. A search of the same
   light curves scrambled sets the detection threshold, and known planets from the TOI catalog run alongside as
   positive controls.
3. **Triage.** Each signal above the threshold is checked for novelty against published catalogs and with
   LEO-Vetter's flux tests. Those that pass both get a pixel centroid check, and those that pass it are shortlisted.
4. **Vetting.** Each shortlisted signal gets the light-curve checks, a held-out season test (a fit that never saw one
   season must predict when and how deep that season's transits fall), a table of nearby stars that could host the
   dip, TRICERATOPS false-positive probabilities and a literature search. An AI model then reviews the evidence
   adversarially, and the maintainer calls the signal passed, killed or held.

The code and documents are written with Claude, Anthropic's AI model, under the maintainer's direction.

## Safeguards

- Pass/fail criteria are committed under [criteria/](criteria/) before the stage that applies them runs on the data
  ([design, section 5.3](docs/design.md#53-criteria-frozen-before-the-data)). Changing one after seeing results takes
  a decision record giving the reason.
- Every vetting check but three is shown to fail on a planted false positive. The three can only pass or be
  inconclusive, because their negative results don't show a signal isn't a planet: a weak dip, a nearby star that
  could host it, or a paper that names the star ([decision 0017](docs/decisions/0017-signal-present-check.md),
  [0025](docs/decisions/0025-neighbours.md), [0027](docs/decisions/0027-literature-by-name.md)).
- Every published run carries a provenance file naming the commit that made it.
- The design is in [docs/design.md](docs/design.md) and every decision in [docs/decisions/](docs/decisions/).

## Repository layout

- `src/tess_hunt/`: the pipeline; `uv run tess-hunt --help` lists its stages
- `criteria/`: the frozen pass/fail criteria, one file per version
- `benchmarks/`: the known-planet and control lists, the sector table and the scripts behind the diagnoses
- `results/`: everything published; [results/README.md](results/README.md) describes each file
  - `benchmarks/`: the runs that set and test the method: the detection threshold, positive controls,
    injection-recovery, completeness and the checks' controls
  - `triage/`: the triage run and its shortlist
  - `vetting/`: one record per vetted signal
  - `catalogs/`: the manifest of the catalog snapshot the novelty check used
- `docs/`: the design and the decision records
- `tests/`: the test suite

## Running it

Requires [uv](https://docs.astral.sh/uv/) on Linux or macOS (Windows through WSL). Pixel vetting also needs `curl`
and `unzip` on PATH.

    uv sync
    uv run tess-hunt --help

Light curves are read anonymously from the public TESS bucket on AWS (`s3://stpubdata`), or from MAST's download API
for files the bucket lacks, and cached in `$TESS_HUNT_DATA` (default `~/.cache/tess-hunt`). Stellar parameters come
from the TIC via MAST and from the Gaia archive, and known objects from ExoFOP, the NASA Exoplanet Archive and the
catalogs listed in [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md), all without credentials. The vetting stage's literature
search also reads SIMBAD and NASA ADS. ADS needs a token, read from `ADS_API_TOKEN` at run time and never stored;
without it ADS is recorded as not searched and the search can't pass
([decision 0027](docs/decisions/0027-literature-by-name.md)). Pixel vetting keeps transit-diffImage's difference
images (pickle files) and records their sha256; transit-diffImage deletes the TESScut cutouts it builds them from.

## Citing

[CITATION.cff](CITATION.cff) gives the citation; GitHub's "Cite this repository" button reads it.

## Licenses

Code: MIT ([LICENSE](LICENSE)). Results in `results/`: CC BY 4.0 ([results/LICENSE](results/LICENSE)), except Gaia
data, such as the `ruwe` column of the triage tables and the vetting records' neighbour tables, which stay under
ESA's CC BY-NC 3.0 IGO terms ([licence](https://www.cosmos.esa.int/web/gaia-users/license)), and ExoFOP's rows in
the vetting records' `literature.json` and dossiers, which stay under ExoFOP's terms;
[results/README.md](results/README.md) lists every one. The FITS files under `tests/fixtures/` are TESS data products
under CC BY 4.0 ([tests/fixtures/README.md](tests/fixtures/README.md)).
Data credits and required acknowledgements: [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).
