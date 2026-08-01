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


def test_only_the_paired_time_sources_feed_more_than_one_column():
    """A header read twice should mean a deliberate pairing, not an accident."""
    headers = [header for column in CRASHES.columns for header in column.normalized_source_headers]
    repeated = {header for header in headers if headers.count(header) > 1}

    assert repeated == {
        "crash date time",
        "crash time description",
        "notificationdate",
        "notificationtimedescription",
    }


@pytest.mark.parametrize(
    ("date_column", "time_column", "description_column", "merged", "described"),
    [
        (
            "crash_date",
            "crash_time",
            "crash_time_description",
            "Crash Date Time",
            "Crash Time Description",
        ),
        (
            "notification_date",
            "notification_time",
            "notification_time_description",
            "NotificationDate",
            "NotificationTimeDescription",
        ),
    ],
)
def test_a_merged_datetime_becomes_a_date_a_resolved_time_and_the_raw_description(
    date_column, time_column, description_column, merged, described
):
    """The date comes from the merged column; the time needs both sources to settle."""
    merged_header, described_header = normalize_header(merged), normalize_header(described)

    assert CRASHES.column(date_column).normalized_source_headers == (merged_header,)
    assert CRASHES.column(time_column).normalized_source_headers == (
        merged_header,
        described_header,
    )
    assert CRASHES.column(description_column).normalized_source_headers == (described_header,)


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
    assert CRASHES.create_index_sql() == [
        "CREATE INDEX index_crashes_crash_date ON crashes (crash_date)"
    ]
    assert PARTIES.create_index_sql() == [
        "CREATE INDEX index_parties_collision_id_party_number "
        "ON parties (collision_id, party_number)"
    ]


def test_a_composite_primary_key_is_declared_at_table_level():
    """vehicles is the one table invented here, so it has to declare its own identity."""
    assert VEHICLES.primary_key == ("party_id", "vehicle_number")
    assert "PRIMARY KEY (party_id, vehicle_number)" in VEHICLES.create_table_sql()
    assert VEHICLES.rowid_alias is None


@pytest.mark.parametrize("table", [CRASHES, PARTIES, INJURED_WITNESS_PASSENGERS])
def test_source_keyed_tables_alias_the_rowid(table):
    """A single INTEGER primary key is the rowid itself, which the loader relies on."""
    assert table.rowid_alias == table.primary_key[0]
    assert f"{table.rowid_alias} INTEGER PRIMARY KEY" in table.create_table_sql()


def test_no_index_repeats_a_primary_key():
    """A primary key builds its own index; a second copy would be paid for twice."""
    for table in ALL_TABLES:
        assert table.primary_key not in table.indexes, table.name


def test_the_documented_person_to_party_link_is_indexed():
    """plan.md names collision_id + party_number as the link; both sides carry it."""
    assert ("collision_id", "party_number") in PARTIES.indexes
    assert ("collision_id", "party_number") in INJURED_WITNESS_PASSENGERS.indexes


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

    assert column_positions(table, header_positions) == ((1,), (0,))


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


@pytest.mark.parametrize(
    ("column_name", "source_header", "cell"),
    [
        ("city_code", "City Code", "0109"),
        ("ncic_code", "NCIC Code", "0109"),
        ("beat", "Beat", "027"),
    ],
)
def test_zero_padded_codes_keep_their_padding(column_name, source_header, cell):
    """These are fixed-width codes, not numbers; INTEGER would drop the leading zero."""
    header_positions = index_header_row(read_real_header_row("crashes"), "crashes")
    positions = column_positions(CRASHES, header_positions)
    row = [""] * len(header_positions)
    row[header_positions[normalize_header(source_header)]] = cell

    values = dict(zip(CRASHES.column_names, convert_row(CRASHES, row, positions), strict=True))

    assert values[column_name] == cell


def test_county_code_stays_numeric():
    """It runs 1 to 58 and is never padded, so it is a number rather than a code."""
    assert CRASHES.column("county_code").sql_type == "INTEGER"


def test_convert_row_names_the_column_that_failed():
    header_positions = index_header_row(read_real_header_row("crashes"), "crashes")
    positions = column_positions(CRASHES, header_positions)
    row = [""] * len(header_positions)
    row[header_positions["collision id"]] = "not a number"

    with pytest.raises(ValueError, match=r"crashes\.collision_id: expected an integer"):
        convert_row(CRASHES, row, positions)
