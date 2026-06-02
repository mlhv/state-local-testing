# Alabama Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a scraper for Alabama BUYS public solicitations that discovers records by paginating the search list (no CSV export exists), filters to "Open for Bidding" client-side, and enriches each record with detail page data.

**Architecture:** Single-phase — `discover_solicitations()` paginates all list pages via GET (page 1) + POST (pages 2..N) collecting open bids; `run()` then scrapes the detail page for each new record. Resume safety via `src_code` keyed output CSV. No input file required.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, `pandas`, `pytest`

---

## File Map

| File | Role |
|---|---|
| `al/scraper.py` | All scraper logic — constants, helpers, `discover_solicitations`, `load_done_ids`, `extract_fields`, `probe`, `run` |
| `al/requirements.txt` | `requests`, `pandas`, `beautifulsoup4` |
| `al/tests/test_scraper.py` | Unit tests for all pure functions |
| `al/tests/fixtures/sample_list_page.html` | Minimal HTML fixture: one list page with 2 rows (one open, one closed) + pager showing 2 pages |
| `al/tests/fixtures/sample_solicitation_detail.html` | Minimal HTML fixture: one detail page with all Solicitation General Information fields |
| `al/solicitations_enriched.csv` | Output — gitignored |

---

## Task 1: Scaffold folder, requirements, empty scraper

**Files:**
- Create: `al/requirements.txt`
- Create: `al/scraper.py`
- Create: `al/tests/__init__.py`
- Create: `al/tests/fixtures/.gitkeep`

- [ ] **Step 1: Create folder structure**

```bash
mkdir -p al/tests/fixtures
touch al/tests/__init__.py al/tests/fixtures/.gitkeep
```

- [ ] **Step 2: Create `al/requirements.txt`**

```
requests
pandas
beautifulsoup4
```

- [ ] **Step 3: Create empty `al/scraper.py` with module docstring and constants**

```python
"""
Alabama BUYS public solicitations scraper.
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
BROWSE_URL = "https://www.alabamabuys.gov/page.aspx/en/rfp/request_browse_public"
AJAX_URL = (
    "https://www.alabamabuys.gov/ajax.aspx/en/rfp/request_browse_public"
    "?ivControlUIDsAsync=body:x:grid:upgrid"
    "&asyncmodulename=rfp"
    "&asyncpagename=request_browse_public"
)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LIST_FIELDS = [
    "src_code",
    "solicitation_label",
    "status",
    "award_status",
    "due_close_date",
    "main_commodity",
    "solicitation_type",
    "buying_agency",
    "sourcing_responsible_first",
    "sourcing_responsible_last",
    "detail_href",
]

SCRAPED_FIELDS = [
    "round_number",
    "begin_date",
    "summary",
    "alabama_url",
    "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}
```

- [ ] **Step 4: Verify import works**

```bash
cd /Users/ml3787/Desktop/state-local/al
/Users/ml3787/Desktop/state-local/venv/bin/python -c "import scraper; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add al/
git commit -m "feat(al): scaffold folder, constants, empty scraper"
```

---

## Task 2: Create HTML fixtures

These fixtures are minimal hand-crafted HTML that mirror the real portal's structure. The list fixture must have: a grid table with 2 data rows (one open, one closed), a detail href in each row, and a pager element showing page 2 exists. The detail fixture must have the Solicitation General Information card with all target fields.

**Files:**
- Create: `al/tests/fixtures/sample_list_page.html`
- Create: `al/tests/fixtures/sample_solicitation_detail.html`

- [ ] **Step 1: Create `al/tests/fixtures/sample_list_page.html`**

