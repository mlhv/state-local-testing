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


# Cell index → field key for Arizona's 12-column grid.
# 0  Edit + title    → detail_href (href only)
# 1  Code            → src_code
# 2  Label           → solicitation_label
# 3  Created date    → (skipped)
# 4  Commodity       → commodity
# 5  Agency          → buying_agency
# 6  Empty/icon      → (skipped)
# 7  Status          → status
# 8  RFx Awarded     → rfx_awarded
# 9  Countdown timer → (skipped)
# 10 Begin (UTC-7)   → begin_date
# 11 End (UTC-7)     → end_date
_CELL_MAP = [
    (1, "src_code"),
    (2, "solicitation_label"),
    (4, "commodity"),
    (5, "buying_agency"),
    (7, "status"),
    (8, "rfx_awarded"),
    (10, "begin_date"),
    (11, "end_date"),
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

    Handles three Ivalua control patterns found inside data-iv-role="controlWrapper":
      1. Dropdown / multi-selector — data-iv-role contains both "control" and "selector";
         displayed value in .selected_label spans (multi) or .text div (single).
      2. Input element — <input data-iv-role="control">; read value= attribute.
      3. Readonly span / div — data-iv-role="control"; read via get_text().
    """
    for el in soup.find_all(string=lambda t: t and t.strip() == label_text):
        label_el = el.parent

        # Walk up to the enclosing data-iv-role="field" div
        field_div = label_el
        while field_div and field_div.get("data-iv-role") != "field":
            field_div = field_div.parent if field_div.parent else None
        if not field_div:
            continue

        wrapper = field_div.find(attrs={"data-iv-role": "controlWrapper"})
        if not wrapper:
            continue

        # 1. Selector controls (dropdown / multi-selector)
        sel = wrapper.find(
            lambda tag: "control" in tag.get("data-iv-role", "")
            and "selector" in tag.get("data-iv-role", "")
        )
        if sel:
            labels = [s.get_text(separator=" ", strip=True)
                      for s in sel.find_all(class_="selected_label")]
            if labels:
                return " | ".join(labels).replace("\xa0", " ").strip()
            for tdiv in sel.find_all(class_="text"):
                if "default" not in (tdiv.get("class") or []):
                    t = tdiv.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
                    if t:
                        return t
            continue

        # 2. Input element — read value attribute (get_text() always returns "")
        inp = wrapper.find("input", attrs={"data-iv-role": "control"})
        if inp:
            return (inp.get("value") or "").strip()

        # 3. Readonly span or div
        ctrl = wrapper.find(attrs={"data-iv-role": "control"})
        if ctrl and ctrl.name in ("span", "div"):
            return ctrl.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()

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


# Payload for AJAX grid pagination.
# The server is stateless — filter fields must be included on every request,
# exactly as the browser resends them with each page-navigation click.
_BASE_PAYLOAD = {
    "__EVENTTARGET": "body_x_grid_grd",
    "__LASTFOCUS": "",
    "REQUEST_METHOD": "GET",
    "hdnUserValue": ",body_x_selStatusCode_1",
    "body:x:selStatusCode_1": "val",
    "body_x_selStatusCode_1_text": "",
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

    patchright's automation fingerprint patches cause reCAPTCHA v2 to auto-pass
    without manual interaction. Strategy:
      1. Launch real Chrome (non-headless) via patchright with persistent profile.
      2. Warm up by visiting google.com and bing.com to deposit Google-domain cookies.
      3. Navigate to the portal list page; wait for the solicitations grid to appear
         (confirms reCAPTCHA passed and page loaded).
      4. Extract cookies into a requests.Session.
    """
    try:
        from patchright.sync_api import sync_playwright
    except ImportError:
        sys.exit(
            "ERROR: patchright is required to pass the Arizona browser check.\n"
            "Install: pip install patchright && patchright install chromium"
        )

    print("Launching Chrome...")
    pw = sync_playwright().start()
    context = pw.chromium.launch_persistent_context(
        user_data_dir=str(USER_DATA_DIR),
        headless=False,
        channel="chrome",
    )
    page = context.new_page()

    for warmup_url in ["https://www.google.com", "https://www.bing.com"]:
        try:
            print(f"Warming up: {warmup_url}")
            page.goto(warmup_url, wait_until="domcontentloaded", timeout=15_000)
            time.sleep(2)
        except Exception:
            pass

    print(f"Loading portal: {BROWSE_URL}")
    page.goto(BROWSE_URL, wait_until="domcontentloaded", timeout=30_000)
    print("Waiting for reCAPTCHA to pass and grid to load...")
    try:
        page.wait_for_selector("#body_x_grid_upgrid", timeout=60_000)
    except Exception:
        pw.stop()
        sys.exit(
            "ERROR: Arizona portal grid did not load within 60 s.\n"
            "The reCAPTCHA may have flagged the browser. Try again."
        )
    print("Grid loaded.")

    # Navigate to a detail page to pass the /bpm/ browser check.
    # The check is module-scoped: the /rfp/ cookie above doesn't cover /bpm/.
    # On the first run this may require a manual CAPTCHA solve; the persistent
    # profile caches the result so subsequent runs pass automatically.
    try:
        href = page.get_attribute(
            "#body_x_grid_upgrid a[href*='process_manage']", "href"
        )
        if href:
            print(f"Passing /bpm/ browser check via detail page...")
            page.goto(BASE_URL + href, wait_until="domcontentloaded", timeout=30_000)
            try:
                page.wait_for_selector("#body_x_tabc_rfp_ext", timeout=15_000)
                print("/bpm/ check passed.")
            except Exception:
                print(
                    "\nBrowser check required for detail pages.\n"
                    "Please complete the CAPTCHA in the Chrome window, then press Enter..."
                )
                input()
    except Exception:
        pass

    cookies = context.cookies()
    # Keep page alive — callers use page.evaluate() to fetch detail pages via
    # the browser's JS fetch(), which carries all cookies without triggering a
    # new navigation-based browser check.  Caller must call pw.stop() when done.

    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    for c in cookies:
        session.cookies.set(c["name"], c["value"], domain=c["domain"])
    return session, page, pw


def discover_solicitations(session, page):
    """
    Paginate the "Open for Bidding" solicitations list via AJAX POST.

    The filter is applied stateless — _BASE_PAYLOAD includes body:x:selStatusCode_1=val
    on every request, so the server re-applies it each time without session state.
    """
    all_rows = []
    seen_src_codes = set()
    page_n = 1

    while True:
        time.sleep(DELAY_SECONDS)
        print(f"  Fetching page {page_n}...", end=" ", flush=True)
        resp = session.post(AJAX_URL, data=_pagination_payload(page_n), timeout=30)
        resp.raise_for_status()
        rows, reported_pages = parse_list_page(resp.text)
        if not rows:
            print("empty — done.")
            break
        new_rows = [r for r in rows if r["src_code"] not in seen_src_codes]
        if not new_rows:
            print("all duplicates — done.")
            break
        for r in new_rows:
            seen_src_codes.add(r["src_code"])
        all_rows.extend(new_rows)
        print(f"{len(new_rows)} rows (total {len(all_rows)}, pager shows {reported_pages} pages)")
        if page_n >= reported_pages:
            break
        page_n += 1

    return [r for r in all_rows if r.get("status") == "Open for Bidding"]


def _browser_get(page, url):
    """Fetch a URL via the browser's JS fetch() — bypasses path-scoped browser checks."""
    return page.evaluate(
        f"fetch({url!r}, {{credentials: 'include'}}).then(r => r.text())"
    )


def probe():
    session, page, pw = make_session()
    try:
        print("Discovering solicitations (paginating list)...")
        open_rows = discover_solicitations(session, page)
        done_ids = load_done_ids(OUTPUT_PATH)

        new_rows = [r for r in open_rows if r["src_code"] not in done_ids]
        if not new_rows:
            print("No new open solicitations to probe.")
            return

        row = new_rows[0]
        url = BASE_URL + row["detail_href"]
        print(f"Probing: {url}\n")

        try:
            html = _browser_get(page, url)
            fields = extract_fields(html)
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
    finally:
        pw.stop()


def run():
    session, page, pw = make_session()
    try:
        print("Discovering solicitations (paginating list)...")
        open_rows = discover_solicitations(session, page)
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
                html = _browser_get(page, url)
                scraped = extract_fields(html)
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
    finally:
        pw.stop()


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
