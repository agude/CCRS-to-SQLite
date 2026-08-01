import csv
from pathlib import Path

import pytest

from ccrs_to_sqlite.make_map import Make
from ccrs_to_sqlite.open_record import open_source_file
from ccrs_to_sqlite.schema import PARTIES, VEHICLES, index_header_row
from ccrs_to_sqlite.vehicles import (
    COLLISION_ID_HEADER,
    INHERITED_COLUMNS,
    PARTY_ID_HEADER,
    plan_vehicles,
    vehicle_rows,
)

HEADER_ROW_FILE = Path(__file__).parent / "data" / "headers" / "parties.csv"


@pytest.fixture
def header_positions():
    with open_source_file(HEADER_ROW_FILE) as header_file:
        return index_header_row(next(csv.reader(header_file)), "parties.csv")


@pytest.fixture
def plan(header_positions):
    return plan_vehicles(header_positions)


def party_row(header_positions, **cells):
    row = [""] * len(header_positions)
    for header, value in cells.items():
        row[header_positions[header]] = value
    return row


def as_dictionary(row):
    return dict(zip(VEHICLES.column_names, row, strict=True))


def test_the_inherited_headers_match_the_ones_parties_uses():
    """These are read here but defined on the parties table; they must not drift apart."""
    assert PARTIES.column("party_id").source_header == PARTY_ID_HEADER
    assert PARTIES.column("collision_id").source_header == COLLISION_ID_HEADER


def test_a_party_with_no_vehicle_produces_no_rows(plan, header_positions):
    pedestrian = party_row(header_positions, partyid="13900351", collisionid="4541904")

    assert vehicle_rows(plan, pedestrian) == []


def test_whitespace_only_cells_do_not_count_as_a_vehicle(plan, header_positions):
    """The source pads empty fields with lone spaces."""
    row = party_row(
        header_positions,
        partyid="13900351",
        collisionid="4541904",
        vehicle1make="  ",
        vehicle1color=" ",
    )

    assert vehicle_rows(plan, row) == []


def test_one_vehicle_group_produces_one_row(plan, header_positions):
    row = party_row(
        header_positions,
        partyid="13900349",
        collisionid="4541904",
        vehicle1typeid="8",
        vehicle1typedesc="MiniVan",
        vehicle1year="2011",
        vehicle1make="TOYT",
        vehicle1model="SIENNA",
        vehicle1color="WHI",
        v1isvehicletowed="False",
    )

    rows = vehicle_rows(plan, row)

    assert len(rows) == 1
    assert as_dictionary(rows[0]) == {
        "party_id": 13900349,
        "collision_id": 4541904,
        "vehicle_number": 1,
        "type_id": 8,
        "type_description": "MiniVan",
        "year": 2011,
        "make_raw": "TOYT",
        "make": Make.TOYOTA,
        "model": "SIENNA",
        "color": "WHI",
        "is_towed": 0,
    }


def test_a_tractor_and_its_trailer_become_two_numbered_rows(plan, header_positions):
    row = party_row(
        header_positions,
        partyid="13900351",
        collisionid="4541904",
        vehicle1typedesc="TruckTractor",
        vehicle1make="VOLV",
        vehicle2typedesc="SemiTrailer",
        vehicle2make="GDAN",
    )

    rows = [as_dictionary(vehicle) for vehicle in vehicle_rows(plan, row)]

    assert [vehicle["vehicle_number"] for vehicle in rows] == [1, 2]
    assert [vehicle["type_description"] for vehicle in rows] == ["TruckTractor", "SemiTrailer"]
    assert [vehicle["make_raw"] for vehicle in rows] == ["VOLV", "GDAN"]
    assert {vehicle["party_id"] for vehicle in rows} == {13900351}
    assert {vehicle["collision_id"] for vehicle in rows} == {4541904}


def test_a_second_vehicle_without_a_first_still_numbers_correctly(plan, header_positions):
    row = party_row(header_positions, partyid="1", collisionid="2", vehicle2make="UTILITY")

    rows = [as_dictionary(vehicle) for vehicle in vehicle_rows(plan, row)]

    assert len(rows) == 1
    assert rows[0]["vehicle_number"] == 2


def test_the_raw_make_survives_normalization(plan, header_positions):
    row = party_row(header_positions, partyid="1", collisionid="2", vehicle1make=" chevy ")

    vehicle = as_dictionary(vehicle_rows(plan, row)[0])

    assert vehicle["make_raw"] == "chevy"
    assert vehicle["make"] == Make.CHEVROLET


def test_an_unmapped_make_leaves_make_null_but_keeps_the_raw_string(plan, header_positions):
    row = party_row(header_positions, partyid="1", collisionid="2", vehicle1make="HOMEMADE")

    vehicle = as_dictionary(vehicle_rows(plan, row)[0])

    assert vehicle["make_raw"] == "HOMEMADE"
    assert vehicle["make"] is None


def test_missing_cells_within_a_present_group_are_null(plan, header_positions):
    row = party_row(header_positions, partyid="1", collisionid="2", vehicle1make="FORD")

    vehicle = as_dictionary(vehicle_rows(plan, row)[0])

    assert vehicle["year"] is None
    assert vehicle["model"] is None
    assert vehicle["is_towed"] is None


def test_a_bad_cell_names_its_column_and_its_vehicle(plan, header_positions):
    row = party_row(header_positions, partyid="1", collisionid="2", vehicle2year="unknown")

    with pytest.raises(ValueError, match=r"vehicles\.year \(vehicle 2\): expected an integer"):
        vehicle_rows(plan, row)


def test_the_plan_covers_every_column_the_groups_are_responsible_for(plan):
    derived_from_the_make_map = {"make"}
    expected = set(VEHICLES.column_names) - set(INHERITED_COLUMNS) - derived_from_the_make_map

    for group in plan.groups:
        assert set(group.positions) == expected
