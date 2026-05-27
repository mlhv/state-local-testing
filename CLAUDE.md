# State Procurement Scraper — Project Context

## Goal

Aggregate state-level government procurement opportunities state by state, feeding into a hybrid vendor-matching system (currently sourced from SAM.gov and similar federal/state portals).

Each state gets its own folder with an independent scraper. All scrapers follow the same CSV-in / CSV-out pattern.

## Directory Structure

```
state-local/
├── venv/                          # shared root venv — use for all states
├── requirements.txt               # shared deps (pandas, requests, bs4, pytest, xlrd)
├── HANDOFF.md                     # master state-by-state status overview
├── cali/                          # California (calEProcure) — COMPLETE
│   ├── scraper.py
│   ├── requirements.txt
│   ├── events.xls                 # manually exported input (gitignored)
│   ├── events_enriched.csv        # output (gitignored)
│   ├── nlx_body.txt               # static InFlight NLX POST body template
│   ├── HANDOFF.md                 # CA-specific technical notes
│   └── POSTDEV.md                 # CA post-development documentation
├── pa/                            # Pennsylvania (PA eMarketplace) — COMPLETE
│   ├── scraper.py
│   ├── requirements.txt
│   ├── tests/
│   │   ├── test_scraper.py
│   │   └── fixtures/
│   │       └── sample_solicitation.html
│   ├── Solicitations-*.csv        # manually exported input (gitignored)
│   ├── solicitations_enriched.csv # output (gitignored)
│   ├── README.md                  # how to run
│   └── POSTDEV.md                 # PA post-development documentation
└── docs/superpowers/
    ├── specs/                     # design docs (brainstorming output)
    └── plans/                     # implementation plans
```

## Venv

One shared venv at the root. Always use it:

```bash
source /Users/ml3787/Desktop/state-local/venv/bin/activate
# or call python directly if activation doesn't work in this environment:
/Users/ml3787/Desktop/state-local/venv/bin/python
```

Install deps for a new state: `pip install -r <state>/requirements.txt`

Run tests: `/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest <state>/tests/ -v`

## Established Patterns

Every scraper follows these conventions — match them exactly when adding a new state:

### Commands
```bash
python scraper.py probe   # fetch one new record and print all fields (sanity check)
python scraper.py run     # process all new/errored records
```

Always run commands from inside the state's folder so relative paths (input CSV glob, output CSV) resolve correctly.

### Resume safety
- Output CSV has a `scrape_status` column: `success` or `error`
- `success` rows are skipped on rerun
- `error` rows are retried automatically
- Output is written after each record — safe to interrupt mid-run

### Output schema
- All columns from the input CSV are carried through unchanged
- Scraped fields are appended
- Always include `scrape_status` and `<state>_url` (the detail page URL) as the last two scraped columns

### Rate limiting
- 0.5s delay between requests (`DELAY_SECONDS = 0.5`)

### Input files
- Manually exported from the state portal before each run
- Gitignored — never commit them

### Output files
- Gitignored — contain PII (contact names, emails, phone numbers)

## Completed States

| State | Folder | Portal | Tech | Notes |
|---|---|---|---|---|
| California | `cali/` | calEProcure | requests + JSON | InFlight NLX POST API — no HTML parsing needed. See `cali/HANDOFF.md` for API details. |
| Pennsylvania | `pa/` | PA eMarketplace | requests + BeautifulSoup | Server-rendered XHTML. BASE_URL must include `www.` |

## Starting a New State

1. Create `<state>/` folder and empty `scraper.py`
2. Investigate the portal: check if detail pages are server-rendered HTML or JS-injected
   - Server-rendered → BeautifulSoup (follow PA pattern)
   - JS-injected → look for the underlying XHR/fetch call (follow CA pattern)
3. Find the manual export mechanism for the solicitation list
4. Run brainstorming skill before writing any code
5. Follow the probe/run command structure and resume-safe output pattern

## Pending Work (all states)

- **S3 upload** — raw output CSV should be uploaded after each run: `raw/<state>/<YYYY-MM-DD>/<output>.csv`
- **DB normalization** — map state fields to common schema alongside SAM.gov records
- **NAICS/UNSPSC crosswalk** — CA uses UNSPSC codes; SAM.gov uses NAICS
- **Automated input export** — manual CSV/XLS download is a known limitation for both CA and PA

## Docs

- Design specs: `docs/superpowers/specs/YYYY-MM-DD-<state>-scraper-design.md`
- Implementation plans: `docs/superpowers/plans/YYYY-MM-DD-<state>-scraper.md`
- Post-dev docs: `<state>/POSTDEV.md`
- CA technical notes: `cali/HANDOFF.md`
