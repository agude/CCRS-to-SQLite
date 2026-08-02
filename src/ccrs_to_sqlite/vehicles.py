"""Lifting the inline vehicle columns out of a parties row.

A party row carries up to two vehicles in two near-identical column groups ---
`Vehicle1Make`, `Vehicle2Make`, and so on. That is a tractor and its trailer,
not two unrelated fields, so the groups become rows in `vehicles` instead of
fourteen half-duplicated columns on `parties`.

The second group is empty on 97% of rows. Emitting a row only when a group has
some content keeps the table honest: a row in `vehicles` means a vehicle was
recorded, not that a party existed.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from ccrs_to_sqlite.color_map import normalize_colors
from ccrs_to_sqlite.make_map import normalize_make
from ccrs_to_sqlite.schema import (
    VEHICLE_GROUP_HEADERS,
    VEHICLES,
    Column,
    SQLiteValue,
    normalize_header,
)

# The parties columns each emitted vehicle row inherits. Kept as literals
# because they are read here but defined on the parties table; a test holds
# the two spellings together.
PARTY_ID_HEADER = "PartyId"
COLLISION_ID_HEADER = "CollisionId"

# Filled from the party row rather than from a vehicle group.
INHERITED_COLUMNS = ("party_id", "collision_id", "vehicle_number")

# Every vehicles column reads a single cell, so the paired kind cannot
# appear here and the narrowing is free.
VEHICLE_COLUMNS_BY_NAME = {
    column.name: column for column in VEHICLES.columns if isinstance(column, Column)
}


@dataclass(frozen=True)
class VehicleGroupPlan:
    """Where one inline vehicle group's cells sit in a parties row."""

    vehicle_number: int
    positions: Mapping[str, int]


@dataclass(frozen=True)
class VehiclePlan:
    """Everything needed to turn a parties row into vehicle rows."""

    party_id_position: int
    collision_id_position: int
    groups: tuple[VehicleGroupPlan, ...]


def plan_vehicles(header_positions: Mapping[str, int]) -> VehiclePlan:
    """Resolve the vehicle group headers against one parties header row.

    Done once per file, so the per-row work is plain indexing.
    """
    groups = tuple(
        VehicleGroupPlan(
            vehicle_number=vehicle_number,
            positions={
                column_name: header_positions[normalize_header(header)]
                for column_name, header in group.items()
            },
        )
        for vehicle_number, group in enumerate(VEHICLE_GROUP_HEADERS, start=1)
    )

    return VehiclePlan(
        party_id_position=header_positions[normalize_header(PARTY_ID_HEADER)],
        collision_id_position=header_positions[normalize_header(COLLISION_ID_HEADER)],
        groups=groups,
    )


def vehicle_rows(plan: VehiclePlan, row: Sequence[str]) -> list[list[SQLiteValue]]:
    """Return the `vehicles` rows a single parties row produces, zero to two of them."""
    party_id = VEHICLE_COLUMNS_BY_NAME["party_id"].convert(row[plan.party_id_position])
    collision_id = VEHICLE_COLUMNS_BY_NAME["collision_id"].convert(row[plan.collision_id_position])

    rows = []
    for group in plan.groups:
        if not _group_has_content(group, row):
            continue

        rows.append(_vehicle_row(group, row, party_id, collision_id))

    return rows


def _group_has_content(group: VehicleGroupPlan, row: Sequence[str]) -> bool:
    """Whether any cell in the group holds something other than whitespace."""
    return any(row[position].strip() for position in group.positions.values())


def _vehicle_row(
    group: VehicleGroupPlan,
    row: Sequence[str],
    party_id: SQLiteValue,
    collision_id: SQLiteValue,
) -> list[SQLiteValue]:
    color, color_secondary = normalize_colors(row[group.positions["color_raw"]])
    values: dict[str, SQLiteValue] = {
        "party_id": party_id,
        "collision_id": collision_id,
        "vehicle_number": group.vehicle_number,
        "make": normalize_make(row[group.positions["make_raw"]]),
        "color": color,
        "color_secondary": color_secondary,
    }

    for column_name, position in group.positions.items():
        column = VEHICLE_COLUMNS_BY_NAME[column_name]
        try:
            values[column_name] = column.convert(row[position])
        except ValueError as error:
            raise ValueError(
                f"vehicles.{column_name} (vehicle {group.vehicle_number}): {error}"
            ) from None

    return [values[column_name] for column_name in VEHICLES.column_names]
