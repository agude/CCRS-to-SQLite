# AGENTS.md

Instructions for AI coding assistants working in this repo.

## Project

`ccrs-to-sqlite` converts California Crash Reporting System (CCRS) CSV
exports from <https://data.ca.gov/dataset/ccrs> into a SQLite database.

It is the successor to `switrs-to-sqlite` (SWITRS access was disabled in
2025) and is **not** backwards compatible with the SWITRS database format.

The design rationale lives in the code that implements it: read the module
docstring of `schema.py` before changing the schema and of `converters.py`
before changing a converter. `README.md` carries the source-data quirks and
the measured counts behind them. There is no separate design document —
earlier revisions referred to a `plan.md` that was never tracked in git.

Status: milestone v0.1.0 is complete except for directory mode. Named source
files convert into the full schema. Directory discovery, the full make map,
and the golden test are the next target.

## Schema changes

The schema freezes at v1.0 and is the deliverable. `tests/data/schema.sql` is
a snapshot of the exact DDL; a rename or a retype fails
`test_the_schema_matches_the_checked_in_snapshot` and nothing else. When the
change is deliberate, run `just schema-snapshot`, review the diff, and bump
`SCHEMA_VERSION` in `schema.py` in the same commit.

## Archetype

Python package (see the project-standards skill,
`references/python-package.md`).

Zero runtime dependencies by design: `csv` and `sqlite3` from the standard
library handle the data volume. Do not add a runtime dependency without a
measured reason.

## Tooling

| Verb | Does |
|---|---|
| `just sync` | install dependencies |
| `just lint` | ruff check + format check (read-only) |
| `just format` | ruff format + fix |
| `just type-check` | mypy strict over `src/` and `tests/` |
| `just test` | pytest with coverage |
| `just check` | full gate: lint + type-check + test |
| `just build` | build the wheel and sdist |
| `just hooks-install` | install the pre-commit hook once per clone |

## Data

`tmp_data/` holds full-year source CSVs (gigabytes) and is gitignored.
Re-download from <https://data.ca.gov/dataset/ccrs>. Small deterministic
samples for the golden test belong in `tests/data/` and are tracked.

## Known exceptions

- **`requires-python = ">=3.11"`.** The standard floor is the oldest non-EOL
  CPython, which is 3.10 until October 2026. 3.10 goes EOL before this
  package reaches v1.0, so supporting it would mean claiming a version the
  matrix drops within months.
*(None besides the Python floor above.)*
