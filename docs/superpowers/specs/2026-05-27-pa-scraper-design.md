# PA eMarketplace Scraper — Design Spec

**Date:** 2026-05-27
**State:** Pennsylvania (PA eMarketplace — emarketplace.state.pa.us)
**Goal:** Scrape all open solicitations from PA eMarketplace into a flat CSV, enriched with detail-page fields not available in the search export.

---

## Context

Part of a multi-state procurement aggregation pipeline feeding a vendor-matching system (currently sourced from SAM.gov and CA calEProcure). This scraper follows the same CSV-in / CSV-out pattern established for California.

---

## Architecture

```
pa/
├── Solicitations-YYYY-MM-DD.csv   ← manually exported from PA eMarketplace (read-only input)
├── solicitations_enriched.csv     ← output, appended to incrementally on each run
└── scraper.py                     ← probe / run commands
```

**Input CSV** is exported manually from the PA eMarketplace search page (no filters, "View Current Records" selected, click "Export Search Results"). The filename includes a timestamp; the scraper accepts any CSV matching `Solicitations-*.csv` in the same directory, using the most recent one.

**Detail page URL pattern:** `https://emarketplace.state.pa.us/Solicitations.aspx?SID=<url_encoded_bid_no>`

---

## Run Flow

1. Find and load the most recent `Solicitations-*.csv` in the `pa/` directory
2. Load `solicitations_enriched.csv` if it exists — collect `bid_no` values where `scrape_status == "success"` (error rows are retried)
3. For each `Bid No` not yet successfully scraped:
   - GET the detail page URL (with 0.5s delay between requests)
   - Parse with BeautifulSoup
   - Extract all fields from all four sections
   - Write the record immediately with `scrape_status = "success"` or `"error"`
4. On completion, print a summary: total processed, success count, error count

---

## Commands

```bash
python scraper.py probe   # scrape the first un-scraped Bid No, print all fields to stdout
python scraper.py run     # process all un-scraped and errored Bid Nos
```

---

## Output Schema

All columns from the input CSV are carried through unchanged. The following scraped columns are appended.

### Carried through from input CSV

| Column | Example |
|---|---|
| `Bid No` | `6100066078` |
| `Bid Type` | `IFB` |
| `Title` | `Growspan S2000 Commercial Greenhouses` |
| `Description` | truncated, may contain HTML |
| `Agency` | `Department of Corrections` |
| `County` | `Wayne` |
| `Bid Start Date` | `5/27/2026` |
| `Bid End Date` | `6/10/2026 8:00:00 AM` |
| `Bid Open Date` | `6/10/2026 10:00:00 AM` |
| `Status` | `Open` |
| `Buyer Name` | `Bonnie Snyder` |
| `Updated Date` | `5/26/2026 4:08:14 PM` |

### Scraped from detail page

| Column | Section | Example |
|---|---|---|
| `department_for_solicitation` | General Info | `Procurement` |
| `date_prepared` | General Info | `05/26/26` |
| `advertisement_type` | General Info | `Materials` |
| `description_full` | General Info | Full plain-text description (HTML stripped) |
| `delivery_location` | Dept Info | `Sci Waymart 11 Farview Drive Waymart Pa 18472` |
| `duration` | Dept Info | `One Time Delivery` |
| `contact_first_name` | Contact Info | `Bonnie` |
| `contact_last_name` | Contact Info | `Snyder` |
| `contact_phone` | Contact Info | `570-674-2717` |
| `contact_email` | Contact Info | `BOSNYDER@PA.GOV` |
| `solicitation_due_time` | Solicitation Info | `8:00 AM` |
| `solicitation_opening_time` | Solicitation Info | `10:00 AM` |
| `opening_location` | Solicitation Info | `Sci Dallas 1000 Follies Road Dallas Pa 18612` |
| `no_of_addendums` | Solicitation Info | `0` |
| `solicitation_url` | Constructed | `https://emarketplace.state.pa.us/Solicitations.aspx?SID=6100066078` |
| `scrape_status` | Meta | `success` or `error` |

---

## Error Handling

- On any request failure or parse error: log the error, write the record with all scraped fields as empty strings and `scrape_status = "error"`
- On next run, `error` rows are retried (only `success` rows are skipped)
- If a BeautifulSoup selector finds no match for a field, default to empty string — do not crash
- Output CSV is written after each record (not batched) so the run is resume-safe if interrupted mid-way

---

## Dependencies

Same as CA — no new packages needed:

```
pandas
requests
beautifulsoup4
```

---

## Future Tasks (out of scope for this implementation)

- Automate the CSV export step by reverse-engineering the Export Search Results POST request
- S3 upload of raw output keyed by date (`raw/pa-emarketplace/YYYY-MM-DD/solicitations_enriched.csv`)
- Parallelization (multiple concurrent sessions for faster runs)
- Schema normalization to map PA fields to the common DB schema alongside SAM.gov / CA records
