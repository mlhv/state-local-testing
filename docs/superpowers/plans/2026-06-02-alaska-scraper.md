# Alaska IRIS VSS Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scraper for Alaska's IRIS VSS portal (CGI Advantage 4) that discovers open solicitations via JSON API and writes `ak/solicitations_enriched.csv`.

**Architecture:** patchright navigates to the portal to pass DataDome and intercepts an Advantage4 API response to capture session tokens; all data fetches POST JSON to `/PRDVSS1X1/Advantage4` with `Adv-*` headers via `requests`. Each solicitation requires 3 sequential API calls: `docTransition`, then two `tabChange` calls for Additional Instructions and Commodity Lines. Session tokens rotate with every response.

**Tech Stack:** Python 3, patchright, requests, pandas, pytest

---

## File Map

```
ak/
├── scraper.py           # all scraping logic + probe/run entry points
├── requirements.txt     # patchright, requests, pandas
└── tests/
    ├── __init__.py
    ├── test_scraper.py
    └── fixtures/
        ├── sample_list_response.json      # trimmed search response
        ├── sample_inst_response.json      # instructions tab response
        └── sample_commodity_response.json # commodity tab response (created in Task 9)
```

---

### Task 1: Scaffold

**Files:**
- Create: `ak/scraper.py`
- Create: `ak/requirements.txt`
- Create: `ak/tests/__init__.py`
- Create: `ak/tests/test_scraper.py`

- [ ] **Step 1: Create `ak/requirements.txt`**

```
patchright
requests
pandas
pytest
```

- [ ] **Step 2: Create `ak/tests/__init__.py`** (empty file)

- [ ] **Step 3: Create stub `ak/scraper.py`**

```python
"""
Alaska IRIS VSS public solicitations scraper.
Usage:
  python scraper.py probe   -- discover open solicitations, pick first, print all fields
  python scraper.py run     -- discover open solicitations, enrich all new, write CSV
"""

import sys, time, uuid, random, datetime
import requests
import pandas as pd
from pathlib import Path

OUTPUT_PATH = "solicitations_enriched.csv"
DELAY_SECONDS = 0.5
BASE_URL = "https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4"
PORTAL_URL = "https://iris-vss.alaska.gov/"
USER_DATA_DIR = Path.home() / ".ak_scraper_profile"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LIST_FIELDS = [
    "doc_ref", "doc_type", "description", "department",
    "buyer_name", "buyer_email", "buyer_phone",
    "closing_dt", "publish_dt", "amended_dt", "status", "category_code",
]

SCRAPED_FIELDS = [
    "additional_instructions", "commodity_descriptions",
    "commodity_codes", "commodity_specs", "alaska_url", "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}

# Static search page checksum (VIEW is stable for this page layout)
_SEARCH_VIEW_CHECKSUM = 3838637284

# Static viewState for the solicitations search page
_SEARCH_VIEWSTATE = {
    "vss.page.VVSSX10019.gridView1.group1.cardSearch": {"editable": True},
    "vss.page.VVSSX10019.gridView1.group1.cardSearch.search1": {"editable": True},
    "vss.page.VVSSX10019": {
        "closed": False, "hidden": False, "editable": False,
        "protected": False, "required": False,
    },
}

# Tab-change action keys (confirmed from network capture)
_INST_TAB_KEY = (
    "vss.page.VSSSolicitationDocument"
    ".SolicitationDocumentView.wizardNavLinks.navSolicitation"
)
_COMM_TAB_KEY = (
    "vss.page.VSSSolicitationDocument"
    ".SolicitationDocumentView.wizardNavLinks.navCommodity"
)
```

- [ ] **Step 4: Create stub `ak/tests/test_scraper.py`**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import scraper
```

- [ ] **Step 5: Verify test file is discoverable**

Run from `ak/`:
```bash
cd /Users/ml3787/Desktop/state-local/ak
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/ -v
```
Expected: `no tests ran` (0 collected)

- [ ] **Step 6: Commit**

```bash
git add ak/
git commit -m "feat(ak): scaffold Alaska IRIS VSS scraper"
```

---

### Task 2: Pure helper functions + tests

**Files:**
- Modify: `ak/scraper.py`
- Modify: `ak/tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Add to `ak/tests/test_scraper.py`:

```python
import datetime

class TestParseDocRef:
    def test_extracts_human_readable_form(self):
        raw = "[RFQ,09,260000015,2][RFQ-09-260000015-2]"
        assert scraper.parse_doc_ref(raw) == "RFQ-09-260000015-2"

    def test_different_doc_type(self):
        raw = "[IFB,01,100000001,0][IFB-01-100000001-0]"
        assert scraper.parse_doc_ref(raw) == "IFB-01-100000001-0"


class TestParseColumnValue:
    def test_extracts_comma_separated_form(self):
        raw = "[RFQ,09,260000015,2][RFQ-09-260000015-2]"
        assert scraper.parse_column_value(raw) == "RFQ,09,260000015,2"


class TestMsToIso:
    def test_converts_ms_timestamp(self):
        # 1780524000000 ms = 2026-06-03T02:00:00Z
        result = scraper.ms_to_iso(1780524000000)
        assert result == "2026-06-03T02:00:00Z"

    def test_empty_string_returns_empty(self):
        assert scraper.ms_to_iso("") == ""

    def test_empty_list_default_returns_empty(self):
        assert scraper.ms_to_iso(None) == ""
```

- [ ] **Step 2: Run tests — expect failures**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: `AttributeError: module 'scraper' has no attribute 'parse_doc_ref'`

- [ ] **Step 3: Implement helpers in `ak/scraper.py`**

Add after the constants block:

```python
def parse_doc_ref(raw: str) -> str:
    """Extract 'RFQ-09-260000015-2' from '[RFQ,09,260000015,2][RFQ-09-260000015-2]'."""
    first_close = raw.index("]")
    second_open = raw.index("[", first_close)
    second_close = raw.index("]", second_open)
    return raw[second_open + 1:second_close]


def parse_column_value(raw: str) -> str:
    """Extract 'RFQ,09,260000015,2' from '[RFQ,09,260000015,2][...]' for docTransition."""
    first_open = raw.index("[")
    first_close = raw.index("]", first_open)
    return raw[first_open + 1:first_close]


def ms_to_iso(ms) -> str:
    """Convert millisecond epoch to ISO 8601 UTC string. Returns '' for falsy input."""
    if not ms:
        return ""
    try:
        return datetime.datetime.utcfromtimestamp(int(ms) / 1000).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""
```

