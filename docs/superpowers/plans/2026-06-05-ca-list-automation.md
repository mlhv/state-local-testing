# CA List Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the manual `events.xls` download with a direct NLX list API call so `python scraper.py run` requires no input file.

**Architecture:** Add `discover_events(session)` that POSTs to `AUC_RESP_INQ_AUC.GBL` and parses the 346-row response from `CaptureResults.tbl[0].Children.tblBodyTr`. Extend `extract_event_data()` to pull four fields already in the detail response (buyer name, email, format, type). Remove `load_xls()` and `xlrd` entirely.

**Tech Stack:** Python 3, `requests`, `pandas`, `pytest`, NLX JSON API

---

## File Map

| File | Change |
|---|---|
| `cali/nlx_list_body.txt` | Replace JSON response content with URL-encoded list request body (+ `tdDeptCode`) |
| `cali/tests/__init__.py` | Create (empty) |
| `cali/tests/fixtures/list_response.json` | Create: copy current `nlx_list_body.txt` content here |
| `cali/tests/test_scraper.py` | Create: tests for `discover_events`, dept code extraction, new detail fields |
| `cali/scraper.py` | Add `discover_events`, `_dept_from_href`; extend `extract_event_data`; update `probe`/`run`; remove `load_xls` |
| `cali/requirements.txt` | Remove `xlrd` |

---

### Task 1: Set up test fixture and list request body

**Context:** `nlx_list_body.txt` currently holds the JSON API response (1.2 MB). The scraper needs the URL-encoded *request* body in that file (same format as `nlx_body.txt`). We move the response to a test fixture and replace the file with the actual request body — modified to also capture `tdDeptCode`.

**Files:**
- Create: `cali/tests/__init__.py`
- Create: `cali/tests/fixtures/list_response.json`
- Modify: `cali/nlx_list_body.txt`

- [ ] **Step 1: Create test directory and move response JSON to fixture**

```bash
mkdir -p cali/tests/fixtures
touch cali/tests/__init__.py
cp cali/nlx_list_body.txt cali/tests/fixtures/list_response.json
```

Verify the fixture is valid:
```bash
python3 -c "
import json
d = json.load(open('cali/tests/fixtures/list_response.json'))
rows = d['CaptureResults']['tbl'][0]['Children']['tblBodyTr']
print(len(rows), 'rows')
print('first event:', rows[0]['Children']['tdEventId'][0]['Properties']['text'])
"
```
Expected: `346 rows` and `first event: 0000039283`

- [ ] **Step 2: Create `build_list_body.py` to add `tdDeptCode` to the request template**

Create `cali/build_list_body.py`:

```python
#!/usr/bin/env python3
"""One-time script: add tdDeptCode to list request body. Delete after running."""
import urllib.parse, json, pathlib

# Paste the full URL-encoded request payload from DevTools here.
# Starts with: IF-TargetVerb=GET&IF-TargetContent=...
RAW = """PASTE_FULL_REQUEST_PAYLOAD_HERE"""

parsed = urllib.parse.parse_qs(RAW, keep_blank_values=True)
content = json.loads(parsed["IF-TargetContent"][0])

dept_code_element = {
    "Lbl": "tdDeptCode",
    "Src": "a[id^='AUC_ID_BUS_UNIT$']",
    "Data": "href",
    "Children": [],
}

for item in content:
    if item.get("Lbl") != "tbl":
        continue
    for child in item.get("Children", []):
        if child.get("Lbl") == "tblBodyTr":
            child["Children"].append(dept_code_element)

extra = {k: v[0] for k, v in parsed.items() if k != "IF-TargetContent"}
result = urllib.parse.urlencode(
    {"IF-TargetVerb": "GET", "IF-TargetContent": json.dumps(content), **extra}
)
pathlib.Path("cali/nlx_list_body.txt").write_text(result)
print(f"Written {len(result):,} bytes to cali/nlx_list_body.txt")
```

- [ ] **Step 3: Run the script**

