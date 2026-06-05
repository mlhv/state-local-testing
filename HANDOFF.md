# State Procurement Scraper — Master Handoff

**Last updated:** 2026-06-04

## Project Goal

Aggregate state government procurement opportunities into a common dataset feeding a vendor-matching system (alongside SAM.gov federal data).

---

## State Status

| State | Status | Folder | Portal | Input | Output |
|---|---|---|---|---|---|
| California | ✅ Complete | `cali/` | calEProcure | Manual XLS export | `events_enriched.csv` (24 cols) |
| Pennsylvania | ✅ Complete | `pa/` | PA eMarketplace | Manual CSV export | `solicitations_enriched.csv` (28 cols) |
| Massachusetts | ✅ Complete | `ma/` | COMMBUYS | Manual CSV export | `solicitations_enriched.csv` (31 cols) |
| Alabama | ✅ Complete | `al/` | Alabama BUYS (Ivalua) | No export — list scraped directly | `solicitations_enriched.csv` (15 cols) |
| Alaska | ✅ Complete | `ak/` | IRIS VSS (CGI Advantage 4) | No export — list scraped directly | `solicitations_enriched.csv` (18 cols) |
| Arizona | ✅ Complete | `az/` | Arizona Procurement Portal (Ivalua) | No export — list scraped directly | `solicitations_enriched.csv` (21 cols) |

---

## California (calEProcure)

**Portal:** https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx

**How it works:** The portal uses InFlight NLX middleware on top of PeopleSoft. Event detail pages are empty HTML shells — all data comes from an internal JSON API that the page calls via XHR. The scraper calls this endpoint directly with `requests`, bypassing HTML rendering entirely.

**Run:**
```bash
cd cali
source ../venv/bin/activate
# Download XLS from calEProcure (Status = Posted), re-save as real XLS from Excel
python scraper.py probe
python scraper.py run
```

**Key files:** `cali/HANDOFF.md` (full API docs), `cali/POSTDEV.md`, `cali/nlx_body.txt` (static POST body — only needs recapturing if the site redesigns)

**Known gaps:** DB normalization, automated XLS export

---

## Pennsylvania (PA eMarketplace)

**Portal:** https://www.emarketplace.state.pa.us/Search.aspx

**How it works:** Standard ASP.NET server-rendered XHTML. Solicitation detail pages are fully rendered in the HTML response — no JS execution needed. The scraper GETs each detail page and parses it with BeautifulSoup using label-text matching.

**Run:**
```bash
cd pa
source ../venv/bin/activate
# Export CSV from PA eMarketplace (no filters, View Current Records)
python scraper.py probe
python scraper.py run
```

**Key files:** `pa/README.md` (run instructions), `pa/POSTDEV.md`, `pa/tests/` (11 tests)

**Known gaps:** DB normalization, automated CSV export

---

## Massachusetts (COMMBUYS)

**Portal:** https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true

**How it works:** Server-rendered HTML (Periscope S2G / JSF). Bid detail pages are fully rendered in the HTML response — no JS execution needed. The scraper GETs each detail page and parses it with BeautifulSoup. Header fields use label-text matching. Ship-to contact info, SBPP eligibility, and multi-item UNSPSC data use dedicated helpers. Items are pipe-delimited when a solicitation has multiple line items.

**Run:**
```bash
cd ma
source ../venv/bin/activate
# Export CSV from COMMBUYS (Bid Solicitations, open bids, Export to CSV)
python scraper.py probe
python scraper.py run
```

**Key files:** `ma/tests/` (11 tests)

**Known gaps:** DB normalization, automated CSV export

---

## Shared Pending Work

1. **DB normalization** — map state-specific fields to common schema; load alongside SAM.gov data
2. **NAICS/UNSPSC crosswalk** — CA outputs UNSPSC codes, SAM.gov uses NAICS
3. **Automated input export** — both states require a manual download step before each run

---

## Alabama (Alabama BUYS)

**Portal:** https://www.alabamabuys.gov/page.aspx/en/rfp/request_browse_public

**How it works:** Ivalua-based portal with no CSV export and Google reCAPTCHA Enterprise on the browse page. `make_session()` launches real Chrome (non-headless) via Playwright to pass the browser check, extracts the session cookie, then hands off to `requests` for all subsequent calls. The list grid is populated via AJAX POST (not the initial GET response) — `discover_solicitations()` POSTs to `ajax.aspx` for every page including page 1. Status filtering is done client-side (server-side filter is broken). Detail pages use Ivalua's `data-iv-role="field"/"control"` structure parsed with BeautifulSoup.

