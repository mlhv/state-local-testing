import pandas as pd
import pytest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import scraper

FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_load_done_ids_missing_file(tmp_path):
    assert scraper.load_done_ids(str(tmp_path / "nonexistent.csv")) == set()


def test_load_done_ids_returns_successes_only(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([
        {"src_code": "BPM007579", "scrape_status": "success"},
        {"src_code": "BPM007580", "scrape_status": "error"},
        {"src_code": "BPM007581", "scrape_status": "success"},
    ]).to_csv(csv, index=False)
    result = scraper.load_done_ids(str(csv))
    assert result == {"BPM007579", "BPM007581"}


def test_load_done_ids_missing_columns(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([{"foo": "bar"}]).to_csv(csv, index=False)
    assert scraper.load_done_ids(str(csv)) == set()


def test_parse_list_page_row_count():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, _ = scraper.parse_list_page(html)
    assert len(rows) == 2


def test_parse_list_page_open_row_fields():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, _ = scraper.parse_list_page(html)
    row = next(r for r in rows if r["src_code"] == "BPM007579")
    assert row["solicitation_label"] == "ADOT Flagstaff Service Center Re-Roof"
    assert row["commodity"] == "Building and Facility Construction and Maintenance Services"
    assert row["buying_agency"] == "Department of Transportation"
    assert row["status"] == "Open for Bidding"
    assert row["begin_date"] == "08/05/2026 00:00:00"
    assert row["end_date"] == "03/06/2026 15:00:00"
    assert "13695" in row["detail_href"]


def test_parse_list_page_total_pages():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    _, total_pages = scraper.parse_list_page(html)
    assert total_pages == 2


def test_parse_list_page_empty_table():
    html = "<html><body><div id='body_x_grid_upgrid'><table><tbody></tbody></table></div></body></html>"
    rows, total_pages = scraper.parse_list_page(html)
    assert rows == []
    assert total_pages == 1


def test_label_value_ivalua_field_control():
    html = (FIXTURE_DIR / "sample_detail_page.html").read_text()
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    assert scraper._label_value(soup, "Round #") == "4"
    assert scraper._label_value(soup, "Procurement Officer") == "Monica Rodriguez"


def test_label_value_missing_returns_empty():
    from bs4 import BeautifulSoup
    soup = BeautifulSoup("<html><body></body></html>", "html.parser")
    assert scraper._label_value(soup, "Nonexistent Field") == ""


def test_extract_fields_all_fields():
    html = (FIXTURE_DIR / "sample_detail_page.html").read_text()
    fields = scraper.extract_fields(html)
    assert fields["lot_number"] == "1"
    assert fields["round_number"] == "4"
    assert fields["fiscal_year"] == ""
    assert fields["rfx_type"] == "IFB"
    assert fields["procurement_officer"] == "Monica Rodriguez"
    assert fields["procurement_officer_email"] == "mrodriguez8@azdot.gov"
    assert fields["procurement_officer_phone"] == "6027122089"
    assert fields["discussion_forum_cutoff"] == ""
    assert fields["commodity_full"] == "72000000 - Building and Facility Construction and Maintenance Services"
    assert "Arizona Procurement Code" in fields["summary"]


def test_extract_fields_missing_returns_empty():
    fields = scraper.extract_fields("<html><body></body></html>")
    for key in [
        "lot_number", "round_number", "fiscal_year", "rfx_type",
        "procurement_officer", "procurement_officer_email",
        "procurement_officer_phone", "discussion_forum_cutoff",
        "commodity_full", "summary",
    ]:
        assert fields[key] == ""
