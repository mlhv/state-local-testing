# COMMBUYS Solicitation Scraper — Handoff Document
**Last updated:** 2026-06-10  
**State:** Massachusetts (COMMBUYS)  
**Goal:** Aggregate state-level government procurement opportunities, feeding into a hybrid vendor-matching system (currently sourced from SAM.gov and similar federal/state portals).

---

## What was built

A Python scraper (`scraper.py`) that:
1. Reads a manually exported `bidSearchResults.csv` from the COMMBUYS portal
2. Constructs a detail URL per bid: `https://www.commbuys.com/bso/external/bidDetail.sda?docId={bid_id}`
3. Fetches the detail page HTML with a plain `requests.Session`
4. Parses all fields from the server-rendered HTML using BeautifulSoup
5. Saves incrementally to `solicitations_enriched.csv` (resume-safe; errored rows retried on rerun)

### Why BeautifulSoup instead of a direct API

COMMBUYS is a server-rendered portal — full HTML is delivered on the initial GET with no JS injection step. There is no public JSON/REST API. BeautifulSoup is sufficient and there is no bot-detection on individual detail pages.

### How the detail page is structured

Each bid detail page (`bidDetail.sda?docId=...`) is a table-heavy XHTML page. Fields are laid out as label/value `<td>` pairs:

```html
<td class="t-head-01">Department:</td>
<td class="inputs-01">Executive Office of Technology...</td>
```

The `_cell_after_label(soup, label_text)` helper finds any `<td>` whose normalized text matches `label_text` and returns the text of its next sibling `<td>`.

The **Ship-to Address** block is special — email and phone are embedded as labeled lines inside a single `<td>`:
```
Email: procurement@example.mass.gov
Phone: 617-555-0100
```

**Items / UNSPSC codes** require a multi-pass parse (`_extract_items`):
- Item header `<td class="t-head-01">` cells contain `Item #` and the 5-segment UNSPSC code in parentheses
- The item description lives in the following `<td class="inputs-01">`
- The top-level UNSPSC code and its English description are in a `U N S P S C Code:` label/value pair following the item header
- Multiple items produce pipe-delimited (`|`) values in `item_descriptions`, `unspsc_codes`, and `unspsc_descriptions`

### Input: `bidSearchResults.csv`

Manually exported from COMMBUYS. Columns carried through unchanged to the output:

| Column | Notes |
|---|---|
| `Bid Solicitation #` | Primary key — used for deduplication and URL construction |
| `Organization Name` | Issuing agency (list-level; `department` from detail may differ) |
| `Blanket #` | Blanket contract reference, often empty |
| `Buyer` | Buyer name from the list page |
| `Description` | Short title from the list page |
| `Bid Opening Date` | Closing deadline |
| `Bid Holder List` | Relative URL to the holder list, or empty |
| `Awarded Vendor(s)` | Populated after award |
| `Status` | e.g. `Sent` |
| `Alternate Id` | Optional alternate reference number |

### Output: `solicitations_enriched.csv`

All 10 input columns are carried through unchanged. Scraped fields appended:

| Column | Source | Notes |
|---|---|---|
| `department` | Detail page | Full department name from the detail page (may differ from `Organization Name`) |
| `location` | Detail page | Geographic location of the issuing office |
| `fiscal_year` | Detail page | e.g. `FY2026` |
| `type_code` | Detail page | Internal type code |
| `allow_electronic_quote` | Detail page | `Yes` or `No` |
| `required_date` | Detail page | Date goods/services are needed |
| `available_date` | Detail page | Date bid documents become available |
| `info_contact` | Detail page | Name of the informational contact |
| `bid_type` | Detail page | e.g. `IFB`, `RFP`, `RFQ` |
| `informal_bid_flag` | Detail page | `Yes` or `No` |
| `purchase_method` | Detail page | e.g. `Competitive Sealed Bid` |
| `pre_bid_conference` | Detail page | Pre-bid conference details, or empty |
| `bulletin_desc` | Detail page | Full-text description of the solicitation |
| `ship_to_email` | Detail page | Contact email from Ship-to Address block |
| `ship_to_phone` | Detail page | Contact phone from Ship-to Address block |
| `sbpp_eligible` | Detail page | Small Business Purchasing Program eligibility; empty if not present |
| `item_descriptions` | Detail page | Pipe-delimited item descriptions |
| `unspsc_codes` | Detail page | Pipe-delimited UNSPSC codes (top-level, 8 digits) |
| `unspsc_descriptions` | Detail page | Pipe-delimited UNSPSC category names |
| `ma_url` | Constructed | `https://www.commbuys.com/bso/external/bidDetail.sda?docId={bid_id}` |
| `scrape_status` | Scraper | `success` or `error` — error rows are retried on next run |

