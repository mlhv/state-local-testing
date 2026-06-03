# Arizona Procurement Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `az/scraper.py` to scrape open solicitations from Arizona's Ivalua procurement portal (`app.az.gov`), producing `az/solicitations_enriched.csv` with 21 columns.

**Architecture:** Direct port of `al/scraper.py`. Three Arizona-specific changes: different URLs, `hdnUserValue: ,body_x_selStatusCode_1` for server-side "Open for Bidding" filter, and `input()` pause for manual reCAPTCHA v2 instead of URL-change detection. All HTML parsing logic is identical — same Ivalua `data-iv-role` structure.

**Tech Stack:** Python 3, patchright (reCAPTCHA bypass), requests, BeautifulSoup4, pandas. All already in the shared venv.

**Run all tests:** `/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/ -v`

**Run from:** always `cd az` first — OUTPUT_PATH and input CSV globs are relative.

---

### Task 1: Scaffold, `load_done_ids`, and requirements

**Files:**
- Create: `az/requirements.txt`
- Create: `az/tests/__init__.py`
- Create: `az/scraper.py` (constants + `load_done_ids` only)
- Create: `az/tests/test_scraper.py` (`load_done_ids` tests only)

- [ ] **Step 1: Create `az/requirements.txt`**

```
requests
pandas
beautifulsoup4
patchright
responses
```

- [ ] **Step 2: Create `az/tests/__init__.py`**

Empty file. Just `touch az/tests/__init__.py`.

- [ ] **Step 3: Write failing `load_done_ids` tests**

Create `az/tests/test_scraper.py`:

```python
import pandas as pd
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import scraper

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_load_done_ids_missing_file(tmp_path):
    assert scraper.load_done_ids(str(tmp_path / "nonexistent.csv")) == set()


def test_load_done_ids_returns_successes_only(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([
        {"src_code": "BPM007579", "scrape_status": "success"},
        {"src_code": "BPM007580", "scrape_status": "error"},
        {"src_code": "BPM007581", "scrape_status": "success"},
    ]).to_csv(csv, index=False)
    result = scraper.load_done_ids(str(csv))
    assert result == {"BPM007579", "BPM007581"}


def test_load_done_ids_missing_columns(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([{"foo": "bar"}]).to_csv(csv, index=False)
    assert scraper.load_done_ids(str(csv)) == set()
```

- [ ] **Step 4: Create stub `az/scraper.py`** with only enough to make the tests importable

```python
"""
Arizona Procurement Portal public solicitations scraper.
Usage:
  python scraper.py probe   -- discover list, pick first open record, print all fields
  python scraper.py run     -- discover list, enrich all new open records, write CSV
"""

import sys
import time
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup

OUTPUT_PATH = "solicitations_enriched.csv"
DELAY_SECONDS = 0.5
BASE_URL = "https://app.az.gov"
BROWSE_URL = "https://app.az.gov/page.aspx/en/rfp/request_browse_public"
AJAX_URL = (
    "https://app.az.gov/ajax.aspx/en/rfp/request_browse_public"
    "?ivControlUIDsAsync=body:x:grid:upgrid"
    "&asyncmodulename=rfp"
    "&asyncpagename=request_browse_public"
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
USER_DATA_DIR = Path.home() / ".az_scraper_profile"

LIST_FIELDS = [
    "src_code",
    "solicitation_label",
    "commodity",
    "buying_agency",
    "status",
    "rfx_awarded",
    "begin_date",
    "end_date",
    "detail_href",
]

SCRAPED_FIELDS = [
    "lot_number",
    "round_number",
    "fiscal_year",
    "rfx_type",
    "procurement_officer",
    "procurement_officer_email",
    "procurement_officer_phone",
    "discussion_forum_cutoff",
    "commodity_full",
    "summary",
    "arizona_url",
    "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}


def load_done_ids(output_path):
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "src_code" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "src_code"].astype(str))
```

