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
| `vehicles` | one row per vehicle, 0–2 per party, keyed by `(party_id, vehicle_number)` |
| `injured_witness_passengers` | one row per injured person, witness, or passenger |
| `metadata` | a log of the load; see below |

`PRAGMA user_version` holds the schema version, so a consumer can check the
file's shape without introspecting it. That is a different question from
`metadata.converter_version`, which records which release wrote the file.

Notable conversions:

- `Crash Date Time` becomes `crash_date` (`YYYY-MM-DD`) and `crash_time`
  (`HH:MM:SS`), and `NotificationDate` splits the same way. `PreparedDate`,
  `ReviewedDate`, `CreatedDate` and `ModifiedDate` become ISO datetimes in
  one column. ISO text sorts correctly and works with SQLite's date
  functions.
- **Times are resolved from two source columns, not one.** See below — this
  is the one place the converter does more than translate a single cell.
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

### How times of day are resolved

CCRS answers "when did this happen" twice, and neither answer alone is right.

`Crash Date Time` is a merged DateTime, but the data dictionary defines it as
*"the date when the collision occurred (YYYYMMDD)"* — a date. The time it also
carries is undocumented, and reads midnight on every row where no time was
recorded. The field the dictionary actually defines as the time of the crash
is a separate four-character 24-hour string, shipped as
`Crash Time Description`, whose marker for an unknown time is `2500`.

So `crash_time` is resolved from both:

1. use `Crash Time Description` when it holds a real clock reading;
2. otherwise fall back to the time in `Crash Date Time`, unless that is
   midnight;
3. otherwise `NULL`.

Measured on the 2025 file, out of 400,215 crashes:

| Case | Rows | Resolved to |
|---|---|---|
| both sources agree | 391,155 | that time |
| merged column is a midnight placeholder, description has the time | 3,189 | the description |
| both hold real times that differ | 1,603 | the description |
| genuine midnight, stated as `0000` | 439 | `00:00:00` |
| description says `2500`, merged column has a real time | 77 | the merged column |
| neither recorded a time | 3,747 | `NULL` |

Reading the merged column alone would have asserted midnight for 3,731 crashes
that never recorded one, making `00:00:00` the most common time in the
database by a factor of three. Reading only the description would have thrown
away the 77 rows it has no answer for.

`crash_time_description` is kept raw beside `crash_time`, so every value the
resolver settled on stays auditable — the same arrangement as `make_raw` and
`make`. `notification_date` / `notification_time` work identically; those are
the only two such pairings in the dataset.

### `metadata`

A log with two kinds of row, told apart by `record_type`:

| `record_type` | Fills |
|---|---|
| `file_load` | `source_file`, `year_label`, `rows_read`, `rows_loaded`, `rows_skipped` |
| `orphan_count` | `orphan_rows` — a property of the finished database, not of any one file |

Both fill `table_name`, `converter_version`, and `loaded_at_utc`. That last
one is UTC; every other timestamp in the database is California local time,
as the source supplies it.

### Caveats worth knowing before you query

Measured on the 2025 file:

- **22.3% of crashes have no coordinates** (89,158 of 400,215). Any map or
  spatial aggregate silently covers about three quarters of the data.
- **884 longitudes are positive**, i.e. sign-flipped into China, and roughly
  1,600 fall outside California altogether. Both are stored as they came.
- **`crash_time` is `NULL` on 3,747 rows** (0.94%) because no time was
  recorded for them. That is deliberate — see the section below.
- **`is_deleted` is false on every row.** The published files carry only the
  current version of each report, so the column is present for fidelity and
  tells you nothing.
- `special_condition` and `road_condition_1` are multi-valued free text, not
  enums.

Indexes cover the documented relationships, not every column you might filter
on. Adding your own is one statement against a local file, and the semver
policy below does not treat that as a schema change.

## Development

```bash
just sync           # install dependencies
just hooks-install  # install the pre-commit hook (once per clone)
just check          # lint + type-check + test
```

`just --list` shows every recipe. See `AGENTS.md` for repo conventions.

## Versioning

From v1.0 the schema is frozen: anything that changes the data stored for
input that already converted waits for the next major release. Renaming a
column, retyping one, or changing how a value is normalized all count.

Two things deliberately do not count, because they change how the database is
reached rather than what it says:

- adding or removing an index
- `PRAGMA user_version`, which is bumped precisely so consumers can see a
  schema change coming

Without that carve-out, noticing a missing index a year after release would
force a major version, which is a good way to guarantee the index never gets
added.

## License

CC0-1.0. See `LICENSE.md`.

The CCRS source data is public domain and is not covered by this license
either.
