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

**Known gaps:** S3 upload, DB normalization, automated XLS export

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

**Known gaps:** S3 upload, DB normalization, automated CSV export

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

**Known gaps:** S3 upload, DB normalization, automated CSV export

---

## Shared Pending Work

1. **S3 upload** — upload raw output after each run: `s3://bucket/raw/<state>/YYYY-MM-DD/<file>.csv`
2. **DB normalization** — map state-specific fields to common schema; load alongside SAM.gov data
3. **NAICS/UNSPSC crosswalk** — CA outputs UNSPSC codes, SAM.gov uses NAICS
4. **Automated input export** — both states require a manual download step before each run

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
