import csv
import io
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ccrs_to_sqlite import __version__
from ccrs_to_sqlite.load import (
    CRASHES_SOURCE,
    INJURED_SOURCE,
    ORPHAN_CHECKED_TABLES,
    PARTIES_SOURCE,
    SCHEMA_VERSION,
    DuplicatePrimaryKeyError,
    PrimaryKeyGuard,
    apply_bulk_load_pragmas,
    count_orphans,
    create_indexes,
    create_schema,
    load_source_file,
    record_file_load,
    record_orphan_count,
)
from ccrs_to_sqlite.open_record import open_source_file
from ccrs_to_sqlite.schema import (
    CRASHES,
    FILE_LOAD_RECORD,
    INJURED_WITNESS_PASSENGERS,
    ORPHAN_COUNT_RECORD,
    PARTIES,
    VEHICLES,
)

HEADER_DIRECTORY = Path(__file__).parent / "data" / "headers"


def header_cells(name):
    with open_source_file(HEADER_DIRECTORY / f"{name}.csv") as header_file:
        return next(csv.reader(header_file))


def write_source_file(directory, name, rows):
    """Write a source file with the real header row and the given cell dictionaries."""
    header = header_cells(name)
    positions = {cell.strip().lower(): index for index, cell in enumerate(header)}

    path = directory / f"{name}_2025.csv"
    with path.open("w", newline="", encoding="utf-8") as source_file:
        writer = csv.writer(source_file)
        writer.writerow(header)
        for cells in rows:
            row = [""] * len(header)
            for source_header, value in cells.items():
                row[positions[source_header]] = value
            writer.writerow(row)

    return path


def a_crash(collision_id, **cells):
    return {
        "collision id": str(collision_id),
        "crash date time": "1/14/2025 7:50:00 AM",
        "city name": "San Mateo",
        **cells,
    }


def a_party(party_id, collision_id, **cells):
    return {"partyid": str(party_id), "collisionid": str(collision_id), **cells}


def a_person(person_id, collision_id, **cells):
    return {"injuredwitpassid": str(person_id), "collisionid": str(collision_id), **cells}


@pytest.fixture
def connection():
    with closing(sqlite3.connect(":memory:")) as open_connection:
        apply_bulk_load_pragmas(open_connection)
        create_schema(open_connection)
        yield open_connection


@pytest.fixture
def progress():
    return io.StringIO()


def load(connection, path, kind, progress, **keywords):
    return load_source_file(connection, path, kind, progress=progress, **keywords)


def stored(connection, table, *column_names):
    names = ", ".join(column_names)
    return connection.execute(f"SELECT {names} FROM {table.name}").fetchall()


def test_a_crashes_file_lands_typed_in_the_crashes_table(tmp_path, connection, progress):
    path = write_source_file(
        tmp_path,
        "crashes",
        [a_crash(4550266, **{"latitude": "32.742237", "is preliminary": "False"})],
    )

    report = load(connection, path, CRASHES_SOURCE, progress)

    assert (report.rows_read, report.rows_loaded, report.rows_skipped) == (1, 1, 0)
    assert stored(connection, CRASHES, "collision_id", "crash_date", "crash_time") == [
        (4550266, "2025-01-14", "07:50:00")
    ]
    assert stored(connection, CRASHES, "latitude", "is_preliminary") == [(32.742237, 0)]


def test_a_parties_file_fills_both_parties_and_vehicles(tmp_path, connection, progress):
    path = write_source_file(
        tmp_path,
        "parties",
        [
            a_party(1, 4541904, vehicle1make="TOYT", vehicle2make="GDAN"),
            a_party(2, 4541904, vehicle1make="FORD"),
            a_party(3, 4541904),
        ],
    )

    report = load(connection, path, PARTIES_SOURCE, progress)

    assert report.rows_loaded == 3
    assert stored(connection, PARTIES, "party_id") == [(1,), (2,), (3,)]
    assert stored(connection, VEHICLES, "party_id", "vehicle_number", "make_raw", "make") == [
        (1, 1, "TOYT", "TOYOTA"),
        (1, 2, "GDAN", None),
        (2, 1, "FORD", "FORD"),
    ]


def test_an_injured_file_loads(tmp_path, connection, progress):
    path = write_source_file(
        tmp_path,
        "injuredwitnesspassengers",
        [a_person(5318055, 4547137, iswitnessonly="True")],
    )

    load(connection, path, INJURED_SOURCE, progress)

    assert stored(
        connection, INJURED_WITNESS_PASSENGERS, "injured_wit_pass_id", "is_witness_only"
    ) == [(5318055, 1)]


