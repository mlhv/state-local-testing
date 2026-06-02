# Massachusetts (COMMBUYS) Solicitation Scraper — Design Spec

**Date:** 2026-05-28
**Portal:** COMMBUYS (commbuys.com) — Massachusetts eProcurement, powered by Periscope S2G
**Approach:** PA clone — self-contained BS4 scraper, CSV-in / CSV-out, probe/run commands

---

## Architecture

Self-contained `ma/scraper.py`. No shared dependencies with other state scrapers. Uses the root venv.

### Commands (run from inside `ma/`)

```bash
python scraper.py probe   # fetch one new record, print all fields
python scraper.py run     # process all new/errored records
```

### Input

`bidSearchResults.csv` — fixed filename, manually exported from COMMBUYS advanced search (open bids). Unlike PA's glob pattern, COMMBUYS always exports with this name so the scraper reads it directly.

### Detail URL

```
https://www.commbuys.com/bso/external/bidDetail.sda?docId=<BID_ID>
```

The `Bid Solicitation #` column in the CSV maps directly to `docId`. Extra query params (`external`, `parentUrl`) are not needed — confirmed they can be omitted.

### Output

`solicitations_enriched.csv` — resume-safe, written after every record. `success` rows are skipped on rerun; `error` rows are retried.

---

## Fields

### Input columns carried through unchanged (10)

| Column |
|---|
| Bid Solicitation # |
| Organization Name |
| Blanket # |
| Buyer |
| Description |
| Bid Opening Date |
| Bid Holder List |
| Awarded Vendor(s) |
| Status |
| Alternate Id |

### Scraped fields appended (21)

| Field | Source | Notes |
|---|---|---|
| `department` | Header Information | label match |
| `location` | Header Information | label match |
| `fiscal_year` | Header Information | label match |
| `type_code` | Header Information | label match |
| `allow_electronic_quote` | Header Information | label match |
| `required_date` | Header Information | label match |
| `available_date` | Header Information | label match |
| `info_contact` | Header Information | label match |
| `bid_type` | Header Information | label match |
| `informal_bid_flag` | Header Information | label match |
| `purchase_method` | Header Information | label match |
| `pre_bid_conference` | Pre Bid Conference section | label match |
| `bulletin_desc` | Bulletin Desc section | label match |
| `ship_to_email` | Ship-to Address block | extract `Email:` line |
| `ship_to_phone` | Ship-to Address block | extract `Phone:` line |
| `sbpp_eligible` | Required Quote Attachments | `YES` / `NO` / `""` if section absent |
| `item_descriptions` | Item Information | pipe-delimited, one entry per item |
| `unspsc_codes` | Item Information | pipe-delimited, one entry per item |
| `unspsc_descriptions` | Item Information | pipe-delimited, one entry per item |
| `ma_url` | constructed | the detail page URL used |
| `scrape_status` | scraper | `success` or `error` |

**Total output columns: 31** (10 input + 21 scraped)

### Note on item_descriptions vs bulletin_desc

On simple single-item solicitations, `item_descriptions` and `bulletin_desc` are often identical — buyers frequently paste the same scope-of-work text into both fields. They remain separate columns because multi-item solicitations will have distinct per-item descriptions, and downstream consumers may prefer one over the other.

---

## Extraction Strategy

### Header fields
`_cell_after_label(soup, label)` helper — identical to PA. Finds a `<td>` whose text matches the label, returns the text of the next sibling `<td>`.

### Ship-to email and phone
Locate the Ship-to Address `<td>` block, scan its text content line by line for lines starting with `Email:` and `Phone:`.

### SBPP eligibility
Find the label `"SBPP (Small Business Purchasing Program) Eligible?"` using `_cell_after_label`. Returns `""` if the Required Quote Attachments section is absent or the field is not present.

### Item Information (multi-item, pipe-delimited)
Find all Item blocks by locating elements matching the `Item # N:` header pattern. For each item:
1. Extract the item description text (the prose following the item header)
2. Extract the UNSPSC code from the `U N S P S C Code:` link text
3. Extract the UNSPSC description from the text node below the code link

Join all values with `|`. A solicitation with a single item produces no pipe character. A solicitation with no Item Information section produces `""` for all three fields.

---

## Error Handling

Identical to PA:
- Any exception during fetch or parse marks the row `scrape_status = error`
- All scraped fields get empty strings on error (no partial writes)
- Output is written after every record — safe to interrupt
- On rerun: error rows are excluded from `done_ids` and purged from the enriched list, so they are retried without duplication

Rate limiting: `DELAY_SECONDS = 0.5`

---

## Tests

File: `ma/tests/test_scraper.py`
Fixture: `ma/tests/fixtures/sample_bid.html` — a real COMMBUYS detail page with ≥2 items

| Test | What it checks |
|---|---|
| `test_find_input_csv_exits_when_none_found` | sys.exit if bidSearchResults.csv missing |
| `test_load_done_ids_returns_empty_when_no_output` | no output file → empty set |
| `test_load_done_ids_skips_error_rows` | error rows excluded from done_ids |
| `test_build_url` | correct docId URL pattern |
| `test_extract_fields_returns_all_keys` | all 19 scraped keys present (excl. ma_url, scrape_status) |
| `test_extract_fields_values_are_strings` | no non-string values |
| `test_extract_fields_no_empty_critical_fields` | bulletin_desc, department, bid_type non-empty |
| `test_output_row_has_all_columns` | 10 input + 21 scraped = 31 columns |
| `test_pipe_delimited_items` | 2-item fixture produces `\|`-joined strings for all three item fields |

---

## File Structure

```
ma/
├── scraper.py
├── requirements.txt              # requests, pandas, beautifulsoup4
├── tests/
│   ├── test_scraper.py
│   └── fixtures/
│       └── sample_bid.html
├── bidSearchResults.csv          # gitignored (manual export)
└── solicitations_enriched.csv    # gitignored (output, may contain PII)
```

---

## Known Gaps (shared with all states)

- DB normalization / common schema mapping
- Automated input export (manual CSV download remains a prerequisite)
