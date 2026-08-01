"""Reading CCRS source files into a SQLite database.

Everything here is shaped by the volume: eleven published years come to
roughly 15-20 million rows over 4-5 GB of CSV. `executemany` over batches,
one transaction per file, bulk-load PRAGMAs, and indexes built after the data
lands turn that into minutes rather than hours. These are the lessons
switrs-to-sqlite learned late; they are built in here from the start.

The failure policy is deliberate. A row the parser cannot make sense of is
skipped with a warning and counted, because aborting a twenty-minute load at
row 151,092 is hostile when the measured rate is one bad row in 780,000.
A duplicate primary key is fatal, because it means two source files disagree
and silently picking one hides the corruption.
"""

from __future__ import annotations

import csv
import re
import sqlite3
import sys
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from ccrs_to_sqlite import __version__
from ccrs_to_sqlite.converters import ISO_DATETIME_FORMAT
from ccrs_to_sqlite.open_record import open_source_file
from ccrs_to_sqlite.schema import (
    ALL_TABLES,
    CRASHES,
    CRASHES_SOURCE_HEADERS,
    INJURED_SOURCE_HEADERS,
    INJURED_WITNESS_PASSENGERS,
    METADATA,
    PARTIES,
    PARTIES_SOURCE_HEADERS,
    VEHICLES,
    SQLiteValue,
    Table,
    check_expected_headers,
    column_positions,
    convert_row,
    index_header_row,
)
from ccrs_to_sqlite.vehicles import VehiclePlan, plan_vehicles, vehicle_rows

# Rows per executemany call. Large enough that the per-call overhead
# disappears, small enough that a batch stays a few tens of megabytes.
BATCH_SIZE = 50_000

# How often to say something while a multi-hundred-thousand-row file loads.
PROGRESS_INTERVAL = 100_000

# SQLite's compiled-in parameter ceiling is 32,766 on current versions and 999
# on older ones. Existence probes stay under the smaller figure so they work
# against whatever sqlite3 the interpreter was built with.
MAX_QUERY_PARAMETERS = 900

BULK_LOAD_PRAGMAS = (
    # No rollback journal: the database is built in a temporary file that is
    # deleted on failure, so there is nothing to roll back to.
    "PRAGMA journal_mode = OFF",
    "PRAGMA synchronous = OFF",
    "PRAGMA cache_size = -262144",
    "PRAGMA temp_store = MEMORY",
)


@dataclass(frozen=True)
class SourceKind:
    """One of the three files the dataset publishes per year."""

    name: str
    table: Table
    expected_headers: frozenset[str]
    # Only parties rows carry inline vehicles to lift into their own table.
    splits_vehicles: bool = False


CRASHES_SOURCE = SourceKind("crashes", CRASHES, CRASHES_SOURCE_HEADERS)
PARTIES_SOURCE = SourceKind("parties", PARTIES, PARTIES_SOURCE_HEADERS, splits_vehicles=True)
INJURED_SOURCE = SourceKind(
    "injuredwitnesspassengers",
    INJURED_WITNESS_PASSENGERS,
    INJURED_SOURCE_HEADERS,
)

SOURCE_KINDS = (CRASHES_SOURCE, PARTIES_SOURCE, INJURED_SOURCE)

# Tables whose collision_id may point at a crash in another year's file.
ORPHAN_CHECKED_TABLES = (PARTIES, VEHICLES, INJURED_WITNESS_PASSENGERS)


# The dataset names its files `crashes_2025.csv`, so the year is the tail of
# the stem. Anything else is unlabelled rather than an error: a renamed file
# still loads, it just says less about itself in the metadata.
_YEAR_SUFFIX = re.compile(r"_(\d{4})$")


def year_label_from(path: Path) -> str | None:
    """Return the four-digit year a source filename ends with, if it has one."""
    stem = path.name.split(".")[0]
    match = _YEAR_SUFFIX.search(stem)
    return match.group(1) if match else None


class DuplicatePrimaryKeyError(Exception):
    """Two source files supplied the same primary key."""


@dataclass
class LoadReport:
    """What happened while one source file was read."""

    source_file: str
    table_name: str
    rows_read: int = 0
    rows_loaded: int = 0
    rows_skipped: int = 0


@dataclass(frozen=True)
class LoadedKeyRange:
    """The span of primary keys one source file contributed."""

    source_file: str
    smallest: int
    largest: int

    def contains(self, key: int) -> bool:
        return self.smallest <= key <= self.largest


