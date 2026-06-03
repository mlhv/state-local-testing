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
    but we also apply a client-side filter to guard against edge cases.

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

    return [r for r in all_rows if r.get("status") == "Open for Bidding"]


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
