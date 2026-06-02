"""
Alaska IRIS VSS public solicitations scraper.
Usage:
  python scraper.py probe   -- discover open solicitations, pick first, print all fields
  python scraper.py run     -- discover open solicitations, enrich all new, write CSV
"""

import sys, time, uuid, random, datetime
import requests
import pandas as pd
from pathlib import Path

OUTPUT_PATH = "solicitations_enriched.csv"
DELAY_SECONDS = 0.5
BASE_URL = "https://iris-vss.alaska.gov/PRDVSS1X1/Advantage4"
PORTAL_URL = "https://iris-vss.alaska.gov/"
USER_DATA_DIR = Path.home() / ".ak_scraper_profile"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

LIST_FIELDS = [
    "doc_ref", "doc_type", "description", "department",
    "buyer_name", "buyer_email", "buyer_phone",
    "closing_dt", "publish_dt", "amended_dt", "status", "category_code",
]

SCRAPED_FIELDS = [
    "additional_instructions", "commodity_descriptions",
    "commodity_codes", "commodity_specs", "alaska_url", "scrape_status",
]

EMPTY_SCRAPED = {k: "" for k in SCRAPED_FIELDS}

# Static search page checksum (VIEW is stable for this page layout)
_SEARCH_VIEW_CHECKSUM = 3838637284

# Static viewState for the solicitations search page
_SEARCH_VIEWSTATE = {
    "vss.page.VVSSX10019.gridView1.group1.cardSearch": {"editable": True},
    "vss.page.VVSSX10019.gridView1.group1.cardSearch.search1": {"editable": True},
    "vss.page.VVSSX10019": {
        "closed": False, "hidden": False, "editable": False,
        "protected": False, "required": False,
    },
}

# Tab-change action keys (confirmed from network capture)
_INST_TAB_KEY = (
    "vss.page.VSSSolicitationDocument"
    ".SolicitationDocumentView.wizardNavLinks.navSolicitation"
)
_COMM_TAB_KEY = (
    "vss.page.VSSSolicitationDocument"
    ".SolicitationDocumentView.wizardNavLinks.navCommodity"
)


def load_done_ids(output_path: str) -> set:
    if not Path(output_path).exists():
        return set()
    df = pd.read_csv(output_path, dtype=str)
    if "scrape_status" not in df.columns or "doc_ref" not in df.columns:
        return set()
    return set(df.loc[df["scrape_status"] == "success", "doc_ref"].astype(str))


def extract_instructions(response: dict) -> dict:
    """Extract ADDL_INFO from a navSolicitation tab-change response."""
    rows = (
        response.get("data", {})
        .get("ds_data", {})
        .get("T1SO_DOC_HDR", {})
        .get("row_data", [])
    )
    addl_info = rows[0].get("ADDL_INFO", "") if rows else ""
    return {"additional_instructions": addl_info}


def parse_list_row(row: dict) -> dict:
    """Extract list fields from a single T1SO_SRCH_QRY row_data entry."""
    return {
        "doc_ref":       parse_doc_ref(row.get("DOC_REF", "")),
        "doc_type":      row.get("DOC_CD_CONCAT", ""),
        "description":   row.get("DOC_DSCR", ""),
        "department":    row.get("DEPT_NM", ""),
        "buyer_name":    row.get("BUYR_NM", ""),
        "buyer_email":   row.get("BUYR_EMAIL_AD", ""),
        "buyer_phone":   row.get("BUYR_PH_NO", ""),
        "closing_dt":    ms_to_iso(row.get("SO_CLSNG_DT_TM", "")),
        "publish_dt":    ms_to_iso(row.get("PUB_DT", "")),
        "amended_dt":    ms_to_iso(row.get("AMND_DT", "")),
        "status":        row.get("SO_STA", ""),
        "category_code": row.get("SO_CAT_CD", ""),
    }


def parse_doc_ref(raw: str) -> str:
    """Extract 'RFQ-09-260000015-2' from '[RFQ,09,260000015,2][RFQ-09-260000015-2]'."""
    first_close = raw.index("]")
    second_open = raw.index("[", first_close)
    second_close = raw.index("]", second_open)
    return raw[second_open + 1:second_close]


def parse_column_value(raw: str) -> str:
    """Extract 'RFQ,09,260000015,2' from '[RFQ,09,260000015,2][...]' for docTransition."""
    first_open = raw.index("[")
    first_close = raw.index("]", first_open)
    return raw[first_open + 1:first_close]


def ms_to_iso(ms) -> str:
    """Convert millisecond epoch to ISO 8601 UTC string. Returns '' for falsy input."""
    if not ms:
        return ""
    try:
        return datetime.datetime.fromtimestamp(int(ms) / 1000, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""
