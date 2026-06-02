# Massachusetts (COMMBUYS) Scraper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a resume-safe COMMBUYS scraper that reads `bidSearchResults.csv`, enriches each bid with detail page fields via BeautifulSoup, and writes `solicitations_enriched.csv` with 31 columns (10 input + 21 scraped).

**Architecture:** Self-contained PA clone in `ma/`. Fixed input filename (not a glob). `_cell_after_label` for header fields, dedicated helpers for ship-to contact, SBPP eligibility, and multi-item UNSPSC data. `probe`/`run` commands. Resume-safe write-after-each-record loop.

**Tech Stack:** Python 3, requests, BeautifulSoup4, pandas. Root venv at `/Users/ml3787/Desktop/state-local/venv/`.

**Spec:** `docs/superpowers/specs/2026-05-28-ma-scraper-design.md`

---

## File Map

| File | Action | Purpose |
|---|---|---|
| `ma/requirements.txt` | Create | requests, pandas, beautifulsoup4 |
| `ma/scraper.py` | Create | All scraper logic |
| `ma/tests/test_scraper.py` | Create | All tests |
| `ma/tests/fixtures/sample_bid.html` | Create | Real COMMBUYS page with 2+ items |
| `.gitignore` | Modify | Add ma/ input/output files |
| `HANDOFF.md` | Modify | Add Massachusetts row |

---

## Task 1: Scaffold

**Files:**
- Create: `ma/requirements.txt`
- Create: `ma/scraper.py`

- [ ] **Step 1: Create `ma/requirements.txt`**

```
requests
pandas
beautifulsoup4
```

- [ ] **Step 2: Create `ma/scraper.py` skeleton**

```python
"""
MA COMMBUYS solicitation scraper.
Usage:
  python scraper.py probe   -- fetch one new record and print all extracted fields
  python scraper.py run     -- process all new/errored records
"""

import sys
import time
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup

INPUT_PATH = "bidSearchResults.csv"
OUTPUT_PATH = "solicitations_enriched.csv"
DELAY_SECONDS = 0.5
BASE_URL = "https://www.commbuys.com/bso/external/bidDetail.sda"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

SCRAPED_FIELDS = [
    "department",
    "location",
    "fiscal_year",
    "type_code",
    "allow_electronic_quote",
    "required_date",
    "available_date",
    "info_contact",
    "bid_type",
    "informal_bid_flag",
    "purchase_method",
    "pre_bid_conference",
    "bulletin_desc",
    "ship_to_email",
    "ship_to_phone",
    "sbpp_eligible",
    "item_descriptions",
    "unspsc_codes",
    "unspsc_descriptions",
    "ma_url",
    "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
```

- [ ] **Step 3: Install dependencies**

Run from `ma/`:
```bash
/Users/ml3787/Desktop/state-local/venv/bin/pip install -r requirements.txt
```
Expected: `Successfully installed` or `already satisfied` for all three packages.

- [ ] **Step 4: Commit**

```bash
git add ma/requirements.txt ma/scraper.py
git commit -m "feat(ma): scaffold scraper with constants and SCRAPED_FIELDS"
```

---

## Task 2: HTML Fixture

**Files:**
- Create: `ma/tests/fixtures/sample_bid.html`

We need a real COMMBUYS detail page with **2 or more items** in the Item Information section. This fixture drives all extraction tests.

- [ ] **Step 1: Create fixture directory**

```bash
mkdir -p /Users/ml3787/Desktop/state-local/ma/tests/fixtures
```

- [ ] **Step 2: Download a 2-item bid**

Run from `ma/`:
```python
# Run with: /Users/ml3787/Desktop/state-local/venv/bin/python3 -c "..."
import requests, pandas as pd
df = pd.read_csv("bidSearchResults.csv", dtype=str)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
for bid_id in df["Bid Solicitation #"]:
    url = f"https://www.commbuys.com/bso/external/bidDetail.sda?docId={bid_id}"
    r = requests.get(url, headers={"User-Agent": UA}, timeout=15)
    if "Item # 2:" in r.text:
        with open("tests/fixtures/sample_bid.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        print(f"Saved fixture from bid: {bid_id}")
        break
else:
    print("No 2-item bid found in first batch — try more rows")
```

