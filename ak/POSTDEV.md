# Alaska IRIS VSS Scraper — Post-Development Notes

## Portal

**URL:** https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4  
**Platform:** CGI Advantage 4 (state ERP/procurement SPA)  
**Bot protection:** DataDome

---

## Architecture

Every user interaction — search, row selection, tab switch, navigation — is a `POST` to the single `/Advantage4` endpoint. The request body contains an `action` object (what the user did), `checksum`/`viewState` (current UI state), `session_info` (rotating auth tokens), and `data` (any datasource payload). The response returns the new page state as JSON, including fresh session tokens.

There is no HTML to parse. Everything is JSON in, JSON out.

---

## Session bootstrap

DataDome blocks plain `requests`. The approach:

1. Launch real Chrome via `patchright` (patched Playwright that strips automation fingerprints), using a persistent profile at `~/.ak_scraper_profile`.
2. Warm up by visiting `google.com` and `bing.com` — deposits Google-domain cookies that DataDome scores positively.
3. Navigate to the portal home, then click "Solicitations" to trigger the VVSSX10019 search page load.
4. Intercept the VVSSX10019 API response to capture `session_id`, `page_id`, `csrf_token`.
5. Extract browser cookies and load into a `requests.Session`. All subsequent calls use `requests` — no more browser.

The persistent profile accumulates state across runs, making DataDome checks faster and more reliable over time.

---

## Token rotation

Every response includes new tokens in `session_info`. `_update_ctx(ctx, body)` must be called after every POST. The `Adv-Request-Id` header is a per-session integer counter that must increment with each call.

Failing to rotate tokens causes 401/403 on the next request.

---

## The key discovery: docTransition returns everything

The biggest lesson from building this scraper: **the `docTransition` response is the richest response in the workflow.**

When the user clicks a solicitation row in the search results, the browser fires a `docTransition` POST. The response loads the full solicitation document and includes *all* datasources at once:
- `T1SO_DOC_HDR` — header fields including `ADDL_INFO` (the free-text instructions field)
- `T3SO_DOC_COMMLN` — commodity line items (`EXT_DSCR`, `COMM_CD`, `COMM_SPECS`)
- Many other datasources for attachments, vendor lists, etc.

The scraper initially made 3 calls per solicitation (docTransition → navSolicitation tab → navComm tab), then 2, then was reduced to 1 after verifying that docTransition carries everything.

**The trap:** Tab-change responses (`navSolicitation`, `navComm`) look like they should return the data for that tab, but they mostly return page schema metadata (field definitions, view layout) — not row data. The row data is already in `docTransition`. Searching for a visible field value (e.g., a commodity description string) in each response body is the fastest way to verify which call actually returns it.

---

## Data sources

| Datasource | Contents | Where returned |
|---|---|---|
| `T1SO_SRCH_QRY` | Search results list (12 fields per row) | `_raw_search()` response |
| `T1SO_DOC_HDR` | Solicitation header + `ADDL_INFO` | `docTransition` response |
| `T3SO_DOC_COMMLN` | Commodity lines: `EXT_DSCR`, `COMM_CD`, `COMM_SPECS` | `docTransition` response |

---

## Output

18 columns: `doc_ref`, `doc_type`, `description`, `department`, `buyer_name`, `buyer_email`, `buyer_phone`, `closing_dt`, `publish_dt`, `amended_dt`, `status`, `category_code`, `additional_instructions`, `commodity_descriptions`, `commodity_codes`, `commodity_specs`, `alaska_url`, `scrape_status`

Commodity fields are pipe-delimited when a solicitation has multiple line items. They will be empty if a solicitation has no commodity lines populated — this is normal.

---

## Running

```bash
cd ak
source ../venv/bin/activate
# First time only:
pip install patchright && patchright install chromium

python scraper.py probe   # fetch one record, print all fields
python scraper.py run     # scrape all new/errored records
```

Chrome must not be running with the same profile when the scraper runs (`~/.ak_scraper_profile`). The scraper opens a new Chrome window — this is required, `headless=False`.

---

## Applying this pattern to other CGI Advantage 4 states

Several other states use CGI Advantage 4 (Montana, Wyoming, Idaho, and others — look for `/Advantage4` in the portal URL). The same scraper structure applies:

1. Identify the portal's search page key (e.g., `VVSSX10019` for Alaska) — look in `page_metadata.key` in any API response.
2. Capture the search checksum (`VIEW.gridView1`) from a real browser session — it's stable and can be hardcoded.
3. Confirm the open-solicitations filter value by inspecting the search request payload in DevTools.
4. Verify in DevTools that `docTransition` returns all the data fields you need before adding any tab-change calls.

See `CLAUDE.md` → "Known Techniques" → "CGI Advantage 4 portals" for the full guidance.
