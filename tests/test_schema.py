import csv
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ccrs_to_sqlite.converters import to_int, to_text
from ccrs_to_sqlite.open_record import open_source_file
from ccrs_to_sqlite.schema import (
    ALL_TABLES,
    CRASHES,
    CRASHES_SOURCE_HEADERS,
    INJURED_SOURCE_HEADERS,
    INJURED_WITNESS_PASSENGERS,
    PARTIES,
    PARTIES_SOURCE_HEADERS,
    VEHICLE_GROUP_HEADERS,
    VEHICLES,
    Column,
    Table,
    check_expected_headers,
    column_positions,
    convert_row,
    index_header_row,
    normalize_header,
    source_headers,
)

# Verbatim copies of the header rows of the real 2025 files, tabs and stray
# spaces and all. If CHP changes the format, these are what to re-capture.
HEADER_DIRECTORY = Path(__file__).parent / "data" / "headers"

SOURCE_FILES = [
    ("crashes", CRASHES_SOURCE_HEADERS),
    ("parties", PARTIES_SOURCE_HEADERS),
    ("injuredwitnesspassengers", INJURED_SOURCE_HEADERS),
]


def read_real_header_row(name):
    with open_source_file(HEADER_DIRECTORY / f"{name}.csv") as header_file:
        return next(csv.reader(header_file))


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("\tReport Number", "report number"),
        (" Weather 2", "weather 2"),
        ("Collision Id", "collision id"),
        ("IsAdditonalObjectStruck", "isadditonalobjectstruck"),
        ("Report  Number", "report number"),
        ("Crash Date Time\r\n", "crash date time"),
    ],
)
def test_normalize_header_absorbs_the_source_filth(cell, expected):
    assert normalize_header(cell) == expected


@pytest.mark.parametrize(("name", "expected_headers"), SOURCE_FILES)
def test_every_real_header_is_mapped_and_every_mapping_is_real(name, expected_headers):
    """The mapping and the real file agree in both directions, or the load stops."""
    header_positions = index_header_row(read_real_header_row(name), name)

    check_expected_headers(header_positions, expected_headers, name)


@pytest.mark.parametrize(("name", "expected_headers"), SOURCE_FILES)
def test_the_real_header_rows_have_the_documented_width(name, expected_headers):
    assert len(read_real_header_row(name)) == len(expected_headers)


def test_column_names_are_unique_within_a_table():
    for table in ALL_TABLES:
        assert len(set(table.column_names)) == len(table.column_names), table.name


def test_source_headers_are_unique_within_a_table():
    """Only Crash Date Time may feed more than one column, and it feeds exactly two."""
    headers = [
        column.source_header for column in CRASHES.columns if column.source_header is not None
    ]

    repeated = {header for header in headers if headers.count(header) > 1}
    assert repeated == {"Crash Date Time"}


def test_crash_date_time_splits_into_a_date_and_a_time():
    split_columns = [
        column.name for column in CRASHES.columns if column.source_header == "Crash Date Time"
    ]

    assert split_columns == ["crash_date", "crash_time"]


def test_computed_tables_read_no_headers_directly():
    assert source_headers(VEHICLES) == frozenset()


def test_the_vehicle_groups_fill_the_same_vehicles_columns():
    computed_by_the_splitter = {"party_id", "collision_id", "vehicle_number"}
    filled_from_headers = set(VEHICLES.column_names) - computed_by_the_splitter - {"make"}

    for group in VEHICLE_GROUP_HEADERS:
        assert set(group) == filled_from_headers


def test_the_parties_table_does_not_also_keep_the_vehicle_columns():
    assert not any(name.startswith("vehicle") for name in PARTIES.column_names)


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda table: table.name)
def test_every_table_creates_cleanly_in_sqlite(table):
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(table.create_table_sql())
        for statement in table.create_index_sql():
            connection.execute(statement)

        stored = connection.execute(
            "SELECT name FROM pragma_table_info(?)", (table.name,)
        ).fetchall()

    assert [row[0] for row in stored] == list(table.column_names)


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda table: table.name)
def test_every_table_is_strict(table):
    """Type affinity would let 'abc' into an INTEGER column; STRICT is the point of converting."""
    assert table.create_table_sql().endswith(") STRICT")


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda table: table.name)
def test_insert_statements_name_their_columns(table):
    statement = table.insert_sql()

    assert statement.startswith(f"INSERT INTO {table.name} (")
    for name in table.column_names:
        assert name in statement
    assert statement.count("?") == len(table.columns)


def test_a_declared_primary_key_reaches_the_ddl():
    assert "collision_id INTEGER PRIMARY KEY" in CRASHES.create_table_sql()


def test_index_statements_cover_the_declared_indexes():
    assert PARTIES.create_index_sql() == [
        "CREATE INDEX index_parties_collision_id ON parties (collision_id)"
    ]
    assert CRASHES.create_index_sql() == [
        "CREATE INDEX index_crashes_crash_date ON crashes (crash_date)"
    ]


def test_index_header_row_rejects_a_repeated_header():
    with pytest.raises(ValueError, match="appears more than once"):
        index_header_row(["Collision Id", "\tCollision Id"], "crashes_2025.csv")


def test_an_unrecognized_header_is_fatal():
    """A new CHP column has to be a decision, not a silently dropped field."""
    header_positions = index_header_row([*read_real_header_row("crashes"), "NewCHPColumn"], "x")

    with pytest.raises(ValueError, match="unrecognized headers: newchpcolumn"):
        check_expected_headers(header_positions, CRASHES_SOURCE_HEADERS, "crashes_2025.csv")


def test_a_missing_header_is_fatal():
    header_positions = index_header_row(read_real_header_row("crashes")[1:], "x")

    with pytest.raises(ValueError, match="missing expected headers: collision id"):
        check_expected_headers(header_positions, CRASHES_SOURCE_HEADERS, "crashes_2025.csv")


def test_column_positions_follows_the_header_row_not_the_column_order():
    table = Table(
        name="example",
        columns=(
            Column("collision_id", "INTEGER", to_int, "Collision Id"),
            Column("beat", "TEXT", to_text, "Beat"),
        ),
    )
    header_positions = index_header_row([" Beat", "\tCollision Id"], "example.csv")

    assert column_positions(table, header_positions) == (1, 0)


def test_column_positions_refuses_a_computed_table():
    with pytest.raises(ValueError, match="is computed, not read from a header"):
        column_positions(VEHICLES, {})


def test_convert_row_types_the_values():
    header_positions = index_header_row(read_real_header_row("injuredwitnesspassengers"), "iwp")
    positions = column_positions(INJURED_WITNESS_PASSENGERS, header_positions)
    row = [""] * len(header_positions)
    row[header_positions["injuredwitpassid"]] = "5318055"
    row[header_positions["iswitnessonly"]] = "True"
    row[header_positions["gender desc"]] = " FEMALE "

    values = dict(
        zip(
            INJURED_WITNESS_PASSENGERS.column_names,
            convert_row(INJURED_WITNESS_PASSENGERS, row, positions),
            strict=True,
        )
    )

    assert values["injured_wit_pass_id"] == 5318055
    assert values["is_witness_only"] == 1
    assert values["gender_description"] == "FEMALE"
    assert values["party_number"] is None


def test_convert_row_names_the_column_that_failed():
    header_positions = index_header_row(read_real_header_row("crashes"), "crashes")
    positions = column_positions(CRASHES, header_positions)
    row = [""] * len(header_positions)
    row[header_positions["collision id"]] = "not a number"

    with pytest.raises(ValueError, match=r"crashes\.collision_id: expected an integer"):
        convert_row(CRASHES, row, positions)
