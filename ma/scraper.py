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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
