# PA eMarketplace Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scrape all open PA eMarketplace solicitations from a manually exported CSV, enrich each with detail-page fields via BeautifulSoup, and write incrementally to `solicitations_enriched.csv`.

**Architecture:** Load the most recent `Solicitations-*.csv` → diff against existing output to find new/errored Bid Nos → GET each detail page → BeautifulSoup extraction → append to output CSV after each record. Resume-safe: only rows with `scrape_status == "success"` are skipped on reruns.

**Tech Stack:** Python 3, `requests`, `beautifulsoup4`, `pandas`

---

## File Map

| File | Role |
|---|---|
| `pa/scraper.py` | All scraper logic + `probe` / `run` CLI commands |
| `pa/requirements.txt` | Per-project deps (beautifulsoup4, pandas, requests) |
| `pa/tests/test_scraper.py` | Unit tests for pure functions |
| `pa/tests/fixtures/sample_solicitation.html` | Captured HTML fixture for extraction tests (created during Task 5) |
| `pa/Solicitations-*.csv` | Manually exported input (read-only) |
| `pa/solicitations_enriched.csv` | Output — all columns, written incrementally |

---

## Task 1: Project setup

**Files:**
- Create: `pa/requirements.txt`
- Create: `pa/tests/__init__.py`
- Modify: `pa/scraper.py` (skeleton)

- [ ] **Step 1: Create `pa/requirements.txt`**

```
beautifulsoup4
pandas
requests
```

- [ ] **Step 2: Install into root venv**

```bash
cd /Users/ml3787/Desktop/state-local
source venv/bin/activate
pip install -r pa/requirements.txt
```

Expected: packages install without errors. `bs4` importable.

- [ ] **Step 3: Create test package init**

```bash
mkdir -p pa/tests
touch pa/tests/__init__.py
```

- [ ] **Step 4: Write scraper.py skeleton**

Replace the empty `pa/scraper.py` with:

```python
"""
PA eMarketplace solicitation scraper.
Usage:
  python scraper.py probe   -- fetch one new solicitation and print all extracted fields
  python scraper.py run     -- scrape all new/errored solicitations and write to CSV
"""

import glob
import sys
import time
import requests
import pandas as pd
from pathlib import Path
from urllib.parse import quote
from bs4 import BeautifulSoup

INPUT_GLOB = "Solicitations-*.csv"
OUTPUT_PATH = "solicitations_enriched.csv"
DELAY_SECONDS = 0.5
BASE_URL = "https://emarketplace.state.pa.us/Solicitations.aspx"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SCRAPED_FIELDS = [
    "department_for_solicitation",
    "date_prepared",
    "advertisement_type",
    "description_full",
    "delivery_location",
    "duration",
    "contact_first_name",
    "contact_last_name",
    "contact_phone",
    "contact_email",
    "solicitation_due_time",
    "solicitation_opening_time",
    "opening_location",
    "no_of_addendums",
    "solicitation_url",
    "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}
```

- [ ] **Step 5: Commit**

```bash
git add pa/requirements.txt pa/tests/__init__.py pa/scraper.py
git commit -m "feat(pa): project setup and scraper skeleton"
```

---

## Task 2: Input CSV loader

**Files:**
- Create: `pa/tests/test_scraper.py`
- Modify: `pa/scraper.py`

- [ ] **Step 1: Write failing test**

Create `pa/tests/test_scraper.py`:

```python
import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import find_input_csv, load_done_ids, build_url


def test_find_input_csv_returns_most_recent(tmp_path):
    (tmp_path / "Solicitations-2026-05-01-09-00-00.csv").write_text("Bid No\n1")
    (tmp_path / "Solicitations-2026-05-27-10-06-38.csv").write_text("Bid No\n2")
    result = find_input_csv(str(tmp_path))
    assert result.endswith("Solicitations-2026-05-27-10-06-38.csv")


def test_find_input_csv_exits_when_none_found(tmp_path):
    with pytest.raises(SystemExit):
        find_input_csv(str(tmp_path))
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd pa && python -m pytest tests/test_scraper.py::test_find_input_csv_returns_most_recent -v
```

Expected: `ImportError` or `NameError` — `find_input_csv` not defined yet.

- [ ] **Step 3: Implement `find_input_csv` in `scraper.py`**

Add after the constants block:

