"""
MA COMMBUYS solicitation scraper.
Usage:
  python scraper.py probe   -- fetch one new record and print all extracted fields
  python scraper.py run     -- process all new/errored records
"""

import re as _re
import sys
import time
import requests
import pandas as pd
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString

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


# ---------------------------------------------------------------------------
# HTML extraction helpers
# ---------------------------------------------------------------------------


def _normalize(text):
    """Collapse internal whitespace so multi-line label TDs compare cleanly."""
    return _re.sub(r"\s+", " ", text).strip()


def _cell_after_label(soup, label_text):
    """Return the text of the <td> immediately after the label <td>."""
    for td in soup.find_all("td"):
        if _normalize(td.get_text(strip=True)) == label_text:
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
    return ""


def _extract_ship_to_contact(soup):
    """Extract email and phone from the Ship-to Address sibling TD."""
    email = ""
    phone = ""
    for td in soup.find_all("td"):
        if _normalize(td.get_text(strip=True)) == "Ship-to Address:":
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
    """Return SBPP Eligible value, or empty string if the field is absent."""
    for td in soup.find_all("td"):
        if "SBPP" in td.get_text() and "Eligible" in td.get_text():
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(strip=True)
    return ""


def _extract_items(soup):
    """
    Return (item_descriptions, unspsc_codes, unspsc_descriptions) as
    pipe-joined strings, one segment per item.

    Item header TDs have class exactly ['t-head-01'] (not 'whcmFix') and
    contain 'Item #'.  The 5-segment UNSPSC code sits in parentheses inside
    that same TD.  The item description is in the following inputs-01 TD.
    The UNSPSC top-level code is the first <u> tag in the tableText-01 value
    TD that follows a 'U N S P S C Code:' label TD.
    """
    tds = list(soup.find_all("td"))
    item_descs = []
    codes = []
    code_descs = []

    for idx, td in enumerate(tds):
        classes = set(td.get("class") or [])
        # Only the non-whcmFix t-head-01 td to avoid duplicates
        if classes != {"t-head-01"}:
            continue
        text = td.get_text(strip=True)
        if "Item #" not in text:
            continue

        # 5-segment UNSPSC code from parentheses in the header td
        m = _re.search(r"\(\s*([\d-]+)\s*\)", td.get_text(separator=" ", strip=True))
        item_code = m.group(1) if m else ""

        # Item description: next inputs-01 td
        item_desc = ""
        for j in range(idx + 1, min(idx + 10, len(tds))):
            c = tds[j].get("class") or []
            if "inputs-01" in c:
                item_desc = tds[j].get_text(strip=True)
                break

        # UNSPSC label + value: look for 'U N S P S C Code:' label td
        unspsc_code = item_code  # fall back to header code if label not found
        unspsc_desc = ""
        for j in range(idx + 1, min(idx + 25, len(tds))):
            label_text = tds[j].get_text(strip=True)
            if label_text == "U N S P S C Code:":
                if j + 1 < len(tds):
                    value_td = tds[j + 1]
                    u_tag = value_td.find("u")
                    if u_tag:
                        unspsc_code = u_tag.get_text(strip=True)
                    # Description is the first non-empty NavigableString after <br/>
                    for child in value_td.children:
                        if isinstance(child, NavigableString):
                            t2 = str(child).replace("\xa0", "").strip()
                            if t2:
                                unspsc_desc = t2
                                break
                break

        item_descs.append(item_desc)
        codes.append(unspsc_code)
        code_descs.append(unspsc_desc)

    return "|".join(item_descs), "|".join(codes), "|".join(code_descs)


def extract_fields(html):
    """Parse a COMMBUYS bid detail HTML page and return a dict of scraped fields."""
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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
