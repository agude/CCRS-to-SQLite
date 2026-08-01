# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog][keepachangelog], and this project
adheres to [Semantic Versioning][semver].

[keepachangelog]: https://keepachangelog.com/en/1.1.0/
[semver]: https://semver.org/spec/v2.0.0.html

## [Unreleased]

### Added

- Repo scaffolding: uv + hatchling packaging, ruff, mypy strict, pytest with
  a 90% coverage gate, a `justfile` holding the one definition of each
  check, a pre-commit hook that calls it, and CI over CPython 3.11–3.14 and
  PyPy.
- `ccrs_to_sqlite` console script and a `convert()` library function that
  read named CCRS source files into a typed SQLite database.
- Five `STRICT` tables: `crashes`, `parties`, `vehicles`,
  `injured_witness_passengers`, and `metadata`. Indexes are built after the
  load.
- Header-driven column mapping, checked against verbatim copies of the real
  2025 header rows. Unknown and missing headers are both fatal.
- Value converters producing ISO dates and times, `INTEGER` booleans, and
  `NULL` for empty cells, with whitespace stripped everywhere.
- The two inline vehicle groups on a party row are lifted into `vehicles`,
  with `make_raw` kept verbatim beside a normalized `make` that is `NULL`
  when unmapped.
- Transparent `.csv.gz` support, detected from the file's contents rather
  than its name, and `--parse-error` for undecodable bytes.
- Malformed rows are skipped with a warning naming the file and line, and
  counted; `--strict` makes them fatal. A primary key supplied by two files
  is always fatal.
- Orphaned `collision_id`s are counted and reported rather than rejected.
- The output file is built under a temporary name and renamed into place on
  success; an existing database is never overwritten.

### Not yet implemented

- Directory mode (`ccrs_to_sqlite DATA_DIR`), which is the planned primary
  interface.
