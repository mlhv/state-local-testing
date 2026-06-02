# California

# 1. Basic Information

| Field | Details |
| --- | --- |
| Project Name | California eProcurement (calEProcure) |
| Data Source Name | calEProcure |
| Source Type | Public Procurement Portal |
| API | No direct public REST API. Data is injected into the page via an internal InFlight NLX JSON API (POST endpoint) on top of PeopleSoft ERP. Called directly without a browser. |
| API limitation | No documented public API<br>Manual XLS export required for the solicitation list<br>Downloaded XLS is actually HTML-disguised — must be re-saved from Excel as real XLS before use<br>Session cookie (InFlightSessionID) must be established via an initial GET before POSTing<br>Custom 278 redirect must be followed manually (requests does not auto-follow non-3xx redirects) |
| API Expiration | N/A |
| How to extract the data | Manually export active bid list as XLS from calEProcure search page<br>Re-save the XLS from Excel (file is HTML-disguised as XLS on download)<br>Send POST requests to the InFlight NLX JSON endpoint for each new event<br>Parse structured JSON responses and extract all procurement fields<br>Write enriched data to local CSV incrementally<br>Normalize extracted fields into standard schema (not yet implemented) |
| Methods | requests<br>JSON parsing<br>Session handling<br>Manual 278 redirect following |

# 2. Data Extracted

| Field | Details |
| --- | --- |
| All column names | Department<br>Department Name<br>Event ID<br>Event Name<br>Format<br>Type<br>End Date<br>Status<br>Buyer Name<br>Buyer Email<br>description<br>unspsc_codes<br>contractor_licenses<br>counties<br>service_area_ids<br>event_version<br>published_date<br>contact_phone<br>prebid_mandatory<br>prebid_date<br>prebid_time<br>prebid_location<br>prebid_comments<br>event_url |
| Unique key | Event ID |
| Primary key | Auto-incremented database ID (post-normalization) |
| Important columns | Event ID<br>Event Name<br>Department Name<br>Type<br>End Date<br>Status<br>Buyer Email<br>description<br>unspsc_codes<br>event_url |

# 3. Script Overview

| Field | Details |
| --- | --- |
| Comprehensive Overview | calEProcure is California's state procurement portal, built on InFlight NLX middleware on top of PeopleSoft ERP. Event detail pages arrive as empty HTML shells — all data is injected by JavaScript after load. Rather than using a headless browser, the scraper calls the internal InFlight NLX JSON endpoint directly via POST requests, which returns all event data as structured JSON. This approach is ~10x faster than browser rendering and eliminates Playwright as a dependency.<br><br>The extraction workflow starts with a manually exported XLS from the calEProcure search page (Status = Posted, no other filters). The XLS must be re-saved from Excel since the downloaded file is an HTML table disguised with a .xls extension. The scraper reads the Event ID and Department columns, establishes a session via an initial GET to set the InFlightSessionID cookie, then POSTs to the NLX endpoint for each new event ID not already in the output CSV.<br><br>Responses are parsed from the CaptureResults JSON structure. Multi-value fields (UNSPSC codes, contractor licenses, counties) are joined as semicolon-separated strings. Output is written incrementally after each event, making the run resume-safe. A full run of ~530 events takes approximately 8 minutes at 0.5s delay. |

# 4. Tech Stack

| Field | Details |
| --- | --- |
| Tech Stack | Python<br>requests<br>pandas<br>xlrd<br>PostgreSQL (planned) |
| Technology used | requests — session management and POST requests to the InFlight NLX JSON endpoint<br>pandas + xlrd — XLS loading and incremental CSV output<br>JSON parsing — structured extraction from CaptureResults response<br>PostgreSQL — normalized storage (not yet implemented) |

# 5. Common Issues & Fixes

| Issue | Fix |
| --- | --- |
| Downloaded XLS is rejected by xlrd | Re-save the file from Excel as a real .xls before running the scraper. The downloaded file is an HTML table with a .xls extension — xlrd rejects it, Excel handles it transparently. |
| 278 redirect on POST | The NLX endpoint returns a custom 278 status with an IFLocation field pointing to a specific backend node. requests does not auto-follow non-3xx redirects — the scraper handles this manually by re-POSTing to the IFLocation URL. |
| Empty fields with no HTTP error | Symptom of an expired InFlightSessionID session cookie. Re-run the scraper — it re-establishes the session on startup. For very long runs, consider adding session refresh logic on empty results. |

Known pending work:

- **Manual XLS export** — the input event list must be downloaded by hand from calEProcure. Automating this step is a separate future task (the signed XLS download URL is available in the NLX search response JSON).
- **DB normalization** — field mapping to the common schema alongside SAM.gov and PA records is not yet implemented. Note: calEProcure uses UNSPSC codes; SAM.gov uses NAICS — a crosswalk will be needed.
