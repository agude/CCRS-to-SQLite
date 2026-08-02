"""Pure value converters from CCRS CSV text to SQLite-ready Python values.

Each converter takes one raw CSV cell and returns the value to bind, or
``None`` when the cell is empty --- an empty string means NULL throughout this
dataset.

Every converter strips before it looks at anything. The source data carries
stray leading spaces on both headers and values, and a converter that forgets
to strip is the bug class switrs-to-sqlite shipped for years.

A non-empty cell that does not fit its type raises `ValueError`, and only
`ValueError`. Silently nulling unparseable values would hide a CHP format
change behind a column of NULLs; the loader turns the exception into a skipped
row with a warning, and any other exception type escapes it as a traceback.
That is why the numeric converters reject what SQLite cannot store rather than
leaving it to fail at insert time, thousands of rows later.
"""

from __future__ import annotations

import math
import re
from datetime import datetime

# The source spells dates `M/D/YYYY H:MM:SS AM` --- no leading zeros, 12-hour
# clock. `strptime` accepts unpadded numbers for %m/%d/%I, so one format
# string covers both padded and unpadded input.
SOURCE_DATETIME_FORMAT = "%m/%d/%Y %I:%M:%S %p"

ISO_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
ISO_DATE_FORMAT = "%Y-%m-%d"
ISO_TIME_FORMAT = "%H:%M:%S"

# `Crash Time Description` and friends are 24-hour `HHMM` strings that the
# data dictionary warns may arrive without their leading zero.
TIME_DESCRIPTION_WIDTH = 4
MAX_HOUR = 23
MAX_MINUTE = 59

# The time a merged DateTime column reads when no time was recorded.
MIDNIGHT = "00:00:00"

BOOLEAN_WORDS = {"true": 1, "false": 0}

# SQLite's INTEGER is 64-bit. Python's is not, so a value past this parses
# fine and then raises OverflowError from executemany, which is not a
# ValueError and so escapes the loader's skip-and-warn path entirely.
SQLITE_INTEGER_MIN = -(2**63)
SQLITE_INTEGER_MAX = 2**63 - 1

# `int()` and `float()` are more generous than this dataset ever needs: `int`
# accepts underscore grouping (`1_0` is ten) and any Unicode decimal digit
# (`٣` is three), and `float` accepts `nan` and `inf`. All of those would be
# silent corruption in a numeric column, so the shapes are matched explicitly.
# `\d` is deliberately not used --- it matches those same Unicode digits.
_ASCII_INTEGER = re.compile(r"[+-]?[0-9]+")
_ASCII_DIGITS = re.compile(r"[0-9]+")
# `H:MM`, `HH:M` and friends: a punctuated clock reading, each half padded on
# its own. Padding the string as a whole after dropping the colon turns `10:5`
# into `0105`, which is a valid-looking time and the wrong one.
_PUNCTUATED_TIME = re.compile(r"([0-9]{1,2}):([0-9]{1,2})")


def to_text(value: str) -> str | None:
    """Return the cell stripped, or None when it holds nothing but whitespace."""
    stripped = value.strip()
    return stripped or None


def to_int(value: str) -> int | None:
    """Return the cell as an integer, or None when empty.

    Only plain ASCII digits with an optional sign count, and only inside the
    range SQLite's INTEGER can hold.
    """
    stripped = value.strip()
    if not stripped:
        return None

    if not _ASCII_INTEGER.fullmatch(stripped):
        raise ValueError(f"expected an integer, got {stripped!r}")

    number = int(stripped)
    if not SQLITE_INTEGER_MIN <= number <= SQLITE_INTEGER_MAX:
        raise ValueError(f"expected a 64-bit integer, got {stripped!r}")

    return number


def to_real(value: str) -> float | None:
    """Return the cell as a float, or None when empty.

    Non-finite values are rejected rather than stored. SQLite has no NaN: it
    writes one as NULL, which would make a NaN latitude indistinguishable from
    the 31% of crashes that genuinely have no coordinates.
    """
    stripped = value.strip()
    if not stripped:
        return None

    try:
        number = float(stripped)
    except ValueError:
        raise ValueError(f"expected a number, got {stripped!r}") from None

    # Catches `nan` and `inf` by name, and also `1e400`, which overflows to
    # infinity without float() ever complaining.
    if not math.isfinite(number):
        raise ValueError(f"expected a finite number, got {stripped!r}")

    return number