```python
def find_input_csv(directory="."):
    files = sorted(glob.glob(str(Path(directory) / INPUT_GLOB)))
    if not files:
        sys.exit(f"ERROR: No {INPUT_GLOB} found in {directory}")
    return files[-1]
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scraper.py -k "find_input_csv" -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pa/scraper.py pa/tests/test_scraper.py
git commit -m "feat(pa): add input CSV loader"
```

---

## Task 3: Resume / done-IDs logic

**Files:**
- Modify: `pa/tests/test_scraper.py`
- Modify: `pa/scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `pa/tests/test_scraper.py`:

```python
def test_load_done_ids_returns_empty_when_no_output(tmp_path):
    result = load_done_ids(str(tmp_path / "solicitations_enriched.csv"))
    assert result == set()


def test_load_done_ids_skips_error_rows(tmp_path):
    output = tmp_path / "solicitations_enriched.csv"
    output.write_text(
        "Bid No,scrape_status\n"
        "6100066078,success\n"
        "6100066090,error\n"
        "6100066071,success\n"
    )
    result = load_done_ids(str(output))
    assert result == {"6100066078", "6100066071"}
    assert "6100066090" not in result
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scraper.py -k "load_done_ids" -v
```

Expected: `NameError` — `load_done_ids` not defined.

- [ ] **Step 3: Implement `load_done_ids` in `scraper.py`**

```python
def load_done_ids(output_path):
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "Bid No" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "Bid No"].astype(str))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scraper.py -k "load_done_ids" -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pa/scraper.py pa/tests/test_scraper.py
git commit -m "feat(pa): add resume logic — retry error rows on rerun"
```

---

## Task 4: URL builder

**Files:**
- Modify: `pa/tests/test_scraper.py`
- Modify: `pa/scraper.py`

- [ ] **Step 1: Write failing tests**

Append to `pa/tests/test_scraper.py`:

```python
def test_build_url_simple_id():
    assert build_url("6100066078") == (
        "https://emarketplace.state.pa.us/Solicitations.aspx?SID=6100066078"
    )


def test_build_url_encodes_spaces():
    assert build_url("DGS C-1050-0001 Phase 1") == (
        "https://emarketplace.state.pa.us/Solicitations.aspx"
        "?SID=DGS%20C-1050-0001%20Phase%201"
    )
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_scraper.py -k "build_url" -v
```

Expected: `NameError` — `build_url` not defined.

- [ ] **Step 3: Implement `build_url` in `scraper.py`**

```python
def build_url(bid_no):
    return f"{BASE_URL}?SID={quote(str(bid_no))}"
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_scraper.py -k "build_url" -v
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add pa/scraper.py pa/tests/test_scraper.py
git commit -m "feat(pa): add URL builder"
```

---

## Task 5: HTTP session, page fetch, and HTML fixture capture

**Files:**
- Modify: `pa/scraper.py`
- Create: `pa/tests/fixtures/sample_solicitation.html` (captured in this task)

- [ ] **Step 1: Implement `make_session` and `fetch_page` in `scraper.py`**

```python
def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    return session


def fetch_page(session, url):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text
```

- [ ] **Step 2: Add a temporary `capture` command to `scraper.py`**

This captures a real page to disk for use as a test fixture. Add to `scraper.py` (will be removed after fixture is saved):

```python
def capture():
    """Fetch the first solicitation's detail page and save raw HTML for test fixtures."""
    input_csv = find_input_csv(".")
    df = pd.read_csv(input_csv, dtype=str)
    bid_no = str(df["Bid No"].iloc[0])
    url = build_url(bid_no)
    print(f"Capturing: {url}")
    session = make_session()
    html = fetch_page(session, url)
    fixture_path = Path("tests/fixtures/sample_solicitation.html")
    fixture_path.parent.mkdir(parents=True, exist_ok=True)
    fixture_path.write_text(html, encoding="utf-8")
    print(f"Saved to {fixture_path} ({len(html):,} bytes)")
