import pandas as pd
import pytest
from pathlib import Path
import sys

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
