import pandas as pd
import pytest
from pathlib import Path
import sys
import responses as responses_lib

sys.path.insert(0, str(Path(__file__).parent.parent))
import scraper


def test_load_done_ids_missing_file(tmp_path):
    assert scraper.load_done_ids(str(tmp_path / "nonexistent.csv")) == set()


def test_load_done_ids_returns_successes_only(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([
        {"src_code": "SRC0000034127", "scrape_status": "success"},
        {"src_code": "SRC0000034128", "scrape_status": "error"},
        {"src_code": "SRC0000034129", "scrape_status": "success"},
    ]).to_csv(csv, index=False)
    result = scraper.load_done_ids(str(csv))
    assert result == {"SRC0000034127", "SRC0000034129"}


def test_load_done_ids_missing_columns(tmp_path):
    csv = tmp_path / "out.csv"
    pd.DataFrame([{"foo": "bar"}]).to_csv(csv, index=False)
    assert scraper.load_done_ids(str(csv)) == set()


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def test_parse_list_page_row_count():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, total_pages = scraper.parse_list_page(html)
    assert len(rows) == 2


def test_parse_list_page_open_row_fields():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    rows, _ = scraper.parse_list_page(html)
    open_row = next(r for r in rows if r["src_code"] == "SRC0000034127")
    assert open_row["status"] == "Open for Bidding"
    assert open_row["solicitation_label"] == "Locksmith Services at FMS #11/Birmingham"
    assert open_row["due_close_date"] == "6/15/2026"
    assert open_row["solicitation_type"] == "Quick Quote"
    assert open_row["buying_agency"] == "Facilities Management"
    assert open_row["sourcing_responsible_first"] == "Tracy"
    assert open_row["sourcing_responsible_last"] == "Fink"
    assert "41760" in open_row["detail_href"]


def test_parse_list_page_total_pages():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    _, total_pages = scraper.parse_list_page(html)
    assert total_pages == 2


def test_parse_list_page_no_pager_means_one_page():
    html = "<html><body><table><thead><tr><th>Sourcing Project Number</th></tr></thead><tbody></tbody></table></body></html>"
    _, total_pages = scraper.parse_list_page(html)
    assert total_pages == 1


def test_parse_list_page_table_without_tbody():
    html = "<html><body><table><tr><td>data</td></tr></table></body></html>"
    rows, total_pages = scraper.parse_list_page(html)
    assert rows == []
    assert total_pages == 1


@responses_lib.activate
def test_discover_solicitations_filters_open_only():
    html = (FIXTURE_DIR / "sample_list_page.html").read_text()
    # Mock the GET for page 1 (fixture has 2 total pages shown by pager)
    responses_lib.add(responses_lib.GET, scraper.BROWSE_URL, body=html, status=200)
    # Mock the POST for page 2 — return same HTML (one open, one closed row)
    responses_lib.add(responses_lib.POST, scraper.AJAX_URL, body=html, status=200)

    result = scraper.discover_solicitations()
    # Only the "Open for Bidding" rows from both pages
    assert len(result) == 2  # 1 open from page 1 + 1 open from page 2 (same fixture)
    assert all(r["status"] == "Open for Bidding" for r in result)
    assert all(r["src_code"] == "SRC0000034127" for r in result)


def test_extract_fields_round_number():
    html = (FIXTURE_DIR / "sample_solicitation_detail.html").read_text()
    fields = scraper.extract_fields(html)
    assert fields["round_number"] == "1"


def test_extract_fields_begin_date():
    html = (FIXTURE_DIR / "sample_solicitation_detail.html").read_text()
    fields = scraper.extract_fields(html)
    assert fields["begin_date"] == "5/29/2026 4:44:49 PM (CST)"


def test_extract_fields_summary():
    html = (FIXTURE_DIR / "sample_solicitation_detail.html").read_text()
    fields = scraper.extract_fields(html)
    assert "Troubleshoot" in fields["summary"]


def test_extract_fields_missing_field_returns_empty():
    fields = scraper.extract_fields("<html><body></body></html>")
    assert fields["round_number"] == ""
    assert fields["begin_date"] == ""
    assert fields["summary"] == ""
