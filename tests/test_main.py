import io
import sqlite3
from contextlib import closing

import pytest

from ccrs_to_sqlite import __version__
from ccrs_to_sqlite.main import DEFAULT_OUTPUT_FILE, SourceFiles, build_parser, convert, main
from ccrs_to_sqlite.schema import FILE_LOAD_RECORD, ORPHAN_COUNT_RECORD
from tests.test_load import a_crash, a_party, a_person, write_source_file


@pytest.fixture
def progress():
    return io.StringIO()


@pytest.fixture
def sources(tmp_path):
    """One complete year: two crashes, three parties with vehicles, two people."""
    return SourceFiles(
        crashes=(write_source_file(tmp_path, "crashes", [a_crash(100), a_crash(200)]),),
        parties=(
            write_source_file(
                tmp_path,
                "parties",
                [
                    a_party(1, 100, vehicle1make="TOYT", vehicle2make="GDAN"),
                    a_party(2, 100, vehicle1make="FORD"),
                    a_party(3, 999),
                ],
            ),
        ),
        injured=(
            write_source_file(
                tmp_path,
                "injuredwitnesspassengers",
                [a_person(10, 200), a_person(11, 200, iswitnessonly="True")],
            ),
        ),
    )


def rows(database, statement):
    with closing(sqlite3.connect(database)) as connection:
        return connection.execute(statement).fetchall()


def test_version_flag_prints_the_package_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])

    assert exit_info.value.code == 0
    assert __version__ in capsys.readouterr().out


def test_no_input_arguments_is_a_usage_error():
    with pytest.raises(SystemExit) as exit_info:
        main([])

    assert exit_info.value.code == 2


def test_directory_mode_is_not_implemented_yet():
    with pytest.raises(SystemExit) as exit_info:
        main(["some_dir"])

    assert exit_info.value.code == 2


def test_output_file_defaults_when_not_given():
    arguments = build_parser().parse_args(["--crashes", "crashes_2025.csv"])

    assert arguments.output_file == DEFAULT_OUTPUT_FILE


def test_file_flags_accumulate():
    arguments = build_parser().parse_args(
        ["--crashes", "a.csv", "--crashes", "b.csv", "--parties", "p.csv"]
    )

    assert [path.name for path in arguments.crashes] == ["a.csv", "b.csv"]
    assert [path.name for path in arguments.parties] == ["p.csv"]
    assert arguments.injured == []


def test_convert_writes_every_table(tmp_path, sources, progress):
    database = tmp_path / "ccrs.sqlite3"

    convert(sources, database, progress=progress)

    assert rows(database, "SELECT COUNT(*) FROM crashes") == [(2,)]
    assert rows(database, "SELECT COUNT(*) FROM parties") == [(3,)]
    assert rows(database, "SELECT COUNT(*) FROM vehicles") == [(3,)]
    assert rows(database, "SELECT COUNT(*) FROM injured_witness_passengers") == [(2,)]


def test_convert_indexes_the_finished_database(tmp_path, sources, progress):
    database = tmp_path / "ccrs.sqlite3"

    convert(sources, database, progress=progress)

    indexes = rows(
        database, "SELECT name FROM sqlite_master WHERE type = 'index' AND name LIKE 'index_%'"
    )
    assert len(indexes) == 4


def test_convert_logs_provenance_for_every_file(tmp_path, sources, progress):
    database = tmp_path / "ccrs.sqlite3"

    convert(sources, database, progress=progress)

    logged = rows(
        database,
        "SELECT source_file, table_name, year_label, rows_loaded FROM metadata"
        f" WHERE record_type = '{FILE_LOAD_RECORD}' ORDER BY source_file",
    )
    assert logged == [
        ("crashes_2025.csv", "crashes", "2025", 2),
        ("injuredwitnesspassengers_2025.csv", "injured_witness_passengers", "2025", 2),
        ("parties_2025.csv", "parties", "2025", 3),
    ]


def test_convert_counts_and_reports_orphans(tmp_path, sources, progress):
    """Party 3 points at collision 999, which no crashes file supplied."""
    database = tmp_path / "ccrs.sqlite3"

    convert(sources, database, progress=progress)

    logged = rows(
        database,
        "SELECT table_name, orphan_rows FROM metadata"
        f" WHERE record_type = '{ORPHAN_COUNT_RECORD}' ORDER BY table_name",
    )
    assert logged == [
        ("injured_witness_passengers", 0),
        ("parties", 1),
        ("vehicles", 0),
    ]
    assert "1 parties rows reference a crash that is not in this database" in progress.getvalue()


def test_convert_refuses_to_overwrite_an_existing_database(tmp_path, sources, progress):
    database = tmp_path / "ccrs.sqlite3"
    database.write_text("not really a database", encoding="utf-8")

    with pytest.raises(FileExistsError, match="already exists"):
        convert(sources, database, progress=progress)

    assert database.read_text(encoding="utf-8") == "not really a database"


def test_a_failed_run_leaves_no_partial_database(tmp_path, progress):
    """A half-written file sitting at the destination would block every retry."""
    broken = tmp_path / "crashes_2025.csv"
    broken.write_text("Collision Id,SomethingNew\r\n1,x\r\n", encoding="utf-8")
    database = tmp_path / "ccrs.sqlite3"

    with pytest.raises(ValueError, match="unrecognized headers"):
        convert(SourceFiles(crashes=(broken,)), database, progress=progress)

    assert not database.exists()
    assert list(tmp_path.glob(".*partial")) == []


def test_a_stale_partial_file_does_not_block_a_retry(tmp_path, sources, progress):
    database = tmp_path / "ccrs.sqlite3"
    (tmp_path / ".ccrs.sqlite3.partial").write_text("left over", encoding="utf-8")

    convert(sources, database, progress=progress)

    assert rows(database, "SELECT COUNT(*) FROM crashes") == [(2,)]


def test_crashes_load_before_the_tables_that_reference_them(tmp_path, sources):
    order = [path.name for _, path in sources.in_load_order()]

    assert order == [
        "crashes_2025.csv",
        "parties_2025.csv",
        "injuredwitnesspassengers_2025.csv",
    ]


def test_main_converts_end_to_end(tmp_path, sources, capsys):
    database = tmp_path / "out.sqlite3"

    exit_code = main(
        [
            "--crashes",
            str(sources.crashes[0]),
            "--parties",
            str(sources.parties[0]),
            "--output-file",
            str(database),
        ]
    )

    assert exit_code == 0
    assert rows(database, "SELECT COUNT(*) FROM parties") == [(3,)]
    assert "wrote" in capsys.readouterr().err


def test_main_reports_a_failure_without_a_traceback(tmp_path, capsys):
    missing = tmp_path / "crashes_2025.csv"

    exit_code = main(["--crashes", str(missing), "--output-file", str(tmp_path / "out.sqlite3")])

    assert exit_code == 1
    assert "error:" in capsys.readouterr().err


def test_strict_reaches_the_loader(tmp_path, capsys):
    path = write_source_file(tmp_path, "crashes", [a_crash(1)])
    with path.open("a", newline="", encoding="utf-8") as source_file:
        source_file.write("3,extra,fields\r\n")

    exit_code = main(
        ["--crashes", str(path), "--output-file", str(tmp_path / "out.sqlite3"), "--strict"]
    )

    assert exit_code == 1
    assert "row has 3 fields" in capsys.readouterr().err