- [ ] **Step 3: Verify fixture**

```bash
grep -c "Item #" /Users/ml3787/Desktop/state-local/ma/tests/fixtures/sample_bid.html
```
Expected: `2` or higher.

- [ ] **Step 4: Commit**

```bash
git add ma/tests/fixtures/sample_bid.html
git commit -m "test(ma): add sample_bid.html fixture with 2+ items"
```

---

## Task 3: Core Utilities (TDD)

**Files:**
- Create: `ma/tests/test_scraper.py`
- Modify: `ma/scraper.py`

- [ ] **Step 1: Write failing tests**

Create `ma/tests/test_scraper.py`:
```python
import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import find_input_csv, load_done_ids, build_url, SCRAPED_FIELDS


def test_find_input_csv_exits_when_none_found(tmp_path):
    with pytest.raises(SystemExit):
        find_input_csv(str(tmp_path))


def test_find_input_csv_returns_path_when_present(tmp_path):
    (tmp_path / "bidSearchResults.csv").write_text('"Bid Solicitation #"\n"BD-25-0001"')
    result = find_input_csv(str(tmp_path))
    assert result.endswith("bidSearchResults.csv")


def test_load_done_ids_returns_empty_when_no_output(tmp_path):
    result = load_done_ids(str(tmp_path / "solicitations_enriched.csv"))
    assert result == set()


def test_load_done_ids_skips_error_rows(tmp_path):
    output = tmp_path / "solicitations_enriched.csv"
    output.write_text(
        '"Bid Solicitation #",scrape_status\n'
        '"BD-25-0001",success\n'
        '"BD-25-0002",error\n'
        '"BD-25-0003",success\n'
    )
    result = load_done_ids(str(output))
    assert result == {"BD-25-0001", "BD-25-0003"}
    assert "BD-25-0002" not in result


def test_load_done_ids_excludes_error_rows_so_run_wont_duplicate(tmp_path):
    output = tmp_path / "solicitations_enriched.csv"
    output.write_text(
        '"Bid Solicitation #",scrape_status\n'
        '"BD-25-AAA",success\n'
        '"BD-25-BBB",error\n'
    )
    done_ids = load_done_ids(str(output))
    assert "BD-25-BBB" not in done_ids
    all_rows = pd.read_csv(str(output), dtype=str).to_dict("records")
    enriched = [r for r in all_rows if r.get("scrape_status") == "success"]
    bid_nos = [r["Bid Solicitation #"] for r in enriched]
    assert "BD-25-BBB" not in bid_nos
    assert "BD-25-AAA" in bid_nos


def test_build_url():
    assert build_url("BD-25-1374-PROCU-PROCU-129995") == (
        "https://www.commbuys.com/bso/external/bidDetail.sda"
        "?docId=BD-25-1374-PROCU-PROCU-129995"
    )
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /Users/ml3787/Desktop/state-local/ma
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -k "find_input or load_done or build_url" -v
```
Expected: `ImportError` or `NameError` — functions not yet defined.

- [ ] **Step 3: Implement utilities in `scraper.py`**

Add after the `EMPTY_SCRAPED` line:
```python
def find_input_csv(directory="."):
    path = Path(directory) / INPUT_PATH
    if not path.exists():
        sys.exit(f"ERROR: {INPUT_PATH} not found in {directory}")
    return str(path)


def load_done_ids(output_path):
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "Bid Solicitation #" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "Bid Solicitation #"].astype(str))


def build_url(bid_id):
    return f"{BASE_URL}?docId={bid_id}"


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    return session


def fetch_page(session, url):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text
```

