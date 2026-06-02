# Alaska IRIS VSS Scraper — Design Spec

**Date:** 2026-06-02
**Portal:** Alaska IRIS Advanced Vendor Self Service — `https://iris-vss.alaska.gov`
**Platform:** CGI Advantage 4

---

## Overview

Scrape open solicitations from Alaska's IRIS VSS procurement portal. The portal exposes a JSON API (`/PRDVSS1X1/Advantage4`) for all data operations. No CSV export exists, so the scraper discovers solicitations directly via the API. Session establishment requires a real browser (DataDome bot protection); all subsequent data fetches use `requests`.

No input file — the scraper discovers all open solicitations itself, like Alabama.

---

## Architecture

Two phases per run:

**Phase 1 — Session establishment (`make_session()`):**
1. Launch Chrome via patchright with persistent profile at `~/.ak_scraper_profile`.
2. Warm up: visit `google.com` and `bing.com` (2s each) to deposit Google-domain cookies that DataDome scores positively.
3. Navigate to the portal; wait for DataDome to clear.
4. Extract cookies (`JSESSIONID_prdvss1-1`, `cookiesession1`, `datadome`) and session tokens (`Adv-Session-Id`, `page_id`, `csrf_token`, `Adv-Window-Id`, `Adv-Conversation-Id`) from the page/response.
5. Load all into a `requests.Session` for reuse.

**Phase 2 — Data collection:**
- `discover_solicitations()`: POST `actionCode: "search"` with `SHOW_TXT: "3"` (Open filter). Paginate using `rows_total` / `rows_per_page`. Returns list of row dicts.
- `fetch_detail()`: POST `actionCode: "docTransition"` keyed on `ADV_ROW_ID`. Returns additional instructions and commodity line data.

All API calls POST JSON to `https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4` with `Adv-*` request headers derived from the session.

---

## API Details

**Endpoint:** `POST https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4`

**Required request headers (all calls):**
```
Content-Type: application/json;charset=UTF-8
Accept: application/json, text/plain, */*
Adv-Session-Id: <from session>
Adv-Page-Id: <from session>
Adv-Window-Id: <from session>
Adv-Conversation-Id: <from session>
Adv-Request-Id: <incrementing integer>
Adv-Action-Code: <per-call>
Adv-Action-Type: <per-call>
```

**List search payload:**
```json
{
  "action": {
    "actionCode": "search",
    "actionType": "searchAction",
    "dataSource": "T1SO_SRCH_QRY",
    "dsNameList": "T1SO_SRCH_QRY",
    "key": "vss.page.VVSSX10019.gridView1.group1.cardSearch.searchActions.search",
    "applicationAction": "search",
    "isCarouselNavigation": true,
    "viewName": "gridView1"
  },
  "data": {
    "page_data": {},
    "ds_query_data": {
      "T1SO_SRCH_QRY": { "SHOW_TXT": "3" }
    }
  },
  "session_info": {
    "session_id": "<session_id>",
    "page_id": "<page_id>",
    "csrf_token": "<csrf_token>"
  },
  "checksum": { ... },
  "viewState": { ... }
}
```

**List response — solicitation rows** at `data.ds_data.T1SO_SRCH_QRY.row_data[]`.
Pagination fields: `rows_total`, `rows_per_page`, `end_data_window`.

**Detail payload:** `actionCode: "docTransition"`, keyed on `ADV_ROW_ID`. Exact payload structure to be captured during `probe` development.

---

## Output Schema

File: `ak/solicitations_enriched.csv` — one row per solicitation.

**From list API:**