```html
<!DOCTYPE html>
<html>
<body>
<div id="body_x_grid_upgrid">
  <table>
    <thead>
      <tr>
        <th>Sourcing Project Number</th>
        <th>Solicitation Label</th>
        <th>Status</th>
        <th>Award Status</th>
        <th>Due / Close Date</th>
        <th>Main Commodity</th>
        <th>Solicitation Type</th>
        <th>Buying Agency</th>
        <th>Sourcing Responsible First Name</th>
        <th>Sourcing Responsible Last Name</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><a href="/page.aspx/en/rfp/request_manage_public/41760">SRC0000034127</a></td>
        <td>Locksmith Services at FMS #11/Birmingham</td>
        <td>Open for Bidding</td>
        <td></td>
        <td>6/15/2026</td>
        <td>Maintenance, Repair and Operations</td>
        <td>Quick Quote</td>
        <td>Facilities Management</td>
        <td>Tracy</td>
        <td>Fink</td>
      </tr>
      <tr>
        <td><a href="/page.aspx/en/rfp/request_manage_public/40000">SRC0000032000</a></td>
        <td>Old Closed Bid</td>
        <td>Awarded</td>
        <td>Awarded</td>
        <td>1/1/2026</td>
        <td>Office Supplies</td>
        <td>Invitation to Bid</td>
        <td>Finance</td>
        <td>John</td>
        <td>Doe</td>
      </tr>
    </tbody>
  </table>
  <span id="body_x_grid_gridPagerBtn2Page">2</span>
</div>
</body>
</html>
```

- [ ] **Step 2: Create `al/tests/fixtures/sample_solicitation_detail.html`**

```html
<!DOCTYPE html>
<html>
<body>
<div class="solicitation-general-info">
  <div><strong>Code</strong> SRC0000034127</div>
  <div><strong>Solicitation Name</strong> Locksmith Services at FMS #11/Birmingham</div>
  <div><strong>Round #</strong><span>1</span></div>
  <div><strong>Solicitation Type</strong> Quick Quote</div>
  <div><strong>Begin</strong><span>5/29/2026 4:44:49 PM (CST)</span></div>
  <div><strong>Status</strong> Open for Bidding</div>
  <div><strong>End</strong> 6/15/2026 5:00:00 PM (CST)</div>
  <div><strong>Award Status</strong></div>
  <div><strong>Summary</strong>
    <div id="summary-text">Vendor to Troubleshoot/Repair the door leading from office area to the shop.</div>
  </div>
</div>
</body>
</html>
```

> **Note:** These fixtures are intentionally minimal. The real HTML structure will differ. Task 4 updates the parsing logic (and fixtures if needed) once you've seen the actual portal HTML. The goal here is to establish the fixture pattern and get tests running.

- [ ] **Step 3: Commit**

```bash
git add al/tests/fixtures/
git commit -m "test(al): add HTML fixtures for list page and detail page"
```

---

## Task 3: `load_done_ids` and `make_session`

**Files:**
- Modify: `al/scraper.py`
- Modify: `al/tests/test_scraper.py`

- [ ] **Step 1: Write failing tests**

Create `al/tests/test_scraper.py`:

```python
import pandas as pd
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import scraper


def test_load_done_ids_missing_file(tmp_path):
    assert scraper.load_done_ids(str(tmp_path / "nonexistent.csv")) == set()


def test_load_done_ids_returns_successes_only(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([
        {"src_code": "SRC0000034127", "scrape_status": "success"},
        {"src_code": "SRC0000034128", "scrape_status": "error"},
        {"src_code": "SRC0000034129", "scrape_status": "success"},
    ]).to_csv(csv, index=False)
    result = scraper.load_done_ids(str(csv))
    assert result == {"SRC0000034127", "SRC0000034129"}


def test_load_done_ids_missing_columns(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([{"foo": "bar"}]).to_csv(csv, index=False)
    assert scraper.load_done_ids(str(csv)) == set()
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/ml3787/Desktop/state-local/al
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: 3 failures — `AttributeError: module 'scraper' has no attribute 'load_done_ids'`

- [ ] **Step 3: Implement `load_done_ids` and `make_session` in `al/scraper.py`**

Add after the constants:

```python
def load_done_ids(output_path):
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "src_code" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "src_code"].astype(str))


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    return session
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add al/scraper.py al/tests/test_scraper.py
git commit -m "feat(al): add load_done_ids and make_session"
```

---

## Task 4: `parse_list_page` — extract rows from one page of HTML

This function takes an HTML string and returns a list of dicts, one per row, using the column order from the list grid. It also returns the total page count parsed from the pager.

**Files:**
- Modify: `al/scraper.py`
- Modify: `al/tests/test_scraper.py`

> **Before coding:** Open the real list page in a browser, right-click → View Page Source, and confirm the actual HTML structure of the grid table and pager. Update `sample_list_page.html` if the real structure differs from the fixture written in Task 2. The implementation below targets the fixture structure — adjust selectors as needed once you've seen the real HTML.

- [ ] **Step 1: Write failing tests**

Add to `al/tests/test_scraper.py`:

```python
FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_list_page_row_count():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, total_pages = scraper.parse_list_page(html)
    assert len(rows) == 2


