import csv
import sqlite3
from collections.abc import Callable
from contextlib import closing
from pathlib import Path

import pytest

from ccrs_to_sqlite.converters import (
    to_bool,
    to_date,
    to_datetime,
    to_int,
    to_real,
    to_text,
    to_time,
    to_time_description,
    to_time_of_day,
)
from ccrs_to_sqlite.open_record import open_source_file
from ccrs_to_sqlite.schema import (
    ALL_TABLES,
    CRASHES,
    CRASHES_SOURCE_HEADERS,
    INJURED_SOURCE_HEADERS,
    INJURED_WITNESS_PASSENGERS,
    METADATA,
    METADATA_RECORD_TYPES,
    PARTIES,
    PARTIES_SOURCE_HEADERS,
    SCHEMA_VERSION,
    VEHICLE_GROUP_HEADERS,
    VEHICLES,
    Column,
    PairedColumn,
    SQLiteValue,
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


TIME_PAIRINGS = [
    ("crash", "Crash Date Time", "Crash Time Description"),
    ("notification", "NotificationDate", "NotificationTimeDescription"),
]


@pytest.mark.parametrize(("prefix", "merged", "described"), TIME_PAIRINGS)
def test_a_merged_datetime_becomes_a_date_a_resolved_time_and_both_raw_inputs(
    prefix, merged, described
):
    """The date comes from the merged column; the time needs both sources to settle."""
    merged_header, described_header = normalize_header(merged), normalize_header(described)

    assert CRASHES.column(f"{prefix}_date").normalized_source_headers == (merged_header,)
    assert CRASHES.column(f"{prefix}_time").normalized_source_headers == (
        merged_header,
        described_header,
    )
    assert CRASHES.column(f"{prefix}_time_description").normalized_source_headers == (
        described_header,
    )
    assert CRASHES.column(f"{prefix}_time_merged").normalized_source_headers == (merged_header,)


@pytest.mark.parametrize(("prefix", "merged", "described"), TIME_PAIRINGS)
def test_both_inputs_to_a_resolved_time_survive_into_the_database(prefix, merged, described):
    """`make_raw` parity: a resolved value is only auditable if what it rejected is kept.

    The date column takes only the date half of the merged column, so without
    a raw column of its own the merged time is discarded — and on the rows
    where the two sources disagree, nothing in the row would show it.
    """
    header_positions = index_header_row(read_real_header_row("crashes"), "crashes")
    positions = column_positions(CRASHES, header_positions)
    row = [""] * len(header_positions)
    row[header_positions[normalize_header(merged)]] = "1/14/2025 7:50:00 AM"
    row[header_positions[normalize_header(described)]] = "1520"

    values = dict(zip(CRASHES.column_names, convert_row(CRASHES, row, positions), strict=True))

    assert values[f"{prefix}_date"] == "2025-01-14"
    assert values[f"{prefix}_time"] == "15:20:00"
    assert values[f"{prefix}_time_description"] == "1520"
    assert values[f"{prefix}_time_merged"] == "07:50:00"


def test_computed_tables_read_no_headers_directly():
    assert source_headers(VEHICLES) == frozenset()


def test_the_vehicle_groups_fill_the_same_vehicles_columns():
    computed_by_the_splitter = {"party_id", "collision_id", "vehicle_number"}
    # make and the two colour columns are derived from a raw column rather
    # than read from a header of their own.
    derived = {"make", "color", "color_secondary"}
    filled_from_headers = set(VEHICLES.column_names) - computed_by_the_splitter - derived

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
    """collision_id + party_number is the link from a person to a party; both sides carry it."""
    assert ("collision_id", "party_number") in PARTIES.indexes
    assert ("collision_id", "party_number") in INJURED_WITNESS_PASSENGERS.indexes


# Every parent/child pair the schema declares. Enforcement stays off, so these
# exist to be read out of the file by tools rather than to reject anything.
DECLARED_FOREIGN_KEYS = [
    ("parties", "collision_id", "crashes", "collision_id"),
    ("vehicles", "party_id", "parties", "party_id"),
    ("vehicles", "collision_id", "crashes", "collision_id"),
    ("injured_witness_passengers", "collision_id", "crashes", "collision_id"),
]


def test_the_relationships_are_declared_in_the_file_not_only_in_the_readme():
    """Datasette, SQLite browsers and ORMs all draw the graph from foreign_key_list."""
    declared = []
    with closing(sqlite3.connect(":memory:")) as connection:
        for table in ALL_TABLES:
            connection.execute(table.create_table_sql())

        for table in ALL_TABLES:
            for row in connection.execute(
                "SELECT * FROM pragma_foreign_key_list(?)", (table.name,)
            ):
                _, _, parent_table, child_column, parent_column = row[:5]
                declared.append((table.name, child_column, parent_table, parent_column))

    assert sorted(declared) == sorted(DECLARED_FOREIGN_KEYS)


def test_every_declared_foreign_key_points_at_a_primary_key():
    """SQLite needs a unique parent, and an unenforced key that names a non-key is a lie."""
    by_name = {table.name: table for table in ALL_TABLES}
    for _, _, parent_table, parent_column in DECLARED_FOREIGN_KEYS:
        assert by_name[parent_table].primary_key == (parent_column,)


def test_foreign_keys_are_declared_but_left_unenforced():
    """A cross-year report puts a party in one file and its crash in another.

    Enforcement would reject those real rows, so the default off state of
    PRAGMA foreign_keys is load-bearing rather than an oversight.
    """
    with closing(sqlite3.connect(":memory:")) as connection:
        for table in ALL_TABLES:
            connection.execute(table.create_table_sql())

        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0

        orphan: list[SQLiteValue] = [None] * len(PARTIES.columns)
        orphan[PARTIES.column_names.index("party_id")] = 1
        orphan[PARTIES.column_names.index("collision_id")] = 999
        connection.execute(PARTIES.insert_sql(), orphan)

        assert connection.execute("SELECT COUNT(*) FROM parties").fetchone()[0] == 1


AnyConverter = Callable[..., SQLiteValue]

CONVERTERS_BY_SQL_TYPE: dict[str, set[AnyConverter]] = {
    "TEXT": {to_text, to_date, to_datetime, to_time, to_time_description, to_time_of_day},
    "INTEGER": {to_int, to_bool},
    "REAL": {to_real},
}


def converter_of(column: Column | PairedColumn) -> AnyConverter:
    return column.convert if isinstance(column, Column) else column.resolve


@pytest.mark.parametrize("table", ALL_TABLES, ids=lambda table: table.name)
def test_every_column_is_typed_the_way_its_converter_returns(table):
    """`Column("latitude", INTEGER, to_real)` passes mypy and fails at insert time.

    The Converter alias erases which of the three types a converter produces,
    so nothing in the type system ties the two halves of a column together.
    On a STRICT table the mismatch surfaces mid-load, thousands of rows in.
    """
    for column in table.columns:
        converter = converter_of(column)

        assert converter in CONVERTERS_BY_SQL_TYPE[column.sql_type], (
            f"{table.name}.{column.name} is {column.sql_type} but is filled by {converter.__name__}"
        )


def test_every_converter_is_accounted_for():
    """Otherwise a new converter is simply absent from the check above."""
    checked = {converter for group in CONVERTERS_BY_SQL_TYPE.values() for converter in group}
    used = {converter_of(column) for table in ALL_TABLES for column in table.columns}

    assert used <= checked


# The exact DDL this package promises to produce, regenerated with
# `just schema-snapshot` when a schema change is deliberate.
SCHEMA_SNAPSHOT = Path(__file__).parent / "data" / "schema.sql"


def rendered_schema():
    """The whole schema as one text, in the order create_schema writes it."""
    statements = [f"PRAGMA user_version = {SCHEMA_VERSION};"]
    for table in ALL_TABLES:
        statements.append(f"{table.create_table_sql()};")
    for table in ALL_TABLES:
        statements.extend(f"{statement};" for statement in table.create_index_sql())

    return "\n\n".join(statements) + "\n"


def test_the_schema_matches_the_checked_in_snapshot():
    """The schema is the deliverable, and from v1.0 it is frozen.

    Line coverage cannot see a rename or a retype --- every test still passes
    with `latitude` spelled `lattitude`. This is the one test that fails, so
    that changing the shape of the database is always a deliberate act with a
    reviewable diff rather than something that ships by accident.
    """
    assert rendered_schema() == SCHEMA_SNAPSHOT.read_text(encoding="utf-8")


def test_metadata_requires_the_fields_this_tool_always_writes():
    """These four are written on every path, so a NULL in one means a bug upstream."""
    always_written = ["record_type", "table_name", "converter_version", "loaded_at_utc"]
    values = dict.fromkeys(METADATA.column_names)
    values["record_type"] = "file_load"
    values["table_name"] = "crashes"
    values["converter_version"] = "0.1.0"
    values["loaded_at_utc"] = "2026-01-01 00:00:00"

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(METADATA.create_table_sql())
        connection.execute(METADATA.insert_sql(), list(values.values()))

        for name in always_written:
            missing = {**values, name: None}
            with pytest.raises(sqlite3.IntegrityError, match="NOT NULL"):
                connection.execute(METADATA.insert_sql(), list(missing.values()))


def test_metadata_states_its_closed_set_of_record_types_in_the_schema():
    """Otherwise the two kinds exist only as Python constants a consumer never sees."""
    values = dict.fromkeys(METADATA.column_names)
    values["table_name"] = "crashes"
    values["converter_version"] = "0.1.0"
    values["loaded_at_utc"] = "2026-01-01 00:00:00"

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute(METADATA.create_table_sql())
        for record_type in METADATA_RECORD_TYPES:
            connection.execute(
                METADATA.insert_sql(), list({**values, "record_type": record_type}.values())
            )

        with pytest.raises(sqlite3.IntegrityError, match="CHECK constraint failed"):
            connection.execute(
                METADATA.insert_sql(), list({**values, "record_type": "invented"}.values())
            )


def test_the_fact_tables_carry_no_check_constraints():
    """Forty boolean columns times twenty million rows is not where to spend on a CHECK.

    The converters already guarantee 0/1/NULL, and the cost would be paid on
    every insert forever.
    """
    for table in [CRASHES, PARTIES, VEHICLES, INJURED_WITNESS_PASSENGERS]:
        assert table.check_constraints == (), table.name


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

    assert values["injured_witness_passenger_id"] == 5318055
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
