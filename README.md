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

Early development. The CLI parses its arguments; conversion is not
implemented yet. See `plan.md` for the design and milestones.

## Installation

```bash
pip install ccrs-to-sqlite
```

The package has no runtime dependencies beyond the standard library.

## Usage

Download the CSVs for the years you want, then point the tool at the
directory:

```bash
ccrs_to_sqlite ccrs_data/ -o ccrs.sqlite3
```

Or name the files explicitly:

```bash
ccrs_to_sqlite \
    --crashes crashes_2025.csv \
    --parties parties_2025.csv \
    --injured injuredwitnesspassengers_2025.csv \
    -o ccrs.sqlite3
```

`.csv.gz` files are accepted anywhere a `.csv` is.

| Flag | Does |
|---|---|
| `-o`, `--output-file` | database to create (default `ccrs.sqlite3`) |
| `--strict` | treat malformed rows as fatal instead of skipping them |
| `--parse-error` | `strict`, `ignore`, or `replace` for undecodable bytes |
| `--version` | print the version |

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