**Run:**
```bash
cd al
source ../venv/bin/activate
# Install playwright browsers first time: playwright install chromium
# Chrome must be closed when running (profile lock)
python scraper.py probe
python scraper.py run
```

**Key technical notes:**
- reCAPTCHA requires non-headless Chrome; headless mode fails the score check
- `make_session()` uses `patchright` (patched Playwright) + `launch_persistent_context` pointing at `~/.al_scraper_profile`. Before hitting alabamabuys.gov it warms up the profile by visiting google.com and bing.com — this deposits Google-domain cookies that reCAPTCHA Enterprise scores positively. The profile accumulates more state on each run, making it more reliable over time.
- One session per run — session is created once and reused for list + all detail fetches
- No manual export step — the scraper discovers all open solicitations itself
- Detail URL is extracted from list HTML (not derivable from SRC code — numeric IDs don't map to SRC numbers)

**Known gaps:** DB normalization

**Install note:** `pip install patchright && patchright install chromium` required on first setup.

---

## Alaska (IRIS VSS)

**Portal:** https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4

**How it works:** CGI Advantage 4 — a full SPA with DataDome bot protection. All data comes from a single JSON endpoint (`Advantage4`) via `POST` with rotating session tokens in every request and response. `make_session()` launches real Chrome via patchright to pass DataDome, intercepts the VVSSX10019 search page response to capture `session_id`/`page_id`/`csrf_token`, then hands off to `requests`. Each detail fetch is a 3-call chain: `docTransition` → `tabChange(navSolicitation)` → `tabChange(navComm)`. Session tokens rotate with every response — `_update_ctx()` must be called after every POST.

**Run:**
```bash
cd ak
source ../venv/bin/activate
# patchright install chromium  (first time only)
# Chrome must be closed when running (profile lock)
python scraper.py probe
python scraper.py run
```

**Key technical notes:**
- DataDome requires non-headless Chrome with patchright's automation fingerprint patches
- `make_session()` uses `launch_persistent_context` at `~/.ak_scraper_profile`, warms up with google.com and bing.com before hitting the portal
- Token rotation: every API response includes new `session_id`, `page_id`, `csrf_token` — always update ctx
- `fetch_detail()` uses a local copy of ctx so the caller's search context is never mutated
- Commodity lines (`T3SO_DOC_COMMLN`) may be empty in the navComm response if a solicitation has no line items or lazy-loads them — this is normal
- No manual export step — open solicitations are fetched directly via `SHOW_TXT:"3"` search filter

**Output columns (18):** `doc_ref`, `doc_type`, `description`, `department`, `buyer_name`, `buyer_email`, `buyer_phone`, `closing_dt`, `publish_dt`, `amended_dt`, `status`, `category_code`, `additional_instructions`, `commodity_descriptions`, `commodity_codes`, `commodity_specs`, `alaska_url`, `scrape_status`

**Known gaps:** DB normalization; commodity data may be sparse if solicitations don't populate line items

**Install note:** `pip install patchright && patchright install chromium` required on first setup.

---

## Arizona (Arizona Procurement Portal)

**Portal:** https://app.az.gov/page.aspx/en/rfp/request_browse_public

**How it works:** Ivalua SaaS portal (same platform as Alabama). `make_session()` launches Chrome via patchright to pass reCAPTCHA v2 and the path-scoped `/bpm/` browser check, then hands off to `requests` for all list pagination. The list grid is populated by POSTing directly to `ajax.aspx` — the server returns only the grid HTML fragment (not a full page). BeautifulSoup parses rows and the pager from that fragment. The browser stays open and is used for detail page fetches via `page.evaluate(fetch(...))`.

**Run:**
```bash
cd az
source ../venv/bin/activate
# patchright install chromium  (first time only)
# Chrome must be closed when running (profile lock)
python scraper.py probe
python scraper.py run
```

**Key technical notes:**
- **Ivalua is stateless** — the filter must be included in the body of every AJAX pagination POST. `hdnUserValue=,body_x_selStatusCode_1` alone is not enough; the actual value field `body:x:selStatusCode_1=val` must also be present. Without it, the server ignores the filter and returns all ~151 records across ~10 pages.
- **`REQUEST_METHOD=GET`** must be in the payload even though the HTTP method is POST — this is an Ivalua internal field and must match what the browser sends or the filter is ignored.
- **Pager is a sliding window** — `reported_pages` grows as you advance through pages (e.g., shows 7 on page 1, 8 on page 4). Do not freeze `total_pages` from page 1. Correct termination: `page_n >= reported_pages` (you're on the last button the current window shows), plus dedup and empty-page guards.
- **Two separate path-scoped browser checks** — `/rfp/` (list page) and `/bpm/` (detail pages) each have their own reCAPTCHA check. `make_session()` must pre-warm both by navigating to a detail page before returning.
- Persistent profile at `~/.az_scraper_profile`; google.com + bing.com warmup before portal.
- With filter working: 41 open records across exactly 3 pages of 15.

**Output columns (21):** `src_code`, `solicitation_label`, `commodity`, `buying_agency`, `status`, `rfx_awarded`, `begin_date`, `end_date`, `detail_href`, `lot_number`, `round_number`, `fiscal_year`, `rfx_type`, `procurement_officer`, `procurement_officer_email`, `procurement_officer_phone`, `discussion_forum_cutoff`, `commodity_full`, `summary`, `arizona_url`, `scrape_status`

**Known gaps:** DB normalization

**Install note:** `pip install patchright && patchright install chromium` required on first setup.

---

## Lessons Learned (apply to future states)

### Ivalua portals (Alabama, Arizona — likely Montana, Wyoming, Idaho, others)

**The server is stateless.** Filter fields must be included in the body of every AJAX pagination POST. It is not enough to do a search POST first and hope the session carries the filter forward — it doesn't. Every request is evaluated from scratch.

**`hdnUserValue` is not the filter — it's a hint.** `hdnUserValue=,body_x_selStatusCode_1` tells the server "this field has a non-default value" but you must also send the field itself: `body:x:selStatusCode_1=val`. Without the actual value field the server treats the filter as empty and returns all records.

**Match `REQUEST_METHOD` to what the browser sends.** For Ivalua portals this is typically `GET` even though the HTTP method is `POST`. Using `POST` here causes the filter to be silently ignored.

**To find the correct filter payload:** Open DevTools → Network → Fetch/XHR, apply the status filter in the browser UI, click Search, then click page 2. Inspect that page-2 request body — it contains all the fields the server needs for filtered pagination. The filter fields will be present in both the Search request and every page navigation after it.

**Pager sliding window.** Ivalua's pager only renders buttons for a window of pages around the current one. `reported_pages` (the max button number visible) grows as you navigate deeper. Correct termination: `if page_n >= reported_pages: break`. Do not freeze `total_pages` from page 1 alone — you'll stop too early.

**Path-scoped browser checks.** Ivalua portals often have separate reCAPTCHA/browser checks for different URL paths (e.g., `/rfp/` for the list, `/bpm/` for detail pages). `make_session()` must navigate to a page under each protected path before returning so both session cookies are populated.

**AJAX endpoint returns HTML, not JSON.** `ajax.aspx?ivControlUIDsAsync=body:x:grid:upgrid` returns a raw HTML fragment of the grid div. Parse it with BeautifulSoup directly — no JSON parsing needed.

**Keep the browser alive for detail pages.** After `make_session()` hands off to `requests` for list pagination, keep the patchright browser open. Use `page.evaluate(fetch(..., {credentials: 'include'}))` for detail page fetches — this re-uses the browser's cookie jar (including path-scoped cookies) without triggering a new browser check.

---

### General AJAX portal scraping

**Capture the pagination request, not just the search request.** The search request and the page-2 request often differ in subtle ways (different `__EVENTTARGET`, missing filter fields in one but not the other). Always capture the exact POST body for a page navigation while a filter is active.

**If you're getting too many records, the filter isn't working.** Check page count: if the portal shows N pages with filter applied in the browser but your scraper fetches 3× that many pages, the filter fields are missing or wrong in your payload.

**`open_on_page` per-page logging is a fast diagnostic.** Adding `sum(r["status"] == "Open for Bidding" for r in rows)` to the page fetch print immediately shows whether the server filter is working (all rows open) or not (mixed statuses).

---

## Next States to Investigate

Suggested priority based on procurement volume:

| State | Portal | Notes |
|---|---|---|
| Texas | TxSmartBuy / ESBD | High volume |
| New York | NY State Contract Reporter | |
| Florida | MyFloridaMarketPlace | |
| Illinois | BidBuy | |

For each new state: investigate whether detail pages are server-rendered (BeautifulSoup) or JS-injected (look for underlying XHR like CA). See `CLAUDE.md` for the new state checklist.
