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
BROWSER_CHECK_URL = "https://www.alabamabuys.gov/page.aspx/en/bas/browser_check"
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


def load_done_ids(output_path):
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "src_code" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "src_code"].astype(str))


def make_session():
    """
    Return a requests.Session pre-loaded with cookies that bypass the Alabama BUYS
    reCAPTCHA browser-check page.

    The portal uses Google reCAPTCHA Enterprise (invisible v3 mode).  A real Chromium
    browser must execute the captcha JS, score the session, POST the token, and be
    redirected to the intended page before we can extract a valid session cookie.

    Strategy:
      1. Launch real Chrome (non-headless) so reCAPTCHA sees a human-like environment.
      2. Navigate to the list page (redirects to browser_check automatically).
      3. Wait up to 60 s for the URL to leave browser_check (captcha auto-submits).
      4. Transfer the resulting ASP.NET_SessionId cookie to a requests.Session.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "ERROR: playwright is required to pass the Alabama BUYS browser check.\n"
            "Install it with: pip install playwright && playwright install chromium"
        )

    chrome_exe = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path=chrome_exe,
            headless=False,
            args=["--no-sandbox"],
        )
        context = browser.new_context(
            user_agent=UA,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()
        # Navigate to the list page — the portal redirects to browser_check first
        page.goto(BROWSE_URL, wait_until="domcontentloaded", timeout=30_000)
        # Wait up to 60 s for reCAPTCHA to auto-submit and redirect back
        try:
            page.wait_for_url(
                lambda url: "browser_check" not in url,
                timeout=60_000,
            )
        except Exception:
            browser.close()
            sys.exit(
                "ERROR: Alabama BUYS browser check did not complete within 60 s.\n"
                "The reCAPTCHA may have flagged the browser as a bot.  Try again."
            )
        cookies = context.cookies()
        browser.close()

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"])
    return session


# Real table has 14 columns.  Index 0 is the "Editing column" (icon link to the
# detail page).  Index 6 is "Remaining time".  Indices 12-13 are Begin/End dates.
# We skip the editing-column cell for text extraction but read its href.
# Column indices → field names (None = skip):
#   0  Editing column    → href only (detail_href)
#   1  Sourcing Project Number → src_code
#   2  Solicitation Label      → solicitation_label
#   3  Status                  → status
#   4  Award Status            → award_status
#   5  Due / Close Date        → due_close_date
#   6  Remaining time          → None (skip)
#   7  Main Commodity          → main_commodity
#   8  Solicitation Type       → solicitation_type
#   9  Buying Agency           → buying_agency
#  10  Sourcing Responsible First Name → sourcing_responsible_first
#  11  Sourcing Responsible Last Name  → sourcing_responsible_last
#  12  Begin (UTC-4)           → None (skip — scraped from detail page)
#  13  End (UTC-4)             → None (skip)

# Ordered list of (cell_index, field_key) pairs used in parse_list_page.
_CELL_MAP = [
    (1, "src_code"),
    (2, "solicitation_label"),
    (3, "status"),
    (4, "award_status"),
    (5, "due_close_date"),
    (7, "main_commodity"),
    (8, "solicitation_type"),
    (9, "buying_agency"),
    (10, "sourcing_responsible_first"),
    (11, "sourcing_responsible_last"),
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
    and total_pages is int.

    The real portal table has 14 columns.  Cell 0 is the "Editing column" whose
    anchor href is the detail page URL.  Cell 6 is "Remaining time" (skipped).
    See _CELL_MAP for the full index-to-key mapping.
    """
    soup = BeautifulSoup(html, "html.parser")
    total_pages = _parse_total_pages(soup)

    # The response contains multiple tables. The data grid has class "iv-grid-view".
    # It lives inside the iv-grid div; fall back to a soup-wide search if needed.
    grid_div = soup.find(id="body_x_grid_upgrid") or soup.find("div", class_="iv-grid")
    container = grid_div if grid_div else soup
    table = container.find("table", class_="iv-grid-view") or container.find("table")
    if not table:
        return [], total_pages

    # Rows may be directly in <table> (no <tbody> wrapper).
    tbody = table.find("tbody") or table

    # Minimum required: we need at least up to the last mapped cell index (11)
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
        # Detail href lives in cell 0 (the editing-column icon link)
        anchor = cells[0].find("a", href=True)
        row["detail_href"] = anchor["href"] if anchor else ""
        rows.append(row)

    return rows, total_pages


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


def discover_solicitations(session=None):
    """
    Paginate all pages of the public solicitations list.
    Returns list of row dicts (LIST_FIELDS) filtered to status == "Open for Bidding".

    Page 1 is fetched via the same AJAX POST as subsequent pages — the grid is
    always populated via the AJAX endpoint, never the initial GET response.

    Pass an existing session to reuse it (avoids a second reCAPTCHA challenge).
    make_session() already navigates to BROWSE_URL via Playwright, so no
    additional GET is needed to establish cookies here.
    """
    if session is None:
        session = make_session()

    all_rows = []
    page_n = 1
    total_pages = 1  # updated after first POST

    while page_n <= total_pages:
        time.sleep(DELAY_SECONDS)
        resp = session.post(AJAX_URL, data=_pagination_payload(page_n), timeout=30)
        resp.raise_for_status()
        rows, total_pages = parse_list_page(resp.text)
        all_rows.extend(rows)
        page_n += 1

    return [r for r in all_rows if r.get("status") == "Open for Bidding"]


def _label_value(soup, label_text):
    """
    Find the value associated with a labelled field.

    Alabama BUYS uses the Ivalua SaaS portal whose detail pages render each field as:

      <div data-iv-role="field" ...>
        <h3>
          <span data-iv-role="label" class="label-field">Label Text</span>
          [optional tooltip span]
        </h3>
        <div data-iv-role="controlWrapper" class="control-wrapper">
          <span|div data-iv-role="control" class="readonly">VALUE</span>
        </div>
      </div>

    Strategy: locate the label text node, walk up to the enclosing
    data-iv-role="field" div, then find the first data-iv-role="control"
    element inside it.

    Falls back through three legacy structures for fixture / unit-test
    compatibility:
      1. Text-node sibling: <strong>Label</strong> value text
      2. Tag sibling:       <strong>Label</strong><span>value</span>
      3. Grandparent's next sibling: <div><strong>Label</strong></div><div>value</div>
    """
    for el in soup.find_all(string=lambda t: t and t.strip() == label_text):
        label_el = el.parent  # typically <span class="label-field">

        # --- Primary path: Ivalua field/controlWrapper pattern ---
        field_div = label_el
        while field_div and field_div.get("data-iv-role") != "field":
            field_div = field_div.parent if field_div.parent else None
        if field_div:
            ctrl = field_div.find(attrs={"data-iv-role": "control"})
            if ctrl:
                return ctrl.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()

        # --- Legacy fallbacks (kept for unit-test fixtures) ---
        # Case 1: immediate text-node sibling
        raw = label_el.next_sibling
        if raw and isinstance(raw, str) and raw.strip():
            return raw.strip().replace("\xa0", " ").strip()
        # Case 2: next tag sibling
        tag_sibling = label_el.find_next_sibling()
        if tag_sibling:
            return tag_sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
        # Case 3: grandparent's next tag sibling
        grandparent_sibling = (
            label_el.parent.find_next_sibling() if label_el.parent else None
        )
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
    url = "https://www.alabamabuys.gov" + row["detail_href"]
    print(f"Probing: {url}\n")

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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
