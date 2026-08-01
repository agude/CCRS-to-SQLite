"""Pure value converters from CCRS CSV text to SQLite-ready Python values.

Each converter takes one raw CSV cell and returns the value to bind, or
``None`` when the cell is empty --- an empty string means NULL throughout this
dataset (plan.md section 1, quirk 5).

Every converter strips before it looks at anything. The source data carries
stray leading spaces on both headers and values (quirk 11), and a converter
that forgets to strip is the bug class switrs-to-sqlite shipped for years.

A non-empty cell that does not fit its type raises `ValueError`. Silently
nulling unparseable values would hide a CHP format change behind a column of
NULLs; the loader turns the exception into a skipped row with a warning.
"""

from __future__ import annotations

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

BOOLEAN_WORDS = {"true": 1, "false": 0}


def to_text(value: str) -> str | None:
    """Return the cell stripped, or None when it holds nothing but whitespace."""
    stripped = value.strip()
    return stripped or None


def to_int(value: str) -> int | None:
    """Return the cell as an integer, or None when empty."""
    stripped = value.strip()
    if not stripped:
        return None

    try:
        return int(stripped)
    except ValueError:
        raise ValueError(f"expected an integer, got {stripped!r}") from None


def to_real(value: str) -> float | None:
    """Return the cell as a float, or None when empty."""
    stripped = value.strip()
    if not stripped:
        return None

    try:
        return float(stripped)
    except ValueError:
        raise ValueError(f"expected a number, got {stripped!r}") from None


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

    Values are left otherwise untouched. The source contains impossible times
    such as ``2500``; correcting them would be guessing, and they are easy to
    filter downstream once the width is uniform.
    """
    stripped = value.strip()
    if not stripped:
        return None

    if stripped.isdigit():
        return stripped.zfill(TIME_DESCRIPTION_WIDTH)

    return stripped


def _parse_source_datetime(value: str) -> datetime | None:
    """Parse the source's ``M/D/YYYY H:MM:SS AM`` format. None when empty."""
    stripped = value.strip()
    if not stripped:
        return None

    try:
        return datetime.strptime(stripped, SOURCE_DATETIME_FORMAT)
    except ValueError:
        raise ValueError(f"expected a M/D/YYYY H:MM:SS AM datetime, got {stripped!r}") from None
