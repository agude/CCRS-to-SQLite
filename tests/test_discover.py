import io

import pytest

from ccrs_to_sqlite.discover import IncompleteYearError, discover
from ccrs_to_sqlite.load import CRASHES_SOURCE, INJURED_SOURCE, PARTIES_SOURCE


def _touch(directory, name):
    path = directory / name
    path.write_text("", encoding="utf-8")
    return path


def _populate_year(directory, year, *, gz=False):
    """Create empty files for a complete year triple."""
    ext = ".csv.gz" if gz else ".csv"
    for prefix in ("crashes", "parties", "injuredwitnesspassengers"):
        _touch(directory, f"{prefix}_{year}{ext}")


@pytest.fixture
def progress():
    return io.StringIO()


def test_discovers_a_complete_year(tmp_path, progress):
    _populate_year(tmp_path, "2025")

    result = discover(tmp_path, progress=progress)

    assert set(result) == {"2025"}
    assert result["2025"][CRASHES_SOURCE] == tmp_path / "crashes_2025.csv"
    assert result["2025"][PARTIES_SOURCE] == tmp_path / "parties_2025.csv"
    assert result["2025"][INJURED_SOURCE] == tmp_path / "injuredwitnesspassengers_2025.csv"


def test_discovers_multiple_years_sorted(tmp_path, progress):
    _populate_year(tmp_path, "2024")
    _populate_year(tmp_path, "2016")
    _populate_year(tmp_path, "2025")

    result = discover(tmp_path, progress=progress)

    assert list(result) == ["2016", "2024", "2025"]


def test_discovers_gzipped_files(tmp_path, progress):
    _populate_year(tmp_path, "2025", gz=True)

    result = discover(tmp_path, progress=progress)

    assert result["2025"][CRASHES_SOURCE] == tmp_path / "crashes_2025.csv.gz"


def test_skips_incomplete_year_with_warning(tmp_path, progress):
    _populate_year(tmp_path, "2025")
    _touch(tmp_path, "crashes_2024.csv")

    result = discover(tmp_path, progress=progress)

    assert "2025" in result
    assert "2024" not in result
    assert "2024" in progress.getvalue()
    assert "missing" in progress.getvalue()


def test_incomplete_year_names_missing_kinds(tmp_path, progress):
    _populate_year(tmp_path, "2025")
    _touch(tmp_path, "crashes_2024.csv")
    _touch(tmp_path, "parties_2024.csv")

    discover(tmp_path, progress=progress)

    assert "injuredwitnesspassengers" in progress.getvalue()


def test_raises_when_all_years_are_incomplete(tmp_path, progress):
    _touch(tmp_path, "crashes_2024.csv")

    with pytest.raises(IncompleteYearError, match="every year found is incomplete"):
        discover(tmp_path, progress=progress)


def test_raises_on_nonexistent_directory(progress):
    from pathlib import Path

    with pytest.raises(FileNotFoundError, match="not a directory"):
        discover(Path("/nonexistent/path"), progress=progress)


def test_raises_when_directory_has_no_source_files(tmp_path, progress):
    _touch(tmp_path, "readme.txt")

    with pytest.raises(FileNotFoundError, match="no CCRS source files found"):
        discover(tmp_path, progress=progress)


def test_raises_on_duplicate_kind_for_same_year(tmp_path, progress):
    _populate_year(tmp_path, "2025")
    _touch(tmp_path, "crashes_2025.csv.gz")

    with pytest.raises(ValueError, match="more than one crashes file for 2025"):
        discover(tmp_path, progress=progress)


def test_ignores_unrelated_files(tmp_path, progress):
    _populate_year(tmp_path, "2025")
    _touch(tmp_path, "notes.txt")
    _touch(tmp_path, "crashes_summary.csv")

    result = discover(tmp_path, progress=progress)

    assert set(result) == {"2025"}
    assert progress.getvalue() == ""