- [ ] **Step 5: Run tests — expect 3 PASS**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/test_scraper.py -v
```

Expected:
```
PASSED test_load_done_ids_missing_file
PASSED test_load_done_ids_returns_successes_only
PASSED test_load_done_ids_missing_columns
3 passed
```

- [ ] **Step 6: Commit**

```bash
git add az/requirements.txt az/tests/__init__.py az/scraper.py az/tests/test_scraper.py
git commit -m "feat(az): scaffold scraper with load_done_ids"
```

---

### Task 2: List page fixture and `parse_list_page`

**Files:**
- Create: `az/tests/fixtures/sample_list_page.html`
- Modify: `az/tests/test_scraper.py` (add 4 parse tests)
- Modify: `az/scraper.py` (add `_CELL_MAP`, `_parse_total_pages`, `parse_list_page`)

- [ ] **Step 1: Create list fixture**

Create `az/tests/fixtures/sample_list_page.html`:

```html
<!DOCTYPE html>
<html>
<body>
<div id="body_x_grid_upgrid">
  <table>
    <thead>
      <tr>
        <th>Editing column</th>
        <th>Code</th>
        <th>Label</th>
        <th>Commodity</th>
        <th>Agency</th>
        <th>Status</th>
        <th>RFx Awarded</th>
        <th>Begin (UTC-7)</th>
        <th>End (UTC-7)</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><a href="/bpm/process_manage_extranet/13695"></a></td>
        <td>BPM007579</td>
        <td>ADOT Flagstaff Service Center Re-Roof</td>
        <td>Building and Facility Construction and Maintenance Services</td>
        <td>Department of Transportation</td>
        <td>Open for Bidding</td>
        <td></td>
        <td>08/05/2026 00:00:00</td>
        <td>03/06/2026 15:00:00</td>
      </tr>
      <tr>
        <td><a href="/bpm/process_manage_extranet/10000"></a></td>
        <td>BPM006000</td>
        <td>Old Awarded Bid</td>
        <td>Office Supplies</td>
        <td>Arizona Department of Administration</td>
        <td>Awarded</td>
        <td></td>
        <td>01/01/2026 00:00:00</td>
        <td>01/01/2026 17:00:00</td>
      </tr>
    </tbody>
  </table>
  <button id="body_x_grid_gridPagerBtn0Page">1</button>
  <button id="body_x_grid_gridPagerBtn1Page">2</button>
</div>
</body>
</html>
```

- [ ] **Step 2: Add failing parse tests to `az/tests/test_scraper.py`**

Append these 4 tests to the existing file (after the `load_done_ids` tests):

```python
def test_parse_list_page_row_count():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, _ = scraper.parse_list_page(html)
    assert len(rows) == 2


def test_parse_list_page_open_row_fields():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, _ = scraper.parse_list_page(html)
    row = next(r for r in rows if r["src_code"] == "BPM007579")
    assert row["solicitation_label"] == "ADOT Flagstaff Service Center Re-Roof"
    assert row["commodity"] == "Building and Facility Construction and Maintenance Services"
    assert row["buying_agency"] == "Department of Transportation"
    assert row["status"] == "Open for Bidding"
    assert row["begin_date"] == "08/05/2026 00:00:00"
    assert row["end_date"] == "03/06/2026 15:00:00"
    assert "13695" in row["detail_href"]


def test_parse_list_page_total_pages():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    _, total_pages = scraper.parse_list_page(html)
    assert total_pages == 2


def test_parse_list_page_empty_table():
    html = "<html><body><div id='body_x_grid_upgrid'><table><tbody></tbody></table></div></body></html>"
    rows, total_pages = scraper.parse_list_page(html)
    assert rows == []
    assert total_pages == 1
```

- [ ] **Step 3: Run tests — expect 4 FAIL (parse tests), 3 PASS (load_done_ids)**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/test_scraper.py -v
```

Expected: `AttributeError: module 'scraper' has no attribute 'parse_list_page'`

- [ ] **Step 4: Add `_CELL_MAP`, `_parse_total_pages`, `parse_list_page` to `az/scraper.py`**

Append to `az/scraper.py` (after `EMPTY_SCRAPED` and `load_done_ids`):

