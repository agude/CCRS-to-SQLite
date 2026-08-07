"""Golden test: convert the sample files and compare against the checked-in snapshot.

The sample in ``tests/data/golden/`` is a deterministic extract from the real
source CSVs, covering NULLs, witnesses, two-vehicle parties, the ragged row,
two-tone colors, unmapped makes, multi-valued road conditions, and multiple
years.  ``expected.sql`` is the SQL dump of the correct conversion.

To regenerate the sample after a source data update::

    python scripts/extract_test_rows.py /path/to/ccrs-data

To regenerate the snapshot after an intentional schema or converter change::

    just golden-snapshot
"""

from __future__ import annotations

import io
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from ccrs_to_sqlite.main import SourceFiles, convert

GOLDEN_DIR = Path(__file__).parent / "data" / "golden"
EXPECTED_SQL = GOLDEN_DIR / "expected.sql"


def _sql_value(value: object) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    return "'" + str(value).replace("'", "''") + "'"


def _dump_data(connection: sqlite3.Connection) -> str:
    tables = ("crashes", "parties", "vehicles", "injured_witness_passengers")
    lines: list[str] = []
    for table in tables:
        cols = [row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()]
        order = "party_id, vehicle_number" if table == "vehicles" else cols[0]
        rows = connection.execute(f"SELECT * FROM {table} ORDER BY {order}").fetchall()
        for row in rows:
            values = ", ".join(_sql_value(v) for v in row)
            lines.append(f"INSERT INTO {table} VALUES ({values});")
        lines.append("")

    return "\n".join(lines)


@pytest.fixture
def golden_database(tmp_path: Path) -> Path:
    db = tmp_path / "golden.sqlite3"
    sources = SourceFiles(
        crashes=(GOLDEN_DIR / "crashes.csv",),
        parties=(GOLDEN_DIR / "parties.csv",),
        injured=(GOLDEN_DIR / "injuredwitnesspassengers.csv",),
    )
    convert(sources, db, progress=io.StringIO())
    return db


def test_golden_output_matches_snapshot(golden_database: Path) -> None:
    with closing(sqlite3.connect(golden_database)) as con:
        actual = _dump_data(con)

    expected = EXPECTED_SQL.read_text(encoding="utf-8")
    assert actual == expected, (
        "golden output differs from snapshot; if the change is intentional, run: just golden-snapshot"
    )


def test_golden_row_counts(golden_database: Path) -> None:
    with closing(sqlite3.connect(golden_database)) as con:
        counts = {
            table: con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in ("crashes", "parties", "vehicles", "injured_witness_passengers")
        }

    assert counts == {
        "crashes": 32,
        "parties": 61,
        "vehicles": 68,
        "injured_witness_passengers": 75,
    }


def test_golden_ragged_row_is_skipped(golden_database: Path) -> None:
    """The ragged row (party 14105771, crash 4649436) has 50 fields and is skipped."""
    with closing(sqlite3.connect(golden_database)) as con:
        party = con.execute("SELECT COUNT(*) FROM parties WHERE party_id = 14105771").fetchone()[0]
        assert party == 0

        crash_parties = con.execute(
            "SELECT COUNT(*) FROM parties WHERE collision_id = 4649436"
        ).fetchone()[0]
        assert crash_parties == 0


def test_golden_witnesses_have_null_party_number(golden_database: Path) -> None:
    with closing(sqlite3.connect(golden_database)) as con:
        witnesses = con.execute(
            "SELECT party_number, is_witness_only FROM injured_witness_passengers "
            "WHERE is_witness_only = 1"
        ).fetchall()

    assert len(witnesses) >= 1
    for party_number, _ in witnesses:
        assert party_number is None


def test_golden_two_vehicle_parties_exist(golden_database: Path) -> None:
    with closing(sqlite3.connect(golden_database)) as con:
        two_vehicle = con.execute(
            "SELECT COUNT(*) FROM (SELECT party_id FROM vehicles GROUP BY party_id HAVING COUNT(*) = 2)"
        ).fetchone()[0]

    assert two_vehicle >= 1