Paste the full URL-encoded request payload (the `IF-TargetVerb=GET&IF-TargetContent=...` string from the DevTools capture used during brainstorming) into the `RAW` variable, then run from the project root:

```bash
cd ~/Desktop/state-local
source venv/bin/activate
python cali/build_list_body.py
```

Expected: `Written X,XXX bytes to cali/nlx_list_body.txt`

- [ ] **Step 4: Verify the output file has the right shape**

```bash
python3 -c "
import urllib.parse, json
raw = open('cali/nlx_list_body.txt').read()
parsed = urllib.parse.parse_qs(raw, keep_blank_values=True)
content = json.loads(parsed['IF-TargetContent'][0])
for item in content:
    if item.get('Lbl') != 'tbl': continue
    for child in item.get('Children', []):
        if child.get('Lbl') == 'tblBodyTr':
            labels = [c['Lbl'] for c in child['Children']]
            print('tblBodyTr children:', labels)
"
```
Expected output includes `tdDeptCode` in the list:
`tblBodyTr children: ['tdEventId', 'tdEventName', 'tdDepName', 'tdPubDate', 'tdEndDate', 'tdStatus', 'tdDeptCode']`

- [ ] **Step 5: Delete the build script and commit**

```bash
rm cali/build_list_body.py
git add cali/nlx_list_body.txt cali/tests/__init__.py cali/tests/fixtures/list_response.json
git commit -m "chore(cali): set up list request body template and test fixtures"
```

---

### Task 2: Write failing tests

**Files:**
- Create: `cali/tests/test_scraper.py`

- [ ] **Step 1: Write the test file**

Create `cali/tests/test_scraper.py`:

```python
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parents[1]))
from scraper import discover_events, extract_event_data, EMPTY_EXTRA

FIXTURES = Path(__file__).parent / "fixtures"


def _mock_list_session():
    """Session mock whose POST returns the list response fixture."""
    data = json.loads((FIXTURES / "list_response.json").read_text())
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    session = MagicMock()
    session.post.return_value = resp
    return session


# ── discover_events ───────────────────────────────────────────────────────────

def test_discover_events_returns_dataframe():
    df = discover_events(_mock_list_session())
    assert isinstance(df, pd.DataFrame)


def test_discover_events_row_count():
    df = discover_events(_mock_list_session())
    assert len(df) == 346


def test_discover_events_required_columns():
    df = discover_events(_mock_list_session())
    for col in ["Event ID", "Event Name", "Department Name", "End Date", "Status", "Department"]:
        assert col in df.columns, f"Missing column: {col}"


def test_discover_events_first_row_values():
    df = discover_events(_mock_list_session())
    row = df.iloc[0]
    assert row["Event ID"] == "0000039283"
    assert row["Event Name"] == "RFQ-R1-0626-01, UTV"
    assert row["Department Name"] == "Department of Fish & Wildlife"
    assert row["End Date"] == "05/06/2026 14:00 PDT"
    assert row["Status"] == "Posted"


def test_discover_events_exits_on_empty_response():
    data = {"CaptureResults": {"tbl": [{"Children": {"tblBodyTr": []}}]}}
    resp = MagicMock()
    resp.status_code = 200
    resp.json.return_value = data
    session = MagicMock()
    session.post.return_value = resp
    with pytest.raises(SystemExit):
        discover_events(session)


# ── dept code extraction ──────────────────────────────────────────────────────

def test_dept_code_numeric():
    from scraper import _dept_from_href
    assert _dept_from_href("https://caleprocure.ca.gov/event/0250/0000038854") == "0250"


def test_dept_code_alphanumeric():
    from scraper import _dept_from_href
    assert _dept_from_href("https://caleprocure.ca.gov/event/SS100/0000012345") == "SS100"


def test_dept_code_empty_href():
    from scraper import _dept_from_href
    assert _dept_from_href("") == ""


def test_dept_code_hash_href():
    from scraper import _dept_from_href
    assert _dept_from_href("#") == ""


# ── extract_event_data new fields ─────────────────────────────────────────────

def _detail_results():
    """Minimal CaptureResults with the four new fields + stubs for existing ones."""
    return {
        "contactName":        [{"Properties": {"text": "Roderick Bustos"}}],
        "emailAnchor":        [{"Properties": {"text": "roderick.bustos@jud.ca.gov"}}],
        "format1":            [{"Properties": {"text": "Sell Event"}}],
        "format2":            [{"Properties": {"text": "RFx"}}],
        "descriptiondetails": [],
        "unspscCodeBody":     [],
        "contractorTblBody":  [],
        "serviceAreaTblBody": [],
        "conferenceRow":      [],
        "eventVersion":       [],
        "eventStartDate":     [],
        "phoneText":          [],
    }


def test_extract_buyer_name():
    assert extract_event_data(_detail_results())["Buyer Name"] == "Roderick Bustos"


def test_extract_buyer_email():
    assert extract_event_data(_detail_results())["Buyer Email"] == "roderick.bustos@jud.ca.gov"


def test_extract_format():
    assert extract_event_data(_detail_results())["Format"] == "Sell Event"


def test_extract_type():
    assert extract_event_data(_detail_results())["Type"] == "RFx"


def test_empty_extra_has_new_keys():
    for key in ["Buyer Name", "Buyer Email", "Format", "Type"]:
        assert key in EMPTY_EXTRA, f"EMPTY_EXTRA missing key: {key}"
```

