# tess-hunt

An independent search for transiting planets in public NASA TESS light curves.

**Status:** under construction. No signal this project reports is a confirmed planet; every one is a candidate until
other observers confirm it. The known planets under `results/benchmarks/` are positive controls from the TOI catalog.

`results/benchmarks/` holds M1's known-planet, injection-recovery and control vet runs
([results/README.md](results/README.md)); no search has run yet.

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

Light curves are read anonymously from the public TESS bucket on AWS (`s3://stpubdata`) and cached in
`$TESS_HUNT_DATA` (default `~/.cache/tess-hunt`). Stellar parameters come from the TIC via MAST, and known planets and
candidates from ExoFOP and the NASA Exoplanet Archive, all without credentials.

## Licenses

Code: MIT ([LICENSE](LICENSE)). Results in `results/`: CC BY 4.0 ([results/LICENSE](results/LICENSE)). The FITS files
under `tests/fixtures/` are TESS data products under CC BY 4.0 ([tests/fixtures/README.md](tests/fixtures/README.md)).
Data credits and required acknowledgements: [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).
