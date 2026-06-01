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
