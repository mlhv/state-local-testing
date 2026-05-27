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
BASE_URL = "https://emarketplace.state.pa.us/Solicitations.aspx"
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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
