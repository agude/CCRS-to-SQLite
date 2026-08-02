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
  check, a pre-commit hook that calls it, and CI over CPython 3.11–3.14.
- `ccrs_to_sqlite` console script and a `convert()` library function that
  read named CCRS source files into a typed SQLite database.
- Five `STRICT` tables: `crashes`, `parties`, `vehicles`,
  `injured_witness_passengers`, and `metadata`. Indexes are built after the
  load.
- Header-driven column mapping, checked against verbatim copies of the real
  2025 header rows. Unknown and missing headers are both fatal.
- Value converters producing ISO dates and times, `INTEGER` booleans, and
  `NULL` for empty cells, with whitespace stripped everywhere.
- Times of day are resolved from both source columns that describe them —
  the merged `DateTime` and the dedicated four-character field — rather than
  read off the merged column, whose time half is midnight wherever no time
  was recorded. `crash_time` and `notification_time` are `NULL` when neither
  source names a time, instead of asserting a midnight.
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

- `PRAGMA user_version` records the schema version, and `metadata.record_type`
  names which of the two kinds each log row is.
- Every source file is checked for existence and readability before any
  loading starts.
- Foreign keys are declared on all four parent/child links. They stay
  unenforced — cross-year reports would fail enforcement — but tools can now
  read the relationships out of the file rather than out of this repo.
- `crash_time_merged` and `notification_time_merged` keep the merged
  DateTime column's time half, so both inputs to a resolved time survive
  beside it. Previously only the description did, and the value the resolver
  rejected was discarded.
- `metadata` declares its invariants: `record_type`, `table_name`,
  `converter_version` and `loaded_at_utc` are `NOT NULL`, and `record_type`
  carries a `CHECK` naming its two values.
- A parties file now logs a `file_load` row for `vehicles` as well as for
  `parties`, so the provenance log names every table it filled and the count
  of parties kept without their vehicles is persisted rather than only
  printed.
- `tests/data/schema.sql` pins the exact DDL, regenerated with
  `just schema-snapshot`. A rename or a retype now fails a test.

- Vehicle colour is normalized the way makes are: `color_raw` keeps the
  source string, `color` and `color_secondary` hold the resolved names. 2.1%
  of values name two tones, so a single column would have had to flatten or
  drop them. The map covers 99.75% of vehicle rows over 29 colours; what is
  left is `UNK`, `OTH` and `MUL`, which name no colour.

### Fixed

- Punctuated times pad each half separately. `10:5` became `0105` — a
  well-formed clock reading nine hours from the truth, accepted by the
  resolver and indistinguishable downstream from a real value.
- `to_int` rejects integers outside SQLite's 64-bit range. They parsed
  cleanly and then raised `OverflowError` from `executemany`, which is not a
  `ValueError` and so escaped both the skipped-row path and the CLI's error
  handling, aborting the load with a bare traceback and no line number.
- `to_int` accepts only plain ASCII digits. `int()` reads underscore
  grouping and Unicode digits, so `1_0` silently became ten.
- `to_real` rejects non-finite values. SQLite stores a NaN as NULL, which
  made a NaN latitude indistinguishable from the 31% of crashes that have no
  coordinates; `inf` and `1e400` were stored as REAL infinities.
- A primary key repeated inside a single file is caught by the guard, with
  the explanation that already existed for the across-files case, instead of
  surfacing as a bare `UNIQUE constraint failed`.

### Changed

- `injured_wit_pass_id` is now `injured_witness_passenger_id`, matching the
  table it lives in and the treatment every other inherited name got.

### Not yet implemented

- Directory mode (`ccrs_to_sqlite DATA_DIR`), which is the planned primary
  interface.
