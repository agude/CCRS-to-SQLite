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
not implemented yet. The schema is documented below and is not frozen until
v1.0; see `CHANGELOG.md` for what has landed.

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
  is `NULL` when the make map does not cover the string. The map covers 96.7%
  of vehicle rows across all published years, over 86 makers. It has to carry
  two conventions: the later years use NCIC codes (`TOYT`), the earlier ones a
  plain truncation (`TOYO`), and `TOYO` alone is 498,501 rows.
- `vehicle_number` is which source column group the row came from, not an
  ordinal over the party's vehicles. An empty first group is skipped, so a
  party carrying only `Vehicle2*` columns would get one row numbered 2 and no
  row numbered 1. Density is therefore not guaranteed — though across all
  published years, no such party exists: every one of the 9.2M vehicle rows
  is dense.

Foreign keys are declared and indexed, but deliberately not enforced —
`PRAGMA foreign_keys` is off, which is SQLite's default. Reports straddling a
year boundary genuinely put a party in one file and its crash in another, so
enforcement would reject valid rows; the orphans are counted and reported
instead. The declarations are there so tools can read the relationships out of
the file:

| Child | Parent |
|---|---|
| `parties.collision_id` | `crashes.collision_id` |
| `vehicles.party_id` | `parties.party_id` |
| `vehicles.collision_id` | `crashes.collision_id` |
| `injured_witness_passengers.collision_id` | `crashes.collision_id` |

A person is linked to their party by `(collision_id, party_number)`, which
both tables index. **That pair is not unique**, so the join can fan out:
measured across all eleven published years, 42 pairs are claimed by two
`parties` rows each (85 rows in ~9M). It is a fifth foreign key that cannot be
declared for the same reason — SQLite requires a unique parent.

In practice the join is reliable enough to use and too lossy to trust blindly:
every `parties` row has a `party_number`, so it never silently drops a person,
but an aggregate over it will occasionally double-count one. `party_id` is the
only truly unique handle on a party.

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

Measured across all published years, out of 4,591,340 crashes:

| Case | Rows | Resolved to |
|---|---|---|
| both sources agree | 4,537,311 | that time |
| merged column is a midnight placeholder, description has the time | 4,644 | the description |
| both hold real times that differ | 1,787 | the description |
| description unusable (`2500` and friends), merged column has a real time | 487 | the merged column |
| neither recorded a time | 47,111 | `NULL` |

Reading the merged column alone would have asserted midnight for the 4,644
crashes in the second row plus every one of the 47,111 that recorded no time
at all, making `00:00:00` the most common time in the database by a wide
margin. Reading only the description would have thrown away the 487 rows it
has no answer for.

Both failure modes are concentrated in recent years: 2025 alone accounts for
3,190 of the 4,644 placeholder rows and 1,605 of the 1,787 disagreements. A
converter built and validated against one year would have been tuned almost
entirely by that year's quirks.

Both inputs are kept raw beside the resolved column, so every value the
resolver settled on stays auditable — the same arrangement as `make_raw` and
`make`:

| Column | Holds |
|---|---|
| `crash_time` | the resolved time, `NULL` when neither source named one |
| `crash_time_description` | `Crash Time Description` as it came, padded to four digits |
| `crash_time_merged` | the time half of `Crash Date Time`, including its midnights |

Keeping only the description would half-build the audit trail: `crash_date`
takes only the date half of the merged column, so the merged *time* would
survive nowhere. Find the rows where the two disagree with
`WHERE crash_time <> crash_time_merged`.

That also means **`crash_date || ' ' || crash_time` is not a source value.**
On the 1,787 rows where the two sources hold different real times, the
concatenation names a moment neither of them stated.

`notification_date` / `notification_time` / `notification_time_merged` work
identically; those are the only two such pairings in the dataset.

### `metadata`

A log with two kinds of row, told apart by `record_type`:

| `record_type` | Fills |
|---|---|
| `file_load` | `source_file`, `year_label`, `rows_read`, `rows_loaded`, `rows_skipped` |
| `orphan_count` | `orphan_rows` — a property of the finished database, not of any one file |

Both fill `table_name`, `converter_version`, and `loaded_at_utc`. That last
one is UTC; every other timestamp in the database is California local time,
as the source supplies it. `record_type`, `table_name`, `converter_version`
and `loaded_at_utc` are `NOT NULL`, and `record_type` carries a `CHECK` naming
the two values, so `.schema` describes the table without reference to this
README.

There is one `file_load` row per table filled, not per file — a parties file
logs two, one for `parties` and one for `vehicles`. On the `vehicles` row,
`rows_read` counts the parties rows it was derived from, since vehicles are
never read directly, and `rows_skipped` counts parties kept whose inline
vehicle columns would not convert.

### Caveats worth knowing before you query

Measured across all 4,591,340 published crashes:

- **31.0% of crashes have no coordinates** (1,423,619). Any map or spatial
  aggregate silently covers about two thirds of the data. This is worse than
  it looks from a recent year alone — 2025 is 22.3%, so coverage has been
  improving and the older years drag the total down.
- **3,281 longitudes are positive**, i.e. sign-flipped into the eastern
  hemisphere, and 9,276 fall outside a California bounding box altogether.
  Both are stored as they came.
- **`crash_time` is `NULL` on 47,111 rows** (1.03%) because no time was
  recorded for them. That is deliberate — see the section below.
- **`is_deleted` is false on every row**, confirmed across all 4.6M. The
  published files carry only the current version of each report, so the
  column is present for fidelity and tells you nothing.
- `special_condition` and `road_condition_1` are multi-valued free text, not
  enums.
- **`crash_time_description` is not guaranteed to be four characters.** Values
  it can read as a clock reading are normalized to four digits; anything else
  — free text like `UNK` — would be kept exactly as it came. No published row
  is anything else: all 4,591,338 non-empty values are four digits, including
  the `2500` unknown-time marker. Filter on `length(...) = 4` if you want to
  stay safe against a future file, but it currently removes nothing.
- Rows whose values do not fit their column are skipped and counted, not
  silently nulled. `metadata.rows_skipped` says how many, per file and table,
  and each one printed a warning naming its line. Across all eleven years
  that is **one row in 19,096,894** — a single party row with two extra
  fields, from an unquoted comma in free text.

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