def test_a_ragged_row_is_skipped_and_counted(tmp_path, connection, progress):
    path = write_source_file(tmp_path, "crashes", [a_crash(1), a_crash(2)])
    with path.open("a", newline="", encoding="utf-8") as source_file:
        source_file.write("3,extra,fields\r\n")

    report = load(connection, path, CRASHES_SOURCE, progress)

    assert (report.rows_read, report.rows_loaded, report.rows_skipped) == (3, 2, 1)
    assert stored(connection, CRASHES, "collision_id") == [(1,), (2,)]


def test_a_skipped_row_warning_names_the_file_line_and_field_count(tmp_path, connection, progress):
    path = write_source_file(tmp_path, "crashes", [a_crash(1)])
    with path.open("a", newline="", encoding="utf-8") as source_file:
        source_file.write("3,extra,fields\r\n")

    load(connection, path, CRASHES_SOURCE, progress)

    assert "crashes_2025.csv:3: row has 3 fields, expected 74" in progress.getvalue()


def test_strict_makes_a_ragged_row_fatal(tmp_path, connection, progress):
    """Aborting a twenty-minute load by default is hostile; asking for it is not."""
    path = write_source_file(tmp_path, "crashes", [a_crash(1)])
    with path.open("a", newline="", encoding="utf-8") as source_file:
        source_file.write("3,extra,fields\r\n")

    with pytest.raises(ValueError, match="row has 3 fields"):
        load(connection, path, CRASHES_SOURCE, progress, strict=True)


def test_a_row_with_an_unconvertible_value_is_skipped(tmp_path, connection, progress):
    path = write_source_file(tmp_path, "crashes", [a_crash(1), a_crash(2, **{"latitude": "north"})])

    report = load(connection, path, CRASHES_SOURCE, progress)

    assert report.rows_skipped == 1
    assert "crashes.latitude: expected a number" in progress.getvalue()
    assert stored(connection, CRASHES, "collision_id") == [(1,)]


def test_a_row_without_a_primary_key_is_skipped(tmp_path, connection, progress):
    """An empty INTEGER PRIMARY KEY would be silently auto-assigned a rowid."""
    path = write_source_file(tmp_path, "crashes", [a_crash(1), {"city name": "Fresno"}])

    report = load(connection, path, CRASHES_SOURCE, progress)

    assert report.rows_skipped == 1
    assert "crashes.collision_id is empty" in progress.getvalue()
    assert stored(connection, CRASHES, "collision_id") == [(1,)]


def test_an_unrecognized_header_stops_the_load(tmp_path, connection, progress):
    path = tmp_path / "crashes_2025.csv"
    path.write_text("Collision Id,SomethingNew\r\n1,x\r\n", encoding="utf-8")

    with pytest.raises(ValueError, match="unrecognized headers"):
        load(connection, path, CRASHES_SOURCE, progress)


def test_an_empty_file_stops_the_load(tmp_path, connection, progress):
    path = tmp_path / "crashes_2025.csv"
    path.write_bytes(b"")

    with pytest.raises(ValueError, match="the file is empty"):
        load(connection, path, CRASHES_SOURCE, progress)


def test_progress_names_the_file_and_reports_the_totals(tmp_path, connection, progress):
    path = write_source_file(tmp_path, "crashes", [a_crash(1), a_crash(2)])

    load(connection, path, CRASHES_SOURCE, progress)

    output = progress.getvalue()
    assert "crashes_2025.csv: reading into crashes" in output
    assert "crashes_2025.csv: 2 rows loaded, 0 skipped" in output


def test_one_file_per_table_needs_no_duplicate_probing(tmp_path, connection, progress):
    path = write_source_file(tmp_path, "crashes", [a_crash(1), a_crash(2)])
    guard = PrimaryKeyGuard(CRASHES)

    report = load(connection, path, CRASHES_SOURCE, progress, guard=guard)

    assert report.rows_loaded == 2


def test_a_key_repeated_across_two_files_is_fatal(tmp_path, connection, progress):
    first = write_source_file(tmp_path, "crashes", [a_crash(4550266)])
    guard = PrimaryKeyGuard(CRASHES)
    load(connection, first, CRASHES_SOURCE, progress, guard=guard)

    second_directory = tmp_path / "again"
    second_directory.mkdir()
    second = write_source_file(second_directory, "crashes", [a_crash(4550266)])

    with pytest.raises(DuplicatePrimaryKeyError, match=r"crashes\.collision_id 4550266"):
        load(connection, second, CRASHES_SOURCE, progress, guard=guard)


