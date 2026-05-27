# Pennsylvania

# 1. Basic Information

| Field | Details |
| --- | --- |
| Project Name | Pennsylvania eMarketplace |
| Data Source Name | Pennsylvania eMarketplace |
| Source Type | Public Procurement Portal |
| API | No direct public REST API. Data is exposed through server-rendered XHTML pages (ASP.NET). |
| API limitation | No documented public API<br>Manual CSV export required for solicitation list<br>Possible request throttling if scraping aggressively |
| API Expiration | N/A |
| How to extract the data | Manually export open solicitation list as CSV from PA eMarketplace search page<br>Send HTTP GET requests to each new solicitation's detail page<br>Parse HTML responses with BeautifulSoup and extract full procurement fields<br>Write enriched data to local CSV incrementally<br>Upload raw CSV to S3 bucket (not yet implemented)<br>Normalize extracted fields into standard schema (not yet implemented) |
| Methods | requests<br>BeautifulSoup<br>HTML parsing<br>Session handling |

# 2. Data Extracted

| Field | Details |
| --- | --- |
| All column names | Bid No<br>Bid Type<br>Title<br>Description<br>Agency<br>County<br>Bid Start Date<br>Bid End Date<br>Bid Open Date<br>Status<br>Buyer Name<br>Updated Date<br>department_for_solicitation<br>date_prepared<br>advertisement_type<br>description_full<br>delivery_location<br>duration<br>contact_first_name<br>contact_last_name<br>contact_phone<br>contact_email<br>solicitation_due_time<br>solicitation_opening_time<br>opening_location<br>no_of_addendums<br>solicitation_url<br>scrape_status |
| Unique key | Bid No |
| Primary key | Auto-incremented database ID (post-normalization) |
| Important columns | Bid No<br>Title<br>Agency<br>Bid End Date<br>Status<br>solicitation_url<br>description_full<br>contact_email |

# 3. Script Overview

| Field | Details |
| --- | --- |
| Comprehensive Overview | PA eMarketplace is a public procurement portal built on ASP.NET that exposes solicitation listings through a search page and individual detail pages rendered as server-side XHTML. Procurement records are directly embedded in the page HTML rather than returned through a separate JSON API, making BeautifulSoup an appropriate parsing tool with no need for browser automation.<br><br>The extraction workflow starts with a manually exported CSV from the PA eMarketplace search page (all open solicitations, no filters). The scraper reads the Bid No column from this CSV, diffs it against an existing enriched output file to identify new or previously errored solicitations, then GETs each detail page and extracts all four sections: General Information, Department Information, Contact Information, and Solicitation Information.<br><br>Rows are written to `solicitations_enriched.csv` after each request, making the run resume-safe if interrupted. Rows that fail to scrape are marked `scrape_status = error` and are automatically retried on the next run. Successfully scraped rows are marked `scrape_status = success` and are skipped on future runs. |

# 4. Tech Stack

| Field | Details |
| --- | --- |
| Tech Stack | Python<br>requests<br>BeautifulSoup<br>pandas<br>PostgreSQL (planned) |
| Technology used | requests — HTTP GET requests to detail pages<br>BeautifulSoup — HTML parsing and field extraction<br>pandas — CSV loading, diffing, and incremental output<br>PostgreSQL — normalized storage (not yet implemented) |

# 5. Common Issues & Fixes

None identified in initial run. Known limitations and pending work:

- **Manual CSV export** — the input solicitation list must be downloaded by hand from the PA eMarketplace search page before each run. Automating this step (reverse-engineering the Export Search Results POST request) is a separate future task.
- **S3 upload** — raw output CSV should be uploaded to S3 keyed by run date. Not yet implemented.
- **DB normalization** — field mapping to the common schema alongside SAM.gov and CA records is not yet implemented.