- [ ] **Step 2: Run tests — confirm they all fail**

```bash
cd ~/Desktop/state-local
source venv/bin/activate
python -m pytest cali/tests/test_scraper.py -v
```

Expected: All tests FAIL (`ImportError: cannot import name 'discover_events'`).

- [ ] **Step 3: Commit failing tests**

```bash
git add cali/tests/test_scraper.py
git commit -m "test(cali): add failing tests for discover_events and new detail fields"
```

---

### Task 3: Implement `_dept_from_href()` and `discover_events()`

**Files:**
- Modify: `cali/scraper.py`

- [ ] **Step 1: Add `import re` to imports (line 8 area)**

Replace:
```python
import json
import sys
import time
import requests
import pandas as pd
from pathlib import Path
```
With:
```python
import json
import re
import sys
import time
import requests
import pandas as pd
from pathlib import Path
```

- [ ] **Step 2: Add `LIST_ENDPOINT` and `LIST_TEMPLATE_PATH` constants after `NLX_BASE`**

After the block ending with `BIDDER_TYPE: "B",` (around line 31), add:

```python
LIST_ENDPOINT = (
    "https://caleprocure.ca.gov/nlx3/psc/psfpd1"
    "/SUPPLIER/ERP/c/AUC_MANAGE_BIDS.AUC_RESP_INQ_AUC.GBL"
)
LIST_TEMPLATE_PATH = "nlx_list_body.txt"
```

- [ ] **Step 3: Add `_dept_from_href()` and `discover_events()` after `load_template()`**

After the `load_template()` function (around line 158), add:

