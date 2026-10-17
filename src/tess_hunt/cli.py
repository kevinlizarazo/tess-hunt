"""Command-line entry point: one subcommand per pipeline stage."""

import argparse
import logging
from importlib.metadata import version

from tess_hunt import benchmark, catalogs, fetch, search, targets, triage, vet, vetting

COMMANDS: list = [catalogs, targets, fetch, search, benchmark, vet, triage, vetting]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tess-hunt", description="Transit search of public TESS light curves."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {version('tess-hunt')}")
    sub = parser.add_subparsers(dest="command", required=True)
    for module in COMMANDS:
        module.add_parser(sub)
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    # lightkurve installs its own handler, so each of its lines would print there and again through
    # the root logger's.
    lightkurve = logging.getLogger("lightkurve")
    lightkurve.setLevel(logging.WARNING)
    lightkurve.propagate = False
    args = build_parser().parse_args(argv)
    return args.func(args)