def test_parse_list_page_open_row_fields():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, _ = scraper.parse_list_page(html)
    open_row = next(r for r in rows if r["src_code"] == "SRC0000034127")
    assert open_row["status"] == "Open for Bidding"
    assert open_row["solicitation_label"] == "Locksmith Services at FMS #11/Birmingham"
    assert open_row["due_close_date"] == "6/15/2026"
    assert open_row["solicitation_type"] == "Quick Quote"
    assert open_row["buying_agency"] == "Facilities Management"
    assert open_row["sourcing_responsible_first"] == "Tracy"
    assert open_row["sourcing_responsible_last"] == "Fink"
    assert "41760" in open_row["detail_href"]


def test_parse_list_page_total_pages():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    _, total_pages = scraper.parse_list_page(html)
    assert total_pages == 2


def test_parse_list_page_no_pager_means_one_page():
    html = "<html><body><table><thead><tr><th>Sourcing Project Number</th></tr></thead><tbody></tbody></table></body></html>"
    _, total_pages = scraper.parse_list_page(html)
    assert total_pages == 1
```

- [ ] **Step 2: Run to verify they fail**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: 4 new failures — `AttributeError: module 'scraper' has no attribute 'parse_list_page'`

- [ ] **Step 3: Implement `parse_list_page` in `al/scraper.py`**

```python
COLUMN_HEADERS = [
    "Sourcing Project Number",
    "Solicitation Label",
    "Status",
    "Award Status",
    "Due / Close Date",
    "Main Commodity",
    "Solicitation Type",
    "Buying Agency",
    "Sourcing Responsible First Name",
    "Sourcing Responsible Last Name",
]

