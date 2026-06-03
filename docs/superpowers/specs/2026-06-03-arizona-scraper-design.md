# Arizona Procurement Scraper — Design Spec

**Date:** 2026-06-03  
**Portal:** Arizona Procurement Portal (Ivalua)  
**URL:** https://app.az.gov/page.aspx/en/rfp/request_browse_public  
**Folder:** `az/`

---

## Overview

Arizona uses the same Ivalua SaaS portal as Alabama (`page.aspx/en/rfp/request_browse_public`). The scraper is a direct port of `al/scraper.py` with three Arizona-specific adaptations:

1. Manual reCAPTCHA v2 — user clicks the checkbox in the browser, then presses Enter to hand off cookies to `requests`
2. Server-side status filter — `hdnUserValue: ,body_x_selStatusCode_1` in the AJAX payload returns only "Open for Bidding" records; no client-side filtering needed
3. Different list columns and detail fields

---

## Architecture

Single file: `az/scraper.py`. One session created once in `make_session()` and reused for all list and detail fetches. No manual CSV export — the scraper discovers all open solicitations itself.

Commands (run from inside `az/`):
```bash
python scraper.py probe   # open browser, solve CAPTCHA, print one record's fields
python scraper.py run     # open browser, solve CAPTCHA, enrich all new records, write CSV
```

---

## Session — `make_session()`

Arizona uses reCAPTCHA v2 (visible checkbox) which requires manual interaction. Strategy:

1. Launch real Chrome (non-headless) via `patchright` with persistent profile at `~/.az_scraper_profile`
2. Warm up profile: visit `https://www.google.com` and `https://www.bing.com` (2 s each) to deposit Google-domain cookies
3. Navigate to `https://app.az.gov/page.aspx/en/rfp/request_browse_public`
4. Print: `"Please solve the CAPTCHA in the browser window, then press Enter to continue..."`
5. Call `input()` — block until user presses Enter
6. Extract all cookies from the patchright context, load into a `requests.Session`
7. Close browser context

No URL-change detection needed — explicit user signal replaces it.

---

## List Discovery — `discover_solicitations()`

AJAX POST endpoint (identical structure to Alabama):
```
https://app.az.gov/ajax.aspx/en/rfp/request_browse_public
  ?ivControlUIDsAsync=body:x:grid:upgrid
  &asyncmodulename=rfp
  &asyncpagename=request_browse_public
```

Base payload keys match Alabama's `_BASE_PAYLOAD` with one addition:
- `hdnUserValue: ,body_x_selStatusCode_1` — applies "Open for Bidding" filter server-side

Pagination: `__EVENTARGUMENT: Page|N`, `__EVENTTARGET: body_x_grid_grd`, same as Alabama. Page 1 is also fetched via POST (not the initial GET).

---

## List Parsing — `parse_list_page()`

Cell index → field key mapping for Arizona's 9-column grid:

| Cell | Field |
|------|-------|
| 0 | `detail_href` (anchor href from editing-column icon) |
| 1 | `src_code` |
| 2 | `solicitation_label` |
| 3 | `commodity` |
| 4 | `buying_agency` |
| 5 | `status` |
| 6 | `rfx_awarded` |
| 7 | `begin_date` |
| 8 | `end_date` |

Pager detection and row parsing logic copied from Alabama (`_parse_total_pages`, `tbody.find_all("tr")`).

---

## Detail Extraction — `extract_fields()`

Detail page URL: `https://app.az.gov` + `detail_href` (e.g. `/bpm/process_manage_extranet/13695`). Fetched via `session.get()`.

Same Ivalua `data-iv-role="field"/"control"` HTML structure as Alabama — `_label_value()` is copied unchanged.

| Label text | Field key |
|------------|-----------|
| `"Lot #"` | `lot_number` |
| `"Round #"` | `round_number` |
| `"Fiscal Year"` | `fiscal_year` |
| `"RFx types"` | `rfx_type` |
| `"Procurement Officer"` | `procurement_officer` |
| `"Procurement Officer Email"` | `procurement_officer_email` |
| `"Procurement Officer Phone"` | `procurement_officer_phone` |
| `"Discussion Forum Cut Off"` | `discussion_forum_cutoff` |
| `"Commodity"` | `commodity_full` |
| `"Summary"` | `summary` |

`"Process"` field is intentionally skipped (not useful for vendor matching).

`SCRAPED_FIELDS` list ends with `arizona_url` and `scrape_status` per project convention.

---

## Output Schema

File: `az/solicitations_enriched.csv` (~19 columns)

**List columns (9):** `src_code`, `solicitation_label`, `commodity`, `buying_agency`, `status`, `rfx_awarded`, `begin_date`, `end_date`, `detail_href`

**Scraped columns (10):** `lot_number`, `round_number`, `fiscal_year`, `rfx_type`, `procurement_officer`, `procurement_officer_email`, `procurement_officer_phone`, `discussion_forum_cutoff`, `commodity_full`, `summary`, `arizona_url`, `scrape_status`

---

## Resume Safety

- `load_done_ids()` reads `src_code` from rows where `scrape_status == "success"`
- `success` rows are skipped on rerun
- `error` rows are retried automatically
- Output CSV written after every record — safe to interrupt mid-run

Rate limiting: `DELAY_SECONDS = 0.5` between detail fetches.

---

## Tests

`az/tests/test_scraper.py` with HTML fixtures in `az/tests/fixtures/`.

| Test | Description |
|------|-------------|
| `test_parse_list_page_basic` | Parses columns and `detail_href` from a fixture table |
| `test_parse_list_page_empty` | Returns `[]` and page count 1 for empty/missing table |
| `test_parse_list_page_pager` | Returns correct `total_pages` from pager widget |
| `test_label_value_ivalua` | Finds value via `data-iv-role="field"/"control"` structure |
| `test_label_value_missing` | Returns `""` for unknown label |
| `test_extract_fields_full` | Full detail fixture returns all 10 scraped fields correctly |

No session/network tests — those require the live portal.

---

## Dependencies

Same as Alabama — no new packages required:
- `patchright` (already in venv)
- `requests`, `pandas`, `beautifulsoup4` (shared `requirements.txt`)

First-time setup: `patchright install chromium`

---

## Deferred / Out of Scope

- DB normalization (shared pending work for all states)
- Automated session refresh if cookie expires mid-run
