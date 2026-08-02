"""Normalization of vehicle colour strings, and the two-tone split.

The published years hold about 3,340 distinct colour strings over 5.4 million
non-empty values, but the vocabulary behind them is small: roughly thirty
colours spelled as NCIC-style codes, as full words, and as a long tail of
typos. `WHI`, `WHT` and `WHITE` alone are 1.49 million rows. The top fifty
forms cover 97.9%, which makes this a better-shaped normalization target than
vehicle makes ever were.

The design is the same as `make_map`, for the same reason: `color_raw` keeps
the source string verbatim, `color` holds the normalized name and is NULL when
unmapped, so a miss degrades to NULL rather than corrupting data and every
normalization stays auditable against the raw column.

Shades stay distinct. `DBL` is dark blue, not blue; `LBL` is light blue.
Collapsing them would be a judgment a consumer can make with a `CASE` and
cannot undo, and unlike a spelling variant the source is drawing a real
distinction.

Two tones
---------

2.1% of colour values name two colours, separated by a slash --- `BLK/WHI`,
11,153 rows, is a patrol car. They become `color` and `color_secondary`
rather than being flattened or dropped:

* flattening to the first tone would throw away the only interesting thing
  about the row;
* dropping them would be wrong for a different reason. A miss becomes NULL
  because the value is *unknown*; `BLK/WHI` is perfectly well known, and
  nulling it would undercount black and white vehicles by six figures.

`color` is **the first colour listed, not the primary colour.** The source
looks like it has a primary/secondary convention until the mirrored pairs are
counted: `BLK/WHI` outnumbers `WHI/BLK` 11,153 to 3,603, but `BLK/GRY` and
`GRY/BLK` are 1,061 to 1,058. There is a tendency, not a rule, and claiming
otherwise would assert a semantics the data does not support.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum, unique

# A slash, either way round --- the backslash form is the same convention
# slipped (3,377 rows) --- or a spelled-out conjunction (158 rows). A hyphen
# is deliberately *not* a separator: `BLUE- DARK` is a shade name, not two
# tones, and splitting it would turn one colour into two wrong ones.
_SEPARATOR = re.compile(r"[/\\]|\s+(?:AND|&)\s+")

# How many tones the schema stores. A third is vanishingly rare (338 rows of
# 5.4 million) and there is nowhere to put it.
MAX_TONES = 2


@unique
class Color(StrEnum):
    """The normalized colour names. The map may only produce one of these.

    `@unique` for the same reason `Make` carries it: two members sharing a
    value do not raise, the second silently becomes an alias and takes its
    raw strings into the other colour.
    """

    ALUMINUM = "ALUMINUM"
    BEIGE = "BEIGE"
    BLACK = "BLACK"
    BLUE = "BLUE"
    BRONZE = "BRONZE"
    BROWN = "BROWN"
    BURGUNDY = "BURGUNDY"
    CHAMPAGNE = "CHAMPAGNE"
    COPPER = "COPPER"
    CREAM = "CREAM"
    DARK_BLUE = "DARK BLUE"
    DARK_GREEN = "DARK GREEN"
    GOLD = "GOLD"
    GRAY = "GRAY"
    GREEN = "GREEN"
    LAVENDER = "LAVENDER"
    LIGHT_BLUE = "LIGHT BLUE"
    LIGHT_GREEN = "LIGHT GREEN"
    MAROON = "MAROON"
    ORANGE = "ORANGE"
    PINK = "PINK"
    PURPLE = "PURPLE"
    RED = "RED"
    SILVER = "SILVER"
    TAN = "TAN"
    TEAL = "TEAL"
    TURQUOISE = "TURQUOISE"
    WHITE = "WHITE"
    YELLOW = "YELLOW"


# Written maker-first, the way the decisions are made and reviewed: "which
# spellings are white?" Frequencies are across all eleven published years.
RAW_STRINGS_BY_COLOR: Mapping[Color, tuple[str, ...]] = {
    Color.ALUMINUM: ("ALU", "ALUMINUM"),
    Color.BEIGE: ("BE", "BEI", "BGE", "BEIGE"),
    # BKL and BK are transposition and truncation of BLK.
    Color.BLACK: ("BK", "BLA", "BLK", "BKL", "BLACK"),
    Color.BLUE: ("BLU", "BLUE"),
    Color.BRONZE: ("BRZ", "BRONZE"),
    Color.BROWN: ("BRN", "BRO", "BROWN"),
    # BURGANDY is the source's own misspelling, and outnumbers the correct
    # spelling two to one.
    Color.BURGUNDY: ("BUR", "BURGANDY", "BURGUNDY"),
    Color.CHAMPAGNE: ("CHAMPAGNE",),
    Color.COPPER: ("CPR", "COPPER"),
    Color.CREAM: ("CRM", "CREAM"),
    # Shades are their own colours, not spellings of blue and green. The
    # hyphenated forms are the same value written the other way round.
    Color.DARK_BLUE: ("DBL", "DARK BLUE", "BLUE- DARK"),
    Color.DARK_GREEN: ("DGR", "DARK GREEN", "GREEN- DARK"),
    Color.GOLD: ("GO", "GLD", "GOL", "GOLD"),
    Color.GRAY: ("GEY", "GRA", "GRY", "GRAY", "GREY"),
    Color.GREEN: ("GRE", "GRN", "GREEN"),
    Color.LAVENDER: ("LAV", "LAVENDER"),
    Color.LIGHT_BLUE: ("LBL", "LIGHT BLUE", "BLUE- LIGHT"),
    Color.LIGHT_GREEN: ("LGR", "LIGHT GREEN", "GREEN- LIGHT"),
    Color.MAROON: ("MR", "MAR", "MRN", "MAROON"),
    Color.ORANGE: ("ONG", "ORA", "ORG", "ORN", "ORANGE"),
    Color.PINK: ("PNK", "PINK"),
    Color.PURPLE: ("PU", "PLE", "PUR", "PURPLE"),
    Color.RED: ("RD", "RED"),
    Color.SILVER: ("SL", "SIL", "SIV", "SLR", "SLV", "SILVER"),
    Color.TAN: ("TAN",),
    Color.TEAL: ("TEA", "TEAL"),
    Color.TURQUOISE: ("TRQ", "TURQUOISE"),
    # WHU and WHY are keyboard slips for WHI, which sits between them.
    Color.WHITE: ("WHI", "WHT", "WHU", "WHY", "WHITE"),
    Color.YELLOW: ("YL", "YEL", "YLW", "YELLOW"),
}

# Deliberately absent, though they appear often enough to tempt: `UNK` and
# `UNKNOWN` name nothing, `OTH` is a category, and `MUL`, `MULTI-COLORED` and
# `COM` say "several" without saying which --- a colour named "multi" would
# aggregate alongside real ones, which is exactly what `UNKNOWN` is kept out
# of the make map to avoid. `CAM`, `AME`, `BRG`, `BRY` and `WIL` are left out
# because nothing in the data says what they stand for; guessing writes a
# wrong colour that `color_raw` records but does not correct.

COLOR_MAP: Mapping[str, Color] = {
    raw_string: color
    for color, raw_strings in RAW_STRINGS_BY_COLOR.items()
    for raw_string in raw_strings
}


def normalize_colors(raw_string: str | None) -> tuple[str | None, str | None]:
    """Return the (first, second) normalized colours for a source colour string.

    ``(None, None)`` for an empty cell and for anything the map does not
    cover. A single colour returns its second element as None.

    Segments that are empty or unmapped are dropped rather than held as a
    positional gap, so `/WHI`, `WHI/` and `WHI` all resolve alike: the source
    writes both a leading and a trailing slash (7,323 and 12,176 rows) and
    neither carries meaning. A colour repeated in both positions collapses to
    one, since `WHI/WHI` names a white vehicle rather than a two-tone one.
    """
    if raw_string is None:
        return None, None

    colors: list[Color] = []
    for segment in _SEPARATOR.split(raw_string.strip().upper()):
        color = COLOR_MAP.get(segment.strip())
        if color is not None and color not in colors:
            colors.append(color)
        if len(colors) == MAX_TONES:
            break

    first = colors[0] if colors else None
    second = colors[1] if len(colors) > 1 else None
    return first, second
