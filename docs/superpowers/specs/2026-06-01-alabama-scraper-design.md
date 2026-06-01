# Alabama (alabamabuys.gov) Scraper Design

**Date:** 2026-06-01
**State:** Alabama
**Portal:** Alabama BUYS (Ivalua platform)
**Target:** Public Solicitations — "Open for Bidding" only

---

## Problem

Unlike CA, PA, and MA, Alabama BUYS has no CSV/XLS export for solicitations. The scraper must discover records itself by paginating the portal's search results list. Additionally, the server-side status filter in the search form is broken, so open/closed filtering must be done client-side by reading the Status column from each list row.

---

## Portal Details

| Property | Value |
|---|---|
| Platform | Ivalua |
| List page | `https://www.alabamabuys.gov/page.aspx/en/rfp/request_browse_public` |
| Pagination endpoint | `https://www.alabamabuys.gov/ajax.aspx/en/rfp/request_browse_public?ivControlUIDsAsync=body:x:grid:upgrid&asyncmodulename=rfp&asyncpagename=request_browse_public` |
| Detail page pattern | `https://www.alabamabuys.gov/page.aspx/en/rfp/request_manage_public/{numeric_id}` |
| Detail URL source | Extracted from list HTML (href in row) — NOT derivable from SRC code |

---

## Architecture

### Commands

```bash
python scraper.py probe   # discover list, pick first open record, print all fields
python scraper.py run     # discover list, enrich all new open records, write CSV
```

### Flow

```
probe / run
├── discover_solicitations()
│   ├── GET browse page → session cookie + parse page 1 rows + total page count
│   └── POST ajax.aspx Page|2..N → parse rows
│       filter client-side: only rows where status == "Open for Bidding"
│       all pages must be visited — open bids appear on any page, not clustered
├── load_done_ids(output CSV)   ← src_codes with scrape_status == "success"
└── for each new open record:
    ├── GET detail_href
    ├── parse Solicitation General Information with BS4
    └── append to output CSV   ← written after every record (resume-safe)
```

---

## Pagination Mechanics

### Page 1 (GET)

`GET https://www.alabamabuys.gov/page.aspx/en/rfp/request_browse_public`

- Establishes session cookie
- Response is server-rendered HTML containing the first page of the grid
- Parse: rows from the grid table + total page count from the pager widget

### Pages 2..N (POST)

`POST https://www.alabamabuys.gov/ajax.aspx/en/rfp/request_browse_public?ivControlUIDsAsync=body:x:grid:upgrid&asyncmodulename=rfp&asyncpagename=request_browse_public`

Form data:

| Field | Value | Notes |
|---|---|---|
| `__EVENTTARGET` | `body_x_grid_grd` | fixed |
| `__EVENTARGUMENT` | `Page|{n}` | changes per page |
| `__LASTFOCUS` | `body_x_grid_gridPagerBtn{n}Page` | changes per page |
| `REQUEST_METHOD` | `POST` | fixed |
| `hdnUserValue` | (empty) | fixed |
| `x_headaction` | (empty) | fixed |
| `x_headloginName` | (empty) | fixed |
| `hdnMandatory` | `0` | fixed |
| `hdnWflAction` | (empty) | fixed |
| `body:_ctl0` | (empty) | fixed |
| `body:x:txtQuery` | (empty) | no keyword filter |
| `body:x:selFamily` | (empty) | no commodity filter |
| (all other filter fields) | (empty) | no filters applied |

The POST response is an HTML fragment containing the updated grid for page N. Parse it the same way as page 1.

`DELAY_SECONDS = 0.5` between each POST.

---

## Status Filtering

The server-side status filter in the POST body does not work reliably. Filter client-side:

- Parse the `Status` column from every row on every page
- Only queue detail-page fetches for rows where `status == "Open for Bidding"`
- All pages must be visited — do not stop early

---

## Detail Page Parsing

Parse the **Solicitation General Information** card using BS4 label-text matching (same helper pattern as PA/MA). Extract only fields not already captured from the list:

| Label text | Output column |
|---|---|
| `Round #` | `round_number` |
| `Begin` | `begin_date` |
| `Summary` | `summary` |

Skip these fields (already in list): Code, Solicitation Name, Solicitation Type, End, Status, Award Status.

---

## Output Schema

Total: 15 columns.

### From list page

| Column | Source column | Notes |
|---|---|---|
| `src_code` | Sourcing Project Number | Primary key, e.g. `SRC0000034127` |
| `solicitation_label` | Solicitation Label | |
| `status` | Status | Always `"Open for Bidding"` (filtered) |
| `award_status` | Award Status | |
| `due_close_date` | Due/Close Date | |
| `main_commodity` | Main Commodity | |
| `solicitation_type` | Solicitation Type | |
| `buying_agency` | Buying Agency | |
| `sourcing_responsible_first` | Sourcing Responsible First Name | |
| `sourcing_responsible_last` | Sourcing Responsible Last Name | |

`remaining_time` intentionally excluded — stale relative value the moment it's written.

### From detail page

| Column | Source | Notes |
|---|---|---|
| `round_number` | Round # | |
| `begin_date` | Begin | |
| `summary` | Summary | Primary value for vendor matching; multi-line free text |

### Standard trailing columns

| Column | Notes |
|---|---|
| `alabama_url` | Full detail page URL |
| `scrape_status` | `success` or `error` |

---

## Resume Safety

- ID key: `src_code`
- `load_done_ids()` reads output CSV and returns the set of `src_code` values where `scrape_status == "success"`
- On each run: discover full open list → subtract done_ids → scrape remainder
- `error` rows are retried automatically (not in done_ids)
- Output is appended and re-written after every record — safe to interrupt

---

## File Structure

```
al/
├── scraper.py
├── requirements.txt                          # requests, pandas, beautifulsoup4
├── tests/
│   ├── test_scraper.py
│   └── fixtures/
│       ├── sample_list_page.html             # one page of list results
│       └── sample_solicitation_detail.html  # one solicitation detail page
└── solicitations_enriched.csv               # output (gitignored)
```

---

## Dependencies

No new dependencies. Uses `requests`, `pandas`, `beautifulsoup4` — all already in the shared venv.

---

## Known Gaps

- **S3 upload** — shared pending work across all states
- **DB normalization** — shared pending work
- **Solicitation Documents** — PDF attachment links not captured; could be added later
- **Session sensitivity** — if Ivalua starts requiring CSRF tokens or ViewState for public pages, the session cookie strategy will need revisiting
- **No automated list refresh** — the scraper always re-paginates the full list on each run; if the portal adds rate limiting this could become slow
