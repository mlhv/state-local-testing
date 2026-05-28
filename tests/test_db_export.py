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