```python
def _dept_from_href(href: str) -> str:
    """Extract dept code from a calEProcure event URL, e.g. /event/0250/..."""
    if not href or href == "#":
        return ""
    m = re.search(r"/event/([^/]+)/", href)
    return m.group(1) if m else ""


def discover_events(session) -> pd.DataFrame:
    """Fetch all open events from the NLX list API. Returns a DataFrame."""
    if not Path(LIST_TEMPLATE_PATH).exists():
        sys.exit(f"ERROR: {LIST_TEMPLATE_PATH} not found")
    body = Path(LIST_TEMPLATE_PATH).read_text()
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Referer": "https://caleprocure.ca.gov/pages/Events-BS3/event-search.aspx",
        "Origin": "https://caleprocure.ca.gov",
    }
    resp = session.post(LIST_ENDPOINT, data=body, headers=headers, timeout=30)
    resp.raise_for_status()
    results = resp.json().get("CaptureResults", {})
    rows = results.get("tbl", [{}])[0].get("Children", {}).get("tblBodyTr", [])
    if not rows:
        sys.exit("ERROR: List API returned 0 events — check session or portal status")

    records = []
    for row in rows:
        ch = row.get("Children", {})
        event_id   = (ch.get("tdEventId",   [{}])[0].get("Properties", {}).get("text")  or "").strip()
        event_name = (ch.get("tdEventName",  [{}])[0].get("Properties", {}).get("text")  or "").strip()
        dep_name   = (ch.get("tdDepName",    [{}])[0].get("Properties", {}).get("text")  or "").strip()
        end_date   = (ch.get("tdEndDate",    [{}])[0].get("Properties", {}).get("text")  or "").strip()
        status     = (ch.get("tdStatus",     [{}])[0].get("Properties", {}).get("text")  or "").strip()
        dept_href  = (ch.get("tdDeptCode",   [{}])[0].get("Properties", {}).get("href")  or "").strip()
        dept_code  = _dept_from_href(dept_href)
        records.append({
            "Event ID":        event_id,
            "Event Name":      event_name,
            "Department Name": dep_name,
            "End Date":        end_date,
            "Status":          status,
            "Department":      dept_code,
        })

    df = pd.DataFrame(records)
    print(f"Discovered {len(df)} events from list API.")
    return df
```

- [ ] **Step 4: Run the `discover_events` and dept-code tests**

```bash
cd ~/Desktop/state-local
source venv/bin/activate
python -m pytest cali/tests/test_scraper.py -k "discover_events or dept_code" -v
```

Expected: All 9 `discover_events`/`dept_code` tests PASS. The `extract_event_data` tests still FAIL.

- [ ] **Step 5: Commit**

```bash
git add cali/scraper.py
git commit -m "feat(cali): add discover_events() and _dept_from_href()"
```

---

### Task 4: Extend `extract_event_data()` and `EMPTY_EXTRA`

**Files:**
- Modify: `cali/scraper.py`

- [ ] **Step 1: Add four keys to `EMPTY_EXTRA`**

Replace:
```python
EMPTY_EXTRA = {k: "" for k in [
    "description", "unspsc_codes", "contractor_licenses", "counties",
    "service_area_ids", "event_version", "published_date", "contact_phone",
    "prebid_mandatory", "prebid_date", "prebid_time", "prebid_location", "prebid_comments",
]}
```
With:
```python
EMPTY_EXTRA = {k: "" for k in [
    "description", "unspsc_codes", "contractor_licenses", "counties",
    "service_area_ids", "event_version", "published_date", "contact_phone",
    "prebid_mandatory", "prebid_date", "prebid_time", "prebid_location", "prebid_comments",
    "Buyer Name", "Buyer Email", "Format", "Type",
]}
```

- [ ] **Step 2: Add four extractions inside `extract_event_data()`, just before the `return`**

In `extract_event_data(results)`, locate the pre-bid `conf_children` block. Just before `return {`, add:

```python
    buyer_name  = leaf(results.get("contactName", []))
    buyer_email = leaf(results.get("emailAnchor", []))
    fmt         = leaf(results.get("format1",     []))
    event_type  = leaf(results.get("format2",     []))
```

- [ ] **Step 3: Add the four fields to the `return` dict**

In the `return` block at the end of `extract_event_data()`, add after `"prebid_comments"`:

```python
        "Buyer Name":  buyer_name,
        "Buyer Email": buyer_email,
        "Format":      fmt,
        "Type":        event_type,
```

The complete `return` dict should now be:
```python
    return {
        "description":         leaf(results.get("descriptiondetails", [])),
        "unspsc_codes":        "; ".join(unspsc_pairs),
        "contractor_licenses": "; ".join(contractor_licenses),
        "counties":            "; ".join(counties),
        "service_area_ids":    "; ".join(service_area_ids),
        "event_version":       leaf(results.get("eventVersion", [])),
        "published_date":      leaf(results.get("eventStartDate", [])),
        "contact_phone":       leaf(results.get("phoneText", [])),
        "prebid_mandatory":    leaf(conf_children.get("conferenceText", [])),
        "prebid_date":         leaf(conf_children.get("dateText", [])),
        "prebid_time":         leaf(conf_children.get("timeText", [])),
        "prebid_location":     leaf(conf_children.get("locationText", [])),
        "prebid_comments":     leaf(conf_children.get("commentsText", [])),
        "Buyer Name":          buyer_name,
        "Buyer Email":         buyer_email,
        "Format":              fmt,
        "Type":                event_type,
    }
```

