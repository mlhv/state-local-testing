import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scraper import find_input_csv, load_done_ids, build_url


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
        "https://emarketplace.state.pa.us/Solicitations.aspx?SID=6100066078"
    )


def test_build_url_encodes_spaces():
    assert build_url("DGS C-1050-0001 Phase 1") == (
        "https://emarketplace.state.pa.us/Solicitations.aspx"
        "?SID=DGS%20C-1050-0001%20Phase%201"
    )
