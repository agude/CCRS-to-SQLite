# CCRS-to-SQLite

Convert California Crash Reporting System (CCRS) CSV exports into a SQLite
database.

The CCRS dataset is published at <https://data.ca.gov/dataset/ccrs> as three
CSVs per year — crashes, parties, and injured/witness/passengers — updated
daily and released into the public domain. This tool cleans them (ISO dates,
real integers and booleans, `NULL` for empty strings, whitespace stripped)
and loads them into one typed, indexed, queryable database.

It is the successor to [SWITRS-to-SQLite][switrs], which stopped being useful
when SWITRS access was disabled in 2025. The schema is designed fresh for
CCRS and is **not** compatible with the SWITRS database format.

[switrs]: https://github.com/agude/SWITRS-to-SQLite

## Status

Early development. Conversion works for named source files; directory mode is
not implemented yet. See `plan.md` for the design and milestones.

## Installation

```bash
pip install ccrs-to-sqlite
```

The package has no runtime dependencies beyond the standard library.

## Usage

Download the CSVs for the years you want, then name them:

```bash
ccrs_to_sqlite \
    --crashes crashes_2025.csv \
    --parties parties_2025.csv \
    --injured injuredwitnesspassengers_2025.csv \
    -o ccrs.sqlite3
```

Each flag is repeatable, so several years can go into one database. Pointing
the tool at a directory (`ccrs_to_sqlite ccrs_data/`) is the planned primary
interface but is not implemented yet.

`.csv.gz` files are accepted anywhere a `.csv` is; compression is detected
from the file's contents, not its name.

| Flag | Does |
|---|---|
| `-o`, `--output-file` | database to create (default `ccrs.sqlite3`) |
| `--strict` | treat malformed rows as fatal instead of skipping them |
| `--parse-error` | `strict`, `ignore`, or `replace` for undecodable bytes |
| `--version` | print the version |

An existing output file is never overwritten. The database is built beside it
under a temporary name and renamed into place only once it is complete, so a
failed run leaves nothing behind.

The converter is importable, too:

```python
from pathlib import Path
from ccrs_to_sqlite.main import SourceFiles, convert

convert(
    SourceFiles(crashes=(Path("crashes_2025.csv"),)),
    Path("ccrs.sqlite3"),
)
```

## Schema

Five `STRICT` tables, all column names snake_case:

| Table | Grain |
|---|---|
| `crashes` | one row per crash, keyed by `collision_id` |
| `parties` | one row per party, keyed by `party_id` |
| `vehicles` | one row per vehicle, 0–2 per party |
| `injured_witness_passengers` | one row per injured person, witness, or passenger |
| `metadata` | one row per file loaded, plus one per table for orphan counts |

Notable conversions:

- `Crash Date Time` becomes `crash_date` (`YYYY-MM-DD`) and `crash_time`
  (`HH:MM:SS`); the other timestamps become ISO datetimes in one column. ISO
  text sorts correctly and works with SQLite's date functions.
- `True`/`False` become `INTEGER` 0/1, and empty stays `NULL`. Fields that
  look boolean but are not — `hit_run` (`F`/`M`), `dispatch_notified`
  (`Yes`/`No`/`NotApplicable`) — stay `TEXT`.
- Both the code and the description columns are kept, as the source ships
  them.
- The two inline vehicle groups on a party row become rows in `vehicles`.
  `make_raw` is the source string; `make` is the normalized maker name, and
  is `NULL` when the make map does not cover the string.

Foreign keys are indexed but not enforced. Reports straddling a year boundary
genuinely put a party in one file and its crash in another, so enforcement
would reject valid rows; the orphans are counted and reported instead.

## Development

```bash
just sync           # install dependencies
just hooks-install  # install the pre-commit hook (once per clone)
just check          # lint + type-check + test
```

`just --list` shows every recipe. See `AGENTS.md` for repo conventions.

## License

CC0-1.0. See `LICENSE.md`.

The CCRS source data is public domain and is not covered by this license
either.
