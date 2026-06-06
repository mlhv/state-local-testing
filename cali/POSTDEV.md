# California

# 1. Basic Information

| Field | Details |
| --- | --- |
| Project Name | California eProcurement (calEProcure) |
| Data Source Name | calEProcure |
| Source Type | Public Procurement Portal |
| API | No direct public REST API. Data is injected into the page via an internal InFlight NLX JSON API (POST endpoint) on top of PeopleSoft ERP. Called directly without a browser. |
| API limitation | No documented public API<br>Session cookie (InFlightSessionID) must be established via an initial GET before POSTing<br>Custom 278 redirect must be followed manually on both the list and detail endpoints (requests does not auto-follow non-3xx redirects) |
| API Expiration | N/A |
| How to extract the data | Call the NLX list API (POST to AUC_RESP_INQ_AUC.GBL) to fetch all open events automatically — no manual export step<br>Send POST requests to the InFlight NLX detail endpoint for each new event ID not already in the output CSV<br>Parse structured JSON responses and extract all procurement fields<br>Write enriched data to local CSV incrementally<br>Normalize extracted fields into standard schema (not yet implemented) |
| Methods | requests<br>JSON parsing<br>Session handling<br>Manual 278 redirect following |

# 2. Data Extracted

| Field | Details |
| --- | --- |
| All column names | Department<br>Department Name<br>Event ID<br>Event Name<br>Format<br>Type<br>End Date<br>Status<br>Buyer Name<br>Buyer Email<br>description<br>unspsc_codes<br>contractor_licenses<br>counties<br>service_area_ids<br>event_version<br>published_date<br>contact_phone<br>prebid_mandatory<br>prebid_date<br>prebid_time<br>prebid_location<br>prebid_comments<br>scrape_status<br>event_url |
| Unique key | Event ID |
| Primary key | Auto-incremented database ID (post-normalization) |
| Important columns | Event ID<br>Event Name<br>Department Name<br>Type<br>End Date<br>Status<br>Buyer Email<br>description<br>unspsc_codes<br>event_url |

# 3. Script Overview

| Field | Details |
| --- | --- |
| Comprehensive Overview | calEProcure is California's state procurement portal, built on InFlight NLX middleware on top of PeopleSoft ERP. Event detail pages arrive as empty HTML shells — all data is injected by JavaScript after load. Rather than using a headless browser, the scraper calls the internal InFlight NLX JSON endpoint directly via POST requests, which returns all event data as structured JSON. This approach is ~10x faster than browser rendering and eliminates Playwright as a dependency.<br><br>The event list is fetched automatically via a POST to the NLX list endpoint (AUC_RESP_INQ_AUC.GBL) using a static template stored in nlx_list_body.txt — no manual export step required. The scraper establishes a session via an initial GET to set the InFlightSessionID cookie, fetches the full list of open events, then POSTs to the detail endpoint for each new event ID not already successfully processed in the output CSV.<br><br>Some events in the list API response have no department code in their href. For these, the scraper falls back to extracting BUSINESS_UNIT from the strCurrScript field in the detail response, which always contains the correct value.<br><br>Responses are parsed from the CaptureResults JSON structure. Multi-value fields (UNSPSC codes, contractor licenses, counties) are joined as semicolon-separated strings. Output is written incrementally after each event with a scrape_status of success or error, making the run resume-safe and ensuring errored rows are retried on the next run. A full run of ~340 active events takes approximately 3 minutes at 0.5s delay. |

# 4. Tech Stack

| Field | Details |
| --- | --- |
| Tech Stack | Python<br>requests<br>pandas<br>PostgreSQL (planned) |
| Technology used | requests — session management and POST requests to the InFlight NLX JSON endpoints<br>pandas — incremental CSV output<br>JSON parsing — structured extraction from CaptureResults response<br>PostgreSQL — normalized storage (not yet implemented) |

# 5. Common Issues & Fixes

| Issue | Fix |
| --- | --- |
| 278 redirect on POST | The NLX endpoint returns a custom 278 status with an IFLocation field pointing to a specific backend node. requests does not auto-follow non-3xx redirects — the scraper handles this manually by re-POSTing to the IFLocation URL. Applies to both the list and detail endpoints. |
| Empty dept code in list API | Some events have no usable href in the tdDeptCode cell. The scraper falls back to extracting BUSINESS_UNIT from the strCurrScript field in the detail response. The console URL printed before the POST will show a double-slash (e.g. /event//0000038887) but the value saved to the CSV is correct after the fallback runs. |
| Empty fields with no HTTP error | Symptom of an expired InFlightSessionID session cookie. Re-run the scraper — it re-establishes the session on startup. For very long runs, consider adding session refresh logic on empty results. |
| Errored rows not retried | Fixed — scrape_status column (success/error) is written for every row. On rerun, only success rows are skipped; error rows are retried automatically. |

Known pending work:

- **DB normalization** — field mapping to the common schema alongside SAM.gov and PA records is not yet implemented. Note: calEProcure uses UNSPSC codes; SAM.gov uses NAICS — a crosswalk will be needed.