- [ ] **Step 4: Run to verify they pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -k "find_input or load_done or build_url" -v
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add ma/scraper.py ma/tests/test_scraper.py
git commit -m "feat(ma): add core utilities — find_input_csv, load_done_ids, build_url"
```

---

## Task 4: Extraction Helpers + extract_fields() (TDD)

**Files:**
- Modify: `ma/tests/test_scraper.py`
- Modify: `ma/scraper.py`

Before implementing, **inspect the fixture HTML** to understand the actual DOM structure around Item sections and UNSPSC labels. Run:

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python3 -c "
from bs4 import BeautifulSoup
html = open('tests/fixtures/sample_bid.html', encoding='utf-8').read()
soup = BeautifulSoup(html, 'html.parser')
# Find item headers
for b in soup.find_all('b'):
    if b.get_text(strip=True).startswith('Item #'):
        print('=== ITEM B TAG ===')
        print(repr(b.parent))
        print()
# Find UNSPSC label
for td in soup.find_all('td'):
    if 'UNSPSC' in td.get_text(strip=True).replace(' ', ''):
        print('=== UNSPSC TD ===')
        print(repr(td))
        print('=== NEXT SIBLING ===')
        print(repr(td.find_next_sibling('td')))
        print()
        break
"
```

Use this output to verify the implementation below matches the actual structure. Adjust `_extract_items` if needed.

- [ ] **Step 1: Add extraction tests to `test_scraper.py`**

Append to the existing test file. First update the import line at the top of `test_scraper.py` to:
```python
from scraper import find_input_csv, load_done_ids, build_url, SCRAPED_FIELDS, extract_fields
```

Then append these tests:
```python

FIXTURE = Path(__file__).parent / "fixtures" / "sample_bid.html"


def test_extract_fields_returns_all_keys():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    expected_keys = [k for k in SCRAPED_FIELDS if k not in ("ma_url", "scrape_status")]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_extract_fields_values_are_strings():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    for key, val in result.items():
        assert isinstance(val, str), f"{key} is not a string: {type(val)}"


def test_extract_fields_no_empty_critical_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    assert result["bid_type"] != "", "bid_type should not be empty"
    assert result["purchase_method"] != "", "purchase_method should not be empty"


def test_pipe_delimited_items():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    assert "|" in result["unspsc_codes"], "Expected pipe-delimited codes for 2+ item bid"
    codes = result["unspsc_codes"].split("|")
    descs = result["item_descriptions"].split("|")
    unspsc_descs = result["unspsc_descriptions"].split("|")
    assert len(codes) == len(descs) == len(unspsc_descs), "Item field lists must be same length"
    assert all(c != "" for c in codes), "All UNSPSC codes should be non-empty"


def test_output_row_has_all_columns():
    input_row = {
        "Bid Solicitation #": "BD-25-1374-PROCU-PROCU-129995",
        "Organization Name": "Town of Winthrop",
        "Blanket #": "",
        "Buyer": "Dylan Cook",
        "Description": "IFB 2027-06 Steel Work for RTU Install",
        "Bid Opening Date": "06/11/2026 11:00:00",
        "Bid Holder List": "",
        "Awarded Vendor(s)": "",
        "Status": "Sent",
        "Alternate Id": "",
    }
    scraped = {k: "test_value" for k in SCRAPED_FIELDS if k not in ("scrape_status", "ma_url")}
    scraped["scrape_status"] = "success"
    scraped["ma_url"] = "https://www.commbuys.com/bso/external/bidDetail.sda?docId=BD-25-1374-PROCU-PROCU-129995"
    output_row = {**input_row, **scraped}
    for col in input_row:
        assert col in output_row
    for col in SCRAPED_FIELDS:
        assert col in output_row
    assert len(output_row) == 31  # 10 input + 21 scraped
```