COLUMN_KEYS = [
    "src_code",
    "solicitation_label",
    "status",
    "award_status",
    "due_close_date",
    "main_commodity",
    "solicitation_type",
    "buying_agency",
    "sourcing_responsible_first",
    "sourcing_responsible_last",
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
    Returns (rows, total_pages) where rows is a list of dicts with LIST_FIELDS keys
    (minus detail_href which is appended here) and total_pages is int.
    """
    soup = BeautifulSoup(html, "html.parser")
    total_pages = _parse_total_pages(soup)

    table = soup.find("table")
    if not table:
        return [], total_pages

    rows = []
    for tr in table.find("tbody").find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < len(COLUMN_KEYS):
            continue
        row = {}
        for key, cell in zip(COLUMN_KEYS, cells):
            row[key] = cell.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
        # Extract detail href from the anchor in the first cell (src_code cell)
        anchor = cells[0].find("a", href=True)
        row["detail_href"] = anchor["href"] if anchor else ""
        # src_code is the link text, not the cell text which may include extra whitespace
        if anchor:
            row["src_code"] = anchor.get_text(strip=True)
        rows.append(row)

    return rows, total_pages
```

- [ ] **Step 4: Run tests**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add al/scraper.py al/tests/test_scraper.py al/tests/fixtures/sample_list_page.html
git commit -m "feat(al): add parse_list_page with pager detection"
```

---

## Task 5: `discover_solicitations` — paginate all pages, return open rows

This function uses `make_session`, GETs page 1, then POSTs pages 2..N, collects all rows where `status == "Open for Bidding"`.

**Files:**
- Modify: `al/scraper.py`
- Modify: `al/tests/test_scraper.py`

- [ ] **Step 1: Write failing test using `responses` mock**

Add to `al/tests/test_scraper.py`:

```python
import responses as responses_lib


@responses_lib.activate
def test_discover_solicitations_filters_open_only():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    # Mock the GET for page 1 (fixture has 2 total pages shown by pager)
    responses_lib.add(responses_lib.GET, scraper.BROWSE_URL, body=html, status=200)
    # Mock the POST for page 2 — return same HTML (one open, one closed row)
    responses_lib.add(responses_lib.POST, scraper.AJAX_URL, body=html, status=200)

    result = scraper.discover_solicitations()
    # Only the "Open for Bidding" rows from both pages
    assert len(result) == 2  # 1 open from page 1 + 1 open from page 2 (same fixture)
    assert all(r["status"] == "Open for Bidding" for r in result)
    assert all(r["src_code"] == "SRC0000034127" for r in result)
```

Install `responses` into the venv first:

```bash
/Users/ml3787/Desktop/state-local/venv/bin/pip install responses
```

- [ ] **Step 2: Run to verify it fails**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py::test_discover_solicitations_filters_open_only -v
```

Expected: FAIL — `AttributeError: module 'scraper' has no attribute 'discover_solicitations'`

- [ ] **Step 3: Implement `_pagination_payload` and `discover_solicitations` in `al/scraper.py`**

```python
_BASE_PAYLOAD = {
    "__EVENTTARGET": "body_x_grid_grd",
    "__LASTFOCUS": "",
    "REQUEST_METHOD": "POST",
    "hdnUserValue": "",
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


def discover_solicitations():
    """
    Paginate all pages of the public solicitations list.
    Returns list of row dicts (LIST_FIELDS) filtered to status == "Open for Bidding".
    """
    session = make_session()

    resp = session.get(BROWSE_URL, timeout=30)
    resp.raise_for_status()
    page1_rows, total_pages = parse_list_page(resp.text)

    all_rows = list(page1_rows)

    for page_n in range(2, total_pages + 1):
        time.sleep(DELAY_SECONDS)
        resp = session.post(AJAX_URL, data=_pagination_payload(page_n), timeout=30)
        resp.raise_for_status()
        rows, _ = parse_list_page(resp.text)
        all_rows.extend(rows)

    return [r for r in all_rows if r.get("status") == "Open for Bidding"]
```

- [ ] **Step 4: Run tests**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add al/scraper.py al/tests/test_scraper.py
git commit -m "feat(al): add discover_solicitations with full pagination"
```

---

## Task 6: `extract_fields` — parse detail page

**Files:**
- Modify: `al/scraper.py`
- Modify: `al/tests/test_scraper.py`

> **Before coding:** Open a real solicitation detail page, View Page Source, find the "Solicitation General Information" card. Confirm the HTML structure — specifically how `Round #`, `Begin`, and `Summary` are marked up (label + adjacent value element). Update `sample_solicitation_detail.html` if the real structure differs from the Task 2 fixture.

- [ ] **Step 1: Write failing tests**

Add to `al/tests/test_scraper.py`:

```python
def test_extract_fields_round_number():
    html = (FIXTURE_DIR / "sample_solicitation_detail.html").read_text()
    fields = scraper.extract_fields(html)
    assert fields["round_number"] == "1"


def test_extract_fields_begin_date():
    html = (FIXTURE_DIR / "sample_solicitation_detail.html").read_text()
    fields = scraper.extract_fields(html)
    assert fields["begin_date"] == "5/29/2026 4:44:49 PM (CST)"


def test_extract_fields_summary():
    html = (FIXTURE_DIR / "sample_solicitation_detail.html").read_text()
    fields = scraper.extract_fields(html)
    assert "Troubleshoot" in fields["summary"]


def test_extract_fields_missing_field_returns_empty():
    fields = scraper.extract_fields("<html><body></body></html>")
    assert fields["round_number"] == ""
    assert fields["begin_date"] == ""
    assert fields["summary"] == ""
```

- [ ] **Step 2: Run to verify they fail**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: 4 new failures

- [ ] **Step 3: Implement helpers and `extract_fields` in `al/scraper.py`**

```python
def _label_value(soup, label_text):
    """
    Find the first element whose text matches label_text, then return
    the text of the next sibling element. Works for <strong>/<span> pairs
    and <div>/<div> pairs common in Ivalua portals.
    """
    for el in soup.find_all(string=lambda t: t and t.strip() == label_text):
        parent = el.parent
        sibling = parent.find_next_sibling()
        if sibling:
            return sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
        # Try parent's parent next sibling (nested structure)
        grandparent_sibling = parent.parent.find_next_sibling() if parent.parent else None
        if grandparent_sibling:
            return grandparent_sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
    return ""


def extract_fields(html):
    """Parse Solicitation General Information from a detail page."""
    soup = BeautifulSoup(html, "html.parser")
    return {
        "round_number": _label_value(soup, "Round #"),
        "begin_date":   _label_value(soup, "Begin"),
        "summary":      _label_value(soup, "Summary"),
    }
```

- [ ] **Step 4: Run tests**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add al/scraper.py al/tests/test_scraper.py al/tests/fixtures/sample_solicitation_detail.html
git commit -m "feat(al): add extract_fields for detail page parsing"
```

---

## Task 7: `probe` and `run` commands

**Files:**
- Modify: `al/scraper.py`

- [ ] **Step 1: Add `probe` function**

```python
def probe():
    print("Discovering solicitations (paginating list)...")
    open_rows = discover_solicitations()
    done_ids = load_done_ids(OUTPUT_PATH)

    new_rows = [r for r in open_rows if r["src_code"] not in done_ids]
    if not new_rows:
        print("No new open solicitations to probe.")
        return

    row = new_rows[0]
    url = "https://www.alabamabuys.gov" + row["detail_href"]
    print(f"Probing: {url}\n")

    session = make_session()
    try:
        resp = session.get(url, timeout=30)
        resp.raise_for_status()
        fields = extract_fields(resp.text)
    except Exception as e:
        sys.exit(f"ERROR fetching {url}: {e}")

    print("=== List Fields ===")
    print(f"SRC Code:        {row['src_code']}")
    print(f"Label:           {row['solicitation_label']}")
    print(f"Status:          {row['status']}")
    print(f"Award Status:    {row['award_status']}")
    print(f"Due/Close Date:  {row['due_close_date']}")
    print(f"Main Commodity:  {row['main_commodity']}")
    print(f"Sol. Type:       {row['solicitation_type']}")
    print(f"Buying Agency:   {row['buying_agency']}")
    print(f"Contact:         {row['sourcing_responsible_first']} {row['sourcing_responsible_last']}")
    print(f"\n=== Detail Fields ===")
    print(f"Round #:         {fields['round_number']}")
    print(f"Begin Date:      {fields['begin_date']}")
    print(f"\n=== Summary ===")
    summary = fields["summary"]
    print(summary[:500] + ("..." if len(summary) > 500 else ""))
```

- [ ] **Step 2: Add `run` function**

```python
def run():
    print("Discovering solicitations (paginating list)...")
    open_rows = discover_solicitations()
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

    session = make_session()
    success_count = 0
    error_count = 0

    for i, row in enumerate(to_scrape, 1):
        url = "https://www.alabamabuys.gov" + row["detail_href"]
        print(f"[{i}/{total_new}] {url}")

        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            scraped = extract_fields(resp.text)
            scraped["alabama_url"] = url
            scraped["scrape_status"] = "success"
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            scraped = EMPTY_SCRAPED.copy()
            scraped["alabama_url"] = url
            scraped["scrape_status"] = "error"
            error_count += 1

        enriched.append({**row, **scraped})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {success_count} succeeded, {error_count} errored. Output: {OUTPUT_PATH}")
```

- [ ] **Step 3: Add `__main__` block**

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

- [ ] **Step 4: Run full test suite**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest al/tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add al/scraper.py
git commit -m "feat(al): add probe and run commands"
```

---

## Task 8: Live probe test and fixture correction

The fixtures in Task 2 were hand-crafted estimates. This task runs the scraper against the real portal and corrects any parsing failures.

**Files:**
- Modify: `al/scraper.py` (adjust selectors if needed)
- Modify: `al/tests/fixtures/sample_list_page.html` (replace with real HTML excerpt if needed)
- Modify: `al/tests/fixtures/sample_solicitation_detail.html` (replace with real HTML excerpt if needed)

- [ ] **Step 1: Run probe against the live site**

```bash
cd /Users/ml3787/Desktop/state-local/al
/Users/ml3787/Desktop/state-local/venv/bin/python scraper.py probe
```

Expected: prints list fields and summary for one open solicitation. If parsing returns empty strings for `round_number`, `begin_date`, or `summary`, the real HTML structure differs from the fixture.

- [ ] **Step 2: If any fields are empty — diagnose**

Add a temporary debug print to see the raw HTML of the detail page:

```python
# temporary — remove after debugging
resp = session.get(url, timeout=30)
with open("/tmp/al_detail_debug.html", "w") as f:
    f.write(resp.text)
```

Open `/tmp/al_detail_debug.html` in a browser or editor. Find the actual HTML structure around `Round #`, `Begin`, and `Summary`. Update `_label_value()` in `scraper.py` and the fixture to match.

- [ ] **Step 3: If list fields are empty — diagnose list parsing**

Similarly dump the list page HTML:

```python
resp = session.get(BROWSE_URL, timeout=30)
with open("/tmp/al_list_debug.html", "w") as f:
    f.write(resp.text)
```

Inspect the table structure. Update `parse_list_page()` and `sample_list_page.html` to match.

- [ ] **Step 4: Re-run tests after any fixture/parser changes**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest al/tests/ -v
```

Expected: all pass

- [ ] **Step 5: Commit any corrections**

```bash
git add al/scraper.py al/tests/fixtures/
git commit -m "fix(al): correct HTML selectors after live probe"
```

---

## Task 9: Add `responses` to requirements, update HANDOFF.md

**Files:**
- Modify: `al/requirements.txt`
- Modify: `HANDOFF.md`

- [ ] **Step 1: Update `al/requirements.txt`**

```
requests
pandas
beautifulsoup4
responses
```

- [ ] **Step 2: Update `HANDOFF.md`** — add Alabama row to the State Status table and a new Alabama section:

In the State Status table add:
```
| Alabama | ✅ Complete | `al/` | Alabama BUYS (Ivalua) | No export — list scraped directly | `solicitations_enriched.csv` (15 cols) |
```

Add a new section after Massachusetts:

```markdown
## Alabama (Alabama BUYS)

**Portal:** https://www.alabamabuys.gov/page.aspx/en/rfp/request_browse_public

**How it works:** Ivalua-based portal with no CSV export. The scraper discovers records by paginating the search results list: page 1 via GET, pages 2..N via POST to the ajax.aspx endpoint with `__EVENTARGUMENT=Page|{n}`. Status filter in the POST body is broken — filtering to "Open for Bidding" is done client-side by reading the Status column from each row. Detail pages are server-rendered HTML parsed with BeautifulSoup.

**Run:**
```bash
cd al
source ../venv/bin/activate
python scraper.py probe
python scraper.py run
```

**Known gaps:** DB normalization, Solicitation Documents (PDF links) not captured
```

- [ ] **Step 3: Commit**

```bash
git add al/requirements.txt HANDOFF.md
git commit -m "docs(al): add requirements.txt and update HANDOFF.md"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `probe` / `run` commands
- ✅ GET page 1 + POST pages 2..N pagination
- ✅ Client-side status filter ("Open for Bidding")
- ✅ All pages visited (no early stop)
- ✅ Detail href extracted from list HTML (not derived from SRC code)
- ✅ `round_number`, `begin_date`, `summary` from detail page
- ✅ All 10 list fields captured
- ✅ `alabama_url` and `scrape_status` trailing columns (15 total)
- ✅ Resume safety via `src_code` + `scrape_status=success`
- ✅ `DELAY_SECONDS = 0.5`
- ✅ `load_done_ids` returns empty set for missing file and missing columns
- ✅ Fixtures for list page and detail page
- ✅ HANDOFF.md updated

**Placeholder scan:** No TBDs, all code blocks complete.

**Type consistency:** `parse_list_page` returns `(list[dict], int)` — consumed correctly in `discover_solicitations`. `extract_fields` returns `dict` with keys matching `SCRAPED_FIELDS` — merged correctly in `run`. `EMPTY_SCRAPED` uses same keys as `SCRAPED_FIELDS`. ✅