```python
# Cell index → field key for Arizona's 9-column grid.
# 0  Editing column (icon link) → detail_href (href only)
# 1  Code            → src_code
# 2  Label           → solicitation_label
# 3  Commodity       → commodity
# 4  Agency          → buying_agency
# 5  Status          → status
# 6  RFx Awarded     → rfx_awarded
# 7  Begin (UTC-7)   → begin_date
# 8  End (UTC-7)     → end_date
_CELL_MAP = [
    (1, "src_code"),
    (2, "solicitation_label"),
    (3, "commodity"),
    (4, "buying_agency"),
    (5, "status"),
    (6, "rfx_awarded"),
    (7, "begin_date"),
    (8, "end_date"),
]


def _parse_total_pages(soup):
    """Return total page count from the pager widget, defaulting to 1."""
    max_page = 1
    for el in soup.find_all(id=lambda x: x and "gridPagerBtn" in x and "Page" in x):
        try:
            n = int(el.get_text(strip=True))
            if n > max_page:
                max_page = n
        except ValueError:
            pass
    return max_page


def parse_list_page(html):
    """
    Parse one page of the solicitations list.
    Returns (rows, total_pages).

    Arizona's Ivalua grid has 9 columns. Cell 0 is the editing-column icon
    anchor whose href is the detail page URL. See _CELL_MAP for the full mapping.
    """
    soup = BeautifulSoup(html, "html.parser")
    total_pages = _parse_total_pages(soup)

    grid_div = soup.find(id="body_x_grid_upgrid") or soup.find("div", class_="iv-grid")
    container = grid_div if grid_div else soup
    table = container.find("table", class_="iv-grid-view") or container.find("table")
    if not table:
        return [], total_pages

    tbody = table.find("tbody") or table
    _MIN_CELLS = max(idx for idx, _ in _CELL_MAP) + 1

    rows = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < _MIN_CELLS:
            continue
        row = {}
        for cell_idx, key in _CELL_MAP:
            row[key] = (
                cells[cell_idx]
                .get_text(separator=" ", strip=True)
                .replace("\xa0", " ")
                .strip()
            )
        anchor = cells[0].find("a", href=True)
        row["detail_href"] = anchor["href"] if anchor else ""
        rows.append(row)

    return rows, total_pages
```

- [ ] **Step 5: Run tests — expect 7 PASS**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/test_scraper.py -v
```

Expected:
```
PASSED test_load_done_ids_missing_file
PASSED test_load_done_ids_returns_successes_only
PASSED test_load_done_ids_missing_columns
PASSED test_parse_list_page_row_count
PASSED test_parse_list_page_open_row_fields
PASSED test_parse_list_page_total_pages
PASSED test_parse_list_page_empty_table
7 passed
```

- [ ] **Step 6: Commit**

```bash
git add az/tests/fixtures/sample_list_page.html az/tests/test_scraper.py az/scraper.py
git commit -m "feat(az): add parse_list_page with Arizona column mapping"
```

---

### Task 3: Detail fixture and `extract_fields`

**Files:**
- Create: `az/tests/fixtures/sample_detail_page.html`
- Modify: `az/tests/test_scraper.py` (add 4 extract tests)
- Modify: `az/scraper.py` (add `_label_value`, `extract_fields`)

- [ ] **Step 1: Create detail fixture**

Create `az/tests/fixtures/sample_detail_page.html`:

```html
<!DOCTYPE html>
<html>
<body>
<div id="body_x_tabc_rfp_ext_prxrfp_ext_x">

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Lot #</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">1</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Round #</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">4</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Fiscal Year</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control"></span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">RFx types</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">IFB</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Procurement Officer</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">Monica Rodriguez</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Procurement Officer Email</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">mrodriguez8@azdot.gov</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Procurement Officer Phone</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">6027122089</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Discussion Forum Cut Off</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control"></span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Commodity</span></h3>
    <div data-iv-role="controlWrapper">
      <span class="readonly" data-iv-role="control">72000000 - Building and Facility Construction and Maintenance Services</span>
    </div>
  </div>

  <div data-iv-role="field">
    <h3><span class="label-field" data-iv-role="label">Summary</span></h3>
    <div data-iv-role="controlWrapper">
      <div class="readonly" data-iv-role="control">
        <p>Pursuant to the Arizona Procurement Code, A.R.S. §41-2501 et seq., the State of Arizona Department of Transportation (ADOT), has a requirement for the re-roofing renovation of the Flagstaff Service Center.</p>
      </div>
    </div>
  </div>

</div>
</body>
</html>
```

- [ ] **Step 2: Add failing extract tests to `az/tests/test_scraper.py`**

Append these 4 tests:

```python
def test_label_value_ivalua_field_control():
    html = (FIXTURE_DIR / "sample_detail_page.html").read_text()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    assert scraper._label_value(soup, "Round #") == "4"
    assert scraper._label_value(soup, "Procurement Officer") == "Monica Rodriguez"


def test_label_value_missing_returns_empty():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert scraper._label_value(soup, "Nonexistent Field") == ""


