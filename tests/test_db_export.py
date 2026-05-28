import sys
import pytest
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from db_export import normalize_col, infer_mysql_type


def test_normalize_col_spaces():
    assert normalize_col("Bid No") == "bid_no"


def test_normalize_col_dots():
    assert normalize_col("Buyer.Name") == "buyer_name"


def test_normalize_col_hyphens():
    assert normalize_col("contact-email") == "contact_email"


def test_normalize_col_strips_whitespace():
    assert normalize_col("  Title  ") == "title"


def test_normalize_col_already_snake():
    assert normalize_col("scrape_status") == "scrape_status"


def test_infer_mysql_type_object():
    df = pd.DataFrame({"col": ["a", "b"]})
    assert infer_mysql_type(df["col"].dtype) == "TEXT"


def test_infer_mysql_type_int():
    df = pd.DataFrame({"col": pd.array([1, 2], dtype="int64")})
    assert infer_mysql_type(df["col"].dtype) == "BIGINT"


def test_infer_mysql_type_float():
    df = pd.DataFrame({"col": [1.0, 2.5]})
    assert infer_mysql_type(df["col"].dtype) == "DOUBLE"


from db_export import filter_successful, load_csv


def test_filter_successful_keeps_only_success():
    df = pd.DataFrame({
        "id":            ["1", "2", "3"],
        "scrape_status": ["success", "error", "success"],
    })
    result = filter_successful(df)
    assert list(result["id"]) == ["1", "3"]


def test_filter_successful_no_status_col_returns_all():
    df = pd.DataFrame({"id": ["1", "2"]})
    result = filter_successful(df)
    assert len(result) == 2


def test_load_csv_reads_file(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("id,name\n1,Alice\n2,Bob\n")
    df = load_csv(str(csv))
    assert len(df) == 2
    assert list(df.columns) == ["id", "name"]


def test_load_csv_reads_all_as_string(tmp_path):
    csv = tmp_path / "test.csv"
    csv.write_text("id,amount\n001,10.5\n002,20\n")
    df = load_csv(str(csv))
    assert df["id"].dtype == object
    assert df["id"].iloc[0] == "001"


def test_load_csv_exits_when_missing():
    with pytest.raises(SystemExit):
        load_csv("/nonexistent/path.csv")
