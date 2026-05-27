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
