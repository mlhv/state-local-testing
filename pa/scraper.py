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
BASE_URL = "https://www.emarketplace.state.pa.us/Solicitations.aspx"
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


def find_input_csv(directory="."):
    files = sorted(glob.glob(str(Path(directory) / INPUT_GLOB)))
    if not files:
        sys.exit(f"ERROR: No {INPUT_GLOB} found in {directory}")
    return files[-1]


def load_done_ids(output_path):
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "Bid No" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "Bid No"].astype(str))


def build_url(bid_no):
    return f"{BASE_URL}?SID={quote(str(bid_no))}"


def make_session():
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    return session


def fetch_page(session, url):
    resp = session.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text


def _cell_after_label(soup, label_text):
    for td in soup.find_all("td"):
        if td.get_text(strip=True) == label_text:
            sibling = td.find_next_sibling("td")
            if sibling:
                return sibling.get_text(separator=" ", strip=True).replace("\xa0", " ").strip()
    return ""


def _selected_radio(soup):
    for inp in soup.find_all("input", {"type": "radio"}):
        if inp.has_attr("checked"):
            label = inp.find_next("label")
            if label:
                return label.get_text(strip=True)
    return ""


def extract_fields(html):
    soup = BeautifulSoup(html, "html.parser")
    return {
        "department_for_solicitation": _cell_after_label(soup, "Department for this solicitation:"),
        "date_prepared":               _cell_after_label(soup, "Date Prepared:"),
        "advertisement_type":          _selected_radio(soup),
        "description_full":            _cell_after_label(soup, "Description:"),
        "delivery_location":           _cell_after_label(soup, "Delivery Location:"),
        "duration":                    _cell_after_label(soup, "Duration:"),
        "contact_first_name":          _cell_after_label(soup, "First Name:"),
        "contact_last_name":           _cell_after_label(soup, "Last Name:"),
        "contact_phone":               _cell_after_label(soup, "Phone Number:(XXX-XXX-XXXX)"),
        "contact_email":               _cell_after_label(soup, "Email:"),
        "solicitation_due_time":       _cell_after_label(soup, "Solicitation Due Time:"),
        "solicitation_opening_time":   _cell_after_label(soup, "Solicitation Opening Time:"),
        "opening_location":            _cell_after_label(soup, "Opening Location:"),
        "no_of_addendums":             _cell_after_label(soup, "No. of Addendums:"),
    }


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

    print("=== General Information ===")
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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
