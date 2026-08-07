"""Discover CCRS source files in a directory and group them by year.

The dataset publishes three CSVs per year — crashes, parties, and
injuredwitnesspassengers — so a full download is a flat directory of files
named ``crashes_2025.csv``, ``parties_2025.csv``, etc.  Directory mode finds
them by filename pattern, groups by the year suffix, requires complete triples
(all three kinds present for a year to load), and returns a `SourceFiles`
ready for `convert`.
"""

from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import TextIO

from ccrs_to_sqlite.load import CRASHES_SOURCE, INJURED_SOURCE, PARTIES_SOURCE, SourceKind

# The three filename prefixes the dataset uses, mapped to their SourceKind.
_PREFIX_TO_KIND: dict[str, SourceKind] = {
    CRASHES_SOURCE.name: CRASHES_SOURCE,
    PARTIES_SOURCE.name: PARTIES_SOURCE,
    INJURED_SOURCE.name: INJURED_SOURCE,
}

_SOURCE_FILE = re.compile(
    r"^(" + "|".join(re.escape(prefix) for prefix in _PREFIX_TO_KIND) + r")_(\d{4})\.csv(\.gz)?$",
    re.IGNORECASE,
)

_ALL_PREFIXES = frozenset(_PREFIX_TO_KIND)


class IncompleteYearError(Exception):
    """At least one year had files but not the full triple."""


def discover(
    directory: Path,
    *,
    progress: TextIO | None = None,
) -> dict[str, dict[SourceKind, Path]]:
    """Find CCRS source files in *directory*, grouped by year.

    Returns ``{year: {kind: path}}`` for every year that has all three file
    kinds.  Years with only one or two files are reported to *progress* and
    excluded — the caller gets only loadable groups.

    Raises `FileNotFoundError` if *directory* does not exist, and
    `IncompleteYearError` if *no* year has a complete triple (so there is
    nothing to load at all).
    """
    progress = sys.stderr if progress is None else progress

    if not directory.is_dir():
        raise FileNotFoundError(f"{directory}: not a directory")

    by_year: dict[str, dict[SourceKind, Path]] = defaultdict(dict)
    for child in sorted(directory.iterdir()):
        match = _SOURCE_FILE.match(child.name)
        if match is None:
            continue

        prefix = match.group(1).lower()
        year = match.group(2)
        kind = _PREFIX_TO_KIND[prefix]

        if kind in by_year[year]:
            raise ValueError(
                f"{directory} has more than one {kind.name} file for {year}: "
                f"{by_year[year][kind].name} and {child.name}"
            )

        by_year[year][kind] = child

    if not by_year:
        raise FileNotFoundError(
            f"{directory}: no CCRS source files found. Expected files named like "
            f"crashes_2025.csv, parties_2025.csv, injuredwitnesspassengers_2025.csv"
        )

    complete: dict[str, dict[SourceKind, Path]] = {}
    incomplete: list[str] = []
    for year in sorted(by_year):
        found_prefixes = {kind.name for kind in by_year[year]}
        missing = _ALL_PREFIXES - found_prefixes
        if missing:
            found_files = ", ".join(p.name for p in by_year[year].values())
            missing_names = ", ".join(sorted(missing))
            print(
                f"warning: {year}: skipping incomplete year — have {found_files}, "
                f"missing {missing_names}",
                file=progress,
            )
            incomplete.append(year)
        else:
            complete[year] = by_year[year]

    if not complete:
        raise IncompleteYearError(
            f"{directory}: every year found is incomplete. "
            + "; ".join(
                f"{y}: missing {', '.join(sorted(_ALL_PREFIXES - {k.name for k in by_year[y]}))}"
                for y in incomplete
            )
        )

    return complete
