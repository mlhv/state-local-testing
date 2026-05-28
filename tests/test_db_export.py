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


from db_export import build_ddl


def test_build_ddl_contains_create_table():
    df = pd.DataFrame({"Bid No": ["1"], "Title": ["test"]})
    result = build_ddl("pa_solicitations", df, "bid_no")
    assert "CREATE TABLE IF NOT EXISTS `pa_solicitations`" in result


def test_build_ddl_pk_col_is_not_null():
    df = pd.DataFrame({"Bid No": ["1"], "Title": ["test"]})
    result = build_ddl("pa_solicitations", df, "bid_no")
    assert "`bid_no` TEXT NOT NULL" in result


def test_build_ddl_non_pk_col_has_no_not_null():
    df = pd.DataFrame({"Bid No": ["1"], "Title": ["test"]})
    result = build_ddl("pa_solicitations", df, "bid_no")
    assert "`title` TEXT\n" in result or "`title` TEXT," in result


def test_build_ddl_has_primary_key_clause():
    df = pd.DataFrame({"Bid No": ["1"], "Title": ["test"]})
    result = build_ddl("pa_solicitations", df, "bid_no")
    assert "PRIMARY KEY (`bid_no`)" in result


def test_build_ddl_normalizes_column_names():
    df = pd.DataFrame({"Bid No": ["1"], "Buyer Name": ["Alice"]})
    result = build_ddl("pa_solicitations", df, "bid_no")
    assert "`bid_no`" in result
    assert "`buyer_name`" in result
    assert "`Bid No`" not in result


def test_build_ddl_int_col_uses_bigint():
    df = pd.DataFrame({"id": pd.array([1, 2], dtype="int64"), "name": ["a", "b"]})
    result = build_ddl("test_table", df, "id")
    assert "`id` BIGINT NOT NULL" in result


def test_build_ddl_includes_charset():
    df = pd.DataFrame({"id": ["1"]})
    result = build_ddl("t", df, "id")
    assert "utf8mb4" in result


import db_export
import pymysql
from unittest.mock import patch, MagicMock
from db_export import connect_db


def test_connect_db_exits_when_user_missing(monkeypatch):
    monkeypatch.delenv("DB_USER", raising=False)
    monkeypatch.delenv("DB_NAME", raising=False)
    with patch("db_export.load_dotenv"):
        with pytest.raises(SystemExit):
            connect_db()


def test_connect_db_exits_when_db_name_missing(monkeypatch):
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.delenv("DB_NAME", raising=False)
    with patch("db_export.load_dotenv"):
        with pytest.raises(SystemExit):
            connect_db()


def test_connect_db_exits_on_connection_error(monkeypatch):
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_NAME", "procurement")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_PASSWORD", "")
    with patch("db_export.load_dotenv"):
        with patch("db_export.pymysql.connect", side_effect=pymysql.Error("refused")):
            with pytest.raises(SystemExit):
                connect_db()


def test_connect_db_returns_connection(monkeypatch):
    monkeypatch.setenv("DB_USER", "root")
    monkeypatch.setenv("DB_NAME", "procurement")
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_PORT", "3306")
    monkeypatch.setenv("DB_PASSWORD", "")
    mock_conn = MagicMock()
    with patch("db_export.load_dotenv"):
        with patch("db_export.pymysql.connect", return_value=mock_conn):
            result = connect_db()
    assert result is mock_conn


from db_export import upsert_rows


def test_upsert_rows_returns_row_count():
    df = pd.DataFrame({"Bid No": ["1", "2"], "Title": ["A", "B"]})
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    count = upsert_rows(mock_conn, "pa_solicitations", df, "bid_no")
    assert count == 2


def test_upsert_rows_calls_executemany():
    df = pd.DataFrame({"Bid No": ["1", "2"], "Title": ["A", "B"]})
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    upsert_rows(mock_conn, "pa_solicitations", df, "bid_no")
    assert mock_cursor.executemany.called
    sql_arg = mock_cursor.executemany.call_args[0][0]
    assert "INSERT INTO `pa_solicitations`" in sql_arg
    assert "ON DUPLICATE KEY UPDATE" in sql_arg