- [ ] **Step 2: Run to verify they fail**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -k "extract_fields or pipe_delimited or output_row" -v
```
Expected: `ImportError` — `extract_fields` not yet defined.

- [ ] **Step 3: Implement all extraction helpers in `scraper.py`**

Add after `fetch_page`:
```python
def _cell_after_label(soup, label_text):
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == label_text:
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
    return ""


def _extract_ship_to_contact(soup):
    email = ""
    phone = ""
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == "Ship-to Address:":
            sibling = td.find_next_sibling("td")
            if sibling:
                for line in sibling.get_text(separator="\n", strip=True).split("\n"):
                    line = line.strip()
                    if line.startswith("Email:"):
                        email = line[len("Email:"):].strip()
                    elif line.startswith("Phone:"):
                        phone = line[len("Phone:"):].strip()
            break
    return email, phone


def _extract_sbpp_eligible(soup):
    for td in soup.find_all("td"):
        if "SBPP" in td.get_text() and "Eligible" in td.get_text():
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(strip=True)
    return ""


def _extract_items(soup):
    """Return (item_descriptions, unspsc_codes, unspsc_descriptions) as pipe-joined strings.

    Each item block starts with a <b> tag: "Item # N:  ( code )".
    The UNSPSC code is a link in the td following the "U N S P S C Code:" label td.
    The UNSPSC description is the text node immediately after that link.
    """
    item_descs = []
    codes = []
    code_descs = []

    for bold in soup.find_all("b"):
        raw = bold.get_text(strip=True)
        if not raw.startswith("Item #"):
            continue

        # Description: parent element text minus the bold header prefix
        parent_text = bold.parent.get_text(separator=" ", strip=True)
        item_descs.append(parent_text[len(raw):].strip())

        unspsc_code = ""
        unspsc_desc = ""

        for td in bold.find_all_next("td"):
            # Stop when the next item's bold header is encountered
            inner_b = td.find("b")
            if inner_b and inner_b.get_text(strip=True).startswith("Item #"):
                break
            # Match "U N S P S C Code:" regardless of internal spacing
            if "UNSPSC" in td.get_text(strip=True).replace(" ", ""):
                # Code link may be in this td or the next sibling td
                a_tag = td.find("a")
                if a_tag is None:
                    sib = td.find_next_sibling("td")
                    if sib:
                        a_tag = sib.find("a")
                if a_tag:
                    unspsc_code = a_tag.get_text(strip=True)
                    for node in a_tag.next_siblings:
                        t = (
                            node.get_text(strip=True)
                            if hasattr(node, "get_text")
                            else str(node).strip()
                        )
                        t = t.replace("\xa0", "").strip()
                        if t:
                            unspsc_desc = t
                            break
                break

        codes.append(unspsc_code)
        code_descs.append(unspsc_desc)

    return "|".join(item_descs), "|".join(codes), "|".join(code_descs)


def extract_fields(html):
    soup = BeautifulSoup(html, "html.parser")
    ship_to_email, ship_to_phone = _extract_ship_to_contact(soup)
    item_descriptions, unspsc_codes, unspsc_descriptions = _extract_items(soup)
    return {
        "department":             _cell_after_label(soup, "Department:"),
        "location":               _cell_after_label(soup, "Location:"),
        "fiscal_year":            _cell_after_label(soup, "Fiscal Year:"),
        "type_code":              _cell_after_label(soup, "Type Code:"),
        "allow_electronic_quote": _cell_after_label(soup, "Allow Electronic Quote:"),
        "required_date":          _cell_after_label(soup, "Required Date:"),
        "available_date":         _cell_after_label(soup, "Available Date :"),
        "info_contact":           _cell_after_label(soup, "Info Contact:"),
        "bid_type":               _cell_after_label(soup, "Bid Type:"),
        "informal_bid_flag":      _cell_after_label(soup, "Informal Bid Flag:"),
        "purchase_method":        _cell_after_label(soup, "Purchase Method:"),
        "pre_bid_conference":     _cell_after_label(soup, "Pre Bid Conference:"),
        "bulletin_desc":          _cell_after_label(soup, "Bulletin Desc:"),
        "ship_to_email":          ship_to_email,
        "ship_to_phone":          ship_to_phone,
        "sbpp_eligible":          _extract_sbpp_eligible(soup),
        "item_descriptions":      item_descriptions,
        "unspsc_codes":           unspsc_codes,
        "unspsc_descriptions":    unspsc_descriptions,
    }