class PrimaryKeyGuard:
    """Refuses a primary key that an earlier source file already supplied.

    Within a single file the ids are already unique --- the dataset publishes
    only the latest version of each report --- so a collision means two files
    overlap, which in a year-partitioned dataset means the user mixed
    snapshots. That is corruption, not a merge, so it stops the load.

    Keys are only probed once a previous file has loaded into the table, so
    the common one-file-per-table case costs nothing.
    """

    def __init__(self, table: Table) -> None:
        if table.primary_key is None:
            raise ValueError(f"{table.name} has no primary key to guard")

        self.table = table
        self.primary_key = table.primary_key
        self._key_index = table.column_names.index(table.primary_key)
        self._loaded_ranges: list[LoadedKeyRange] = []
        self._smallest_seen: int | None = None
        self._largest_seen: int | None = None

    def check_batch(
        self,
        connection: sqlite3.Connection,
        rows: Sequence[Sequence[SQLiteValue]],
        source_file: str,
    ) -> None:
        """Fail if any key in the batch is already in the table. Records the batch either way."""
        keys = [row[self._key_index] for row in rows]
        if self._loaded_ranges:
            self._fail_on_existing_key(connection, keys, source_file)

        for key in keys:
            if not isinstance(key, int):
                continue
            self._smallest_seen = (
                key if self._smallest_seen is None else min(self._smallest_seen, key)
            )
            self._largest_seen = key if self._largest_seen is None else max(self._largest_seen, key)

    def finish_file(self, source_file: str) -> None:
        """Close out a file, remembering the key span it contributed."""
        if self._smallest_seen is None or self._largest_seen is None:
            return

        self._loaded_ranges.append(
            LoadedKeyRange(source_file, self._smallest_seen, self._largest_seen)
        )
        self._smallest_seen = None
        self._largest_seen = None

    def _fail_on_existing_key(
        self,
        connection: sqlite3.Connection,
        keys: Sequence[SQLiteValue],
        source_file: str,
    ) -> None:
        for chunk in _chunked(keys, MAX_QUERY_PARAMETERS):
            placeholders = ", ".join("?" for _ in chunk)
            found = connection.execute(
                f"SELECT {self.primary_key} FROM {self.table.name} "
                f"WHERE {self.primary_key} IN ({placeholders}) LIMIT 1",
                chunk,
            ).fetchone()
            if found is not None:
                raise DuplicatePrimaryKeyError(self._describe_duplicate(found[0], source_file))

    def _describe_duplicate(self, key: int, source_file: str) -> str:
        earlier = [loaded.source_file for loaded in self._loaded_ranges if loaded.contains(key)]
        if not earlier:
            earlier = [loaded.source_file for loaded in self._loaded_ranges]

        return (
            f"{self.table.name}.{self.primary_key} {key} appears in {source_file} "
            f"and in {', '.join(earlier)}. The dataset is partitioned by year, so "
            f"this means two snapshots of the same data were loaded together."
        )


def create_schema(connection: sqlite3.Connection) -> None:
    """Create every table. Indexes are deliberately left until after loading."""
    for table in ALL_TABLES:
        connection.execute(table.create_table_sql())


def apply_bulk_load_pragmas(connection: sqlite3.Connection) -> None:
    """Trade durability for speed while building a throwaway file."""
    for pragma in BULK_LOAD_PRAGMAS:
        connection.execute(pragma)


def create_indexes(connection: sqlite3.Connection, progress: TextIO | None = None) -> None:
    """Build the indexes, after the data is in place rather than during the load."""
    progress = _default_progress(progress)
    for table in ALL_TABLES:
        for statement in table.create_index_sql():
            print(f"indexing: {statement}", file=progress)
            connection.execute(statement)


def load_source_file(
    connection: sqlite3.Connection,
    path: Path,
    kind: SourceKind,
    *,
    strict: bool = False,
    parse_error: str = "strict",
    guard: PrimaryKeyGuard | None = None,
    progress: TextIO | None = None,
) -> LoadReport:
    """Read one source file into its table, returning what happened."""
    progress = _default_progress(progress)
    report = LoadReport(source_file=path.name, table_name=kind.table.name)
    print(f"{path.name}: reading into {kind.table.name}", file=progress)

    with open_source_file(path, parse_error) as source_file:
        reader = csv.reader(source_file)
        plan = _plan_source_file(reader, kind, path.name)
        batches = _Batches(connection, kind, guard, path.name)

        for row in reader:
            report.rows_read += 1
            try:
                table_values, vehicles = plan.convert(row)
            except ValueError as error:
                report.rows_skipped += 1
                _warn_skipped_row(path, reader.line_num, error, strict, progress)
                continue

            batches.add(table_values, vehicles)
            report.rows_loaded += 1
            if report.rows_read % PROGRESS_INTERVAL == 0:
                print(f"{path.name}: {report.rows_read:,} rows", file=progress)

        batches.flush()

    if guard is not None:
        guard.finish_file(path.name)

    print(
        f"{path.name}: {report.rows_loaded:,} rows loaded, {report.rows_skipped:,} skipped",
        file=progress,
    )
    return report


def count_orphans(connection: sqlite3.Connection, table: Table) -> int:
    """Count rows whose collision_id matches no crash.

    Not an error. A report that straddles a year boundary lands its parties in
    one file and its crash in another, so about 0.06% of rows are orphaned
    when a single year is loaded. Enforced foreign keys would reject them;
    counting them says how much of the picture is missing.
    """
    statement = (
        f"SELECT COUNT(*) FROM {table.name} "
        f"WHERE collision_id IS NOT NULL "
        f"AND collision_id NOT IN (SELECT collision_id FROM {CRASHES.name})"
    )
    count: int = connection.execute(statement).fetchone()[0]
    return count


