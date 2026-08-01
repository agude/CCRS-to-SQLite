"""Normalization of vehicle make strings.

The 2025 parties file holds 7,837 distinct make strings over 735,093 non-empty
values, mixing NCIC abbreviations with full names: `TOYT` 72,162 against
`TOYOTA` 60,577, `CHEV`/`CHEVROLET`/`CHEVY`, `MERZ`/`MERCEDES-BENZ`. Any
per-make aggregate is meaningless without a map.

The map is deliberately *not* the switrs-to-sqlite design, where the mapped
value replaced the raw string and every correction to the map changed the
output for previously convertible input. Here:

* `vehicles.make_raw` keeps the source string verbatim.
* `vehicles.make` holds the normalized name, and is NULL when unmapped.

A miss degrades to NULL instead of corrupting data, and every normalization
stays auditable against the raw column. Adding entries is additive: rows that
were NULL become populated, and nothing already populated changes.

Ambiguous strings are left out on purpose. `UNKNOWN` is the obvious one --- it
is not a manufacturer, so it stays NULL rather than becoming a make named
"unknown" that aggregates alongside real ones.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum


class Make(StrEnum):
    """The normalized maker names. The map may only produce one of these."""

    ACURA = "ACURA"
    AUDI = "AUDI"
    BMW = "BMW"
    BUICK = "BUICK"
    CADILLAC = "CADILLAC"
    CHEVROLET = "CHEVROLET"
    CHRYSLER = "CHRYSLER"
    DODGE = "DODGE"
    FORD = "FORD"
    FREIGHTLINER = "FREIGHTLINER"
    GMC = "GMC"
    HARLEY_DAVIDSON = "HARLEY-DAVIDSON"
    HINO = "HINO"
    HONDA = "HONDA"
    HYUNDAI = "HYUNDAI"
    INFINITI = "INFINITI"
    INTERNATIONAL = "INTERNATIONAL"
    JEEP = "JEEP"
    KAWASAKI = "KAWASAKI"
    KENWORTH = "KENWORTH"
    KIA = "KIA"
    LAND_ROVER = "LAND ROVER"
    LEXUS = "LEXUS"
    LINCOLN = "LINCOLN"
    MAZDA = "MAZDA"
    MERCEDES_BENZ = "MERCEDES-BENZ"
    MERCURY = "MERCURY"
    MINI = "MINI"
    MITSUBISHI = "MITSUBISHI"
    NISSAN = "NISSAN"
    PETERBILT = "PETERBILT"
    PORSCHE = "PORSCHE"
    RAM = "RAM"
    SCION = "SCION"
    SUBARU = "SUBARU"
    SUZUKI = "SUZUKI"
    TESLA = "TESLA"
    TOYOTA = "TOYOTA"
    UTILITY = "UTILITY"
    VOLKSWAGEN = "VOLKSWAGEN"
    VOLVO = "VOLVO"
    YAMAHA = "YAMAHA"


# Source strings per maker, written this way round because that is how the
# decisions are actually made and reviewed: "which spellings are Toyota?"
#
# The seed covers the strings above roughly 750 occurrences in the 2025 file,
# about 93% of non-empty values. Extending it toward the top 200 is v0.2.0
# work; the long tail of 5,149 single-occurrence strings stays NULL for good.
RAW_STRINGS_BY_MAKE: Mapping[Make, tuple[str, ...]] = {
    Make.ACURA: ("ACUR", "ACURA"),
    Make.AUDI: ("AUDI",),
    Make.BMW: ("BMW",),
    Make.BUICK: ("BUIC", "BUICK"),
    Make.CADILLAC: ("CADI", "CADILLAC"),
    Make.CHEVROLET: ("CHEV", "CHEVROLET", "CHEVY"),
    Make.CHRYSLER: ("CHRY", "CHRYSLER"),
    Make.DODGE: ("DODG", "DODGE"),
    Make.FORD: ("FORD",),
    Make.FREIGHTLINER: ("FRHT", "FREIGHTLINER"),
    Make.GMC: ("GMC",),
    Make.HARLEY_DAVIDSON: ("HD", "HARLEY-DAVIDSON", "HARLEY DAVIDSON"),
    Make.HINO: ("HINO",),
    Make.HONDA: ("HOND", "HONDA"),
    Make.HYUNDAI: ("HYUN", "HYUNDAI"),
    Make.INFINITI: ("INFI", "INFINITI"),
    Make.INTERNATIONAL: ("INTL", "INTERNATIONAL"),
    Make.JEEP: ("JEEP",),
    Make.KAWASAKI: ("KAWK", "KAWASAKI"),
    Make.KENWORTH: ("KW", "KENWORTH"),
    Make.KIA: ("KIA",),
    Make.LAND_ROVER: ("LNDR", "LAND ROVER", "LANDROVER"),
    Make.LEXUS: ("LEXS", "LEXUS"),
    Make.LINCOLN: ("LINC", "LINCOLN"),
    Make.MAZDA: ("MAZD", "MAZDA"),
    # MERZ (9,376) is Mercedes-Benz and MERC (366) is Mercury. The CCRS
    # frequencies settle a judgment call switrs-to-sqlite guessed at.
    Make.MERCEDES_BENZ: ("MERZ", "MERCEDES-BENZ", "MERCEDES BENZ", "MERCEDES"),
    Make.MERCURY: ("MERC", "MERCURY"),
    Make.MINI: ("MNNI", "MINI", "MINI COOPER"),
    Make.MITSUBISHI: ("MITS", "MITSUBISHI"),
    Make.NISSAN: ("NISS", "NISSAN"),
    Make.PETERBILT: ("PTRB", "PETERBILT"),
    Make.PORSCHE: ("PORS", "PORSCHE"),
    Make.RAM: ("RAM",),
    Make.SCION: ("SCIO", "SCION"),
    Make.SUBARU: ("SUBA", "SUBARU"),
    Make.SUZUKI: ("SUZI", "SUZUKI"),
    # TSMR is the NCIC code for Tesla Motors.
    Make.TESLA: ("TESL", "TESLA", "TSMR"),
    Make.TOYOTA: ("TOYT", "TOYOTA"),
    # Utility Trailer Manufacturing, which is why it outranks most cars.
    Make.UTILITY: ("UTILITY", "UTIL"),
    Make.VOLKSWAGEN: ("VOLK", "VOLKSWAGEN", "VW"),
    Make.VOLVO: ("VOLV", "VOLVO"),
    Make.YAMAHA: ("YAMA", "YAMAHA"),
}

MAKE_MAP: Mapping[str, Make] = {
    raw_string: make
    for make, raw_strings in RAW_STRINGS_BY_MAKE.items()
    for raw_string in raw_strings
}


def normalize_make(raw_string: str | None) -> str | None:
    """Return the normalized maker name for a source make string.

    None for an empty cell, and None for anything the map does not cover.
    """
    if raw_string is None:
        return None

    return MAKE_MAP.get(raw_string.strip().upper())