- [ ] **Step 4: Run all tests**

```bash
cd ~/Desktop/state-local
source venv/bin/activate
python -m pytest cali/tests/test_scraper.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cali/scraper.py
git commit -m "feat(cali): extract Buyer Name/Email, Format, Type from detail API"
```

---

### Task 5: Update `probe()` and `run()` to use `discover_events()`

**Files:**
- Modify: `cali/scraper.py`

- [ ] **Step 1: Replace `probe()`**

Replace the entire `probe()` function with:

```python
def probe():
    session = make_session()
    df = discover_events(session)
    body = load_template()
    row = df.iloc[0]
    event_id  = str(row["Event ID"])
    dept      = norm_dept(row["Department"])
    event_url = build_url(row["Department"], event_id)
    print(f"Probing: {event_url}\n")

    results = fetch_results(session, body, event_id, dept, event_url)

    Path("probe_response.json").write_text(json.dumps(results, indent=2))
    print("Raw JSON saved to probe_response.json\n")

    data = extract_event_data(results)

    print("=== Description ===")
    print(data["description"] or "(empty — check probe_response.json)")
    print("\n=== UNSPSC Codes ===")
    print(data["unspsc_codes"] or "(none)")
    print("\n=== Contractor License Types ===")
    print(data["contractor_licenses"] or "(none)")
    print("\n=== Counties (Service Area) ===")
    print(data["counties"] or "(none)")
    print("\n=== Event Details ===")
    print(f"Buyer Name:        {data['Buyer Name']}")
    print(f"Buyer Email:       {data['Buyer Email']}")
    print(f"Format:            {data['Format']}")
    print(f"Type:              {data['Type']}")
    print(f"Version:           {data['event_version']}")
    print(f"Published Date:    {data['published_date']}")
    print(f"Contact Phone:     {data['contact_phone']}")
    print(f"Pre-Bid Mandatory: {data['prebid_mandatory']}")
    print(f"Pre-Bid Date:      {data['prebid_date']}")
    print(f"Pre-Bid Time:      {data['prebid_time']}")
    print(f"Pre-Bid Location:  {data['prebid_location']}")
    print(f"Pre-Bid Comments:  {data['prebid_comments']}")
```

- [ ] **Step 2: Replace `run()`**

Replace the entire `run()` function with:

```python
def run():
    session = make_session()
    df = discover_events(session)
    body = load_template()
    total = len(df)
    enriched = []

    done_ids = set()
    if Path(OUTPUT_PATH).exists():
        existing = pd.read_csv(OUTPUT_PATH)
        done_ids = set(existing["Event ID"].astype(str))
        enriched = existing.to_dict("records")
        print(f"Resuming — {len(done_ids)} already done, {total - len(done_ids)} remaining")

    for i, row in df.iterrows():
        event_id = str(row["Event ID"])
        if event_id in done_ids:
            continue

        dept      = norm_dept(row["Department"])
        event_url = build_url(row["Department"], event_id)
        print(f"[{i+1}/{total}] {event_url}")

        try:
            results = fetch_results(session, body, event_id, dept, event_url)
            extra   = extract_event_data(results)
        except Exception as e:
            print(f"  ERROR: {e}")
            extra = EMPTY_EXTRA.copy()

        enriched.append({**row.to_dict(), **extra, "event_url": event_url})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {len(enriched)} rows saved to {OUTPUT_PATH}")
```

- [ ] **Step 3: Run all tests**

