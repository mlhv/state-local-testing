import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import find_input_csv, load_done_ids, build_url, SCRAPED_FIELDS, extract_fields


def test_find_input_csv_exits_when_none_found(tmp_path):
    with pytest.raises(SystemExit):
        find_input_csv(str(tmp_path))


def test_find_input_csv_returns_path_when_present(tmp_path):
    (tmp_path / "bidSearchResults.csv").write_text('"Bid Solicitation #"\n"BD-25-0001"')
    result = find_input_csv(str(tmp_path))
    assert result.endswith("bidSearchResults.csv")


def test_load_done_ids_returns_empty_when_no_output(tmp_path):
    result = load_done_ids(str(tmp_path / "solicitations_enriched.csv"))
    assert result == set()


def test_load_done_ids_skips_error_rows(tmp_path):
    output = tmp_path / "solicitations_enriched.csv"
    output.write_text(
        '"Bid Solicitation #",scrape_status\n'
        '"BD-25-0001",success\n'
        '"BD-25-0002",error\n'
        '"BD-25-0003",success\n'
    )
    result = load_done_ids(str(output))
    assert result == {"BD-25-0001", "BD-25-0003"}
    assert "BD-25-0002" not in result


def test_load_done_ids_excludes_error_rows_so_run_wont_duplicate(tmp_path):
    output = tmp_path / "solicitations_enriched.csv"
    output.write_text(
        '"Bid Solicitation #",scrape_status\n'
        '"BD-25-AAA",success\n'
        '"BD-25-BBB",error\n'
    )
    done_ids = load_done_ids(str(output))
    assert "BD-25-BBB" not in done_ids
    all_rows = pd.read_csv(str(output), dtype=str).to_dict("records")
    enriched = [r for r in all_rows if r.get("scrape_status") == "success"]
    bid_nos = [r["Bid Solicitation #"] for r in enriched]
    assert "BD-25-BBB" not in bid_nos
    assert "BD-25-AAA" in bid_nos


def test_build_url():
    assert build_url("BD-25-1374-PROCU-PROCU-129995") == (
        "https://www.commbuys.com/bso/external/bidDetail.sda"
        "?docId=BD-25-1374-PROCU-PROCU-129995"
    )


FIXTURE = Path(__file__).parent / "fixtures" / "sample_bid.html"


def test_extract_fields_returns_all_keys():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    expected_keys = [k for k in SCRAPED_FIELDS if k not in ("ma_url", "scrape_status")]
    for key in expected_keys:
        assert key in result, f"Missing key: {key}"


def test_extract_fields_values_are_strings():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    for key, val in result.items():
        assert isinstance(val, str), f"{key} is not a string: {type(val)}"


def test_extract_fields_no_empty_critical_fields():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    assert result["bid_type"] != "", "bid_type should not be empty"
    assert result["purchase_method"] != "", "purchase_method should not be empty"


def test_pipe_delimited_items():
    html = FIXTURE.read_text(encoding="utf-8")
    result = extract_fields(html)
    assert "|" in result["unspsc_codes"], "Expected pipe-delimited codes for 2+ item bid"
    codes = result["unspsc_codes"].split("|")
    descs = result["item_descriptions"].split("|")
    unspsc_descs = result["unspsc_descriptions"].split("|")
    assert len(codes) == len(descs) == len(unspsc_descs), "Item field lists must be same length"
    assert all(c != "" for c in codes), "All UNSPSC codes should be non-empty"


def test_output_row_has_all_columns():
    input_row = {
        "Bid Solicitation #": "BD-25-1374-PROCU-PROCU-129995",
        "Organization Name": "Town of Winthrop",
        "Blanket #": "",
        "Buyer": "Dylan Cook",
        "Description": "IFB 2027-06 Steel Work for RTU Install",
        "Bid Opening Date": "06/11/2026 11:00:00",
        "Bid Holder List": "",
        "Awarded Vendor(s)": "",
        "Status": "Sent",
        "Alternate Id": "",
    }
    scraped = {k: "test_value" for k in SCRAPED_FIELDS if k not in ("scrape_status", "ma_url")}
    scraped["scrape_status"] = "success"
    scraped["ma_url"] = "https://www.commbuys.com/bso/external/bidDetail.sda?docId=BD-25-1374-PROCU-PROCU-129995"
    output_row = {**input_row, **scraped}
    for col in input_row:
        assert col in output_row
    for col in SCRAPED_FIELDS:
        assert col in output_row
    assert len(output_row) == 31  # 10 input + 21 scraped
