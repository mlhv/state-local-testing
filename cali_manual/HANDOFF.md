# calEProcure Manual Scraper — Handoff

**Last updated:** 2026-06-09  
**State:** California (calEProcure)  
**Folder:** `cali_manual/`  
**Variant:** Manual XLS input — export from portal, then run script

---

## What this is

A Python scraper that enriches a manually exported list of calEProcure procurement events with full detail data (description, UNSPSC codes, buyer contact, pre-bid info, etc.) by calling the portal's internal InFlight NLX JSON API directly — no browser required.

The only difference from the fully automated `cali/` scraper is the **input**: here you download a `.xls` file from the portal yourself and drop it in this folder. The enrichment logic and output format are identical.

---

## Step 1 — Get the input XLS from calEProcure

1. Go to [https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx](https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx)
2. Search with default filters (Status = **Posted**, no other filters) to see all open events
3. Click the **Export** button (top-right of the results table) — this downloads a file named `events.xls`
4. Move `events.xls` into the `cali_manual/` folder:
   ```bash
   mv ~/Downloads/events.xls ~/Desktop/state-local/cali_manual/
   ```

> **Note:** The file has an `.xls` extension but is actually an HTML table. The scraper handles this automatically — no conversion needed.

---

## Step 2 — Set up the environment

From the repo root:

```bash
source venv/bin/activate
pip install -r cali_manual/requirements.txt
```

You also need `nlx_body.txt` in the `cali_manual/` folder — this is the static POST body template for the detail API. Copy it from the sibling scraper:

```bash
cp cali/nlx_body.txt cali_manual/
```

---

## Step 3 — Run the scraper

Always run from inside the `cali_manual/` folder so relative paths resolve correctly:

```bash
cd cali_manual/

# Sanity check — scrapes one event and prints all fields
python scraper.py probe

# Full run — scrapes all events in events.xls
python scraper.py run
```

**Expected output for `probe`:**

```
Loaded 335 rows. Columns: ['Department', 'Department Name', 'Event ID', ...]
Probing: https://caleprocure.ca.gov/event/2660/08A4002

=== Description ===
...
=== UNSPSC Codes ===
...
=== Event Details ===
Buyer Name:   ...
Buyer Email:  ...
```

**Expected output for `run`:**

```
Loaded 335 rows. ...
[1/335] https://caleprocure.ca.gov/event/...
[2/335] ...
...
Done. 335 rows saved to events_enriched.csv
```

A full run of ~335 events takes roughly **3 minutes** at the built-in 0.5s delay.

### Resume safety

The run is safe to interrupt. Each row is written to `events_enriched.csv` immediately after it's scraped with a `scrape_status` of `success` or `error`. On rerun:

- `success` rows are skipped
- `error` rows are retried automatically

---

## Step 4 — Load into MySQL

From the **repo root** (not inside `cali_manual/`):

```bash
# Set up credentials (one-time)
cp .env.example .env
# Edit .env — fill in DB_USER, DB_PASSWORD, DB_NAME

# Load into MySQL
python db_export.py cali_manual
```

This will:
1. Read `cali_manual/events_enriched.csv`
2. Filter to only `scrape_status = success` rows
3. Auto-create table `cali_events` if it doesn't exist (columns inferred from CSV, `event_id` as primary key)
4. Upsert all rows in batches of 500 (`ON DUPLICATE KEY UPDATE` — safe to re-run)

**MySQL credentials** (`.env`):

```
DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=
DB_NAME=procurement
```

> **Same table as the automated scraper:** `cali_manual` writes to `cali_events`, the same table used by `python db_export.py cali`. If you're running both scrapers, they will upsert into the same table — that's intentional, `Event ID` is the primary key so there are no duplicates.

---

## Output schema

`events_enriched.csv` — all columns from the input XLS are carried through, plus these appended columns:

| Column | Source | Notes |
|---|---|---|
| Department | XLS export | Numeric or alphanumeric dept code (e.g. `2660`, `SS100`) |
| Department Name | XLS export | e.g. "Dept of Transportation" |
| Event ID | XLS export | e.g. `08A4002` — **primary key** |
| Event Name | XLS export | Title of the bid |
| Format | XLS export / Detail API | e.g. "Sell Event" |
| Type | XLS export / Detail API | e.g. "RFx", "IFB" |
| End Date | XLS export | Closing date/time |
| Status | XLS export | "Posted" for all active bids |
| Buyer Name | XLS export / Detail API | Contact person |
| Buyer Email | XLS export / Detail API | Contact email |
| description | Detail API | Full text description |
| unspsc_codes | Detail API | Semicolon-separated: `81101500: Professional engineering services` |
| contractor_licenses | Detail API | Semicolon-separated (construction bids only): `B: General Building Contractor` |
| counties | Detail API | Semicolon-separated service area counties |
| service_area_ids | Detail API | Semicolon-separated calEProcure area IDs, aligned with `counties` |
| event_version | Detail API | Integer version of the event |
| published_date | Detail API | e.g. `05/07/2026  7:00AM PDT` |
| contact_phone | Detail API | Buyer phone number |
| prebid_mandatory | Detail API | `Mandatory` or `Non Mandatory` |
| prebid_date | Detail API | Pre-bid conference date (empty if none) |
| prebid_time | Detail API | Pre-bid conference time |
| prebid_location | Detail API | Pre-bid conference location |
| prebid_comments | Detail API | Pre-bid conference comments |
| scrape_status | Scraper | `success` or `error` |
| event_url | Constructed | `https://caleprocure.ca.gov/event/{dept}/{event_id}` |

> **Note on Format/Type/Buyer Name/Buyer Email:** These columns exist in both the XLS export and the Detail API response. The Detail API values overwrite the XLS values in the output — they are richer and more reliable.

> **Note on `service_area_ids`:** These are calEProcure's own sequential numbers, not FIPS codes. For geographic joins use the `counties` column and map to FIPS by county name externally.

---

## Key files

| File | Purpose |
|---|---|
| `scraper.py` | Main scraper — `probe` and `run` commands |
| `nlx_body.txt` | Static POST body for the InFlight NLX detail endpoint — copy from `../cali/nlx_body.txt` |
| `events.xls` | Manual export from calEProcure — gitignored, must be re-downloaded each run |
| `events_enriched.csv` | Output — gitignored |
| `probe_response.json` | Last probe's raw JSON — useful for debugging missing fields |

---

## Common issues

| Issue | Fix |
|---|---|
| `events.xls not found` | Re-export from the portal (Step 1) and place in this folder |
| `xlrd` error on load | The portal exports HTML-as-XLS — the scraper auto-falls-back to `pd.read_html`. If this fails, install `lxml`: `pip install lxml` |
| 278 redirect on POST | Handled automatically — the scraper re-POSTs to the `IFLocation` URL |
| Empty dept code | Handled automatically — falls back to extracting `BUSINESS_UNIT` from `strCurrScript` in the detail response |
| Empty fields, no HTTP error | Expired `InFlightSessionID` session cookie — just rerun, the session is re-established on startup |
| `DB_USER and DB_NAME must be set` | Copy `.env.example` to `.env` and fill in credentials before running `db_export.py` |