def test_extract_fields_all_fields():
    html = (FIXTURE_DIR / "sample_detail_page.html").read_text()
    fields = scraper.extract_fields(html)
    assert fields["lot_number"] == "1"
    assert fields["round_number"] == "4"
    assert fields["fiscal_year"] == ""
    assert fields["rfx_type"] == "IFB"
    assert fields["procurement_officer"] == "Monica Rodriguez"
    assert fields["procurement_officer_email"] == "mrodriguez8@azdot.gov"
    assert fields["procurement_officer_phone"] == "6027122089"
    assert fields["discussion_forum_cutoff"] == ""
    assert fields["commodity_full"] == "72000000 - Building and Facility Construction and Maintenance Services"
    assert "Arizona Procurement Code" in fields["summary"]


def test_extract_fields_missing_returns_empty():
    fields = scraper.extract_fields("<html><body></body></html>")
    for key in [
        "lot_number", "round_number", "fiscal_year", "rfx_type",
        "procurement_officer", "procurement_officer_email",
        "procurement_officer_phone", "discussion_forum_cutoff",
        "commodity_full", "summary",
    ]:
        assert fields[key] == ""
```

- [ ] **Step 3: Run tests — expect 4 FAIL (extract tests), 7 PASS**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/test_scraper.py -v
```

Expected: `AttributeError: module 'scraper' has no attribute '_label_value'`

- [ ] **Step 4: Add `_label_value` and `extract_fields` to `az/scraper.py`**

Append to `az/scraper.py` (after `parse_list_page`):

```python
def _label_value(soup, label_text):
    """
    Find the value associated with a labelled field on an Ivalua detail page.

    Primary path: data-iv-role="field" containing a data-iv-role="label" span
    with label_text, then finds the data-iv-role="control" element inside it.

    Falls back through legacy structures for fixture compatibility.
    """
    for el in soup.find_all(string=lambda t: t and t.strip() == label_text):
        label_el = el.parent

        # Primary: Ivalua field/controlWrapper pattern
        field_div = label_el
        while field_div and field_div.get("data-iv-role") != "field":
            field_div = field_div.parent if field_div.parent else None
        if field_div:
            ctrl = field_div.find(attrs={"data-iv-role": "control"})
            if ctrl:
                return ctrl.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()

        # Legacy fallbacks
        raw = label_el.next_sibling
        if raw and isinstance(raw, str) and raw.strip():
            return raw.strip().replace("\xa0", " ").strip()
        tag_sibling = label_el.find_next_sibling()
        if tag_sibling:
            return tag_sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
        grandparent_sibling = (
            label_el.parent.find_next_sibling() if label_el.parent else None
        )
        if grandparent_sibling:
            return grandparent_sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
    return ""


def extract_fields(html):
    """Parse Solicitation General Information from an Arizona detail page."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        "lot_number":                _label_value(soup, "Lot #"),
        "round_number":              _label_value(soup, "Round #"),
        "fiscal_year":               _label_value(soup, "Fiscal Year"),
        "rfx_type":                  _label_value(soup, "RFx types"),
        "procurement_officer":       _label_value(soup, "Procurement Officer"),
        "procurement_officer_email": _label_value(soup, "Procurement Officer Email"),
        "procurement_officer_phone": _label_value(soup, "Procurement Officer Phone"),
        "discussion_forum_cutoff":   _label_value(soup, "Discussion Forum Cut Off"),
        "commodity_full":            _label_value(soup, "Commodity"),
        "summary":                   _label_value(soup, "Summary"),
    }
```

