# DB Export Design — State Procurement Scrapers

**Date:** 2026-05-28
**Scope:** Shared MySQL export utility for PA and CA enriched CSVs

---

## Problem

PA (`pa/solicitations_enriched.csv`) and CA (`cali/events_enriched.csv`) scrapers produce flat enriched CSVs. The backend teammate needs a way to load this data into their own local MySQL tables without writing custom import logic per state.

---

## Solution Overview

A single `db_export.py` script at the project root. It reads a state's enriched CSV, auto-creates the MySQL table if it doesn't exist, and upserts all successful rows. Credentials live in a `.env` file at the project root.

---

## Files

| File | Status | Purpose |
|---|---|---|
| `db_export.py` | new | Standalone export script |
| `.env` | new (gitignored) | MySQL credentials |
| `.env.example` | new (committed) | Credential template for the teammate |
| `requirements.txt` | updated | Add `pymysql`, `python-dotenv` |

---

## Usage

```bash
# From the project root, with venv active:
python db_export.py pa      # exports pa/solicitations_enriched.csv → pa_solicitations
python db_export.py cali    # exports cali/events_enriched.csv      → cali_events
```

---

## State Registry

Inside `db_export.py`, a dict drives all state-specific behavior. Adding a new state = one new dict entry.

```python
STATE_CONFIG = {
    "pa": {
        "csv_path": "pa/solicitations_enriched.csv",
        "table":    "pa_solicitations",
        "pk_col":   "Bid No",
    },
    "cali": {
        "csv_path": "cali/events_enriched.csv",
        "table":    "cali_events",
        "pk_col":   "Event ID",
    },
}
```

---

## Column Handling

- Column names are normalized to snake_case: `"Bid No"` → `bid_no`, `"Buyer Name"` → `buyer_name`
- Column types are inferred from pandas dtypes:
  - `object` → `TEXT`
  - `int64` → `BIGINT`
  - `float64` → `DOUBLE`
- Since both scrapers produce string-typed CSVs, virtually all columns will be `TEXT`
- The PK column gets `PRIMARY KEY` on table creation
- The teammate can cast to target types in SQL as needed

---

## Table Creation

```sql
CREATE TABLE IF NOT EXISTS pa_solicitations (
    bid_no TEXT PRIMARY KEY,
    bid_type TEXT,
    title TEXT,
    ...
);
```

Safe to run on every export — no-ops if table already exists.

---

## Upsert Logic

- Only rows with `scrape_status == "success"` are exported (error rows have empty scraped fields and are skipped)
- Rows are upserted in batches of 500:
  ```sql
  INSERT INTO pa_solicitations (...) VALUES (...)
  ON DUPLICATE KEY UPDATE col1=VALUES(col1), col2=VALUES(col2), ...
  ```
- Progress printed to stdout: `[500/1402] upserted...`
- Final summary: `Done. 1402 rows upserted to pa_solicitations.`

---

## Credentials

`.env.example` (committed to git):
```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=procurement
```

The teammate copies this to `.env` and fills in their values. If `.env` is missing, the script exits with a message pointing to `.env.example`.

---

## Error Handling

| Scenario | Behavior |
|---|---|
| CSV file not found | Exit with clear message naming the missing file |
| `.env` missing | Exit, prompt teammate to copy `.env.example` |
| DB connection failure | Exit with the MySQL error message |
| Row with null/empty PK | Skip with a warning, continue |
| Unknown state argument | Print list of valid state keys and exit |

---

## Dependencies Added

- `pymysql` — pure-Python MySQL driver, no system dependencies
- `python-dotenv` — reads `.env` file into environment variables

---

## Out of Scope

- DB normalization / common schema across states (tracked in CLAUDE.md as pending)
- Automated invocation — this is a manual tool for the teammate
