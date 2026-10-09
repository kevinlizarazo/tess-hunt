# tess-hunt

An independent search for transiting planets in public NASA TESS light curves.

**Status:** under construction. Nothing here is a confirmed planet. Any signal this project reports is a candidate
until other observers confirm it.

## What it searches

Sun-like dwarfs (5300 to 6500 K) of TESS magnitude 10.5 or brighter, observed in at least four sectors including at
least one of sectors 97 to 107, for periodic dips between 1 and 40 days. Every vetting check is proven to fail on a
planted false positive, and pass/fail criteria are committed before the data is searched. The design is in
[docs/design.md](docs/design.md); decisions are in [docs/decisions/](docs/decisions/).

## Setup

Requires [uv](https://docs.astral.sh/uv/) on Linux or macOS (Windows through WSL).

    uv sync
    uv run tess-hunt --help

Light curves are cached in `$TESS_HUNT_DATA` (default `~/.cache/tess-hunt`). Data is read anonymously from the
public TESS bucket on AWS (`s3://stpubdata`); no credentials are needed.

## Licenses

Code: MIT ([LICENSE](LICENSE)). Results in `results/`: CC BY 4.0 ([results/LICENSE](results/LICENSE)). Data
credits and required acknowledgements: [ACKNOWLEDGEMENTS.md](ACKNOWLEDGEMENTS.md).
