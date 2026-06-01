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
    and total_pages is int.
    """
    soup = BeautifulSoup(html, "html.parser")
    total_pages = _parse_total_pages(soup)

    table = soup.find("table")
    if not table:
        return [], total_pages

    tbody = table.find("tbody")
    if not tbody:
        return [], total_pages

    rows = []
    for tr in tbody.find_all("tr"):
        cells = tr.find_all("td")
        if len(cells) < len(COLUMN_KEYS):
            continue
        row = {}
        for key, cell in zip(COLUMN_KEYS, cells):
            row[key] = cell.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
        # Extract detail href from the anchor in the first cell
        anchor = cells[0].find("a", href=True)
        row["detail_href"] = anchor["href"] if anchor else ""
        # src_code is the link text
        if anchor:
            row["src_code"] = anchor.get_text(strip=True)
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


def _label_value(soup, label_text):
    """
    Find the first element whose text matches label_text, then return
    the adjacent value. Handles three structures common in Ivalua portals:
      1. Text node sibling: <strong>Label</strong> value text
      2. Tag sibling:       <strong>Label</strong><span>value</span>
      3. Grandparent sibling: <div><strong>Label</strong></div><div>value</div>
    """
    for el in soup.find_all(string=lambda t: t and t.strip() == label_text):
        parent = el.parent
        # Case 1: immediate text-node sibling
        raw = parent.next_sibling
        if raw and isinstance(raw, str) and raw.strip():
            return raw.strip().replace("\xa0", " ").strip()
        # Case 2: next tag sibling
        tag_sibling = parent.find_next_sibling()
        if tag_sibling:
            return tag_sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
        # Case 3: grandparent's next tag sibling (nested structure)
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