def record_file_load(
    connection: sqlite3.Connection,
    report: LoadReport,
    year_label: str | None = None,
) -> None:
    """Log one source file's load in the metadata table."""
    _record_metadata(
        connection,
        source_file=report.source_file,
        table_name=report.table_name,
        year_label=year_label,
        rows_read=report.rows_read,
        rows_loaded=report.rows_loaded,
        rows_skipped=report.rows_skipped,
    )


def record_orphan_count(connection: sqlite3.Connection, table: Table, orphan_rows: int) -> None:
    """Log one table's orphan count in the metadata table.

    Orphans are a property of the finished database rather than of any one
    file --- a party is orphaned only because no file supplied its crash ---
    so this is its own entry, with no source file attached.
    """
    _record_metadata(connection, table_name=table.name, orphan_rows=orphan_rows)


def _record_metadata(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    source_file: str | None = None,
    year_label: str | None = None,
    rows_read: int | None = None,
    rows_loaded: int | None = None,
    rows_skipped: int | None = None,
    orphan_rows: int | None = None,
) -> None:
    entry: dict[str, SQLiteValue] = {
        "source_file": source_file,
        "table_name": table_name,
        "year_label": year_label,
        "rows_read": rows_read,
        "rows_loaded": rows_loaded,
        "rows_skipped": rows_skipped,
        "orphan_rows": orphan_rows,
        "converter_version": __version__,
        "loaded_at": datetime.now(tz=UTC).strftime(ISO_DATETIME_FORMAT),
    }
    connection.execute(METADATA.insert_sql(), [entry[name] for name in METADATA.column_names])


@dataclass
class _SourceFilePlan:
    """The per-file setup that makes per-row work plain indexing."""

    kind: SourceKind
    field_count: int
    positions: tuple[int, ...]
    primary_key_index: int | None
    vehicle_plan: VehiclePlan | None

    def convert(self, row: Sequence[str]) -> tuple[list[SQLiteValue], list[list[SQLiteValue]]]:
        """Convert one raw row, raising ValueError if it cannot be used."""
        if len(row) != self.field_count:
            raise ValueError(f"row has {len(row)} fields, expected {self.field_count}")

        values = convert_row(self.kind.table, row, self.positions)
        if self.primary_key_index is not None and values[self.primary_key_index] is None:
            raise ValueError(f"{self.kind.table.name}.{self.kind.table.primary_key} is empty")

        vehicles = vehicle_rows(self.vehicle_plan, row) if self.vehicle_plan else []
        return values, vehicles


def _plan_source_file(
    reader: Iterator[list[str]],
    kind: SourceKind,
    source_name: str,
) -> _SourceFilePlan:
    header_row = next(reader, None)
    if header_row is None:
        raise ValueError(f"{source_name}: the file is empty")

    header_positions = index_header_row(header_row, source_name)
    check_expected_headers(header_positions, kind.expected_headers, source_name)

    primary_key = kind.table.primary_key
    return _SourceFilePlan(
        kind=kind,
        field_count=len(header_row),
        positions=column_positions(kind.table, header_positions),
        primary_key_index=(
            kind.table.column_names.index(primary_key) if primary_key is not None else None
        ),
        vehicle_plan=plan_vehicles(header_positions) if kind.splits_vehicles else None,
    )


@dataclass
class _Batches:
    """Accumulates converted rows and writes them out in bulk."""

    connection: sqlite3.Connection
    kind: SourceKind
    guard: PrimaryKeyGuard | None
    source_file: str
    table_rows: list[list[SQLiteValue]] = field(default_factory=list)
    vehicle_rows: list[list[SQLiteValue]] = field(default_factory=list)

    def add(self, table_values: list[SQLiteValue], vehicles: list[list[SQLiteValue]]) -> None:
        self.table_rows.append(table_values)
        self.vehicle_rows.extend(vehicles)
        if len(self.table_rows) >= BATCH_SIZE:
            self.flush()

    def flush(self) -> None:
        if self.table_rows:
            if self.guard is not None:
                self.guard.check_batch(self.connection, self.table_rows, self.source_file)

            self.connection.executemany(self.kind.table.insert_sql(), self.table_rows)
            self.table_rows.clear()

        if self.vehicle_rows:
            self.connection.executemany(VEHICLES.insert_sql(), self.vehicle_rows)
            self.vehicle_rows.clear()


def _warn_skipped_row(
    path: Path,
    line_number: int,
    error: ValueError,
    strict: bool,
    progress: TextIO,
) -> None:
    message = f"{path.name}:{line_number}: {error}"
    if strict:
        raise ValueError(message) from None

    print(f"warning: skipping row, {message}", file=progress)


def _default_progress(progress: TextIO | None) -> TextIO:
    """Resolve the progress stream at call time.

    Reading sys.stderr in a default argument would freeze whatever it was at
    import, which breaks anything that replaces the stream afterwards.
    """
    return sys.stderr if progress is None else progress


def _chunked(values: Sequence[SQLiteValue], size: int) -> Iterator[Sequence[SQLiteValue]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]
