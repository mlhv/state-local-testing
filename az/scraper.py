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
