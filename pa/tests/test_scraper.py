import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import find_input_csv, load_done_ids, build_url, extract_fields


def test_find_input_csv_returns_most_recent(tmp_path):
    (tmp_path / "Solicitations-2026-05-01-09-00-00.csv").write_text("Bid No\n1")
    (tmp_path / "Solicitations-2026-05-27-10-06-38.csv").write_text("Bid No\n2")
    result = find_input_csv(str(tmp_path))
    assert result.endswith("Solicitations-2026-05-27-10-06-38.csv")


def test_find_input_csv_exits_when_none_found(tmp_path):
    with pytest.raises(SystemExit):
        find_input_csv(str(tmp_path))


def test_load_done_ids_returns_empty_when_no_output(tmp_path):
    result = load_done_ids(str(tmp_path / "solicitations_enriched.csv"))
    assert result == set()


def test_load_done_ids_skips_error_rows(tmp_path):
    output = tmp_path / "solicitations_enriched.csv"
    output.write_text(
        "Bid No,scrape_status\n"
        "6100066078,success\n"
        "6100066090,error\n"
        "6100066071,success\n"
    )
    result = load_done_ids(str(output))
    assert result == {"6100066078", "6100066071"}
    assert "6100066090" not in result


def test_build_url_simple_id():
    assert build_url("6100066078") == (
        "https://www.emarketplace.state.pa.us/Solicitations.aspx?SID=6100066078"
    )


def test_build_url_encodes_spaces():
    assert build_url("DGS C-1050-0001 Phase 1") == (
        "https://www.emarketplace.state.pa.us/Solicitations.aspx"
        "?SID=DGS%20C-1050-0001%20Phase%201"
    )


def test_extract_fields_returns_all_keys():
    fixture = Path(__file__).parent / "fixtures" / "sample_solicitation.html"
    html = fixture.read_text(encoding="utf-8")
    result = extract_fields(html)
    expected_keys = [
        "department_for_solicitation", "date_prepared", "advertisement_type",
        "description_full", "delivery_location", "duration",
        "contact_first_name", "contact_last_name", "contact_phone", "contact_email",
        "solicitation_due_time", "solicitation_opening_time",
        "opening_location", "no_of_addendums",
    ]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_extract_fields_values_are_strings():
    fixture = Path(__file__).parent / "fixtures" / "sample_solicitation.html"
    html = fixture.read_text(encoding="utf-8")
    result = extract_fields(html)
    for key, val in result.items():
        assert isinstance(val, str), f"{key} is not a string: {type(val)}"


def test_extract_fields_no_empty_critical_fields():
    fixture = Path(__file__).parent / "fixtures" / "sample_solicitation.html"
    html = fixture.read_text(encoding="utf-8")
    result = extract_fields(html)
    assert result["description_full"] != "", "description_full should not be empty"
    assert result["department_for_solicitation"] != "", "department_for_solicitation should not be empty"
    assert result["contact_first_name"] != "", "contact_first_name should not be empty"
