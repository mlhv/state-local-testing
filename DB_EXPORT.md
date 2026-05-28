# DB Export Utility

Exports any state's enriched CSV into a local MySQL database. Run this after a scraper `run` to load the latest procurement data into your own tables.

## Prerequisites

- MySQL 5.7+ or 8.x running locally (or accessible over the network)
- A database already created (the script creates tables automatically, but not the database itself)
- Python venv set up at the project root (see root `HANDOFF.md`)

## Setup

### 1. Install dependencies

```bash
cd ~/Desktop/state-local
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Create your .env file

```bash
cp .env.example .env
```

Open `.env` and fill in your MySQL credentials:

```
DB_HOST=localhost       # hostname or IP of your MySQL server
DB_PORT=3306            # default MySQL port
DB_USER=root            # your MySQL username
DB_PASSWORD=yourpass    # your MySQL password (leave blank if none)
DB_NAME=procurement     # the database to write into (must already exist)
```

Create the target database if it doesn't exist yet:

```sql
CREATE DATABASE procurement CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

`.env` is gitignored — never commit it.

## How to run

Run from the project root with the venv active:

```bash
python db_export.py pa      # exports PA data → pa_solicitations table
python db_export.py cali    # exports CA data → cali_events table
```

The script will:
1. Read the state's enriched CSV (must exist — run the scraper first)
2. Create the table if it doesn't exist yet
3. Upsert all successfully-scraped rows in batches of 500
4. Print progress and a final count

```
[500/1402] upserted...
[1000/1402] upserted...
[1402/1402] upserted...

Done. 1402 rows upserted to `pa_solicitations`.
```

Re-running is safe — existing rows are updated in place, new rows are inserted.

## Tables created

### `pa_solicitations`

Primary key: `bid_no` (VARCHAR 255)

All columns from `pa/solicitations_enriched.csv` are created as columns, with names converted to snake_case (e.g. `Bid Type` → `bid_type`, `Buyer Name` → `buyer_name`). Column types default to TEXT; the primary key column is VARCHAR(255).

### `cali_events`

Primary key: `event_id` (VARCHAR 255)

All columns from `cali/events_enriched.csv`, same naming convention.

## Notes

- Only rows with `scrape_status = 'success'` are exported — error rows are skipped
- Rows with a null or empty primary key are skipped with a warning
- The enriched CSV must exist before running — run `python scraper.py run` in the state folder first
- Adding a new state: add one entry to `STATE_CONFIG` at the top of `db_export.py`

## Troubleshooting

| Error | Fix |
|---|---|
| `ERROR: CSV not found: pa/solicitations_enriched.csv` | Run the PA scraper first: `cd pa && python scraper.py run` |
| `ERROR: DB_USER and DB_NAME must be set` | Copy `.env.example` to `.env` and fill in credentials |
| `ERROR: Could not connect to MySQL: ...` | Check MySQL is running and credentials in `.env` are correct |
| `No successful rows to export` | All rows in the CSV have `scrape_status = error` — re-run the scraper |
