import re
import sqlite3
from contextlib import closing

import pytest

from ccrs_to_sqlite.make_map import MAKE_MAP, RAW_STRINGS_BY_MAKE, Make, normalize_make


def test_no_raw_string_is_claimed_by_two_makers():
    """Building MAKE_MAP by inversion would silently let the later maker win."""
    declared = [
        raw_string for raw_strings in RAW_STRINGS_BY_MAKE.values() for raw_string in raw_strings
    ]

    assert len(declared) == len(MAKE_MAP)


def test_every_key_is_already_stripped_and_uppercase():
    """Lookup upper-cases and strips; a key that is not in that form can never match."""
    for raw_string in MAKE_MAP:
        assert raw_string == raw_string.strip().upper(), raw_string


def test_every_value_is_a_member_of_the_make_enum():
    for make in MAKE_MAP.values():
        assert isinstance(make, Make)


def test_every_make_declares_at_least_one_raw_string():
    assert set(RAW_STRINGS_BY_MAKE) == set(Make)
    for make, raw_strings in RAW_STRINGS_BY_MAKE.items():
        assert raw_strings, make


def test_no_two_makers_share_a_value():
    """A duplicate value aliases silently rather than raising.

    The second member becomes an alias of the first, vanishes from iteration,
    and hands its raw strings to the wrong maker. `set(RAW_STRINGS_BY_MAKE) ==
    set(Make)` above cannot see it, because aliases are not iterated. With 83
    makers merged from two source maps this is the likeliest way the map
    breaks, so it is asserted directly as well as via @unique.
    """
    assert len(Make.__members__) == len(list(Make))
    assert len({make.value for make in Make}) == len(list(Make))


def test_no_raw_string_is_another_makers_name():
    """Many spellings may share a maker; a maker's own name may not be shared.

    The map is many-to-one by design, but the canonical names have to stay
    one-to-one or `make` stops being a key you can group by.
    """
    canonical = {make.value: make for make in Make}
    for raw_string, make in MAKE_MAP.items():
        owner = canonical.get(raw_string)
        assert owner is None or owner is make, (
            f"{raw_string!r} is {make.value}'s spelling but {owner} is named that"
        )


def test_member_names_match_their_values():
    """Catches a typo in either half, which nothing else would notice."""
    for make in Make:
        expected = re.sub(r"[^A-Z0-9]+", "_", make.value).strip("_")
        assert make.name == expected, f"{make.name} declares {make.value!r}"


def test_every_make_maps_its_own_full_name():
    """A file that already spells the maker out must not come back NULL."""
    for make in Make:
        assert normalize_make(make.value) == make


@pytest.mark.parametrize(
    ("raw_string", "expected"),
    [
        ("TOYT", Make.TOYOTA),
        ("TOYOTA", Make.TOYOTA),
        ("CHEV", Make.CHEVROLET),
        ("CHEVY", Make.CHEVROLET),
        ("TSMR", Make.TESLA),
        ("KW", Make.KENWORTH),
        ("HD", Make.HARLEY_DAVIDSON),
    ],
)
def test_abbreviations_and_full_names_land_on_one_maker(raw_string, expected):
    assert normalize_make(raw_string) == expected


def test_merz_is_mercedes_and_merc_is_mercury():
    """The CCRS frequencies settle a call switrs-to-sqlite guessed at."""
    assert normalize_make("MERZ") == Make.MERCEDES_BENZ
    assert normalize_make("MERC") == Make.MERCURY


@pytest.mark.parametrize("raw_string", [" toyt ", "toyota", "Toyt", "TOYT\t"])
def test_lookup_strips_and_upper_cases_first(raw_string):
    assert normalize_make(raw_string) == Make.TOYOTA


@pytest.mark.parametrize("raw_string", [None, "", "   ", "ZZZZ", "HOMEMADE", "1988"])
def test_an_unmapped_string_becomes_null_rather_than_a_guess(raw_string):
    assert normalize_make(raw_string) is None


def test_unknown_is_not_treated_as_a_maker():
    """It appears 2,101 times and is not a manufacturer."""
    assert normalize_make("UNKNOWN") is None


def test_a_normalized_make_stores_as_plain_text():
    """Make is a StrEnum; the database must end up with the bare string."""
    with closing(sqlite3.connect(":memory:")) as connection:
        connection.execute("CREATE TABLE example (make TEXT) STRICT")
        connection.execute("INSERT INTO example (make) VALUES (?)", (normalize_make("TOYT"),))
        stored = connection.execute("SELECT make, typeof(make) FROM example").fetchone()

    assert stored == ("TOYOTA", "text")