```

Add `capture` to the `if __name__ == "__main__"` dispatch block (add temporarily alongside probe/run).

- [ ] **Step 3: Run capture from the `pa/` directory**

```bash
cd /Users/ml3787/Desktop/state-local/pa
python scraper.py capture
```

Expected: prints the URL and "Saved to tests/fixtures/sample_solicitation.html (N bytes)". Open the file and confirm it contains the full solicitation HTML.

- [ ] **Step 4: Remove the `capture` command**

Delete the `capture()` function and its dispatch entry from `scraper.py` — it was only needed to create the fixture.

- [ ] **Step 5: Commit**

```bash
git add pa/scraper.py pa/tests/fixtures/sample_solicitation.html
git commit -m "feat(pa): add HTTP session/fetch and HTML fixture for tests"
```

---

## Task 6: BeautifulSoup field extraction

**Files:**
- Modify: `pa/tests/test_scraper.py`
- Modify: `pa/scraper.py`

- [ ] **Step 1: Inspect the fixture to confirm HTML structure**

```bash
cd /Users/ml3787/Desktop/state-local/pa
python - <<'EOF'
from bs4 import BeautifulSoup
from pathlib import Path

html = Path("tests/fixtures/sample_solicitation.html").read_text()
soup = BeautifulSoup(html, "html.parser")

# Find all tds containing "Department for this solicitation"
for td in soup.find_all("td"):
    text = td.get_text(strip=True)
    if "Department for this" in text or "Date Prepared" in text:
        print(repr(td))
        print("---")
EOF
```

Read the output to understand the actual HTML structure (class names, nesting depth) before writing selectors.

- [ ] **Step 2: Write failing test using the fixture**

Append to `pa/tests/test_scraper.py`. Also update the import line at the top of the file to add `extract_fields`:

```python
# Updated top-of-file import line (replace the existing from scraper import ... line):
from scraper import find_input_csv, load_done_ids, build_url, extract_fields
```

Then append the tests:

```python
from scraper import extract_fields

def test_extract_fields_returns_all_keys():
    fixture = Path(__file__).parent / "fixtures" / "sample_solicitation.html"
    html = fixture.read_text(encoding="utf-8")
    result = extract_fields(html)
    expected_keys = [
        "department_for_solicitation", "date_prepared", "advertisement_type",
        "description_full", "delivery_location", "duration",
        "contact_first_name", "contact_last_name", "contact_phone", "contact_email",
        "solicitation_due_time", "solicitation_opening_time",
        "opening_location", "no_of_addendums",
    ]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_extract_fields_values_are_strings():
    fixture = Path(__file__).parent / "fixtures" / "sample_solicitation.html"
    html = fixture.read_text(encoding="utf-8")
    result = extract_fields(html)
    for key, val in result.items():
        assert isinstance(val, str), f"{key} is not a string: {type(val)}"


def test_extract_fields_no_empty_critical_fields():
    """description_full and department_for_solicitation must not be empty for a real page."""
    fixture = Path(__file__).parent / "fixtures" / "sample_solicitation.html"
    html = fixture.read_text(encoding="utf-8")
    result = extract_fields(html)
    assert result["description_full"] != "", "description_full should not be empty"
    assert result["department_for_solicitation"] != "", "department_for_solicitation should not be empty"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_scraper.py -k "extract_fields" -v
```

Expected: `ImportError` — `extract_fields` not defined.

- [ ] **Step 4: Implement `extract_fields` in `scraper.py`**

Use the HTML structure observed in Step 1 to write selectors. The implementation below uses label-text search — adjust class names or tag types if Step 1 reveals a different structure:

```python
def _cell_after_label(soup, label_text):
    """Find a <td> whose stripped text matches label_text, return next sibling <td> text."""
    for td in soup.find_all("td"):
        if td.get_text(strip=True).rstrip(":") == label_text:
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(separator=" ", strip=True)
    return ""


def _selected_radio(soup):
    """Return the label text of the checked radio button in the Advertisement Type row."""
    for inp in soup.find_all("input", {"type": "radio"}):
        if inp.has_attr("checked"):
            nxt = inp.find_next_sibling(string=True)
            if nxt:
                return nxt.strip()
            label = inp.find_next("label")
            if label:
                return label.get_text(strip=True)
    return ""


