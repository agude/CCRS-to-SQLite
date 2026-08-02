import re

import pytest

from ccrs_to_sqlite.color_map import (
    COLOR_MAP,
    RAW_STRINGS_BY_COLOR,
    Color,
    normalize_colors,
)


def test_no_raw_string_is_claimed_by_two_colors():
    """Building COLOR_MAP by inversion would silently let the later colour win."""
    declared = [raw for raw_strings in RAW_STRINGS_BY_COLOR.values() for raw in raw_strings]

    assert len(declared) == len(COLOR_MAP)


def test_no_two_colors_share_a_value():
    """A duplicate value aliases silently: the second member vanishes from iteration."""
    assert len(Color.__members__) == len(list(Color))
    assert len({color.value for color in Color}) == len(list(Color))


def test_member_names_match_their_values():
    for color in Color:
        assert color.name == re.sub(r"[^A-Z0-9]+", "_", color.value).strip("_")


def test_every_key_is_already_stripped_and_uppercase():
    """Lookup upper-cases and strips; a key not in that form can never match."""
    for raw_string in COLOR_MAP:
        assert raw_string == raw_string.strip().upper(), raw_string


def test_every_color_declares_at_least_one_raw_string():
    assert set(RAW_STRINGS_BY_COLOR) == set(Color)
    for color, raw_strings in RAW_STRINGS_BY_COLOR.items():
        assert raw_strings, color


def test_every_color_maps_its_own_full_name():
    """A file that spells the colour out must not come back NULL."""
    for color in Color:
        assert normalize_colors(color.value) == (color, None)


@pytest.mark.parametrize(
    ("raw_string", "expected"),
    [
        # The three spellings of white are 1.49M rows between them.
        ("WHI", Color.WHITE),
        ("WHT", Color.WHITE),
        ("WHITE", Color.WHITE),
        ("BLK", Color.BLACK),
        ("GRY", Color.GRAY),
        ("GREY", Color.GRAY),
        ("SIL", Color.SILVER),
        ("SLV", Color.SILVER),
    ],
)
def test_codes_and_full_names_land_on_one_color(raw_string, expected):
    assert normalize_colors(raw_string) == (expected, None)


@pytest.mark.parametrize(
    ("raw_string", "expected"),
    [
        ("DBL", Color.DARK_BLUE),
        ("DARK BLUE", Color.DARK_BLUE),
        ("BLUE- DARK", Color.DARK_BLUE),
        ("LBL", Color.LIGHT_BLUE),
        ("DGR", Color.DARK_GREEN),
        ("LGR", Color.LIGHT_GREEN),
    ],
)
def test_shades_stay_distinct_from_their_base_color(raw_string, expected):
    """DBL is dark blue, not blue.

    Collapsing a shade is a judgment a consumer can make with a CASE and
    cannot undo, and unlike a spelling variant the source means something by
    the distinction. The hyphenated forms are the same value written the
    other way round -- a hyphen is a shade modifier here, never a separator.
    """
    assert normalize_colors(raw_string) == (expected, None)
    assert normalize_colors(raw_string)[0] not in (Color.BLUE, Color.GREEN)


@pytest.mark.parametrize("separator", ["/", "\\", " AND ", " & "])
def test_both_tones_are_resolved_whatever_separates_them(separator):
    """The backslash form is the same convention slipped, on 3,377 rows."""
    assert normalize_colors(f"BLK{separator}WHI") == (Color.BLACK, Color.WHITE)


@pytest.mark.parametrize(
    ("raw_string", "why"),
    [
        ("WHI/", "trailing slash, 12,176 rows"),
        ("/WHI", "leading slash, 7,323 rows"),
        ("WHI/WHI", "the same colour twice is not a two-tone"),
        ("WHI//", "more than one empty segment"),
        (" whi / ", "whitespace around the segments"),
    ],
)
def test_empty_and_repeated_segments_collapse_to_one_colour(raw_string, why):
    """Neither a leading nor a trailing slash carries meaning."""
    assert normalize_colors(raw_string) == (Color.WHITE, None), why


def test_an_unmapped_segment_is_dropped_rather_than_held_as_a_gap():
    """`color` should hold a colour we know whenever the row names one.

    Keeping the position would leave `color` NULL while `color_secondary`
    held a real colour, which loses it from every `GROUP BY color`.
    """
    assert normalize_colors("CHARTREUSE/WHI") == (Color.WHITE, None)
    assert normalize_colors("WHI/CHARTREUSE") == (Color.WHITE, None)


def test_only_the_first_two_tones_are_kept():
    """A third tone is 338 rows of 5.4 million and there is nowhere to put it."""
    assert normalize_colors("BLK/WHI/RED") == (Color.BLACK, Color.WHITE)


@pytest.mark.parametrize("raw_string", [None, "", "   ", "/", "ZZZZ", "CHARTREUSE"])
def test_an_unmapped_string_becomes_null_rather_than_a_guess(raw_string):
    assert normalize_colors(raw_string) == (None, None)


@pytest.mark.parametrize(
    ("raw_string", "what_it_actually_is"),
    [
        ("UNK", "a placeholder"),
        ("UNKNOWN", "the same"),
        ("OTH", "a category"),
        ("MUL", "'several', without saying which"),
        ("MULTI-COLORED", "the same"),
        ("COM", "ambiguous; nothing in the data expands it"),
        ("CAM", "ambiguous -- camouflage or champagne?"),
        ("BRG", "ambiguous -- bronze or burgundy?"),
    ],
)
def test_placeholders_and_ambiguous_codes_are_not_colours(raw_string, what_it_actually_is):
    """A colour named "multi" would aggregate alongside real ones.

    That is exactly what UNKNOWN is kept out of the make map to avoid, and
    guessing at an ambiguous code writes a wrong colour that `color_raw`
    records but does not correct.
    """
    assert normalize_colors(raw_string) == (None, None), what_it_actually_is


@pytest.mark.parametrize("raw_string", [" blk/whi ", "Blk/Whi", "BLK/WHI\t"])
def test_lookup_strips_and_upper_cases_first(raw_string):
    assert normalize_colors(raw_string) == (Color.BLACK, Color.WHITE)


def test_a_normalized_colour_stores_as_plain_text():
    """Color is a StrEnum; the database must end up with the bare string."""
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("CREATE TABLE example (color TEXT) STRICT")
        connection.execute(
            "INSERT INTO example (color) VALUES (?)", (normalize_colors("BLK/WHI")[0],)
        )
        stored = connection.execute("SELECT color, typeof(color) FROM example").fetchone()

    assert stored == ("BLACK", "text")
