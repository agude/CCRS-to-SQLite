"""Command-line entry point for the CCRS-to-SQLite converter.

The argument surface here is the one described in plan.md §5. Conversion
itself is not implemented yet; the parser exists so that packaging, the CI
smoke test, and `--version` are exercised from the first commit.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ccrs_to_sqlite import __version__

DEFAULT_OUTPUT_FILE = Path("ccrs.sqlite3")
PARSE_ERROR_MODES = ("strict", "ignore", "replace")


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser for the ``ccrs_to_sqlite`` console script."""
    parser = argparse.ArgumentParser(
        prog="ccrs_to_sqlite",
        description="Convert California Crash Reporting System CSV exports to SQLite.",
    )
    parser.add_argument(
        "data_dir",
        nargs="?",
        type=Path,
        help=(
            "directory of CCRS CSVs to discover and load; omit it and pass "
            "--crashes/--parties/--injured instead to load specific files"
        ),
    )
    parser.add_argument(
        "--crashes",
        action="append",
        type=Path,
        default=[],
        metavar="FILE",
        help="a crashes CSV to load; repeatable",
    )
    parser.add_argument(
        "--parties",
        action="append",
        type=Path,
        default=[],
        metavar="FILE",
        help="a parties CSV to load; repeatable",
    )
    parser.add_argument(
        "--injured",
        action="append",
        type=Path,
        default=[],
        metavar="FILE",
        help="an injuredwitnesspassengers CSV to load; repeatable",
    )
    parser.add_argument(
        "-o",
        "--output-file",
        type=Path,
        default=DEFAULT_OUTPUT_FILE,
        help="the SQLite database to create (default: %(default)s)",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="treat rows with an unexpected field count as fatal instead of skipping them",
    )
    parser.add_argument(
        "--parse-error",
        choices=PARSE_ERROR_MODES,
        default="strict",
        help="how to handle undecodable bytes in the input (default: %(default)s)",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Parse arguments and run the conversion. Returns a process exit code."""
    parser = build_parser()
    arguments = parser.parse_args(argv)

    has_explicit_files = bool(arguments.crashes or arguments.parties or arguments.injured)
    if arguments.data_dir is None and not has_explicit_files:
        parser.error("give a data directory, or at least one of --crashes/--parties/--injured")

    print("ccrs_to_sqlite: conversion is not implemented yet", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