- [ ] **Step 5: Run tests — expect 11 PASS**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/test_scraper.py -v
```

Expected:
```
PASSED test_load_done_ids_missing_file
PASSED test_load_done_ids_returns_successes_only
PASSED test_load_done_ids_missing_columns
PASSED test_parse_list_page_row_count
PASSED test_parse_list_page_open_row_fields
PASSED test_parse_list_page_total_pages
PASSED test_parse_list_page_empty_table
PASSED test_label_value_ivalua_field_control
PASSED test_label_value_missing_returns_empty
PASSED test_extract_fields_all_fields
PASSED test_extract_fields_missing_returns_empty
11 passed
```

- [ ] **Step 6: Commit**

```bash
git add az/tests/fixtures/sample_detail_page.html az/tests/test_scraper.py az/scraper.py
git commit -m "feat(az): add _label_value and extract_fields with detail fixture"
```

---

### Task 4: Session, discovery, `probe`, and `run`

**Files:**
- Modify: `az/scraper.py` (add `make_session`, payload constants, `discover_solicitations`, `probe`, `run`, `__main__`)

No unit tests for this task — `make_session` and `discover_solicitations` require the live portal. Verified via `python scraper.py probe`.

- [ ] **Step 1: Append the remaining implementation to `az/scraper.py`**

Append to `az/scraper.py` (after `extract_fields`):

```python
_BASE_PAYLOAD = {
    "__EVENTTARGET": "body_x_grid_grd",
    "__LASTFOCUS": "",
    "REQUEST_METHOD": "POST",
    # Server-side "Open for Bidding" filter — keeps closed/awarded records off the list.
    "hdnUserValue": ",body_x_selStatusCode_1",
    "x_headaction": "",
    "x_headloginName": "",
    "hdnMandatory": "0",
    "hdnWflAction": "",
    "body:_ctl0": "",
    "body:x:txtQuery": "",
    "body:x:selFamily": "",
    "body_x_selFamily_text": "",
    "header:x:prxHeaderLogInfo:x:ContrastModal:chkContrastTheme_radio": "true",
    "header:x:prxHeaderLogInfo:x:ContrastModal:chkContrastTheme": "True",
    "header:x:prxHeaderLogInfo:x:ContrastModal:chkPassiveNotification": "0",
    "proxyActionBar:x:txtWflRefuseMessage": "",
}


def _pagination_payload(page_n):
    payload = dict(_BASE_PAYLOAD)
    payload["__EVENTARGUMENT"] = f"Page|{page_n}"
    payload["__LASTFOCUS"] = f"body_x_grid_gridPagerBtn{page_n}Page"
    return payload