| Column | Source field | Notes |
|---|---|---|
| `doc_ref` | `DOC_REF` | Parse `RFQ-09-260000015-2` from `[...][RFQ-09-...]` |
| `doc_type` | `DOC_CD_CONCAT` | e.g. `Request for Quotes (RFQ)` |
| `description` | `DOC_DSCR` | Short title |
| `department` | `DEPT_NM` | |
| `buyer_name` | `BUYR_NM` | |
| `buyer_email` | `BUYR_EMAIL_AD` | |
| `buyer_phone` | `BUYR_PH_NO` | |
| `closing_dt` | `SO_CLSNG_DT_TM` | ms timestamp → ISO string |
| `publish_dt` | `PUB_DT` | ms timestamp → ISO string |
| `amended_dt` | `AMND_DT` | ms timestamp → ISO string |
| `status` | `SO_STA` | Raw status code |
| `category_code` | `SO_CAT_CD` | |

**From detail API (scraped):**

| Column | Source | Notes |
|---|---|---|
| `additional_instructions` | Solicitation Instructions tab | Free-text description |
| `commodity_descriptions` | Commodity Lines tab | Pipe-delimited if multiple lines |
| `commodity_codes` | Commodity Lines tab | Pipe-delimited |
| `commodity_specs` | Commodity Lines tab | Pipe-delimited specifications |
| `alaska_url` | Constructed | Detail page URL |
| `scrape_status` | Scraper | `success` or `error` |

**Resume key:** `doc_ref`. Rows with `scrape_status = success` are skipped on rerun; `error` rows are retried.

---

## Components

```
ak/
├── scraper.py
├── requirements.txt
└── tests/
    ├── test_scraper.py
    └── fixtures/
        ├── sample_list_response.json
        └── sample_detail_response.json
```

**Functions in `scraper.py`:**

- `make_session()` → `(requests.Session, session_info: dict)` — patchright warmup, DataDome bypass, token extraction.
- `discover_solicitations(session, session_info)` → `list[dict]` — paginates list API, applies Open filter, returns parsed rows.
- `fetch_detail(session, session_info, adv_row_id, request_id)` → `dict` — docTransition POST, returns detail fields.
- `parse_doc_ref(raw: str)` → `str` — extracts `RFQ-09-260000015-2` from `[...][RFQ-09-260000015-2]`.
- `ms_to_iso(ms: int | str)` → `str` — converts ms epoch to ISO 8601 string; returns `""` on empty.
- `load_done_ids(output_path)` → `set[str]` — reads existing CSV, returns `doc_ref` values with `scrape_status = success`.
- `probe()` — discover list, pick first new record, print all fields.
- `run()` — discover list, scrape all new/errored records, write CSV.

---

## Error Handling

- Each `fetch_detail()` call is wrapped in try/except. On failure: `scrape_status = "error"`, detail fields blank, row written to CSV immediately.
- CSV is written after every record — safe to interrupt mid-run.
- `DELAY_SECONDS = 0.5` between all API calls.
- `make_session()` exits with a clear message if DataDome check doesn't clear within 60s.

---

## Testing

Unit tests in `ak/tests/test_scraper.py` using JSON fixtures:

- `parse_doc_ref()` — round-trips the `[...][human-readable]` format.
- `ms_to_iso()` — known timestamp → expected ISO string; empty string input.
- List row parsing — fixture `sample_list_response.json` → expected dict of list fields.
- Detail field extraction — fixture `sample_detail_response.json` → expected dict of detail fields.
- `load_done_ids()` — CSV with mixed success/error rows → correct set returned.

No browser or network calls in tests.

---

## Commands

```bash
cd ak
source ../venv/bin/activate
python scraper.py probe   # session → first open record → print all fields
python scraper.py run     # session → all new/errored → write solicitations_enriched.csv
```

---

## Known Unknowns

- **Detail page POST payload**: exact `docTransition` JSON body structure is not yet captured. Will be discovered by inspecting the Network tab when clicking a solicitation row during probe development.
- **Checksum/viewState fields**: the list POST payload includes `checksum` and `viewState` blobs that may need to be replayed exactly. Values will be captured from the initial page load response.
- **Session token location**: `Adv-Session-Id`, `page_id`, `csrf_token` are embedded somewhere in the initial page HTML or a bootstrap API call — exact extraction method TBD during probe development.

---

## Install

```bash
pip install patchright && patchright install chromium
```

(patchright is already installed for the Alabama scraper.)