def extract_fields(html):
    soup = BeautifulSoup(html, "html.parser")

    return {
        # General Information
        "department_for_solicitation": _cell_after_label(soup, "Department for this solicitation"),
        "date_prepared":               _cell_after_label(soup, "Date Prepared"),
        "advertisement_type":          _selected_radio(soup),
        "description_full":            _cell_after_label(soup, "Description"),

        # Department Information
        "delivery_location":           _cell_after_label(soup, "Delivery Location"),
        "duration":                    _cell_after_label(soup, "Duration"),

        # Contact Information
        "contact_first_name":          _cell_after_label(soup, "First Name"),
        "contact_last_name":           _cell_after_label(soup, "Last Name"),
        "contact_phone":               _cell_after_label(soup, "Phone Number(XXX-XXX-XXXX)"),
        "contact_email":               _cell_after_label(soup, "Email"),

        # Solicitation Information
        "solicitation_due_time":       _cell_after_label(soup, "Solicitation Due Time"),
        "solicitation_opening_time":   _cell_after_label(soup, "Solicitation Opening Time"),
        "opening_location":            _cell_after_label(soup, "Opening Location"),
        "no_of_addendums":             _cell_after_label(soup, "No. of Addendums"),
    }
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_scraper.py -k "extract_fields" -v
```

Expected: 3 passed. If any field comes back empty, re-inspect the fixture HTML and adjust the label string in `_cell_after_label` to match exactly. Common issues:
- Label text has a trailing colon in the HTML (add `rstrip(":")` or adjust the match string)
- Nested tags inside the `<td>` — use `.get_text(strip=True)` on the found td rather than checking `.string`
- Phone label may include the format hint in parentheses — check the exact text in the fixture

- [ ] **Step 6: Commit**

```bash
git add pa/scraper.py pa/tests/test_scraper.py
git commit -m "feat(pa): BeautifulSoup field extraction with fixture tests"
```

---

## Task 7: probe command

**Files:**
- Modify: `pa/scraper.py`

- [ ] **Step 1: Implement `probe()` in `scraper.py`**

```python
def probe():
    input_csv = find_input_csv(".")
    df = pd.read_csv(input_csv, dtype=str)
    done_ids = load_done_ids(OUTPUT_PATH)

    new_rows = df[~df["Bid No"].astype(str).isin(done_ids)]
    if new_rows.empty:
        print("No new solicitations to probe.")
        return

    row = new_rows.iloc[0]
    bid_no = str(row["Bid No"])
    url = build_url(bid_no)
    print(f"Probing: {url}\n")

    session = make_session()
    html = fetch_page(session, url)
    fields = extract_fields(html)

    print(f"=== General Information ===")
    print(f"Department:        {fields['department_for_solicitation']}")
    print(f"Date Prepared:     {fields['date_prepared']}")
    print(f"Advertisement Type:{fields['advertisement_type']}")
    print(f"\n=== Description (full) ===")
    print(fields["description_full"][:500] + ("..." if len(fields["description_full"]) > 500 else ""))
    print(f"\n=== Department Information ===")
    print(f"Delivery Location: {fields['delivery_location']}")
    print(f"Duration:          {fields['duration']}")
    print(f"\n=== Contact Information ===")
    print(f"Name:  {fields['contact_first_name']} {fields['contact_last_name']}")
    print(f"Phone: {fields['contact_phone']}")
    print(f"Email: {fields['contact_email']}")
    print(f"\n=== Solicitation Information ===")
    print(f"Due Time:          {fields['solicitation_due_time']}")
    print(f"Opening Time:      {fields['solicitation_opening_time']}")
    print(f"Opening Location:  {fields['opening_location']}")
    print(f"No. of Addendums:  {fields['no_of_addendums']}")
