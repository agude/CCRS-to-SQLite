"""The public `convert` entry point, and the command-line wrapper around it.

`main` is a thin argparse shim: everything it does is available to a caller
who imports `convert` instead, which is how the converter stays usable from a
notebook or another script without shelling out.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import sys
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from ccrs_to_sqlite import __version__
from ccrs_to_sqlite.load import (
    CRASHES_SOURCE,
    INJURED_SOURCE,
    ORPHAN_CHECKED_TABLES,
    PARTIES_SOURCE,
    DuplicatePrimaryKeyError,
    PrimaryKeyGuard,
    SourceKind,
    apply_bulk_load_pragmas,
    count_orphans,
    create_indexes,
    create_schema,
    load_source_file,
    record_file_load,
    record_orphan_count,
    year_label_from,
)
from ccrs_to_sqlite.open_record import PARSE_ERROR_MODES
from ccrs_to_sqlite.schema import Table

DEFAULT_OUTPUT_FILE = Path("ccrs.sqlite3")

USAGE_EXIT_CODE = 2
FAILURE_EXIT_CODE = 1


@dataclass(frozen=True)
class SourceFiles:
    """The source files to load, grouped by which of the three kinds they are."""

    crashes: tuple[Path, ...] = ()
    parties: tuple[Path, ...] = ()
    injured: tuple[Path, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.crashes or self.parties or self.injured)

    def in_load_order(self) -> list[tuple[SourceKind, Path]]:
        """Crashes first, so the crash rows exist before anything references them."""
        return [
            (kind, path)
            for kind, paths in (
                (CRASHES_SOURCE, self.crashes),
                (PARTIES_SOURCE, self.parties),
                (INJURED_SOURCE, self.injured),
            )
            for path in paths
        ]


def convert(
    sources: SourceFiles,
    output_file: Path = DEFAULT_OUTPUT_FILE,
    *,
    strict: bool = False,
    parse_error: str = "strict",
    progress: TextIO | None = None,
) -> None:
    """Convert CCRS source files into a SQLite database at `output_file`.

    The database is built in a temporary file beside the destination and
    renamed into place only once it is complete, so a failed run never leaves
    a half-written database sitting where the next run has to work around it.
    """
    progress = sys.stderr if progress is None else progress

    if output_file.exists():
        raise FileExistsError(
            f"{output_file} already exists. Move it aside, or choose another "
            f"path with --output-file; refusing to overwrite a database."
        )

    temporary_file = output_file.with_name(f".{output_file.name}.partial")
    temporary_file.unlink(missing_ok=True)
    try:
        with closing(sqlite3.connect(temporary_file)) as connection:
            _build_database(
                connection,
                sources,
                strict=strict,
                parse_error=parse_error,
                progress=progress,
            )
    except BaseException:
        temporary_file.unlink(missing_ok=True)
        raise

    temporary_file.replace(output_file)
    print(f"wrote {output_file}", file=progress)


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

    sources = SourceFiles(
        crashes=tuple(arguments.crashes),
        parties=tuple(arguments.parties),
        injured=tuple(arguments.injured),
    )
    if arguments.data_dir is None and not sources:
        parser.error("give a data directory, or at least one of --crashes/--parties/--injured")

    if arguments.data_dir is not None:
        parser.error(
            "directory mode is not implemented yet; name the files with "
            "--crashes/--parties/--injured"
        )

    try:
        convert(
            sources,
            arguments.output_file,
            strict=arguments.strict,
            parse_error=arguments.parse_error,
        )
    except (OSError, ValueError, csv.Error, sqlite3.Error, DuplicatePrimaryKeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return FAILURE_EXIT_CODE

    return 0


def _build_database(
    connection: sqlite3.Connection,
    sources: SourceFiles,
    *,
    strict: bool,
    parse_error: str,
    progress: TextIO,
) -> None:
    apply_bulk_load_pragmas(connection)
    create_schema(connection)

    guards: dict[str, PrimaryKeyGuard] = {}
    for kind, path in sources.in_load_order():
        guard = guards.setdefault(kind.table.name, PrimaryKeyGuard(kind.table))
        report = load_source_file(
            connection,
            path,
            kind,
            strict=strict,
            parse_error=parse_error,
            guard=guard,
            progress=progress,
        )
        record_file_load(connection, report, year_label_from(path))
        connection.commit()

    create_indexes(connection, progress)
    for table in ORPHAN_CHECKED_TABLES:
        _record_and_report_orphans(connection, table, progress)

    connection.commit()


def _record_and_report_orphans(
    connection: sqlite3.Connection,
    table: Table,
    progress: TextIO,
) -> None:
    orphans = count_orphans(connection, table)
    record_orphan_count(connection, table, orphans)
    if orphans:
        print(
            f"note: {orphans:,} {table.name} rows reference a crash that is not in this "
            f"database. Reports straddling a year boundary do this; loading more years "
            f"shrinks the count.",
            file=progress,
        )


if __name__ == "__main__":
    raise SystemExit(main())