---

## How to run

### Step 1 — Export the input CSV from COMMBUYS

1. Go to [https://www.commbuys.com/bso/external/publicBids.sdo](https://www.commbuys.com/bso/external/publicBids.sdo)
2. Search for open bids (leave filters at default to get all, or filter by status = `Sent`)
3. Use the **Export** button to download `bidSearchResults.csv`
4. Place the file in `ma/bidSearchResults.csv`

### Step 2 — Run the scraper

```bash
cd ~/Desktop/state-local/ma
source ../venv/bin/activate

# Sanity check — fetch and print one new record
python scraper.py probe

# Full run (~N min depending on volume, at 0.5 s/request)
python scraper.py run
```

The run is **resume-safe**: rows with `scrape_status = success` are skipped on rerun; rows with `scrape_status = error` are retried.

### Key files

| File | Purpose |
|---|---|
| `scraper.py` | Main scraper — `probe` and `run` commands |
| `bidSearchResults.csv` | Manually exported input from COMMBUYS (gitignored) |
| `solicitations_enriched.csv` | Output — all bids with enriched fields (gitignored) |
| `tests/test_scraper.py` | Unit tests covering parsing, deduplication, URL construction |
| `tests/fixtures/sample_bid.html` | Static HTML fixture used by tests — re-export if page layout changes |

---

## Running tests

```bash
cd ~/Desktop/state-local
venv/bin/python -m pytest ma/tests/ -v
```

---

## Known gaps / next tasks

### 1. Manual export step
The input CSV must be re-downloaded from COMMBUYS before each run. There is no public list API to automate this. Automating it would require either a browser session (login required) or a reverse-engineered POST to the search endpoint — not yet implemented.

### 2. Schema normalization — NOT YET DONE
Before loading into the app's DB alongside SAM.gov data, the COMMBUYS fields need to be mapped to the common schema. Key questions:
- `solicitation_number` → `Bid Solicitation #`
- `agency` → `department` (detail) or `Organization Name` (list)
- UNSPSC codes are already captured; SAM.gov uses NAICS — a crosswalk will be needed
- `state` field = hardcode `"MA"` for all COMMBUYS records

### 3. Bid Holder List URL
The `Bid Holder List` column from the input CSV contains a relative path (e.g. `/bso/external/bidAckList.sda`) but is not currently fetched. Vendor interest data lives there and may be valuable for matching.

---

## Tech notes

- **Site tech stack:** Server-rendered XHTML — no JS injection, no API layer
- **Auth:** None required for public bid detail pages
- **Bot detection:** None observed — plain `requests.Session` with a standard Chrome User-Agent is sufficient
- **BASE_URL:** Must include `www.` — `commbuys.com` without it redirects
- **Encoding:** Pages use UTF-8; `\xa0` (non-breaking space) is normalized to regular space in all extractors
- **UNSPSC format:** `unspsc_codes` stores the 8-digit top-level code (e.g. `72154700`); the 5-segment code (e.g. `72-15-47-00-00`) appears in parentheses in item headers and is used as a fallback when the labeled code is absent
- **Dependencies:** `pandas`, `requests`, `beautifulsoup4` — no browser or XLS libraries needed
- **Python version:** 3.14 (venv at `~/Desktop/state-local/venv`)
