# tess-hunt

An independent search for transiting planets in public NASA TESS light curves.

**Status:** under construction. No signal this project reports is a confirmed planet; every one is a candidate until
other observers confirm it. The known planets under `results/benchmarks/` are positive controls from the TOI catalog.

M2 searched the whole sample. `targets` builds it from the TIC with a Gaia DR3 dwarf cut, `fetch` reads the light
curves, a search of scrambled light curves sets the detection threshold, and the production search runs with the
known planets as positive controls. `triage` checks every signal above the threshold for novelty against published
catalogs and with LEO-Vetter's flux tests, runs pixel centroids on the signals that pass both, and shortlists those
that pass all three. The [shortlist](results/triage/20261015T155441Z-triage-7b12e25-3f57/summary.md) is the input to
M3's vetting; none of its signals has been vetted yet.

Published results ([results/README.md](results/README.md)):
- `results/benchmarks/`: M1's runs, the search fix's reruns, the null threshold, the production search's positive
  controls and the completeness map for typical sample stars
- `results/triage/`: the triage run with its shortlist, and the pixel check's controls
- `results/catalogs/`: the manifest of the catalog snapshot the novelty check used

## What it searches

Sun-like dwarfs (5300 to 6500 K) of TESS magnitude 10.5 or brighter, observed in at least four sectors including at
least one of sectors 97 to 107, for periodic dips between 1 and 40 days. Every vetting check is proven to fail on a
planted false positive, and pass/fail criteria are committed before the data is searched. The design is in
[docs/design.md](docs/design.md); decisions are in [docs/decisions/](docs/decisions/).

## Setup

Requires [uv](https://docs.astral.sh/uv/) on Linux or macOS (Windows through WSL). Pixel vetting also needs `curl`
and `unzip` on PATH.

    uv sync
    uv run tess-hunt --help

Light curves are read anonymously from the public TESS bucket on AWS (`s3://stpubdata`), or from MAST's download API
for files the bucket lacks, and cached in `$TESS_HUNT_DATA` (default `~/.cache/tess-hunt`). Stellar parameters come
from the TIC via MAST and from the Gaia archive, and known objects from ExoFOP, the NASA Exoplanet Archive and the
catalogs listed in [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md), all without credentials. Pixel vetting keeps
transit-diffImage's difference images (pickle files) and records their sha256; transit-diffImage deletes the TESScut
cutouts it builds them from.

## Licenses

Code: MIT ([LICENSE](LICENSE)). Results in `results/`: CC BY 4.0 ([results/LICENSE](results/LICENSE)), except the
`ruwe` column of the triage tables, which is Gaia DR3 data under ESA's CC BY-NC 3.0 IGO terms
([licence](https://www.cosmos.esa.int/web/gaia-users/license)). The FITS files
under `tests/fixtures/` are TESS data products under CC BY 4.0 ([tests/fixtures/README.md](tests/fixtures/README.md)).
Data credits and required acknowledgements: [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).
