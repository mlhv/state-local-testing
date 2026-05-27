# PA eMarketplace Scraper

Scrapes open solicitations from [PA eMarketplace](https://www.emarketplace.state.pa.us) into a flat CSV with full detail-page fields.

## Setup

```bash
cd ~/Desktop/state-local
source venv/bin/activate
pip install -r pa/requirements.txt
```

## How to run

### 1. Export the solicitation list

1. Go to https://www.emarketplace.state.pa.us/Search.aspx
2. Leave all filters blank, make sure **View Current Records** is selected
3. Click **Export Search Results** — save the CSV into `pa/`

The filename will look like `Solicitations-2026-05-27-10-06-38.csv`. The scraper automatically picks the most recent one.

### 2. Test a single record first

```bash
cd pa
python scraper.py probe
```

Fetches the first new solicitation and prints all extracted fields. Use this to sanity-check before a full run.

### 3. Full run

```bash
python scraper.py run
```

Scrapes all new solicitations not yet in `solicitations_enriched.csv` and appends them incrementally. Safe to interrupt and re-run — already-scraped rows (status `success`) are skipped, failed rows (status `error`) are retried.

## Output

`pa/solicitations_enriched.csv` — 28 columns:

**From the exported CSV:** `Bid No`, `Bid Type`, `Title`, `Description`, `Agency`, `County`, `Bid Start Date`, `Bid End Date`, `Bid Open Date`, `Status`, `Buyer Name`, `Updated Date`

**Scraped from each detail page:** `department_for_solicitation`, `date_prepared`, `advertisement_type`, `description_full`, `delivery_location`, `duration`, `contact_first_name`, `contact_last_name`, `contact_phone`, `contact_email`, `solicitation_due_time`, `solicitation_opening_time`, `opening_location`, `no_of_addendums`, `solicitation_url`, `scrape_status`

## Notes

- Run from the `pa/` directory so the scraper finds the input CSV
- 0.5s delay between requests — a full run of ~200 solicitations takes ~2 min
- `solicitations_enriched.csv` is gitignored — do not commit it (contains PII)
- To start fresh, delete `solicitations_enriched.csv` and re-run
