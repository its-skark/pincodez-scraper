# pincodez-scraper

`pincodez-scraper` is a courteous, restartable scraper for building a structured India postal-address dataset from [pincodez.info](https://pincodez.info). It collects states and districts, PIN-code and post-office records, sub-districts/tehsils, coordinates, and DIGIPINs, then produces JSONL, CSV, and a queryable SQLite database.

**Current version:** `0.1.0`

The scraper is deliberately rate limited. It shares one adaptive request limiter between concurrent workers, backs off and persists its state when it encounters a bot wall or temporary service failure, and can resume completed units after an interruption.

## What it produces

The default output directory is `data/`:

| Path | Contents |
| --- | --- |
| `raw/` | Downloaded source CSV exports. |
| `jsonl/` | One JSON object per line for source-derived and normalized entities. |
| `csv/` | CSV mirrors generated from normalized JSONL. |
| `pincodez.sqlite` | SQLite database with indexes and FTS5 full-text search tables. |
| `state/checkpoints.db` | Per-phase checkpoints used by `--resume`. |
| `state/limiter.json` | Persisted rate-limit and cooldown state. |
| `validation_report.json` | Results and artifact digests from `validate`. |
| `conflicts.jsonl` | Differences found between bulk exports and per-PIN detail data. |

The included local dataset validates with 36 states/UTs, 737 districts, 6,000 sub-districts, 19,300 PIN codes, and 157,126 post offices. Counts describe this captured dataset and will change as the upstream source changes.

## Requirements

- [Devbox](https://www.jetify.com/devbox/) (recommended for this repository)
- Or Python 3.12 or later and [uv](https://docs.astral.sh/uv/)

The included `devbox.json` pins the development environment to Python 3.12 and uv 0.13.4, and also provides SQLite, jq, ripgrep, and curl. It configures uv to place the virtual environment in `.venv`.

## Install

### Devbox (recommended)

Enter the repository's reproducible development shell, then resolve the application and test dependencies:

```bash
devbox shell
uv sync --group dev
```

Once inside the Devbox shell, use all of the `uv run ...` commands in this guide as written. For one-off commands without opening an interactive shell, prefix them with `devbox run --`:

```bash
devbox run -- uv sync --group dev
devbox run -- uv run pincodez info
devbox run -- uv run pytest
```

### Existing uv environment

If Devbox is not being used, install with uv:

```bash
uv sync --group dev
```

Or install the package in an existing Python 3.12+ environment:

```bash
python -m pip install -e .
```

The test dependencies are defined as a uv dependency group. For a pip-managed environment, install them separately:

```bash
python -m pip install pytest pytest-asyncio
```

Confirm the command and its resolved settings:

```bash
uv run pincodez --help
uv run pincodez info
```

## Quick start

Use a separate directory while experimenting so the included dataset is untouched:

```bash
# Fetch a small, representative dataset: all discovery phases and 25 PIN details.
uv run pincodez --data-dir run-data scrape all --sample 25

# Materialize run-data/pincodez.sqlite and CSV files.
uv run pincodez --data-dir run-data build-db
```

The `--sample` option limits only the per-PIN detail phase. A sampled run is useful for checking connectivity and the output shape, but is not a complete dataset and is not expected to pass the full row-count validation gate.

To retrieve the full dataset:

```bash
uv run pincodez --data-dir run-data scrape all
uv run pincodez --data-dir run-data build-db
uv run pincodez --data-dir run-data validate
```

## Command guide

Global options belong before the command or command group:

```text
pincodez [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]
```

| Command | Purpose |
| --- | --- |
| `scrape states` | Fetch the state/UT index and state details, including district lists. |
| `scrape districts` | Fetch district details and the district-to-PIN membership map. |
| `scrape bulk` | Download and normalize all-India post-office and PIN-code CSV exports. |
| `scrape pins [--sample N]` | Fetch authoritative detail JSON for each discovered PIN and normalize post offices. |
| `scrape subdistricts` | Extract sub-district/tehsil names from district pages. |
| `scrape all [--sample N]` | Run the five scraping phases in dependency order. |
| `build-db` | Rebuild SQLite and CSV artifacts from JSONL files. |
| `validate` | Run integrity gates and write `validation_report.json` and `conflicts.jsonl`. |
| `verify [--sample N] [--seed N]` | Re-fetch a deterministic random sample and compare it with stored PIN/post-office data. |
| `info` | Print the effective data directory, rate settings, and resume mode. |
| `digipin encode --lat LAT --lon LON` | Encode coordinates as a 10-character DIGIPIN. |
| `digipin decode CODE` | Return a DIGIPIN cell’s bounds and centre as JSON. |

### Important global options

| Option | Default | Meaning |
| --- | --- | --- |
| `--data-dir PATH` | `data` | Root for all outputs, checkpoints, and rate-limit state. |
| `--resume` | off | Append to phase output and skip checkpointed work. |
| `--rate FLOAT` | `6.0` | Initial global requests per second. The rate auto-tunes within its bounds. |
| `--rate-min FLOAT` / `--rate-max FLOAT` | `2.0` / `8.0` | Lower and upper bounds for automatic tuning. |
| `--workers INT` | `4` | Concurrent workers sharing the one global limiter. |
| `--user-agent TEXT` | built-in browser-like value | Override the HTTP `User-Agent`. |

For example, resume an interrupted full scrape with fewer workers:

```bash
uv run pincodez --data-dir run-data --resume --workers 2 scrape all
```

`--resume` is intended for the same data directory. Without it, each scraper phase rewrites its phase output; use a new `--data-dir` when you want an independent run.

### Recommended staged workflow

The all-in-one command is convenient, but these commands make it easier to inspect intermediate artifacts:

```bash
uv run pincodez --data-dir run-data scrape states
uv run pincodez --data-dir run-data scrape districts
uv run pincodez --data-dir run-data scrape bulk
uv run pincodez --data-dir run-data scrape pins
uv run pincodez --data-dir run-data scrape subdistricts
uv run pincodez --data-dir run-data build-db
uv run pincodez --data-dir run-data validate
```

`states` must run before `districts`; `pins` needs PINs discovered by `bulk` or `districts`; and `subdistricts` needs `districts`. `build-db` should follow the relevant scrape phases. It replaces the SQLite file at the selected data directory, so close any application holding that database first.

## Querying the SQLite database

The database contains `states`, `districts`, `subdistricts`, `pincodes`, `post_offices`, and `district_pincodes`. Foreign-key relationships and useful lookup indexes are created during `build-db`.

Use the `sqlite3` CLI:

```bash
sqlite3 run-data/pincodez.sqlite \
  "SELECT name, office_type, district_name, state_name
   FROM post_offices
   WHERE pincode = '122001'
   ORDER BY name;"
```

Two FTS5 virtual tables support text search:

```sql
SELECT po.name, po.pincode, po.district_name, po.state_name
FROM post_offices_fts AS search
JOIN post_offices AS po ON po.rowid = search.rowid
WHERE post_offices_fts MATCH 'gurgaon';
```

For a PIN code’s district membership and the authoritative PIN record:

```sql
SELECT p.pincode, p.district_name, p.state_name,
       p.latitude, p.longitude, p.digipin
FROM pincodes AS p
WHERE p.pincode = '122001';
```

## Data model notes

- `pincodes` contains the canonical PIN-level geography, counts, coordinates, DIGIPIN, and source/release metadata.
- `post_offices` contains office type, delivery status, hierarchy fields, coordinates, DIGIPIN, and a reference to `pincodes.pincode`.
- `district_pincodes` retains the source’s district-to-PIN mapping and its PIN-level counts.
- `latitude`, `longitude`, `digipin`, and `taluk` may be null or empty when the upstream source does not provide a value. Do not treat a missing coordinate as `(0, 0)`.
- The source can publish aggregate counters that differ from the deduplicated membership data. The validation report records those differences; use the row-level records and `district_pincodes` for exact membership.

## Validation and verification

`validate` checks row counts, foreign-key relationships, unique IDs, coordinate bounds, DIGIPIN format and re-encoding, district membership, bulk-versus-detail consistency, and JSONL SHA-256 digests. It exits non-zero if a required check fails.

```bash
uv run pincodez --data-dir run-data validate
uv run pincodez --data-dir run-data verify --sample 100 --seed 42
```

`verify` performs live requests, so its result can legitimately differ after the source updates. It reports up to the first 50 differences in its command result.

## DIGIPIN utilities

The DIGIPIN commands work locally; they do not make network requests:

```bash
uv run pincodez digipin encode --lat 28.622788 --lon 77.213033
# 39J49LL8T4  (39J49-LL8T4)

uv run pincodez digipin decode 39J49LL8T4
```

`decode` returns the cell’s minimum/maximum latitude and longitude along with its centre. Inputs outside the supported grid, and malformed codes, are rejected.

## Responsible use and source freshness

This project reads from a third-party site. Respect its terms, robots policy, capacity, and applicable laws before running a full collection. Keep the default conservative rate settings, avoid simultaneous runs against the same source, and use `--resume` instead of restarting after an interruption. The data is a snapshot, not an official postal authority feed; retain source and release metadata and verify important downstream uses against an authoritative source.

## Development

Run the test suite after installing the development dependencies:

```bash
uv run pytest
```

The tests cover the local DIGIPIN implementation, request-rate/wall handling, source-page parsers, and normalization helpers. They do not require a full live scrape.
