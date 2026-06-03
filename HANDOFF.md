# State Procurement Scraper — Master Handoff

**Last updated:** 2026-05-27

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

## Next States to Investigate

Suggested priority based on procurement volume:

| State | Portal | Notes |
|---|---|---|
| Texas | TxSmartBuy / ESBD | High volume |
| New York | NY State Contract Reporter | |
| Florida | MyFloridaMarketPlace | |
| Illinois | BidBuy | |

For each new state: investigate whether detail pages are server-rendered (BeautifulSoup) or JS-injected (look for underlying XHR like CA). See `CLAUDE.md` for the new state checklist.