- [ ] **Step 4: Run tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add ak/scraper.py ak/tests/test_scraper.py
git commit -m "feat(ak): add parse_doc_ref, parse_column_value, ms_to_iso helpers"
```

---

### Task 3: load_done_ids + test

**Files:**
- Modify: `ak/scraper.py`
- Modify: `ak/tests/test_scraper.py`

- [ ] **Step 1: Write failing test**

Add to `ak/tests/test_scraper.py`:

```python
import tempfile, os

class TestLoadDoneIds:
    def test_returns_empty_set_when_no_file(self, tmp_path):
        result = scraper.load_done_ids(str(tmp_path / "missing.csv"))
        assert result == set()

    def test_returns_success_doc_refs_only(self, tmp_path):
        csv = tmp_path / "out.csv"
        csv.write_text(
            "doc_ref,scrape_status\n"
            "RFQ-09-260000015-2,success\n"
            "RFQ-09-260000016-0,error\n"
            "IFB-01-100000001-0,success\n"
        )
        result = scraper.load_done_ids(str(csv))
        assert result == {"RFQ-09-260000015-2", "IFB-01-100000001-0"}

    def test_returns_empty_set_for_missing_columns(self, tmp_path):
        csv = tmp_path / "out.csv"
        csv.write_text("col_a,col_b\nfoo,bar\n")
        result = scraper.load_done_ids(str(csv))
        assert result == set()
```

- [ ] **Step 2: Run tests — expect failures**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py::TestLoadDoneIds -v
```
Expected: `AttributeError: module 'scraper' has no attribute 'load_done_ids'`

- [ ] **Step 3: Implement `load_done_ids` in `ak/scraper.py`**

```python
def load_done_ids(output_path: str) -> set:
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "doc_ref" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "doc_ref"].astype(str))
```

- [ ] **Step 4: Run tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add ak/scraper.py ak/tests/test_scraper.py
git commit -m "feat(ak): add load_done_ids"
```

---

### Task 4: parse_list_row + fixture + test

**Files:**
- Create: `ak/tests/fixtures/sample_list_response.json`
- Modify: `ak/scraper.py`
- Modify: `ak/tests/test_scraper.py`

- [ ] **Step 1: Create fixture `ak/tests/fixtures/sample_list_response.json`**

```json
{
  "data": {
    "ds_data": {
      "T1SO_SRCH_QRY": {
        "rows_total": 1,
        "rows_per_page": 20,
        "end_data_window": 1,
        "row_data": [
          {
            "ADV_ROW_ID": "Wkzn3MKijwsLyp7H",
            "ADV_ROW_SEL": false,
            "SHOW_TXT": "",
            "SO_CAT_CD": "145",
            "SO_STA": "M",
            "DOC_CD": "RFQ",
            "DOC_DSCR": "H21 400Hz GPU",
            "DEPT_NM": "Department of Military and Veterans' Affairs",
            "BUYR_NM": "DAVID BAKER",
            "DOC_REF": "[RFQ,09,260000015,2][RFQ-09-260000015-2]",
            "DOC_CD_CONCAT": "Request for Quotes (RFQ)",
            "SO_CLSNG_DT_TM": 1780524000000,
            "PUB_DT": 1779436800000,
            "AMND_DT": 1779436800000,
            "BUYR_EMAIL_AD": "david.baker@alaska.gov",
            "BUYR_PH_NO": "907-428-7220",
            "BUYR_FAX_NO": ""
          }
        ]
      }
    }
  },
  "session_info": {
    "session_id": "3fe929365bd83b00",
    "page_id": "5816087771366880920",
    "csrf_token": "XnZRj25GgAEkWRFF3mmp"
  },
  "checksum": {
    "VIEW": {"gridView1": 3838637284},
    "DS_DATA": {"T1SO_SRCH_QRY": 3352782786},
    "DATASOURCE": {"T1SO_SRCH_QRY": 1650476997}
  },
  "viewState": {
    "vss.page.VVSSX10019.gridView1.group1.cardSearch": {"editable": true},
    "vss.page.VVSSX10019.gridView1.group1.cardSearch.search1": {"editable": true},
    "vss.page.VVSSX10019": {"closed": false, "hidden": false, "editable": false, "protected": false, "required": false}
  }
}
```

- [ ] **Step 2: Write failing test**

Add to `ak/tests/test_scraper.py`:

```python
import json
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"