```bash
cd ~/Desktop/state-local
source venv/bin/activate
python -m pytest cali/tests/test_scraper.py -v
```

Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add cali/scraper.py
git commit -m "feat(cali): wire probe() and run() to use discover_events()"
```

---

### Task 6: Remove dead code and `xlrd`

**Files:**
- Modify: `cali/scraper.py`
- Modify: `cali/requirements.txt`

- [ ] **Step 1: Delete `XLS_PATH` constant**

Remove the line:
```python
XLS_PATH = "events.xls"
```

- [ ] **Step 2: Delete `load_xls()`**

Remove the entire function:
```python
def load_xls():
    df = pd.read_excel(XLS_PATH, header=0, engine="xlrd")
    print(f"Loaded {len(df)} rows. Columns: {df.columns.tolist()}")
    return df
```

- [ ] **Step 3: Remove `xlrd` from `cali/requirements.txt`**

Replace the file contents with:
```
pandas
requests
```

- [ ] **Step 4: Run all tests**

```bash
cd ~/Desktop/state-local
source venv/bin/activate
python -m pytest cali/tests/test_scraper.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add cali/scraper.py cali/requirements.txt
git commit -m "chore(cali): remove load_xls(), XLS_PATH, xlrd — no longer needed"
```

---

### Task 7: Smoke test

**No code changes — live verification only. Run from `cali/` with `events.xls` absent.**

- [ ] **Step 1: Confirm no `events.xls` is present**

```bash
ls ~/Desktop/state-local/cali/events.xls 2>/dev/null && echo "FILE PRESENT — remove it" || echo "OK — events.xls absent"
```

Expected: `OK — events.xls absent`

- [ ] **Step 2: Run probe**

```bash
cd ~/Desktop/state-local/cali
source ../venv/bin/activate
python scraper.py probe
```

Expected output:
```
Discovered 346 events from list API.
Probing: https://caleprocure.ca.gov/event/XXXX/0000039283

...
Buyer Name:        <non-empty name>
Buyer Email:       <non-empty email>
Format:            <non-empty format>
Type:              <non-empty type>
```

**If `Department` is empty (event URL shows `.../event//0000039283`):** The `AUC_ID_BUS_UNIT$` href is JS-only with no `href` attribute. Apply this fallback: in `run()` and `probe()`, after a successful `fetch_results()` call, extract the dept code from the detail response's `strCurrScript`:

```python
# After: results = fetch_results(session, body, event_id, dept, event_url)
if not dept:
    script_nodes = results.get("strCurrScript", [])
    if script_nodes:
        html = script_nodes[0].get("Properties", {}).get("html", "")
        m = re.search(r"BUSINESS_UNIT=([^&'\"]+)", html)
        if m:
            dept = m.group(1)
            event_url = build_url(dept, event_id)
```

Add this block in both `probe()` (right after `results = fetch_results(...)`) and `run()` (inside the `try` block, right after `results = fetch_results(...)`). Commit as `fix(cali): fallback dept code from strCurrScript when href is empty`.

- [ ] **Step 3: Run a 3-row batch and inspect output columns**

```bash
cd ~/Desktop/state-local/cali
python3 -c "
import scraper, pandas as pd, time
scraper.DELAY_SECONDS = 0
session = scraper.make_session()
df = scraper.discover_events(session).head(3)
body = scraper.load_template()
rows = []
for _, row in df.iterrows():
    dept = scraper.norm_dept(row['Department'])
    url = scraper.build_url(row['Department'], row['Event ID'])
    results = scraper.fetch_results(session, body, row['Event ID'], dept, url)
    extra = scraper.extract_event_data(results)
    rows.append({**row.to_dict(), **extra, 'event_url': url})
out = pd.DataFrame(rows)
print('Columns:', out.columns.tolist())
print(out[['Event ID', 'Department', 'Buyer Name', 'Buyer Email', 'Format', 'Type']].to_string())
"
```

Confirm all six spot-check columns are non-empty.

- [ ] **Step 4: Final commit**

```bash
cd ~/Desktop/state-local
git add -p
git commit -m "chore(cali): smoke test complete — CA list automation verified"
```
