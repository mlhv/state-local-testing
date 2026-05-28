import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import find_input_csv, load_done_ids, build_url, SCRAPED_FIELDS


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
