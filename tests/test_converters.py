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
)

ALL_CONVERTERS = [
    to_text,
    to_int,
    to_real,
    to_bool,
    to_datetime,
    to_date,
    to_time,
    to_time_description,
]

# The source pads values with spaces at random (plan.md quirk 11), so a cell
# that is nothing but whitespace has to read as NULL, not as a value.
EMPTY_CELLS = ["", " ", "  ", "\t", " \t "]


@pytest.mark.parametrize("converter", ALL_CONVERTERS)
@pytest.mark.parametrize("cell", EMPTY_CELLS)
def test_every_converter_reads_an_empty_cell_as_null(converter, cell):
    assert converter(cell) is None


def test_to_text_strips_surrounding_whitespace():
    assert to_text(" NO UNUSUAL CONDITIONS") == "NO UNUSUAL CONDITIONS"
    assert to_text("SCION ") == "SCION"


def test_to_text_keeps_interior_whitespace():
    assert to_text(" OCCUPANT LAP SHOULDER HARNESS USED ") == "OCCUPANT LAP SHOULDER HARNESS USED"


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("4550266", 4550266), (" 55 ", 55), ("0", 0), ("-1", -1)],
)
def test_to_int_parses_integers(cell, expected):
    assert to_int(cell) == expected


@pytest.mark.parametrize("cell", ["1.5", "abc", "1,000", "T602", "12 34"])
def test_to_int_rejects_non_integers(cell):
    with pytest.raises(ValueError, match="expected an integer"):
        to_int(cell)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("-117.050468", -117.050468), (" 32.742237", 32.742237), ("120", 120.0), ("0.000", 0.0)],
)
def test_to_real_parses_numbers(cell, expected):
    assert to_real(cell) == pytest.approx(expected)


@pytest.mark.parametrize("cell", ["abc", "1.2.3", "N/A"])
def test_to_real_rejects_non_numbers(cell):
    with pytest.raises(ValueError, match="expected a number"):
        to_real(cell)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("True", 1), ("False", 0), (" True ", 1), ("true", 1), ("FALSE", 0)],
)
def test_to_bool_maps_the_source_words_to_integers(cell, expected):
    assert to_bool(cell) == expected


@pytest.mark.parametrize("cell", ["Yes", "No", "NotApplicable", "1", "0", "Y", "F", "M"])
def test_to_bool_rejects_words_the_source_does_not_use_for_booleans(cell):
    """Tri-state fields such as HitRun and DispatchNotified must not coerce."""
    with pytest.raises(ValueError, match="expected True or False"):
        to_bool(cell)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("1/14/2025 7:50:00 AM", "2025-01-14 07:50:00"),
        ("1/18/2025 3:20:00 PM", "2025-01-18 15:20:00"),
        ("12/31/2024 12:00:00 AM", "2024-12-31 00:00:00"),
        ("12/31/2024 12:00:00 PM", "2024-12-31 12:00:00"),
        ("10/05/2025 09:04:35 AM", "2025-10-05 09:04:35"),
        (" 1/27/2025 9:04:38 AM ", "2025-01-27 09:04:38"),
    ],
)
def test_to_datetime_produces_sortable_iso_text(cell, expected):
    assert to_datetime(cell) == expected


def test_to_date_and_to_time_split_one_source_datetime():
    cell = "1/18/2025 3:20:00 PM"

    assert to_date(cell) == "2025-01-18"
    assert to_time(cell) == "15:20:00"


@pytest.mark.parametrize("converter", [to_datetime, to_date, to_time])
@pytest.mark.parametrize(
    "cell",
    [
        "2025-01-14",
        "1/14/2025",
        "13/14/2025 7:50:00 AM",
        "1/14/2025 25:50:00 AM",
        "1/14/2025 7:50 AM",
        "not a date",
    ],
)
def test_datetime_converters_reject_anything_but_the_source_format(converter, cell):
    with pytest.raises(ValueError, match="expected a M/D/YYYY"):
        converter(cell)


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("750", "0750"), ("0750", "0750"), ("1520", "1520"), ("0", "0000"), (" 828 ", "0828")],
)
def test_to_time_description_pads_to_four_digits(cell, expected):
    assert to_time_description(cell) == expected


@pytest.mark.parametrize(
    ("cell", "expected"),
    [("7:50", "0750"), ("07:50", "0750"), ("15:20", "1520"), (" 8:28 ", "0828")],
)
def test_to_time_description_drops_the_colon_from_punctuated_times(cell, expected):
    """448 notification times in the 2025 file are punctuated; the column holds one shape."""
    assert to_time_description(cell) == expected


def test_to_time_description_keeps_impossible_times_as_they_came():
    """2500 appears thousands of times in the 2025 file; correcting it would be a guess."""
    assert to_time_description("2500") == "2500"


def test_to_time_description_passes_non_numeric_text_through():
    assert to_time_description(" UNK ") == "UNK"
