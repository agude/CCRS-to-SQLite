"""Opening CCRS source files, compressed or not.

The dataset is published as plain CSV, but the files are large enough that
people gzip them before archiving. Compression is detected from the magic
bytes rather than the suffix, so a `crashes_2025.csv` that is secretly gzipped
still loads.
"""

from __future__ import annotations

import gzip
from pathlib import Path
from typing import TextIO

GZIP_MAGIC_BYTES = b"\x1f\x8b"

# The files are UTF-8 and some carry a byte-order mark; `utf-8-sig` eats the
# mark when present so the first header cell is not `﻿Collision Id`.
SOURCE_ENCODING = "utf-8-sig"

PARSE_ERROR_MODES = ("strict", "ignore", "replace")

# The `csv` module does its own line splitting, and needs newline translation
# left off to keep quoted fields containing newlines intact.
CSV_NEWLINE = ""


def is_gzipped(path: Path) -> bool:
    """Return whether the file begins with the gzip magic bytes."""
    with path.open("rb") as raw_file:
        return raw_file.read(len(GZIP_MAGIC_BYTES)) == GZIP_MAGIC_BYTES


def open_source_file(path: Path, parse_error: str = "strict") -> TextIO:
    """Open a CCRS CSV for reading as text, decompressing it if it is gzipped.

    `parse_error` is the codec error handler applied to undecodable bytes:
    `strict` (the default) fails loudly, `ignore` drops them, `replace`
    substitutes U+FFFD.
    """
    if parse_error not in PARSE_ERROR_MODES:
        raise ValueError(f"parse_error must be one of {PARSE_ERROR_MODES}, got {parse_error!r}")

    if is_gzipped(path):
        return gzip.open(
            path,
            mode="rt",
            encoding=SOURCE_ENCODING,
            errors=parse_error,
            newline=CSV_NEWLINE,
        )

    return path.open(
        mode="rt",
        encoding=SOURCE_ENCODING,
        errors=parse_error,
        newline=CSV_NEWLINE,
    )