def make_session():
    """
    Return a requests.Session pre-loaded with cookies that bypass Arizona's
    reCAPTCHA v2 browser check.

    reCAPTCHA v2 requires a human to click the "I'm not a robot" checkbox —
    it cannot be auto-submitted. Strategy:
      1. Launch real Chrome (non-headless) via patchright with persistent profile.
      2. Warm up by visiting google.com and bing.com to deposit Google-domain cookies.
      3. Navigate to the portal list page and wait for user to solve the CAPTCHA.
      4. User presses Enter; extract cookies into a requests.Session.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "ERROR: patchright is required to pass the Arizona browser check.\n"
            "Install: pip install patchright && patchright install chromium"
        )

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(USER_DATA_DIR),
            headless=False,
            channel="chrome",
        )
        page = context.new_page()

        for warmup_url in ["https://www.google.com", "https://www.bing.com"]:
            try:
                page.goto(warmup_url, wait_until="domcontentloaded", timeout=15_000)
                time.sleep(2)
            except Exception:
                pass

        page.goto(BROWSE_URL, wait_until="domcontentloaded", timeout=30_000)
        input("Please solve the CAPTCHA in the browser window, then press Enter to continue...")

        cookies = context.cookies()
        context.close()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"])
    return session


def discover_solicitations(session=None):
    """
    Paginate all pages of the open solicitations list via AJAX POST.

    The hdnUserValue payload key applies the "Open for Bidding" filter server-side,
    so no client-side filtering is needed after this call.

    Pass an existing session to reuse cookies (avoids a second CAPTCHA prompt).
    """
    if session is None:
        session = make_session()

    all_rows = []
    page_n = 1
    total_pages = 1

    while page_n <= total_pages:
        time.sleep(DELAY_SECONDS)
        resp = session.post(AJAX_URL, data=_pagination_payload(page_n), timeout=30)
        resp.raise_for_status()
        rows, total_pages = parse_list_page(resp.text)
        all_rows.extend(rows)
        page_n += 1

    return all_rows


def probe():
    session = make_session()
    print("Discovering solicitations (paginating list)...")
    open_rows = discover_solicitations(session)
    done_ids = load_done_ids(OUTPUT_PATH)

    new_rows = [r for r in open_rows if r["src_code"] not in done_ids]
    if not new_rows:
        print("No new open solicitations to probe.")
        return

    row = new_rows[0]
    url = BASE_URL + row["detail_href"]
    print(f"Probing: {url}\n")

    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        fields = extract_fields(resp.text)
    except Exception as e:
        sys.exit(f"ERROR fetching {url}: {e}")

    print("=== List Fields ===")
    print(f"Code:               {row['src_code']}")
    print(f"Label:              {row['solicitation_label']}")
    print(f"Commodity:          {row['commodity']}")
    print(f"Buying Agency:      {row['buying_agency']}")
    print(f"Status:             {row['status']}")
    print(f"RFx Awarded:        {row['rfx_awarded']}")
    print(f"Begin:              {row['begin_date']}")
    print(f"End:                {row['end_date']}")
    print(f"\n=== Detail Fields ===")
    print(f"Lot #:              {fields['lot_number']}")
    print(f"Round #:            {fields['round_number']}")
    print(f"Fiscal Year:        {fields['fiscal_year']}")
    print(f"RFx Type:           {fields['rfx_type']}")
    print(f"Procurement Officer:{fields['procurement_officer']}")
    print(f"Email:              {fields['procurement_officer_email']}")
    print(f"Phone:              {fields['procurement_officer_phone']}")
    print(f"Forum Cut Off:      {fields['discussion_forum_cutoff']}")
    print(f"Commodity (full):   {fields['commodity_full']}")
    print(f"\n=== Summary ===")
    summary = fields["summary"]
    print(summary[:500] + ("..." if len(summary) > 500 else ""))


def run():
    session = make_session()
    print("Discovering solicitations (paginating list)...")
    open_rows = discover_solicitations(session)
    done_ids = load_done_ids(OUTPUT_PATH)

    to_scrape = [r for r in open_rows if r["src_code"] not in done_ids]
    total_new = len(to_scrape)
    print(f"Open: {len(open_rows)}. Already done: {len(done_ids)}. To scrape: {total_new}")

    if total_new == 0:
        print("Nothing to do.")
        return

    enriched = []
    if Path(OUTPUT_PATH).exists():
        all_rows = pd.read_csv(OUTPUT_PATH, dtype=str).to_dict("records")
        enriched = [r for r in all_rows if r.get("scrape_status") == "success"]
    success_count = 0
    error_count = 0

    for i, row in enumerate(to_scrape, 1):
        url = BASE_URL + row["detail_href"]
        print(f"[{i}/{total_new}] {url}")

        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            scraped = extract_fields(resp.text)
            scraped["arizona_url"] = url
            scraped["scrape_status"] = "success"
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            scraped = EMPTY_SCRAPED.copy()
            scraped["arizona_url"] = url
            scraped["scrape_status"] = "error"
            error_count += 1

        enriched.append({**row, **scraped})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {success_count} succeeded, {error_count} errored. Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
```

- [ ] **Step 2: Run the full test suite — expect 11 PASS, 0 FAIL**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest az/tests/test_scraper.py -v
```

Expected: `11 passed`

- [ ] **Step 3: Commit**

```bash
git add az/scraper.py
git commit -m "feat(az): add make_session, discover_solicitations, probe, run"
```

- [ ] **Step 4: Live probe test**

Make sure Chrome is closed (patchright needs the profile lock). Run from inside `az/`:

```bash
cd az
/Users/ml3787/Desktop/state-local/venv/bin/python scraper.py probe
```

Expected flow:
1. Chrome opens, visits google.com then bing.com (warmup)
2. Navigates to `app.az.gov/page.aspx/en/rfp/request_browse_public`
3. Terminal prints: `Please solve the CAPTCHA in the browser window, then press Enter to continue...`
4. User clicks "I'm not a robot" in the browser → page loads with solicitation list
5. User presses Enter in terminal
6. Script prints: `Discovering solicitations (paginating list)...`
7. Prints list fields + detail fields for one solicitation

Verify:
- All 8 list fields have non-empty values (`src_code`, `solicitation_label`, `commodity`, `buying_agency`, `status`, `begin_date`, `end_date`, `detail_href`)
- `status` == `"Open for Bidding"`
- Detail fields: at minimum `procurement_officer_email` and `summary` have values (other fields may be empty for some solicitations)
- No Python exceptions

If `commodity_full` is empty but the field is visible on the page, the label text may differ — open the detail page in DevTools and check the exact text of the label span. Update `extract_fields` accordingly.

- [ ] **Step 5: Final commit (if any probe fixes were needed)**

```bash
git add az/scraper.py
git commit -m "fix(az): adjust field label text based on live probe results"
```

If no fixes needed, skip this step.