```

**Note on label strings:** The exact label text (e.g., `"Available Date :"` has a trailing space before the colon) must match character-for-character what appears in the HTML. After running tests, if any critical field returns empty, use the fixture inspector from above to find the exact label text and adjust.

- [ ] **Step 4: Run to verify tests pass**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: all tests pass. If `test_pipe_delimited_items` fails because `unspsc_codes` is empty, re-run the fixture inspector to find the actual UNSPSC label text and structure, then adjust `_extract_items`.

- [ ] **Step 5: Commit**

```bash
git add ma/scraper.py ma/tests/test_scraper.py
git commit -m "feat(ma): add extraction helpers and extract_fields()"
```

---

## Task 5: probe() and run() Commands

**Files:**
- Modify: `ma/scraper.py`

No new tests — these commands are exercised via smoke test after implementation.

- [ ] **Step 1: Add `probe()` to `scraper.py`**

```python
def probe():
    input_csv = find_input_csv(".")
    df = pd.read_csv(input_csv, dtype=str)
    done_ids = load_done_ids(OUTPUT_PATH)

    new_rows = df[~df["Bid Solicitation #"].astype(str).isin(done_ids)]
    if new_rows.empty:
        print("No new solicitations to probe.")
        return

    row = new_rows.iloc[0]
    bid_id = str(row["Bid Solicitation #"])
    url = build_url(bid_id)
    print(f"Probing: {url}\n")

    session = make_session()
    try:
        html = fetch_page(session, url)
    except Exception as e:
        sys.exit(f"ERROR fetching {url}: {e}")
    fields = extract_fields(html)

    print("=== Header Information ===")
    print(f"Department:             {fields['department']}")
    print(f"Location:               {fields['location']}")
    print(f"Fiscal Year:            {fields['fiscal_year']}")
    print(f"Type Code:              {fields['type_code']}")
    print(f"Allow Electronic Quote: {fields['allow_electronic_quote']}")
    print(f"Required Date:          {fields['required_date']}")
    print(f"Available Date:         {fields['available_date']}")
    print(f"Info Contact:           {fields['info_contact']}")
    print(f"Bid Type:               {fields['bid_type']}")
    print(f"Informal Bid Flag:      {fields['informal_bid_flag']}")
    print(f"Purchase Method:        {fields['purchase_method']}")
    print(f"\n=== Pre Bid Conference ===")
    print(fields["pre_bid_conference"] or "(none)")
    print(f"\n=== Bulletin Desc ===")
    bd = fields["bulletin_desc"]
    print(bd[:500] + ("..." if len(bd) > 500 else ""))
    print(f"\n=== Contact (Ship-to) ===")
    print(f"Email: {fields['ship_to_email']}")
    print(f"Phone: {fields['ship_to_phone']}")
    print(f"\n=== SBPP Eligibility ===")
    print(f"SBPP Eligible: {fields['sbpp_eligible'] or '(not specified)'}")
    item_count = len([c for c in fields["unspsc_codes"].split("|") if c])
    print(f"\n=== Items ({item_count} item(s)) ===")
    for i, (code, code_desc, item_desc) in enumerate(zip(
        fields["unspsc_codes"].split("|"),
        fields["unspsc_descriptions"].split("|"),
        fields["item_descriptions"].split("|"),
    ), 1):
        print(f"Item {i}: UNSPSC {code} — {code_desc}")
        print(f"  Desc: {item_desc[:200]}{'...' if len(item_desc) > 200 else ''}")
