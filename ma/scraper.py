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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