def to_bool(value: str) -> int | None:
    """Return 1 for ``True``, 0 for ``False``, or None when empty.

    SQLite has no boolean type, so booleans are stored as INTEGER. Only the
    two literal words the source emits are accepted: tri-state fields such as
    `HitRun` and `DispatchNotified` look boolean but are not, and must stay
    TEXT rather than be coerced here.
    """
    stripped = value.strip()
    if not stripped:
        return None

    word = BOOLEAN_WORDS.get(stripped.lower())
    if word is None:
        raise ValueError(f"expected True or False, got {stripped!r}")

    return word


def to_datetime(value: str) -> str | None:
    """Return the cell as an ISO ``YYYY-MM-DD HH:MM:SS`` string, or None when empty."""
    parsed = _parse_source_datetime(value)
    if parsed is None:
        return None

    return parsed.strftime(ISO_DATETIME_FORMAT)


def to_date(value: str) -> str | None:
    """Return the date half of a source datetime as ``YYYY-MM-DD``, or None when empty."""
    parsed = _parse_source_datetime(value)
    if parsed is None:
        return None

    return parsed.strftime(ISO_DATE_FORMAT)


def to_time(value: str) -> str | None:
    """Return the time half of a source datetime as ``HH:MM:SS``, or None when empty."""
    parsed = _parse_source_datetime(value)
    if parsed is None:
        return None

    return parsed.strftime(ISO_TIME_FORMAT)


def to_time_description(value: str) -> str | None:
    """Return a 24-hour ``HHMM`` string zero-padded to four digits, or None when empty.

    Two shapes are recognized and normalized to that width: a bare digit run
    missing its leading zeros, and a punctuated clock reading. 448 of the
    214,873 `NotificationTimeDescription` values in the 2025 file are
    punctuated.

    Each half of a punctuated value is padded separately, because the halves
    mean different things. Dropping the colon first and padding the result as
    one string reads ``10:5`` as ``0105`` --- a well-formed time, four digits
    wide, nine hours off, and indistinguishable downstream from a real one.

    Anything else is passed through exactly as it came, so this column is not
    a width guarantee. The source contains impossible times such as ``2500``,
    its marker for an unknown time, and free text such as ``UNK``; correcting
    either would be guessing. Consumers wanting only clock readings should
    filter on ``length(x) = 4``, which is what `_time_from_description` does.
    """
    stripped = value.strip()
    if not stripped:
        return None

    punctuated = _PUNCTUATED_TIME.fullmatch(stripped)
    if punctuated is not None:
        hours, minutes = punctuated.groups()
        return f"{hours:0>2}{minutes:0>2}"

    if _ASCII_DIGITS.fullmatch(stripped):
        return stripped.zfill(TIME_DESCRIPTION_WIDTH)

    return stripped


def to_time_of_day(datetime_value: str, description_value: str) -> str | None:
    """Resolve a time of day from the two half-answers CCRS gives for one.

    The dataset merges a date and a time into one DateTime column, then
    documents that column as "the date when the collision occurred" and puts
    the time it actually stands behind in a separate four-character field.
    The merged column's time half reads midnight on rows where no time was
    recorded, so taking it at face value invents a time for them: in the 2025
    file that fabricates 3,731 midnight crashes, making 00:00:00 the single
    most common crash time in the database.

    Reading only the dedicated field is not right either --- on 77 rows it
    holds the unknown-time marker while the merged column carries a real
    time. So prefer the dedicated field, fall back to the merged column when
    that field says nothing usable, and return None rather than assert a
    midnight neither of them meant.
    """
    described = _time_from_description(description_value)
    if described is not None:
        return described

    merged = to_time(datetime_value)
    if merged is not None and merged != MIDNIGHT:
        return merged

    return None


def _time_from_description(value: str) -> str | None:
    """Read a four-character 24-hour time as ``HH:MM:SS``. None if it is not one.

    Rejects the unknown-time marker ``2500`` and the handful of neighbouring
    typos (``2501``, ``2559``) along with it, since neither names a time.
    """
    padded = to_time_description(value)
    if padded is None or len(padded) != TIME_DESCRIPTION_WIDTH:
        return None

    if not _ASCII_DIGITS.fullmatch(padded):
        return None

    hours, minutes = int(padded[:2]), int(padded[2:])
    if hours > MAX_HOUR or minutes > MAX_MINUTE:
        return None

    return f"{hours:02d}:{minutes:02d}:00"


def _parse_source_datetime(value: str) -> datetime | None:
    """Parse the source's ``M/D/YYYY H:MM:SS AM`` format. None when empty."""
    stripped = value.strip()
    if not stripped:
        return None

    try:
        return datetime.strptime(stripped, SOURCE_DATETIME_FORMAT)
    except ValueError:
        raise ValueError(f"expected a M/D/YYYY H:MM:SS AM datetime, got {stripped!r}") from None