```

- [ ] **Step 2: Add `run()` to `scraper.py`**

```python
def run():
    input_csv = find_input_csv(".")
    df = pd.read_csv(input_csv, dtype=str)
    done_ids = load_done_ids(OUTPUT_PATH)

    to_scrape = df[~df["Bid Solicitation #"].astype(str).isin(done_ids)]
    total_new = len(to_scrape)
    print(f"Input: {len(df)} rows. Already done: {len(done_ids)}. To scrape: {total_new}")

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

    for i, (_, row) in enumerate(to_scrape.iterrows(), 1):
        bid_id = str(row["Bid Solicitation #"])
        url = build_url(bid_id)
        print(f"[{i}/{total_new}] {url}")

        try:
            html = fetch_page(session, url)
            scraped = extract_fields(html)
            scraped["ma_url"] = url
            scraped["scrape_status"] = "success"
            success_count += 1
        except Exception as e:
            print(f"  ERROR: {e}")
            scraped = EMPTY_SCRAPED.copy()
            scraped["ma_url"] = url
            scraped["scrape_status"] = "error"
            error_count += 1

        enriched.append({**row.to_dict(), **scraped})
        pd.DataFrame(enriched).to_csv(OUTPUT_PATH, index=False)
        time.sleep(DELAY_SECONDS)

    print(f"\nDone. {success_count} succeeded, {error_count} errored. Output: {OUTPUT_PATH}")
```

- [ ] **Step 3: Smoke test — run probe**

```bash
cd /Users/ml3787/Desktop/state-local/ma
/Users/ml3787/Desktop/state-local/venv/bin/python scraper.py probe
```
Expected: prints a URL and all field sections with real data. Verify:
- At least one header field (e.g. `Bid Type`, `Purchase Method`) is non-empty
- UNSPSC section shows `Item 1: UNSPSC <code> — <description>`
- No Python exceptions

- [ ] **Step 4: Run all tests one final time**

```bash
/Users/ml3787/Desktop/state-local/venv/bin/python -m pytest tests/test_scraper.py -v
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add ma/scraper.py
git commit -m "feat(ma): add probe() and run() commands"
```

---

## Task 6: Gitignore + HANDOFF.md

**Files:**
- Modify: `.gitignore`
- Modify: `HANDOFF.md`

- [ ] **Step 1: Update `.gitignore`**

Add to the root `.gitignore`:
```
ma/bidSearchResults.csv
ma/solicitations_enriched.csv
```

- [ ] **Step 2: Update `HANDOFF.md`**

In the State Status table, add a row for Massachusetts:
```markdown
| Massachusetts | ✅ Complete | `ma/` | COMMBUYS | Manual CSV export | `solicitations_enriched.csv` (31 cols) |
```

Also add a Massachusetts section after the Pennsylvania section:
```markdown
## Massachusetts (COMMBUYS)

**Portal:** https://www.commbuys.com/bso/view/search/external/advancedSearchBid.xhtml?openBids=true

**How it works:** Server-rendered HTML (Periscope S2G / JSF). Bid detail pages are fully rendered in the HTML response — no JS execution needed. The scraper GETs each detail page and parses it with BeautifulSoup. Header fields use label-text matching. Ship-to contact info, SBPP eligibility, and multi-item UNSPSC data use dedicated helpers. Items are pipe-delimited when a solicitation has multiple line items.

**Run:**
```bash
cd ma
source ../venv/bin/activate
# Export CSV from COMMBUYS (Bid Solicitations, open bids, Export to CSV)
python scraper.py probe
python scraper.py run
```

**Key files:** `ma/POSTDEV.md` (post-dev notes), `ma/tests/` (11 tests)

**Known gaps:** DB normalization, automated CSV export
```

- [ ] **Step 3: Commit**

```bash
git add .gitignore HANDOFF.md
git commit -m "docs: add MA to gitignore and HANDOFF.md"
```