class TestParseListRow:
    def setup_method(self):
        with open(FIXTURES / "sample_list_response.json") as f:
            resp = json.load(f)
        self.raw_row = resp["data"]["ds_data"]["T1SO_SRCH_QRY"]["row_data"][0]

    def test_doc_ref(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["doc_ref"] == "RFQ-09-260000015-2"

    def test_doc_type(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["doc_type"] == "Request for Quotes (RFQ)"

    def test_description(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["description"] == "H21 400Hz GPU"

    def test_department(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["department"] == "Department of Military and Veterans' Affairs"

    def test_buyer_fields(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["buyer_name"] == "DAVID BAKER"
        assert row["buyer_email"] == "david.baker@alaska.gov"
        assert row["buyer_phone"] == "907-428-7220"

    def test_timestamps_converted_to_iso(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["closing_dt"] == "2026-06-03T02:00:00Z"
        assert row["publish_dt"] == "2026-05-22T00:00:00Z"

    def test_status_and_category(self):
        row = scraper.parse_list_row(self.raw_row)
        assert row["status"] == "M"
        assert row["category_code"] == "145"
```

- [ ] **Step 3: Run tests — expect failures**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py::TestParseListRow -v
```
Expected: `AttributeError: module 'scraper' has no attribute 'parse_list_row'`

- [ ] **Step 4: Implement `parse_list_row` in `ak/scraper.py`**

```python
def parse_list_row(row: dict) -> dict:
    """Extract list fields from a single T1SO_SRCH_QRY row_data entry."""
    return {
        "doc_ref":       parse_doc_ref(row.get("DOC_REF", "")),
        "doc_type":      row.get("DOC_CD_CONCAT", ""),
        "description":   row.get("DOC_DSCR", ""),
        "department":    row.get("DEPT_NM", ""),
        "buyer_name":    row.get("BUYR_NM", ""),
        "buyer_email":   row.get("BUYR_EMAIL_AD", ""),
        "buyer_phone":   row.get("BUYR_PH_NO", ""),
        "closing_dt":    ms_to_iso(row.get("SO_CLSNG_DT_TM", "")),
        "publish_dt":    ms_to_iso(row.get("PUB_DT", "")),
        "amended_dt":    ms_to_iso(row.get("AMND_DT", "")),
        "status":        row.get("SO_STA", ""),
        "category_code": row.get("SO_CAT_CD", ""),
    }
```

- [ ] **Step 5: Run tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 16 passed

- [ ] **Step 6: Commit**

```bash
git add ak/scraper.py ak/tests/test_scraper.py ak/tests/fixtures/sample_list_response.json
git commit -m "feat(ak): add parse_list_row with fixture"
```

---

### Task 5: extract_instructions + fixture + test

**Files:**
- Create: `ak/tests/fixtures/sample_inst_response.json`
- Modify: `ak/scraper.py`
- Modify: `ak/tests/test_scraper.py`

- [ ] **Step 1: Create fixture `ak/tests/fixtures/sample_inst_response.json`**

This is the response from the `navSolicitation` tab-change call (trimmed):

```json
{
  "data": {
    "ds_data": {
      "T1SO_DOC_HDR": {
        "row_data": [
          {
            "ADV_ROW_ID": "Bo04AFNfuP1vhgV4",
            "SRCH_DOC_ID": "RFQ-09-260000015-2",
            "ADDL_INFO": "The State of Alaska, Department of Military and Veterans Affairs (DMVA), Alaska Air National Guard is soliciting for quotes from qualified vendors to provide one (1) 400Hz dual output solid-state Ground Power Unit (GPU) as specified in the attached Request for Quotes (RFQ)."
          }
        ]
      }
    }
  },
  "session_info": {
    "session_id": "3feff59447e0d3f6",
    "page_id": "98772138390642301339",
    "csrf_token": "soMJ4iLfSZZXSpd2JN3b"
  },
  "checksum": {
    "VIEW": {
      "SolicitationDocumentView": 70985443,
      "solicitationInstView": 3784087706,
      "generalInfoView": 2598906815,
      "commoditiesView": 2215349693
    },
    "DS_DATA": {
      "T1SO_DOC_HDR": 4274830125,
      "T3SO_DOC_COMMLN": 2082338324,
      "T2SO_DOC_COMMGP": 137053144
    },
    "DATASOURCE": {
      "T3SO_DOC_COMMLN": 1245200392,
      "T1SO_DOC_HDR": 2926664375,
      "T2SO_DOC_COMMGP": 2496649304
    }
  },
  "viewState": {
    "vss.page.VSSSolicitationDocument": {
      "closed": false, "hidden": false, "editable": false, "protected": false, "required": false
    }
  }
}
```

- [ ] **Step 2: Write failing test**

Add to `ak/tests/test_scraper.py`:

```python
class TestExtractInstructions:
    def setup_method(self):
        with open(FIXTURES / "sample_inst_response.json") as f:
            self.resp = json.load(f)

    def test_extracts_addl_info(self):
        result = scraper.extract_instructions(self.resp)
        assert "400Hz dual output solid-state Ground Power Unit" in result["additional_instructions"]

    def test_empty_string_when_no_rows(self):
        resp = {"data": {"ds_data": {"T1SO_DOC_HDR": {"row_data": []}}}}
        result = scraper.extract_instructions(resp)
        assert result["additional_instructions"] == ""
```

- [ ] **Step 3: Run tests — expect failures**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py::TestExtractInstructions -v
```
Expected: `AttributeError: module 'scraper' has no attribute 'extract_instructions'`

- [ ] **Step 4: Implement `extract_instructions` in `ak/scraper.py`**

```python
def extract_instructions(response: dict) -> dict:
    """Extract ADDL_INFO from a navSolicitation tab-change response."""
    rows = (
        response.get("data", {})
        .get("ds_data", {})
        .get("T1SO_DOC_HDR", {})
        .get("row_data", [])
    )
    addl_info = rows[0].get("ADDL_INFO", "") if rows else ""
    return {"additional_instructions": addl_info}
```

- [ ] **Step 5: Run tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 19 passed

- [ ] **Step 6: Commit**

```bash
git add ak/scraper.py ak/tests/test_scraper.py ak/tests/fixtures/sample_inst_response.json
git commit -m "feat(ak): add extract_instructions with fixture"
```

---

### Task 6: API plumbing helpers + make_session()

**Files:**
- Modify: `ak/scraper.py`

No unit tests — browser required. Verified manually in Task 8 probe.

- [ ] **Step 1: Add `_adv_headers` and `_update_ctx` to `ak/scraper.py`**

```python
def _adv_headers(ctx: dict, action_code: str, action_type: str) -> dict:
    """Build Adv-* request headers and increment request_id in ctx."""
    ctx["request_id"] += 1
    return {
        "Accept":             "application/json, text/plain, */*",
        "Content-Type":       "application/json;charset=UTF-8",
        "Adv-Action-Code":    action_code,
        "Adv-Action-Type":    action_type,
        "Adv-Conversation-Id": ctx["conversation_id"],
        "Adv-Page-Id":        ctx["page_id"],
        "Adv-Request-Id":     str(ctx["request_id"]),
        "Adv-Session-Id":     ctx["session_id"],
        "Adv-Window-Id":      ctx["window_id"],
    }


def _update_ctx(ctx: dict, response_body: dict) -> None:
    """Update session tokens in ctx from an API response (mutates ctx)."""
    si = response_body.get("session_info", {})
    if si.get("session_id"):
        ctx["session_id"] = si["session_id"]
        ctx["page_id"]    = si["page_id"]
        ctx["csrf_token"] = si["csrf_token"]
    if response_body.get("checksum"):
        ctx["checksum"]  = response_body["checksum"]
    if response_body.get("viewState"):
        ctx["viewState"] = response_body["viewState"]
```

- [ ] **Step 2: Add `make_session()` to `ak/scraper.py`**

```python
def make_session():
    """
    Launch Chrome via patchright to bypass DataDome, intercept an Advantage4
    response to capture session tokens, return (requests.Session, ctx).

    ctx keys: session_id, page_id, csrf_token, window_id, conversation_id, request_id
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "ERROR: patchright required.\n"
            "Install: pip install patchright && patchright install chromium"
        )

    captured = {}

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
        )
        page = context.new_page()

        def on_response(response):
            if BASE_URL in response.url and not captured:
                try:
                    body = response.json()
                    si = body.get("session_info", {})
                    if si.get("session_id"):
                        captured.update(si)
                except Exception:
                    pass

        page.on("response", on_response)

        # Warm up profile so DataDome sees Google cookies
        for warmup in ["https://www.google.com", "https://www.bing.com"]:
            try:
                page.goto(warmup, wait_until="domcontentloaded", timeout=15_000)
                time.sleep(2)
            except Exception:
                pass

        # Navigate to portal — DataDome check runs here
        page.goto(PORTAL_URL, wait_until="networkidle", timeout=60_000)
        time.sleep(2)

        # Click into Solicitations to trigger an Advantage4 API call
        try:
            page.click("text=Solicitations", timeout=10_000)
            page.wait_for_load_state("networkidle", timeout=30_000)
        except Exception:
            pass

        # Wait up to 30 s for session tokens to be captured
        deadline = time.time() + 30
        while not captured and time.time() < deadline:
            time.sleep(0.5)

        if not captured:
            context.close()
            sys.exit(
                "ERROR: Could not capture IRIS VSS session tokens.\n"
                "The portal may have blocked the session. Try again."
            )

        cookies = context.cookies()
        context.close()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"])

    ctx = {
        "session_id":      captured["session_id"],
        "page_id":         captured["page_id"],
        "csrf_token":      captured["csrf_token"],
        "window_id":       str(uuid.uuid4()),
        "conversation_id": str(random.randint(10**18, 10**19 - 1)),
        "request_id":      0,
        "checksum":        {},
        "viewState":       {},
    }
    return session, ctx
```

- [ ] **Step 3: Run existing tests to confirm nothing broken**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 19 passed

- [ ] **Step 4: Commit**

```bash
git add ak/scraper.py
git commit -m "feat(ak): add make_session, _adv_headers, _update_ctx"
```

---

### Task 7: discover_solicitations() + fetch_detail() partial

**Files:**
- Modify: `ak/scraper.py`

No unit tests for these — they require network. Verified in Task 8 probe.

- [ ] **Step 1: Add `discover_solicitations()` to `ak/scraper.py`**

```python
def discover_solicitations(session: requests.Session, ctx: dict) -> list:
    """
    POST the search action to get open solicitations.
    Mutates ctx with the latest session_info, checksum, and viewState.
    Returns list of dicts with LIST_FIELDS keys.

    Alaska is low-volume; a single search page returns all open records.
    Prints a warning if rows_total > rows_per_page (pagination not implemented).
    """
    payload = {
        "action": {
            "key":                  "vss.page.VVSSX10019.gridView1.group1.cardSearch.searchActions.search",
            "actionCode":           "search",
            "actionType":           "searchAction",
            "applicationAction":    "search",
            "backgroundAction":     "userInitiated",
            "bypassPopupClose":     False,
            "customActionName":     None,
            "dataSource":           "T1SO_SRCH_QRY",
            "dsNameList":           "T1SO_SRCH_QRY",
            "hideActionButton":     False,
            "hotkey":               "SHIFT+E",
            "isCarouselNavigation": True,
            "isEntpriseSrchCreateAction": False,
            "isShiftKey":           False,
            "name":                 "search",
            "shouldIgnoreSysFeedback": False,
            "targetLocation":       "noDisplay",
            "viewName":             "gridView1",
        },
        "checksum": {
            "VIEW":    {"gridView1": _SEARCH_VIEW_CHECKSUM},
            "DS_DATA": {"T1SO_SRCH_QRY": "-1"},
        },
        "data": {
            "ds_query_data": {"T1SO_SRCH_QRY": {"SHOW_TXT": "3"}},
            "page_data": {},
        },
        "session_info": {
            "session_id": ctx["session_id"],
            "page_id":    ctx["page_id"],
            "csrf_token": ctx["csrf_token"],
        },
        "viewState": _SEARCH_VIEWSTATE,
    }

    headers = _adv_headers(ctx, "search", "searchAction")
    resp = session.post(BASE_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    _update_ctx(ctx, body)

    ds = body["data"]["ds_data"]["T1SO_SRCH_QRY"]
    rows_total = ds.get("rows_total", 0)
    rows_per_page = ds.get("rows_per_page", 20)
    if rows_total > rows_per_page:
        print(
            f"WARNING: {rows_total} open solicitations but only {rows_per_page} returned. "
            "Pagination not implemented — some records will be missed."
        )

    return [parse_list_row(r) for r in ds.get("row_data", [])]
```

- [ ] **Step 2: Add `fetch_detail()` (docTransition + instructions tab) to `ak/scraper.py`**

```python
def fetch_detail(session: requests.Session, search_ctx: dict, raw_row: dict) -> dict:
    """
    Fetch detail fields for one solicitation via 3 sequential API calls:
      1. docTransition  — navigate to solicitation document
      2. tabChange      — Solicitation Instructions (ADDL_INFO)
      3. tabChange      — Commodity Lines (commodity fields)

    raw_row is the original row dict from T1SO_SRCH_QRY.row_data (not parse_list_row output).
    search_ctx is used read-only; a local copy manages token rotation within this call.
    Returns dict with SCRAPED_FIELDS keys minus alaska_url and scrape_status.
    """
    ctx = dict(search_ctx)  # local copy — don't mutate caller's context
    ctx["request_id"] = 0   # fresh counter for this detail chain

    doc_ref_raw = raw_row.get("DOC_REF", "")
    column_value = parse_column_value(doc_ref_raw)

    # ── 1. docTransition ──────────────────────────────────────────────────────
    dt_payload = {
        "action": {
            "key": "vss.page.VVSSX10019.gridView1.group1.cardGrid.grid1.solNumTypCat.DOC_REF.DOC_REF_Detail",
            "actionType":           "transitionAction",
            "actionCode":           "docTransition",
            "columnValue":          column_value,
            "layoutName":           "stdNoNav_Hdr3_Main101",
            "dsNameList":           "T1SO_SRCH_QRY",
            "isCarouselNavigation": True,
        },
        "checksum": {
            "VIEW":       search_ctx.get("checksum", {}).get("VIEW", {}),
            "DS_DATA":    {"T1SO_SRCH_QRY": "-1"},
            "DATASOURCE": search_ctx.get("checksum", {}).get("DATASOURCE", {}),
        },
        "viewState": search_ctx.get("viewState", {}),
        "data": {
            "ds_data": {
                "T1SO_SRCH_QRY": {
                    "row_data": [{**raw_row, "ADV_ROW_SEL": True}],
                    "current_row_id": raw_row.get("ADV_ROW_ID", ""),
                }
            },
            "page_data": {},
        },
        "session_info": {
            "session_id": search_ctx["session_id"],
            "page_id":    search_ctx["page_id"],
            "csrf_token": search_ctx["csrf_token"],
        },
    }
    time.sleep(DELAY_SECONDS)
    dt_headers = _adv_headers(ctx, "docTransition", "transitionAction")
    dt_resp = session.post(BASE_URL, json=dt_payload, headers=dt_headers, timeout=30)
    dt_resp.raise_for_status()
    dt_body = dt_resp.json()
    _update_ctx(ctx, dt_body)

    # ── 2. tabChange → Solicitation Instructions ───────────────────────────────
    inst_payload = {
        "action": {
            "key":                  _INST_TAB_KEY,
            "actionCode":           "tabChange",
            "actionType":           "dsAction",
            "tabName":              "navSolicitation",
            "viewName":             "solicitationInstView",
            "isCarouselNavigation": False,
            "targetLocation":       "display",
        },
        "checksum":    ctx.get("checksum", {}),
        "viewState":   ctx.get("viewState", {}),
        "data":        {"page_data": {}, "ds_data": {}},
        "session_info": {
            "session_id": ctx["session_id"],
            "page_id":    ctx["page_id"],
            "csrf_token": ctx["csrf_token"],
        },
    }
    time.sleep(DELAY_SECONDS)
    inst_headers = _adv_headers(ctx, "tabChange", "dsAction")
    inst_resp = session.post(BASE_URL, json=inst_payload, headers=inst_headers, timeout=30)
    inst_resp.raise_for_status()
    inst_body = inst_resp.json()
    _update_ctx(ctx, inst_body)
    instructions = extract_instructions(inst_body)

    # ── 3. tabChange → Commodity Lines ────────────────────────────────────────
    comm_payload = {
        "action": {
            "key":                  _COMM_TAB_KEY,
            "actionCode":           "tabChange",
            "actionType":           "dsAction",
            "tabName":              "navCommodity",
            "viewName":             "commoditiesView",
            "isCarouselNavigation": False,
            "targetLocation":       "display",
        },
        "checksum":    ctx.get("checksum", {}),
        "viewState":   ctx.get("viewState", {}),
        "data":        {"page_data": {}, "ds_data": {}},
        "session_info": {
            "session_id": ctx["session_id"],
            "page_id":    ctx["page_id"],
            "csrf_token": ctx["csrf_token"],
        },
    }
    time.sleep(DELAY_SECONDS)
    comm_headers = _adv_headers(ctx, "tabChange", "dsAction")
    comm_resp = session.post(BASE_URL, json=comm_payload, headers=comm_headers, timeout=30)
    comm_resp.raise_for_status()
    comm_body = comm_resp.json()

    # Print raw commodity response during first probe run so we can verify field names
    # (remove this print after Task 9 is complete)
    print("\n=== RAW COMMODITY RESPONSE (verify field names for Task 9) ===")
    import json as _json
    comm_rows = (
        comm_body.get("data", {})
        .get("ds_data", {})
        .get("T3SO_DOC_COMMLN", {})
        .get("row_data", [])
    )
    print(_json.dumps(comm_rows[:2], indent=2))
    print("=== END RAW COMMODITY RESPONSE ===\n")

    commodity = extract_commodity_lines(comm_body)
    return {**instructions, **commodity}
```

- [ ] **Step 3: Add placeholder `extract_commodity_lines` so scraper.py imports cleanly**

```python
def extract_commodity_lines(response: dict) -> dict:
    """Extract commodity line fields. Field names verified in Task 8 probe."""
    rows = (
        response.get("data", {})
        .get("ds_data", {})
        .get("T3SO_DOC_COMMLN", {})
        .get("row_data", [])
    )
    descriptions, codes, specs = [], [], []
    for row in rows:
        # Field names confirmed from probe output in Task 8.
        # Update ITEM_DSCR/COMM_CD/ITEM_SPEC_DSCR if actual names differ.
        descriptions.append(row.get("ITEM_DSCR", ""))
        codes.append(row.get("COMM_CD", ""))
        specs.append(row.get("ITEM_SPEC_DSCR", ""))
    return {
        "commodity_descriptions": "|".join(d for d in descriptions if d),
        "commodity_codes":        "|".join(c for c in codes if c),
        "commodity_specs":        "|".join(s for s in specs if s),
    }
```

- [ ] **Step 4: Run existing tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 19 passed

- [ ] **Step 5: Commit**

```bash
git add ak/scraper.py
git commit -m "feat(ak): add discover_solicitations and fetch_detail skeleton"
```

---

### Task 8: probe() — first working version

**Files:**
- Modify: `ak/scraper.py`

- [ ] **Step 1: Add `probe()` to `ak/scraper.py`**

```python
def probe():
    session, ctx = make_session()
    print("Discovering open solicitations...")
    rows = discover_solicitations(session, ctx)
    done_ids = load_done_ids(OUTPUT_PATH)

    # Keep raw_rows for fetch_detail (needs ADV_ROW_ID and original field names)
    # Rebuild by running a fresh search — rows from discover_solicitations are parsed.
    # We need the raw row too, so restructure discover_solicitations to return both.
    # TEMPORARY: re-fetch raw rows from the search response saved in ctx.
    # (We'll clean this up after verifying the commodity response in Task 9.)
    print(f"Found {len(rows)} open solicitations.")

    new_rows = [r for r in rows if r["doc_ref"] not in done_ids]
    if not new_rows:
        print("No new solicitations to probe.")
        return

    # Pick first new solicitation
    target = new_rows[0]
    print(f"\nProbing: {target['doc_ref']} — {target['description']}")

    # Re-run search to get the raw T1SO_SRCH_QRY row (needed for docTransition payload)
    # This is a second search call; see note in run() which avoids this by saving raw rows.
    session2, ctx2 = make_session()
    import json as _json

    # Make raw search to get the raw row data
    raw_rows = _raw_search(session2, ctx2)
    raw_row = next(
        (r for r in raw_rows if parse_doc_ref(r.get("DOC_REF", "")) == target["doc_ref"]),
        None
    )
    if not raw_row:
        print(f"ERROR: Could not find raw row for {target['doc_ref']}")
        return

    try:
        detail = fetch_detail(session2, ctx2, raw_row)
    except Exception as e:
        print(f"ERROR fetching detail: {e}")
        return

    print("\n=== List Fields ===")
    for k, v in target.items():
        print(f"  {k}: {v}")
    print("\n=== Detail Fields ===")
    for k, v in detail.items():
        print(f"  {k}: {v[:200] if isinstance(v, str) and len(v) > 200 else v}")
```

Note: `probe()` currently calls `make_session()` twice because `discover_solicitations` and `fetch_detail` share the same session context and the search must be run before the detail fetch. Simplify this in Task 10 when `run()` is implemented to avoid the duplication.

- [ ] **Step 2: Add `_raw_search()` helper to support probe**

This avoids re-implementing the search payload. Add before `discover_solicitations`:

```python
def _raw_search(session: requests.Session, ctx: dict) -> list:
    """Like discover_solicitations but returns raw T1SO_SRCH_QRY row_data dicts."""
    payload = {
        "action": {
            "key":                  "vss.page.VVSSX10019.gridView1.group1.cardSearch.searchActions.search",
            "actionCode":           "search",
            "actionType":           "searchAction",
            "applicationAction":    "search",
            "backgroundAction":     "userInitiated",
            "bypassPopupClose":     False,
            "customActionName":     None,
            "dataSource":           "T1SO_SRCH_QRY",
            "dsNameList":           "T1SO_SRCH_QRY",
            "hideActionButton":     False,
            "hotkey":               "SHIFT+E",
            "isCarouselNavigation": True,
            "isEntpriseSrchCreateAction": False,
            "isShiftKey":           False,
            "name":                 "search",
            "shouldIgnoreSysFeedback": False,
            "targetLocation":       "noDisplay",
            "viewName":             "gridView1",
        },
        "checksum": {
            "VIEW":    {"gridView1": _SEARCH_VIEW_CHECKSUM},
            "DS_DATA": {"T1SO_SRCH_QRY": "-1"},
        },
        "data": {
            "ds_query_data": {"T1SO_SRCH_QRY": {"SHOW_TXT": "3"}},
            "page_data": {},
        },
        "session_info": {
            "session_id": ctx["session_id"],
            "page_id":    ctx["page_id"],
            "csrf_token": ctx["csrf_token"],
        },
        "viewState": _SEARCH_VIEWSTATE,
    }
    headers = _adv_headers(ctx, "search", "searchAction")
    resp = session.post(BASE_URL, json=payload, headers=headers, timeout=30)
    resp.raise_for_status()
    body = resp.json()
    _update_ctx(ctx, body)
    return body["data"]["ds_data"]["T1SO_SRCH_QRY"].get("row_data", [])
```

Then simplify `discover_solicitations` to call `_raw_search` and apply `parse_list_row`:

```python
def discover_solicitations(session: requests.Session, ctx: dict) -> list:
    """Returns list of dicts with LIST_FIELDS keys. Mutates ctx."""
    raw_rows = _raw_search(session, ctx)
    ds_meta = {}  # rows_total for warning — re-fetch if needed
    return [parse_list_row(r) for r in raw_rows]
```

And update `_raw_search` to also check rows_total:

Immediately after `_update_ctx(ctx, body)` in `_raw_search`, add:

```python
    ds = body["data"]["ds_data"]["T1SO_SRCH_QRY"]
    if ds.get("rows_total", 0) > ds.get("rows_per_page", 20):
        print(
            f"WARNING: {ds['rows_total']} open solicitations, "
            f"only {ds['rows_per_page']} returned. Pagination not implemented."
        )
    return ds.get("row_data", [])
```

- [ ] **Step 3: Add `__main__` block to `ak/scraper.py`**

```python
if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
```

- [ ] **Step 4: Run probe — read the commodity raw output carefully**

```bash
cd /Users/ml3787/Desktop/state-local/ak
/Users/ml3787/Desktop/state-local/venv/bin/python scraper.py probe
```

Expected: Chrome opens, warms up, navigates to portal, returns to terminal and prints list + detail fields. The commodity tab prints raw JSON rows — **note the actual field names** for use in Task 9.

If `navCommodity` tab name is wrong, the commodity API call will fail with a 4xx or return empty `row_data`. Capture the actual response and look for the correct tab name in the Network tab (filter by Advantage4, click the commodity lines tab, check Request Headers for `Adv-Action-Code`/payload for `tabName`).

- [ ] **Step 5: Commit**

```bash
git add ak/scraper.py
git commit -m "feat(ak): add probe command with raw commodity output"
```

---

### Task 9: extract_commodity_lines — TDD with confirmed field names

**Files:**
- Create: `ak/tests/fixtures/sample_commodity_response.json`
- Modify: `ak/scraper.py`
- Modify: `ak/tests/test_scraper.py`

Run this task AFTER Task 8 probe has printed the raw commodity JSON.

- [ ] **Step 1: Create `ak/tests/fixtures/sample_commodity_response.json`**

Build this fixture from the raw JSON printed by probe. It should look like:

```json
{
  "data": {
    "ds_data": {
      "T3SO_DOC_COMMLN": {
        "row_data": [
          {
            "ADV_ROW_ID": "<from probe output>",
            "<desc_field>": "400Hz Output Solid-State GPU",
            "<code_field>": "03523",
            "<spec_field>": "Airport Equipment Ground Power for Aircraft at the Gates"
          }
        ]
      }
    }
  }
}
```

Replace `<desc_field>`, `<code_field>`, `<spec_field>` with actual field names from probe output. Trim all other fields not needed for extraction.

- [ ] **Step 2: Update `extract_commodity_lines` field names based on probe output**

If probe output showed field names differ from `ITEM_DSCR`/`COMM_CD`/`ITEM_SPEC_DSCR`, update the function in `ak/scraper.py`:

```python
def extract_commodity_lines(response: dict) -> dict:
    rows = (
        response.get("data", {})
        .get("ds_data", {})
        .get("T3SO_DOC_COMMLN", {})
        .get("row_data", [])
    )
    descriptions, codes, specs = [], [], []
    for row in rows:
        descriptions.append(row.get("<desc_field>", ""))  # replace with actual
        codes.append(row.get("<code_field>", ""))          # replace with actual
        specs.append(row.get("<spec_field>", ""))          # replace with actual
    return {
        "commodity_descriptions": "|".join(d for d in descriptions if d),
        "commodity_codes":        "|".join(c for c in codes if c),
        "commodity_specs":        "|".join(s for s in specs if s),
    }
```

- [ ] **Step 3: Write tests**

Add to `ak/tests/test_scraper.py`:

```python
class TestExtractCommodityLines:
    def setup_method(self):
        with open(FIXTURES / "sample_commodity_response.json") as f:
            self.resp = json.load(f)

    def test_extracts_commodity_description(self):
        result = scraper.extract_commodity_lines(self.resp)
        assert "400Hz Output Solid-State GPU" in result["commodity_descriptions"]

    def test_extracts_commodity_code(self):
        result = scraper.extract_commodity_lines(self.resp)
        assert "03523" in result["commodity_codes"]

    def test_extracts_specifications(self):
        result = scraper.extract_commodity_lines(self.resp)
        assert "Airport Equipment Ground Power" in result["commodity_specs"]

    def test_pipe_delimited_multiple_lines(self):
        resp = {"data": {"ds_data": {"T3SO_DOC_COMMLN": {"row_data": [
            {"<desc_field>": "Item A", "<code_field>": "001", "<spec_field>": "Spec A"},
            {"<desc_field>": "Item B", "<code_field>": "002", "<spec_field>": "Spec B"},
        ]}}}}
        result = scraper.extract_commodity_lines(resp)
        assert result["commodity_descriptions"] == "Item A|Item B"
        assert result["commodity_codes"] == "001|002"

    def test_empty_when_no_rows(self):
        resp = {"data": {"ds_data": {"T3SO_DOC_COMMLN": {"row_data": []}}}}
        result = scraper.extract_commodity_lines(resp)
        assert result["commodity_descriptions"] == ""
        assert result["commodity_codes"] == ""
        assert result["commodity_specs"] == ""
```

Replace `<desc_field>`, `<code_field>`, `<spec_field>` with actual field names.

- [ ] **Step 4: Run tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 24 passed (all prior tests + 5 new)

- [ ] **Step 5: Remove the debug print from `fetch_detail`**

In `ak/scraper.py`, find and delete the `=== RAW COMMODITY RESPONSE ===` print block (the one added in Task 7 Step 2).

- [ ] **Step 6: Commit**

```bash
git add ak/scraper.py ak/tests/test_scraper.py ak/tests/fixtures/sample_commodity_response.json
git commit -m "feat(ak): implement extract_commodity_lines with confirmed field names"
```

---

### Task 10: run() + end-to-end

**Files:**
- Modify: `ak/scraper.py`

- [ ] **Step 1: Add `run()` to `ak/scraper.py`**

```python
def run():
    session, ctx = make_session()
    print("Discovering open solicitations...")
    raw_rows = _raw_search(session, ctx)
    done_ids = load_done_ids(OUTPUT_PATH)

    to_scrape = [r for r in raw_rows if parse_doc_ref(r.get("DOC_REF", "")) not in done_ids]
    total_new = len(to_scrape)
    print(
        f"Open: {len(raw_rows)}. Already done: {len(done_ids)}. To scrape: {total_new}"
    )

    if total_new == 0:
        print("Nothing to do.")
        return

    enriched = []
    if Path(OUTPUT_PATH).exists():
        all_rows = pd.read_csv(OUTPUT_PATH, dtype=str).to_dict("records")
        enriched = [r for r in all_rows if r.get("scrape_status") == "success"]

    success_count = 0
    error_count = 0

    for i, raw_row in enumerate(to_scrape, 1):
        doc_ref = parse_doc_ref(raw_row.get("DOC_REF", ""))
        list_fields = parse_list_row(raw_row)
        # Construct detail URL from DOC_REF components
        col_val = parse_column_value(raw_row.get("DOC_REF", ""))
        parts = col_val.split(",")  # ['RFQ', '09', '260000015', '2']
        alaska_url = (
            f"https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4"
            f"?action=docTransition&columnValue={col_val}"
        ) if len(parts) == 4 else ""

        print(f"[{i}/{total_new}] {doc_ref}")
        try:
            detail = fetch_detail(session, ctx, raw_row)
            detail["alaska_url"] = alaska_url
            detail["scrape_status"] = "success"
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            detail = EMPTY_SCRAPED.copy()
            detail["alaska_url"] = alaska_url
            detail["scrape_status"] = "error"
            error_count += 1

        enriched.append({**list_fields, **detail})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(
        f"\nDone. {success_count} succeeded, {error_count} errored. "
        f"Output: {OUTPUT_PATH}"
    )
```

Note on `alaska_url`: the portal URL for a solicitation is not a simple deep link (it's a stateful SPA). The `alaska_url` field records a reference string so the record can be identified; the true entry point is the search page.

- [ ] **Step 2: Simplify `probe()` to use the single session pattern**

Replace `probe()` with this cleaner version that avoids the double `make_session()` call:

```python
def probe():
    session, ctx = make_session()
    print("Discovering open solicitations...")
    raw_rows = _raw_search(session, ctx)
    done_ids = load_done_ids(OUTPUT_PATH)

    new_raw = [
        r for r in raw_rows
        if parse_doc_ref(r.get("DOC_REF", "")) not in done_ids
    ]
    if not new_raw:
        print("No new open solicitations to probe.")
        return

    raw_row = new_raw[0]
    doc_ref = parse_doc_ref(raw_row.get("DOC_REF", ""))
    print(f"\nProbing: {doc_ref} — {raw_row.get('DOC_DSCR', '')}")

    try:
        detail = fetch_detail(session, ctx, raw_row)
    except Exception as e:
        sys.exit(f"ERROR fetching detail: {e}")

    list_fields = parse_list_row(raw_row)
    print("\n=== List Fields ===")
    for k, v in list_fields.items():
        print(f"  {k}: {v}")
    print("\n=== Detail Fields ===")
    for k, v in detail.items():
        val = v[:300] + "..." if isinstance(v, str) and len(v) > 300 else v
        print(f"  {k}: {val}")
```

- [ ] **Step 3: Run existing tests — expect pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: 24 passed

- [ ] **Step 4: Run probe end-to-end**

```bash
cd /Users/ml3787/Desktop/state-local/ak
/Users/ml3787/Desktop/state-local/venv/bin/python scraper.py probe
```

Expected: Chrome opens, warms up, portal loads, prints list and detail fields cleanly with `additional_instructions` and commodity fields populated.

- [ ] **Step 5: Run run end-to-end**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python scraper.py run
```

Expected: Chrome opens once, finds 1 open solicitation, fetches detail, writes `solicitations_enriched.csv` with `scrape_status = success`.

- [ ] **Step 6: Verify output CSV**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -c "
import pandas as pd
df = pd.read_csv('solicitations_enriched.csv')
print(df.columns.tolist())
print(df[['doc_ref','scrape_status','additional_instructions']].to_string())
"
```

Expected: 18 columns, 1 row, `scrape_status = success`, `additional_instructions` non-empty.

- [ ] **Step 7: Commit**

```bash
git add ak/scraper.py
git commit -m "feat(ak): implement run() and clean up probe()"
```

---

### Task 11: HANDOFF.md update

**Files:**
- Modify: `HANDOFF.md`

- [ ] **Step 1: Add Alaska section to `HANDOFF.md`**

In `HANDOFF.md`, add Alaska to the State Status table:

```markdown
| Alaska | ✅ Complete | `ak/` | IRIS VSS (CGI Advantage 4) | No export — list scraped directly | `solicitations_enriched.csv` (18 cols) |
```

- [ ] **Step 2: Add Alaska section after Alabama**

```markdown
## Alaska (IRIS VSS)

**Portal:** https://iris-vss.alaska.gov

**How it works:** CGI Advantage 4 portal with DataDome bot protection. All data comes from the `Advantage4` JSON API via POST. The scraper uses patchright to navigate the portal and intercept an API response to capture session tokens (`Adv-Session-Id`, `page_id`, `csrf_token`), then uses `requests` for all data calls. Per-solicitation detail requires 3 API calls: `docTransition` to navigate to the document, then two `tabChange` calls for Solicitation Instructions (`ADDL_INFO`) and Commodity Lines (`T3SO_DOC_COMMLN`). Session tokens rotate with every response.

**Run:**
```bash
cd ak
source ../venv/bin/activate
# Chrome must be closed when running (profile lock)
python scraper.py probe
python scraper.py run
```

**Key technical notes:**
- DataDome requires non-headless Chrome via patchright + persistent profile at `~/.ak_scraper_profile`
- No manual export step — the scraper discovers all open solicitations itself
- `alaska_url` is a reference string, not a deep link (portal is a stateful SPA)
- Alaska is low-volume (~1–20 open solicitations); pagination not implemented

**Known gaps:** DB normalization
```

- [ ] **Step 3: Commit**

```bash
git add HANDOFF.md
git commit -m "docs: add Alaska to HANDOFF.md"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Covered in task |
|---|---|
| patchright + persistent profile + DataDome warmup | Task 6 |
| `make_session()` returns session + ctx | Task 6 |
| `discover_solicitations()` search POST + SHOW_TXT:"3" | Task 7 |
| `parse_list_row()` all 12 list fields | Task 4 |
| `parse_doc_ref()` + `parse_column_value()` | Task 2 |
| `ms_to_iso()` timestamp conversion | Task 2 |
| `fetch_detail()` — docTransition payload with columnValue | Task 7 |
| `fetch_detail()` — tabChange navSolicitation → ADDL_INFO | Task 7 |
| `fetch_detail()` — tabChange commodity lines | Task 7 |
| `extract_instructions()` from T1SO_DOC_HDR | Task 5 |
| `extract_commodity_lines()` pipe-delimited | Task 9 |
| `load_done_ids()` resume safety | Task 3 |
| `probe` command | Task 8 |
| `run` command | Task 10 |
| DELAY_SECONDS = 0.5 | Task 1 (constant) |
| Output written after each record | Task 10 |
| HANDOFF.md updated | Task 11 |

**Placeholder scan:** Task 9 uses `<desc_field>` etc. — these are intentional blanks to fill from Task 8 probe output, not TBDs. All other steps have complete code.

**Type consistency:** `ctx` dict used consistently across `_adv_headers`, `_update_ctx`, `make_session`, `_raw_search`, `discover_solicitations`, `fetch_detail`. `raw_row` (original API dict) vs `list_fields` (parsed dict) are distinct throughout.
