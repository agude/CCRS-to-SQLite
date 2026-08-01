"""The database shape, and the map from CCRS headers onto it.

One table definition per output table, each column naming the source header it
reads and the converter that types it. The loader does nothing but walk these
lists, so this module is the single place where "what does the database look
like" is answered.

Two rules from plan.md shape everything here:

* Mapping is header-driven, never positional. The source header rows are
  filthy --- literal tabs after commas, leading spaces, CRLF endings, a
  spelling error, three naming conventions mixed --- and CHP reorders and
  renames columns between releases. Headers are normalized and looked up by
  name, and anything unrecognized is a hard error.
* Code and description columns are both kept. They are source data, they are
  cheap, and they occasionally disagree with each other; dropping either
  loses information.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass

from ccrs_to_sqlite.converters import (
    to_bool,
    to_date,
    to_datetime,
    to_int,
    to_real,
    to_text,
    to_time,
    to_time_description,
)

SQLiteValue = str | int | float | None
Converter = Callable[[str], SQLiteValue]

INTEGER = "INTEGER"
REAL = "REAL"
TEXT = "TEXT"

_WHITESPACE_RUN = re.compile(r"\s+")


def normalize_header(cell: str) -> str:
    """Reduce a raw header cell to the form used for matching.

    Strips, collapses interior whitespace runs (which include the literal tabs
    the source leaves after commas) to a single space, and lowercases. That
    makes `\\tReport Number`, `Report  Number`, and `report number` the same
    header, while still refusing to match a genuinely new one.
    """
    return _WHITESPACE_RUN.sub(" ", cell).strip().lower()


@dataclass(frozen=True)
class Column:
    """One output column, and where its value comes from.

    `source_header` is the header spelled as the source spells it, kept
    verbatim so this file reads as documentation of the upstream format.
    It is None for columns the loader computes rather than reads.
    """

    name: str
    sql_type: str
    convert: Converter
    source_header: str | None = None

    @property
    def normalized_source_header(self) -> str | None:
        if self.source_header is None:
            return None

        return normalize_header(self.source_header)


@dataclass(frozen=True)
class Table:
    """One output table."""

    name: str
    columns: tuple[Column, ...]
    # One column for the tables the source keys itself; several for a table
    # whose identity is a combination, as `vehicles` is.
    primary_key: tuple[str, ...] = ()
    # Each entry is one index, over one or more columns in order.
    indexes: tuple[tuple[str, ...], ...] = ()

    @property
    def column_names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)

    @property
    def rowid_alias(self) -> str | None:
        """The single INTEGER column that is this table's primary key, if it has one.

        Such a column *is* SQLite's rowid rather than a copy of it, which is
        why the loader can rely on the engine to reject a duplicate. A
        composite key gets no such treatment.
        """
        if len(self.primary_key) != 1:
            return None

        name = self.primary_key[0]
        return name if self.column(name).sql_type == INTEGER else None

    def column(self, name: str) -> Column:
        """Return the named column, or raise KeyError."""
        for column in self.columns:
            if column.name == name:
                return column

        raise KeyError(f"{self.name} has no column named {name!r}")

    def create_table_sql(self) -> str:
        """Return the CREATE TABLE statement for this table.

        Tables are STRICT: the whole point of converting off CSV is to get
        types, and SQLite's default type affinity would happily store the
        string 'abc' in an INTEGER column.
        """
        definitions = [
            f"    {column.name} {column.sql_type}"
            + (" PRIMARY KEY" if column.name == self.rowid_alias else "")
            for column in self.columns
        ]
        if self.primary_key and self.rowid_alias is None:
            definitions.append(f"    PRIMARY KEY ({', '.join(self.primary_key)})")

        body = ",\n".join(definitions)
        return f"CREATE TABLE {self.name} (\n{body}\n) STRICT"

    def create_index_sql(self) -> list[str]:
        """Return the CREATE INDEX statements, run after loading rather than before.

        A primary key already builds its own index, so nothing here repeats
        one: `vehicles(party_id, vehicle_number)` serves lookups by party as
        well, since a lookup can use any leading run of an index's columns.
        """
        return [
            f"CREATE INDEX index_{self.name}_{'_'.join(columns)} "
            f"ON {self.name} ({', '.join(columns)})"
            for columns in self.indexes
        ]

    def insert_sql(self) -> str:
        """Return the INSERT statement, with every column named.

        Naming the columns costs a line and means a schema change can never
        silently shift values into the wrong column.
        """
        names = ", ".join(self.column_names)
        placeholders = ", ".join("?" for _ in self.columns)
        return f"INSERT INTO {self.name} ({names}) VALUES ({placeholders})"


CRASHES = Table(
    name="crashes",
    primary_key=("collision_id",),
    indexes=(("crash_date",),),
    columns=(
        Column("collision_id", INTEGER, to_int, "Collision Id"),
        Column("report_number", TEXT, to_text, "Report Number"),
        Column("report_version", INTEGER, to_int, "Report Version"),
        Column("is_preliminary", INTEGER, to_bool, "Is Preliminary"),
        Column("ncic_code", TEXT, to_text, "NCIC Code"),
        # The one source column that becomes two: a date and a time that sort
        # and filter independently, which is the whole point of leaving
        # `M/D/YYYY H:MM:SS AM` behind.
        Column("crash_date", TEXT, to_date, "Crash Date Time"),
        Column("crash_time", TEXT, to_time, "Crash Date Time"),
        Column("crash_time_description", TEXT, to_time_description, "Crash Time Description"),
        Column("beat", TEXT, to_text, "Beat"),
        Column("city_id", INTEGER, to_int, "City Id"),
        # A zero-padded four-character code, not a number: 34,305 of the
        # 400,215 rows in the 2025 file start with a zero ('0109' is Oakland).
        # Storing it as INTEGER drops the padding and breaks every join
        # against a published city or NCIC code list. `ncic_code` shares this
        # code space and is TEXT for the same reason.
        Column("city_code", TEXT, to_text, "City Code"),
        Column("city_name", TEXT, to_text, "City Name"),
        # Genuinely numeric: 1 to 58, never padded.
        Column("county_code", INTEGER, to_int, "County Code"),
        Column("city_is_active", INTEGER, to_bool, "City Is Active"),
        Column("city_is_incorporated", INTEGER, to_bool, "City Is Incorporated"),
        Column("collision_type_code", TEXT, to_text, "Collision Type Code"),
        Column("collision_type_description", TEXT, to_text, "Collision Type Description"),
        Column("collision_type_other_description", TEXT, to_text, "Collision Type Other Desc"),
        Column("day_of_week", TEXT, to_text, "Day Of Week"),
        # Documented as a smallint, delivered as Yes/No/NotApplicable. Trust
        # the file, not the data dictionary.
        Column("dispatch_notified", TEXT, to_text, "DispatchNotified"),
        Column("has_photographs", INTEGER, to_bool, "HasPhotographs"),
        # F/M/blank, not a boolean despite the name.
        Column("hit_run", TEXT, to_text, "HitRun"),
        Column("is_attachments_mailed", INTEGER, to_bool, "IsAttachmentsMailed"),
        Column("is_deleted", INTEGER, to_bool, "IsDeleted"),
        Column("is_highway_related", INTEGER, to_bool, "IsHighwayRelated"),
        Column("is_tow_away", INTEGER, to_bool, "IsTowAway"),
        Column("judicial_district", TEXT, to_text, "JudicialDistrict"),
        Column("motor_vehicle_involved_with_code", TEXT, to_text, "MotorVehicleInvolvedWithCode"),
        Column(
            "motor_vehicle_involved_with_description",
            TEXT,
            to_text,
            "MotorVehicleInvolvedWithDesc",
        ),
        Column(
            "motor_vehicle_involved_with_other_description",
            TEXT,
            to_text,
            "MotorVehicleInvolvedWithOtherDesc",
        ),
        Column("number_injured", INTEGER, to_int, "NumberInjured"),
        Column("number_killed", INTEGER, to_int, "NumberKilled"),
        Column("weather_1", TEXT, to_text, "Weather 1"),
        Column("weather_2", TEXT, to_text, "Weather 2"),
        Column("road_condition_1", TEXT, to_text, "Road Condition 1"),
        Column("road_condition_2", TEXT, to_text, "Road Condition 2"),
        # Multi-valued and slash-separated. Kept raw; a junction table is a
        # later release, not a v1 problem.
        Column("special_condition", TEXT, to_text, "Special Condition"),
        Column("lighting_code", TEXT, to_text, "LightingCode"),
        Column("lighting_description", TEXT, to_text, "LightingDescription"),
        Column("latitude", REAL, to_real, "Latitude"),
        Column("longitude", REAL, to_real, "Longitude"),
        Column("milepost_direction", TEXT, to_text, "MilepostDirection"),
        Column("milepost_distance", REAL, to_real, "MilepostDistance"),
        # Mostly numeric, but carries values like '25.5 N' in the real file.
        Column("milepost_marker", TEXT, to_text, "MilepostMarker"),
        Column("milepost_unit_of_measure", TEXT, to_text, "MilepostUnitOfMeasure"),
        Column("pedestrian_action_code", TEXT, to_text, "PedestrianActionCode"),
        Column("pedestrian_action_description", TEXT, to_text, "PedestrianActionDesc"),
        Column("prepared_date", TEXT, to_datetime, "PreparedDate"),
        Column("primary_collision_factor_code", TEXT, to_text, "Primary Collision Factor Code"),
        Column(
            "primary_collision_factor_violation",
            TEXT,
            to_text,
            "Primary Collision Factor Violation",
        ),
        Column(
            "primary_collision_factor_is_cited",
            INTEGER,
            to_bool,
            "PrimaryCollisionFactorIsCited",
        ),
        Column("primary_collision_party_number", INTEGER, to_int, "PrimaryCollisionPartyNumber"),
        Column("primary_road", TEXT, to_text, "PrimaryRoad"),
        Column("reporting_district", TEXT, to_text, "ReportingDistrict"),
        Column("reporting_district_code", TEXT, to_text, "ReportingDistrictCode"),
        Column("reviewed_date", TEXT, to_datetime, "ReviewedDate"),
        Column("roadway_surface_code", TEXT, to_text, "RoadwaySurfaceCode"),
        Column("secondary_direction", TEXT, to_text, "SecondaryDirection"),
        Column("secondary_distance", REAL, to_real, "SecondaryDistance"),
        Column("secondary_road", TEXT, to_text, "SecondaryRoad"),
        Column("secondary_unit_of_measure", TEXT, to_text, "SecondaryUnitOfMeasure"),
        Column("sketch_description", TEXT, to_text, "SketchDesc"),
        Column("traffic_control_device_code", TEXT, to_text, "TrafficControlDeviceCode"),
        Column("created_date", TEXT, to_datetime, "CreatedDate"),
        Column("modified_date", TEXT, to_datetime, "ModifiedDate"),
        Column("is_county_road", INTEGER, to_bool, "IsCountyRoad"),
        Column("is_freeway", INTEGER, to_bool, "IsFreeway"),
        Column("chp_555_version", INTEGER, to_int, "CHP555Version"),
        # The source misspells this header; the database does not.
        Column("is_additional_object_struck", INTEGER, to_bool, "IsAdditonalObjectStruck"),
        Column("notification_date", TEXT, to_datetime, "NotificationDate"),
        Column(
            "notification_time_description",
            TEXT,
            to_time_description,
            "NotificationTimeDescription",
        ),
        Column("has_digital_media_files", INTEGER, to_bool, "HasDigitalMediaFiles"),
        Column("evidence_number", TEXT, to_text, "EvidenceNumber"),
        Column("is_location_refer_to_narrative", INTEGER, to_bool, "IsLocationReferToNarrative"),
        Column("is_aoi_one_same_as_location", INTEGER, to_bool, "IsAOIOneSameAsLocation"),
    ),
)


PARTIES = Table(
    name="parties",
    primary_key=("party_id",),
    # Indexed but not an enforced foreign key: cross-year reports leave real
    # rows pointing at collision ids that live in another year's file, and
    # enforcement would reject them.
    #
    # The index covers party_number too, because (collision_id, party_number)
    # is how injured_witness_passengers names the party a person was with.
    # Lookups by collision_id alone still use it.
    indexes=(("collision_id", "party_number"),),
    columns=(
        Column("party_id", INTEGER, to_int, "PartyId"),
        Column("collision_id", INTEGER, to_int, "CollisionId"),
        Column("party_number", INTEGER, to_int, "PartyNumber"),
        Column("party_type", TEXT, to_text, "PartyType"),
        Column("is_at_fault", INTEGER, to_bool, "IsAtFault"),
        Column("is_on_duty_emergency_vehicle", INTEGER, to_bool, "IsOnDutyEmergencyVehicle"),
        Column("is_hit_and_run", INTEGER, to_bool, "IsHitAndRun"),
        Column("airbag_code", TEXT, to_text, "AirbagCode"),
        Column("airbag_description", TEXT, to_text, "AirbagDescription"),
        Column("safety_equipment_code", TEXT, to_text, "SafetyEquipmentCode"),
        Column("safety_equipment_description", TEXT, to_text, "SafetyEquipmentDescription"),
        Column("special_information", TEXT, to_text, "Special Information"),
        Column("other_associate_factor", TEXT, to_text, "Other Associate Factor"),
        Column("inattention", TEXT, to_text, "Inattention"),
        Column("direction_of_travel", TEXT, to_text, "DirectionOfTravel"),
        Column("street_or_highway_name", TEXT, to_text, "StreetOrHighwayName"),
        Column("speed_limit", INTEGER, to_int, "SpeedLimit"),
        Column("movement_preceding_collision_code", TEXT, to_text, "MovementPrecCollCode"),
        Column(
            "movement_preceding_collision_description",
            TEXT,
            to_text,
            "MovementPrecCollDescription",
        ),
        Column("sobriety_drug_physical_code_1", TEXT, to_text, "SobrietyDrugPhysicalCode1"),
        Column(
            "sobriety_drug_physical_description_1",
            TEXT,
            to_text,
            "SobrietyDrugPhysicalDescription1",
        ),
        Column("sobriety_drug_physical_code_2", TEXT, to_text, "SobrietyDrugPhysicalCode2"),
        Column(
            "sobriety_drug_physical_description_2",
            TEXT,
            to_text,
            "SobrietyDrugPhysicalDescription2",
        ),
        Column("gender_code", TEXT, to_text, "GenderCode"),
        Column("gender_description", TEXT, to_text, "GenderDescription"),
        Column("stated_age", INTEGER, to_int, "StatedAge"),
        Column("driver_license_class", TEXT, to_text, "DriverLicenseClass"),
        Column("driver_license_state_code", TEXT, to_text, "DriverLicenseStateCode"),
        Column("race_code", TEXT, to_text, "RaceCode"),
        Column("race_description", TEXT, to_text, "RaceDesc"),
        # Free text in practice: '1', '1-2', 'SHOULDER'.
        Column("lane", TEXT, to_text, "Lane"),
        Column("thru_lanes", INTEGER, to_int, "ThruLanes"),
        Column("total_lanes", INTEGER, to_int, "TotalLanes"),
        Column("is_dre_conducted", INTEGER, to_bool, "IsDREConducted"),
    ),
)


# The vehicle columns arrive inline on the party row, in two near-identical
# groups (a tractor and its trailer, say). They are lifted into their own
# table, so these columns are filled by vehicles.py rather than read straight
# off a header --- hence no source_header here.
VEHICLES = Table(
    name="vehicles",
    # The one table invented here rather than inherited, so it has to declare
    # its own identity: a party has at most one vehicle per number.
    primary_key=("party_id", "vehicle_number"),
    indexes=(("collision_id",),),
    columns=(
        Column("party_id", INTEGER, to_int),
        Column("collision_id", INTEGER, to_int),
        Column("vehicle_number", INTEGER, to_int),
        Column("type_id", INTEGER, to_int),
        Column("type_description", TEXT, to_text),
        Column("year", INTEGER, to_int),
        # The source string, kept verbatim, next to the normalized maker name.
        # A miss in the make map leaves `make` NULL rather than corrupting
        # `make_raw`, so every normalization stays auditable.
        Column("make_raw", TEXT, to_text),
        Column("make", TEXT, to_text),
        Column("model", TEXT, to_text),
        Column("color", TEXT, to_text),
        Column("is_towed", INTEGER, to_bool),
    ),
)

# Which parties header feeds which `vehicles` column, one mapping per group.
# The position in this tuple is the vehicle_number, one-based.
VEHICLE_GROUP_HEADERS: tuple[Mapping[str, str], ...] = (
    {
        "type_id": "Vehicle1TypeId",
        "type_description": "Vehicle1TypeDesc",
        "year": "Vehicle1Year",
        "make_raw": "Vehicle1Make",
        "model": "Vehicle1Model",
        "color": "Vehicle1Color",
        "is_towed": "V1IsVehicleTowed",
    },
    {
        "type_id": "Vehicle2TypeId",
        "type_description": "Vehicle2TypeDesc",
        "year": "Vehicle2Year",
        "make_raw": "Vehicle2Make",
        "model": "Vehicle2Model",
        "color": "Vehicle2Color",
        "is_towed": "V2IsVehicleTowed",
    },
)


INJURED_WITNESS_PASSENGERS = Table(
    name="injured_witness_passengers",
    primary_key=("injured_wit_pass_id",),
    # Covers party_number for the same reason parties does: it is the other
    # half of the documented link between a person and their party.
    indexes=(("collision_id", "party_number"),),
    columns=(
        Column("injured_wit_pass_id", INTEGER, to_int, "InjuredWitPassId"),
        Column("collision_id", INTEGER, to_int, "CollisionId"),
        # NULL for witnesses, who are attached to the crash but to no party.
        Column("party_number", INTEGER, to_int, "PartyNumber"),
        Column("stated_age", INTEGER, to_int, "StatedAge"),
        # Renamed from the source's bare `Gender`/`Race` to match parties.
        Column("gender_code", TEXT, to_text, "Gender"),
        Column("gender_description", TEXT, to_text, "Gender Desc"),
        Column("race_code", TEXT, to_text, "Race"),
        Column("race_description", TEXT, to_text, "Race Desc"),
        Column("is_witness_only", INTEGER, to_bool, "IsWitnessOnly"),
        Column("is_passenger_only", INTEGER, to_bool, "IsPassengerOnly"),
        Column("extent_of_injury_code", TEXT, to_text, "ExtentOfInjuryCode"),
        Column("injured_person_type", TEXT, to_text, "InjuredPersonType"),
        Column("seat_position", TEXT, to_text, "SeatPosition"),
        Column("seat_position_other", TEXT, to_text, "SeatPositionOther"),
        Column("seat_position_description", TEXT, to_text, "SeatPositionDescription"),
        Column("airbag_code", TEXT, to_text, "AirBagCode"),
        Column("airbag_description", TEXT, to_text, "AirBagDescription"),
        Column("safety_equipment_code", TEXT, to_text, "SafetyEquipmentCode"),
        Column("safety_equipment_description", TEXT, to_text, "SafetyEquipmentDescription"),
        Column("ejected", TEXT, to_text, "Ejected"),
        Column("is_vovc_notified", INTEGER, to_bool, "IsVOVCNotified"),
    ),
)


# What the metadata table records. Two things get logged and they carry
# different fields, so the kind is stated in the row rather than inferred from
# which columns happen to be NULL.
FILE_LOAD_RECORD = "file_load"
ORPHAN_COUNT_RECORD = "orphan_count"

# Provenance: a log of what was done to build this database. Cheap, and it
# answers "what is actually in here" long after the shell history is gone.
METADATA = Table(
    name="metadata",
    # No index: this table holds a handful of rows per load, and one more
    # B-tree to maintain would cost more than it ever saves.
    columns=(
        # FILE_LOAD_RECORD or ORPHAN_COUNT_RECORD. A file load fills
        # source_file, year_label and the row counts; an orphan count fills
        # orphan_rows. Neither fills the other's columns.
        Column("record_type", TEXT, to_text),
        Column("table_name", TEXT, to_text),
        Column("source_file", TEXT, to_text),
        Column("year_label", TEXT, to_text),
        Column("rows_read", INTEGER, to_int),
        Column("rows_loaded", INTEGER, to_int),
        Column("rows_skipped", INTEGER, to_int),
        Column("orphan_rows", INTEGER, to_int),
        Column("converter_version", TEXT, to_text),
        # UTC, unlike every other timestamp in this database: crash_date and
        # the report dates are California local time as the source gives them.
        # The name is the only thing that can carry that distinction.
        Column("loaded_at_utc", TEXT, to_text),
    ),
)


ALL_TABLES = (CRASHES, PARTIES, VEHICLES, INJURED_WITNESS_PASSENGERS, METADATA)


def source_headers(*tables: Table) -> frozenset[str]:
    """Return the normalized headers the given tables read, ignoring computed columns."""
    return frozenset(
        column.normalized_source_header
        for table in tables
        for column in table.columns
        if column.normalized_source_header is not None
    )


def vehicle_group_headers() -> frozenset[str]:
    """Return the normalized parties headers that feed the vehicles table."""
    return frozenset(
        normalize_header(header) for group in VEHICLE_GROUP_HEADERS for header in group.values()
    )


# The headers each source file is expected to carry. Parties files own the
# vehicle columns too, even though those end up in a different table.
CRASHES_SOURCE_HEADERS = source_headers(CRASHES)
PARTIES_SOURCE_HEADERS = source_headers(PARTIES) | vehicle_group_headers()
INJURED_SOURCE_HEADERS = source_headers(INJURED_WITNESS_PASSENGERS)


def index_header_row(header_row: Iterable[str], source_name: str) -> dict[str, int]:
    """Return normalized header -> column position for one source file."""
    positions: dict[str, int] = {}
    for position, cell in enumerate(header_row):
        header = normalize_header(cell)
        if header in positions:
            raise ValueError(f"{source_name}: header {header!r} appears more than once")

        positions[header] = position

    return positions


def check_expected_headers(
    header_positions: Mapping[str, int],
    expected_headers: Collection[str],
    source_name: str,
) -> None:
    """Fail unless the file carries exactly the headers we know how to read.

    Both directions are fatal on purpose. An unknown header means CHP added or
    renamed a column and this schema needs a decision; a missing one means a
    column silently vanished. Guessing either way produces a database that
    looks fine and is wrong.
    """
    unknown = sorted(set(header_positions) - set(expected_headers))
    if unknown:
        raise ValueError(f"{source_name}: unrecognized headers: {', '.join(unknown)}")

    missing = sorted(set(expected_headers) - set(header_positions))
    if missing:
        raise ValueError(f"{source_name}: missing expected headers: {', '.join(missing)}")


def column_positions(table: Table, header_positions: Mapping[str, int]) -> tuple[int, ...]:
    """Return the source cell index for each of the table's columns, in order."""
    positions = []
    for column in table.columns:
        header = column.normalized_source_header
        if header is None:
            raise ValueError(f"{table.name}.{column.name} is computed, not read from a header")

        positions.append(header_positions[header])

    return tuple(positions)


def convert_row(table: Table, row: Sequence[str], positions: Sequence[int]) -> list[SQLiteValue]:
    """Convert one raw CSV row into the values to bind for `table`.

    A converter failure is re-raised naming the column, since "expected an
    integer, got 'T602'" is not much use across 74 of them.
    """
    values: list[SQLiteValue] = []
    for column, position in zip(table.columns, positions, strict=True):
        try:
            values.append(column.convert(row[position]))
        except ValueError as error:
            raise ValueError(f"{table.name}.{column.name}: {error}") from None

    return values