def test_the_duplicate_message_points_at_the_file_that_supplied_the_key_first(
    tmp_path, connection, progress
):
    """The guard remembers each file's key span, so it can say which load to blame."""
    guard = PrimaryKeyGuard(CRASHES)
    for name, keys in (("first", (10, 20)), ("second", (30, 40))):
        directory = tmp_path / name
        directory.mkdir()
        load(
            connection,
            write_source_file(directory, "crashes", [a_crash(key) for key in keys]),
            CRASHES_SOURCE,
            progress,
            guard=guard,
        )

    third_directory = tmp_path / "third"
    third_directory.mkdir()
    overlapping = write_source_file(third_directory, "crashes", [a_crash(30)])

    with pytest.raises(DuplicatePrimaryKeyError) as failure:
        load(connection, overlapping, CRASHES_SOURCE, progress, guard=guard)

    assert "crashes.collision_id 30" in str(failure.value)
    assert "crashes_2025.csv and in crashes_2025.csv" in str(failure.value)
    assert "two snapshots" in str(failure.value)


def test_a_table_without_a_single_column_key_cannot_be_guarded():
    """vehicles has a composite key, which is not a rowid and needs no guard."""
    with pytest.raises(ValueError, match="has no single-column primary key to guard"):
        PrimaryKeyGuard(VEHICLES)


def test_orphans_are_counted_not_rejected(tmp_path, connection, progress):
    """Reports straddling a year boundary leave real rows pointing at another year's crash."""
    crashes = write_source_file(tmp_path, "crashes", [a_crash(100)])
    parties = write_source_file(tmp_path, "parties", [a_party(1, 100), a_party(2, 999)])
    load(connection, crashes, CRASHES_SOURCE, progress)
    load(connection, parties, PARTIES_SOURCE, progress)

    assert count_orphans(connection, PARTIES) == 1
    assert stored(connection, PARTIES, "party_id") == [(1,), (2,)]


def test_a_row_with_no_collision_id_is_not_an_orphan(tmp_path, connection, progress):
    parties = write_source_file(tmp_path, "parties", [{"partyid": "1"}])
    load(connection, parties, PARTIES_SOURCE, progress)

    assert count_orphans(connection, PARTIES) == 0


@pytest.mark.parametrize("table", ORPHAN_CHECKED_TABLES, ids=lambda table: table.name)
def test_every_orphan_checked_table_can_be_counted(connection, table):
    assert count_orphans(connection, table) == 0


def test_indexes_are_built_after_loading(connection, progress):
    create_indexes(connection, progress)

    indexes = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'index_%'"
    ).fetchall()

    assert sorted(name for (name,) in indexes) == [
        "index_crashes_crash_date",
        "index_injured_witness_passengers_collision_id_party_number",
        "index_parties_collision_id_party_number",
        "index_vehicles_collision_id",
    ]


def test_a_file_load_is_logged_in_metadata(tmp_path, connection, progress):
    path = write_source_file(tmp_path, "crashes", [a_crash(1)])
    report = load(connection, path, CRASHES_SOURCE, progress)

    record_file_load(connection, report, year_label="2025")

    logged = connection.execute(
        "SELECT record_type, table_name, source_file, year_label, rows_read, rows_loaded,"
        " rows_skipped, orphan_rows, converter_version FROM metadata"
    ).fetchall()
    assert logged == [
        (FILE_LOAD_RECORD, "crashes", "crashes_2025.csv", "2025", 1, 1, 0, None, __version__)
    ]


def test_an_orphan_count_is_logged_as_its_own_record_type(connection):
    """Orphans belong to the finished database, not to any one file."""
    record_orphan_count(connection, PARTIES, 455)

    logged = connection.execute(
        "SELECT record_type, table_name, source_file, orphan_rows FROM metadata"
    ).fetchall()
    assert logged == [(ORPHAN_COUNT_RECORD, "parties", None, 455)]


def test_the_two_record_types_are_told_apart_by_record_type_not_by_nulls(
    tmp_path, connection, progress
):
    path = write_source_file(tmp_path, "crashes", [a_crash(1)])
    record_file_load(connection, load(connection, path, CRASHES_SOURCE, progress))
    record_orphan_count(connection, PARTIES, 455)

    kinds = connection.execute(
        "SELECT record_type, COUNT(*) FROM metadata GROUP BY record_type ORDER BY record_type"
    ).fetchall()

    assert kinds == [(FILE_LOAD_RECORD, 1), (ORPHAN_COUNT_RECORD, 1)]


def test_metadata_timestamps_are_iso(connection):
    record_orphan_count(connection, PARTIES, 0)

    loaded_at = connection.execute("SELECT loaded_at_utc FROM metadata").fetchone()[0]

    assert len(loaded_at) == len("2025-01-14 07:50:00")
    assert loaded_at[4] == loaded_at[7] == "-"


def test_the_schema_version_is_stamped_into_the_file(connection):
    """A consumer should be able to check the shape without introspecting it."""
    assert connection.execute("PRAGMA user_version").fetchone()[0] == SCHEMA_VERSION
    assert SCHEMA_VERSION > 0


def test_bulk_load_pragmas_take_effect(connection):
    journal_mode = connection.execute("PRAGMA journal_mode").fetchone()[0]

    assert journal_mode.lower() == "off"