```

- [ ] **Step 2: Add `if __name__ == "__main__"` dispatch block**

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

- [ ] **Step 3: Run probe and verify all fields print correctly**

```bash
cd /Users/ml3787/Desktop/state-local/pa
python scraper.py probe
```

Expected: URL printed, all field groups printed with real values. If any field is blank, go back to Task 6 Step 5 and fix the label string for that field.

- [ ] **Step 4: Commit**

```bash
git add pa/scraper.py
git commit -m "feat(pa): add probe command"
```

---

## Task 8: run command and full pipeline

**Files:**
- Modify: `pa/tests/test_scraper.py`
- Modify: `pa/scraper.py`

- [ ] **Step 1: Write failing test for output row assembly**

Append to `pa/tests/test_scraper.py`. Also update the import line at the top of the file to add `SCRAPED_FIELDS`:

```python
# Updated top-of-file import line:
from scraper import find_input_csv, load_done_ids, build_url, extract_fields, SCRAPED_FIELDS
```

Then append the test:

```python
def test_output_row_has_all_columns():
    input_row = {
        "Bid No": "6100066078",
        "Bid Type": "IFB",
        "Title": "Test Solicitation",
        "Description": "Short desc",
        "Agency": "Dept of Corrections",
        "County": "Wayne",
        "Bid Start Date": "5/27/2026",
        "Bid End Date": "6/10/2026 8:00:00 AM",
        "Bid Open Date": "6/10/2026 10:00:00 AM",
        "Status": "Open",
        "Buyer Name": "Bonnie Snyder",
        "Updated Date": "5/26/2026",
    }
    scraped = {k: "test_value" for k in SCRAPED_FIELDS if k != "scrape_status"}
    scraped["scrape_status"] = "success"
    scraped["solicitation_url"] = "https://emarketplace.state.pa.us/Solicitations.aspx?SID=6100066078"

    output_row = {**input_row, **scraped}

    # All input CSV columns present
    for col in input_row:
        assert col in output_row

    # All scraped columns present
    for col in SCRAPED_FIELDS:
        assert col in output_row

    # Total column count: 12 input + 16 scraped
    assert len(output_row) == 28
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_scraper.py::test_output_row_has_all_columns -v
```

Expected: `ImportError` — `SCRAPED_FIELDS` not importable yet (it's defined in scraper.py but test needs to verify the count). Confirm the test runs and checks the column count.

- [ ] **Step 3: Implement `run()` in `scraper.py`**

```python
def run():
    input_csv = find_input_csv(".")
    df = pd.read_csv(input_csv, dtype=str)
    done_ids = load_done_ids(OUTPUT_PATH)

    to_scrape = df[~df["Bid No"].astype(str).isin(done_ids)]
    total_new = len(to_scrape)
    print(f"Input: {len(df)} rows. Already done: {len(done_ids)}. To scrape: {total_new}")

    if total_new == 0:
        print("Nothing to do.")
        return

    # Load existing enriched rows to append to
    enriched = []
    if Path(OUTPUT_PATH).exists():
        enriched = pd.read_csv(OUTPUT_PATH, dtype=str).to_dict("records")

    session = make_session()
    success_count = 0
    error_count = 0

    for i, (_, row) in enumerate(to_scrape.iterrows(), 1):
        bid_no = str(row["Bid No"])
        url = build_url(bid_no)
        print(f"[{i}/{total_new}] {url}")

        try:
            html = fetch_page(session, url)
            scraped = extract_fields(html)
            scraped["solicitation_url"] = url
            scraped["scrape_status"] = "success"
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            scraped = EMPTY_SCRAPED.copy()
            scraped["solicitation_url"] = url
            scraped["scrape_status"] = "error"
            error_count += 1

        enriched.append({**row.to_dict(), **scraped})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {success_count} succeeded, {error_count} errored. Output: {OUTPUT_PATH}")
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_scraper.py::test_output_row_has_all_columns -v
```

Expected: 1 passed.

- [ ] **Step 5: Run full pipeline**

```bash
cd /Users/ml3787/Desktop/state-local/pa
python scraper.py run
```

Expected: progress printed per solicitation, `solicitations_enriched.csv` written incrementally.

- [ ] **Step 6: Verify output CSV has all expected columns**

```bash
python - <<'EOF'
import pandas as pd
df = pd.read_csv("solicitations_enriched.csv")
print(f"Rows: {len(df)}")
print(f"Columns ({len(df.columns)}):")
for col in df.columns:
    print(f"  {col}")
non_empty = {col: df[col].notna().sum() for col in df.columns}
print("\nNon-empty counts:")
for col, count in non_empty.items():
    print(f"  {col}: {count}/{len(df)}")
EOF
```

Expected: 28 columns, all 12 input columns present, all 16 scraped columns present. Check that `description_full` and `department_for_solicitation` have high non-empty counts (not all blank).

- [ ] **Step 7: Run all tests one final time**

```bash
python -m pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add pa/scraper.py pa/tests/test_scraper.py
git commit -m "feat(pa): add run command — full incremental scrape pipeline"
```

---

## Future Tasks (out of scope)

- Automate the CSV export step (reverse-engineer the Export Search Results POST)
- Parallelization with multiple concurrent sessions
- Schema normalization for DB import alongside SAM.gov / CA records
