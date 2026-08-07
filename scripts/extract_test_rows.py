#!/usr/bin/env python3
"""Extract a deterministic sample of CCRS source rows for the golden test.

Reads the full source CSVs from a data directory, selects rows whose
collision ID is in the curated set below, and writes small sample files to
``tests/data/``.  The sample is chosen to cover NULLs, both-vehicle parties,
witnesses, the ragged row and its neighbors, two-tone colors, unmapped makes,
multi-valued road conditions, hit-and-run codes, multiple years, and orphan
foreign keys (the ragged row's crash has no surviving parties).

Run from the repo root:

    python scripts/extract_test_rows.py /path/to/ccrs-data

The output files are checked into git; re-running the script reproduces them
identically (the source CSVs are deterministic for a given download).
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

# Collision IDs chosen to cover the cases the plan lists.  Each is annotated
# with what it contributes; many cover more than one case.
#
# 2016 (earliest year — tests format-convention stability):
#   86779  plain crash, 2016-01-01
#   86890  NULL lat/lon, DispatchNotified=NotApplicable
#   86947  DispatchNotified=NotApplicable
#   86948  plain 2016 crash
#   86950  DispatchNotified=NotApplicable
#   86974  NULL lat/lon
#   87035  witness (IWP is_witness_only), hit-run M, NULL party_number on IWP
#   87063  hit-run M
#   87224  NULL lat/lon
#   87239  witness, NULL party_number on IWP
#   87329  hit-run M
#   87342  witness, NULL party_number on IWP
#   87573  4+ parties on one crash
#   87726  two-vehicle party (tractor+trailer)
#   87976  4+ parties
#   88109  4+ parties
#   88214  road_condition_1 with " - " separator
#   88228  road_condition_1 with " - " separator
#   88848  two-vehicle party
#   88859  two-vehicle party
#   90407  road_condition_1 with " - " separator
#   98909  two-tone vehicle color
#   98918  two-tone color
#   98934  unmapped make
#   98939  unmapped make
#   98946  two-tone color + unmapped make
#
# 2025 (ragged row and neighbors):
#   4649435  neighbor after ragged row
#   4649436  the ragged row's crash (its only party is skipped → 0 parties)
#   4649437  neighbor before ragged row
#
# 2026 (latest partial year):
#   4995299  2026 crash
#   4995434  2026 crash
#   4995442  2026 crash

SAMPLE_COLLISION_IDS: frozenset[int] = frozenset(
    {
        86779,
        86890,
        86947,
        86948,
        86950,
        86974,
        87035,
        87063,
        87224,
        87239,
        87329,
        87342,
        87573,
        87726,
        87976,
        88109,
        88214,
        88228,
        88848,
        88859,
        90407,
        98909,
        98918,
        98934,
        98939,
        98946,
        4649435,
        4649436,
        4649437,
        4995299,
        4995434,
        4995442,
    }
)

# Which source column holds the collision ID, per file kind.
_COLLISION_ID_HEADERS = {
    "crashes": "collision id",
    "parties": "collisionid",
    "injuredwitnesspassengers": "collisionid",
}

# Which years to scan for the sample.  Only years that contain at least one
# sample collision ID need scanning, but listing all is harmless — an empty
# year just writes a header-only file if no IDs match (which won't happen
# with the curated set).
_YEARS = ("2016", "2025", "2026")

_KINDS = ("crashes", "parties", "injuredwitnesspassengers")


def _find_collision_id_index(header: list[str], kind: str) -> int:
    target = _COLLISION_ID_HEADERS[kind]
    for i, cell in enumerate(header):
        if cell.strip().lower() == target:
            return i
    raise ValueError(f"no {target!r} column in {kind} header")


def _extract(data_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for kind in _KINDS:
        all_rows: list[list[str]] = []
        header: list[str] | None = None

        for year in _YEARS:
            source = data_dir / f"{kind}_{year}.csv"
            if not source.exists():
                print(f"  skipping {source.name} (not found)", file=sys.stderr)
                continue

            with source.open(newline="", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                file_header = next(reader)

                if header is None:
                    header = file_header
                    cid_index = _find_collision_id_index(header, kind)

                for row in reader:
                    if cid_index < len(row):
                        raw = row[cid_index].strip()
                        if raw.isdigit() and int(raw) in SAMPLE_COLLISION_IDS:
                            all_rows.append(row)

        if header is None:
            print(f"  warning: no source files found for {kind}", file=sys.stderr)
            continue

        out_path = output_dir / f"{kind}.csv"
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for row in all_rows:
                writer.writerow(row)

        print(f"  {out_path.name}: {len(all_rows)} rows", file=sys.stderr)


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} DATA_DIR", file=sys.stderr)
        return 2

    data_dir = Path(sys.argv[1])
    if not data_dir.is_dir():
        print(f"error: {data_dir} is not a directory", file=sys.stderr)
        return 1

    output_dir = Path("tests/data/golden")
    print(
        f"extracting {len(SAMPLE_COLLISION_IDS)} collision IDs into {output_dir}/", file=sys.stderr
    )
    _extract(data_dir, output_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
