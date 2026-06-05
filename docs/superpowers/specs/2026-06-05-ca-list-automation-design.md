# CA List Automation Design

**Date:** 2026-06-05
**State:** California (calEProcure)
**Goal:** Eliminate the manual XLS download step by replacing `load_xls()` with a direct NLX list API call, making CA fully automated alongside AL, AK, and AZ.

---

## Background

The CA scraper currently requires a manually downloaded `events.xls` before each run. The XLS is an HTML table disguised with a `.xls` extension that must be re-saved from Excel before `xlrd` can parse it. The scraper already calls the NLX JSON API for detail pages — the list page uses the same NLX infrastructure and can be called the same way.

---

## Architecture

**Current flow:**
```
load_xls() → DataFrame → [for each row] fetch_results() → events_enriched.csv
```

**New flow:**
```
discover_events(session) → DataFrame → [for each row] fetch_results() → events_enriched.csv
```

Everything downstream of the list-loading step is unchanged: resume-safety logic, rate limiting, `probe`/`run` command structure, and output format all stay the same.

**Template files:**
- `nlx_body.txt` — detail API template (unchanged)
- `nlx_list_body.txt` — list API template (already saved; needs one addition for dept code)

---

## List API

**Endpoint:** `POST https://caleprocure.ca.gov/nlx3/psc/psfpd1/SUPPLIER/ERP/c/AUC_MANAGE_BIDS.AUC_RESP_INQ_AUC.GBL`

**Session:** same `make_session()` call (plain GET to establish `InFlightSessionID` cookie). No separate session setup needed.

**Request body:** `nlx_list_body.txt` (the `IF-TargetContent` template the user captured from DevTools).

**Response structure:** `CaptureResults["tbl"][0]["Children"]["tblBodyTr"]` — a flat array of row objects. Confirmed 346 rows in a single response with all pager buttons hidden, meaning no pagination is needed.

**Per-row fields extracted:**

| Output column | Response key | Notes |
|---|---|---|
| `Event ID` | `tdEventId.Properties.text` | 10-digit zero-padded string |
| `Event Name` | `tdEventName.Properties.text` | |
| `Department Name` | `tdDepName.Properties.text` | |
| `End Date` | `tdEndDate.Properties.text` | e.g. `05/06/2026 14:00 PDT` |
| `Status` | `tdStatus.Properties.text` | Always "Posted" for this query |
| `Department` (code) | `tdDeptCode.Properties.href` → regex | See dept code section below |

---

## Dept Code Discovery

The `tdEventId` cell in the search results HTML template has two source selectors:
```
a[id^='AUC_ID_COL$'], a[id^='AUC_ID_BUS_UNIT$']
```

The `AUC_ID_BUS_UNIT$N` anchor is a PeopleSoft compound-key element whose `href` is expected to be the detail page URL (e.g. `https://caleprocure.ca.gov/event/0250/0000038854`), from which the dept code can be regex-extracted.

**Implementation:** Add a `tdDeptCode` child element to `nlx_list_body.txt` targeting `a[id^='AUC_ID_BUS_UNIT$']` with `href` content. Extract the dept code with:
```python
re.search(r'/event/([^/]+)/', href)
```

**Fallback:** If `href` is empty or a bare `#` anchor (i.e. JS-only navigation), extract `BUSINESS_UNIT=([^&]+)` from `strCurrScript` in the detail response on first call. The detail response already captures `strCurrScript` in `nlx_body.txt` and it is confirmed to contain `BUSINESS_UNIT=0250` in the current probe response.

---

## Detail API Changes

No new API calls or template changes. Four new fields are extracted from keys already present in the detail response:

| New output column | Detail response key | Confirmed value (probe) |
|---|---|---|
| `Buyer Name` | `contactName.Properties.text` | `"Roderick Bustos"` |
| `Buyer Email` | `emailAnchor.Properties.text` | `"roderick.bustos@jud.ca.gov"` |
| `Format` | `format1.Properties.text` | `"Sell Event"` |
| `Type` | `format2.Properties.text` | `"RFx"` |

`EMPTY_EXTRA` gains these four keys so error rows get empty strings consistently.

---

## Output Schema

No columns removed. Four columns move from XLS-sourced to API-sourced but keep the same names. `Department` (code) now comes from the list API instead of the XLS.

Column order is preserved: list-API fields first (matching current XLS column order), then detail-API enrichment fields appended at the end.

**Before (XLS-sourced):** `Department`, `Department Name`, `Event ID`, `Event Name`, `Format`, `Type`, `End Date`, `Status`, `Buyer Name`, `Buyer Email`

**After (list-API-sourced):** `Event ID`, `Event Name`, `Department Name`, `End Date`, `Status`, `Department` — plus `Buyer Name`, `Buyer Email`, `Format`, `Type` from detail API

Note: column order within the first group changes slightly (XLS had `Department` first; list API naturally returns `Event ID` first). This is acceptable since the output is a CSV consumed programmatically, not displayed directly.

---

## Removed

- `load_xls()` function — deleted
- `XLS_PATH = "events.xls"` constant — deleted
- `xlrd` from `cali/requirements.txt` — removed
- `events.xls` input file dependency — eliminated; no manual step before `python scraper.py run`

---

## Error Handling

- If the list API returns an empty `tblBodyTr`, exit with a clear error: `"ERROR: List API returned 0 events — check session or portal status"`
- If dept code extraction from `href` fails for a row, log a warning and fall back to `strCurrScript` extraction from the detail response
- All existing error handling in `fetch_results()` and the main run loop is unchanged

---

## Testing

- `python scraper.py probe` — must run without `events.xls` present and successfully fetch one event
- Spot-check: confirm `Buyer Name`, `Buyer Email`, `Format`, `Type` are populated in probe output
- Confirm `Department` code is present and matches the event URL (e.g. `0250` in `caleprocure.ca.gov/event/0250/...`)
- Run against a small batch (first 5 rows) and diff output schema against current `events_enriched.csv` to confirm no columns lost
