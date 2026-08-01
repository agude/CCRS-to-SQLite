# AGENTS.md

Instructions for AI coding assistants working in this repo.

## Project

`ccrs-to-sqlite` converts California Crash Reporting System (CCRS) CSV
exports from <https://data.ca.gov/dataset/ccrs> into a SQLite database.

It is the successor to `switrs-to-sqlite` (SWITRS access was disabled in
2025) and is **not** backwards compatible with the SWITRS database format.
The full design — source-data quirks, schema, parsing rules, CLI, and
milestones — lives in `plan.md`. Read it before changing anything about the
schema or the converters.

Status: milestone v0.1.0 is complete except for directory mode. Named source
files convert into the full schema. Milestone v0.2.0 in `plan.md` — directory
discovery, the full make map, and the golden test — is the next target.

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
  matrix drops within months. `plan.md` §2 sets 3.11.
*(None besides the Python floor above.)*