def test_upsert_rows_batches_large_datasets():
    # 1200 rows → 3 batches of 500/500/200
    df = pd.DataFrame({
        "Bid No": [str(i) for i in range(1200)],
        "Title":  ["test"] * 1200,
    })
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    count = upsert_rows(mock_conn, "pa_solicitations", df, "bid_no")
    assert count == 1200
    assert mock_cursor.executemany.call_count == 3


def test_upsert_rows_pk_excluded_from_update():
    df = pd.DataFrame({"Bid No": ["1"], "Title": ["A"]})
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    upsert_rows(mock_conn, "pa_solicitations", df, "bid_no")
    sql_arg = mock_cursor.executemany.call_args[0][0]
    # PK should NOT appear in the UPDATE clause
    update_part = sql_arg.split("ON DUPLICATE KEY UPDATE")[1]
    assert "`bid_no`" not in update_part


def test_export_only_upserts_successful_rows(tmp_path, monkeypatch):
    csv = tmp_path / "solicitations_enriched.csv"
    csv.write_text(
        "Bid No,Title,scrape_status\n"
        "A001,Widget,success\n"
        "B002,Gadget,error\n"
        "C003,Sprocket,success\n"
    )
    monkeypatch.setitem(db_export.STATE_CONFIG, "pa", {
        "csv_path": str(csv),
        "table":    "pa_solicitations",
        "pk_col":   "Bid No",
    })
    mock_conn   = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)

    with patch("db_export.connect_db", return_value=mock_conn):
        db_export.export("pa")

    # executemany is called for the upsert (execute is called for CREATE TABLE)
    upsert_call = mock_cursor.executemany.call_args
    rows = upsert_call[0][1]
    assert len(rows) == 2
    bid_nos = [r[0] for r in rows]
    assert "A001" in bid_nos
    assert "C003" in bid_nos
    assert "B002" not in bid_nos


def test_export_skips_null_pk_rows(tmp_path, monkeypatch):
    csv = tmp_path / "solicitations_enriched.csv"
    csv.write_text(
        "Bid No,Title,scrape_status\n"
        ",Missing PK,success\n"
        "X001,Valid,success\n"
    )
    monkeypatch.setitem(db_export.STATE_CONFIG, "pa", {
        "csv_path": str(csv),
        "table":    "pa_solicitations",
        "pk_col":   "Bid No",
    })
    mock_conn   = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)

    with patch("db_export.connect_db", return_value=mock_conn):
        db_export.export("pa")

    upsert_call = mock_cursor.executemany.call_args
    rows = upsert_call[0][1]
    assert len(rows) == 1
    assert rows[0][0] == "X001"


def test_export_prints_done_message(tmp_path, monkeypatch, capsys):
    csv = tmp_path / "solicitations_enriched.csv"
    csv.write_text("Bid No,scrape_status\nZ001,success\n")
    monkeypatch.setitem(db_export.STATE_CONFIG, "pa", {
        "csv_path": str(csv),
        "table":    "pa_solicitations",
        "pk_col":   "Bid No",
    })
    mock_conn   = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)

    with patch("db_export.connect_db", return_value=mock_conn):
        db_export.export("pa")

    out = capsys.readouterr().out
    assert "pa_solicitations" in out
    assert "Done" in out


def test_export_closes_connection_on_success(tmp_path, monkeypatch):
    csv = tmp_path / "solicitations_enriched.csv"
    csv.write_text("Bid No,scrape_status\nZ001,success\n")
    monkeypatch.setitem(db_export.STATE_CONFIG, "pa", {
        "csv_path": str(csv),
        "table":    "pa_solicitations",
        "pk_col":   "Bid No",
    })
    mock_conn   = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
    mock_conn.cursor.return_value.__exit__  = MagicMock(return_value=False)

    with patch("db_export.connect_db", return_value=mock_conn):
        db_export.export("pa")

    mock_conn.close.assert_called_once()


def test_export_raises_for_unknown_state():
    # The __main__ guard catches this before calling export(); export() itself
    # raises KeyError so the CLI can exit with a helpful message.
    with pytest.raises(KeyError):
        db_export.export("unknown_state")
