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


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "probe"
    if cmd == "probe":
        probe()
    elif cmd == "run":
        run()
    else:
        print(__doc__)
