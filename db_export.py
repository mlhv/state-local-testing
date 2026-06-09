"""
MySQL export utility for state procurement scrapers.
Usage:
  python db_export.py <state>   -- export enriched CSV to MySQL

Valid states: pa, cali, cali_manual, ma, al, ak, az
"""

import os
import sys
import pymysql
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

STATE_CONFIG = {
    "pa": {
        "csv_path": "pa/solicitations_enriched.csv",
        "table":    "pa_solicitations",
        "pk_col":   "Bid No",
    },
    "cali": {
        "csv_path": "cali/events_enriched.csv",
        "table":    "cali_events",
        "pk_col":   "Event ID",
    },
    "cali_manual": {
        "csv_path": "cali_manual/events_enriched.csv",
        "table":    "cali_events",
        "pk_col":   "Event ID",
    },
    "ma": {
        "csv_path": "ma/solicitations_enriched.csv",
        "table":    "ma_solicitations",
        "pk_col":   "Bid Solicitation #",
    },
    "al": {
        "csv_path": "al/solicitations_enriched.csv",
        "table":    "al_solicitations",
        "pk_col":   "src_code",
    },
    "ak": {
        "csv_path": "ak/solicitations_enriched.csv",
        "table":    "ak_solicitations",
        "pk_col":   "doc_ref",
    },
    "az": {
        "csv_path": "az/solicitations_enriched.csv",
        "table":    "az_solicitations",
        "pk_col":   "src_code",
    },
}

BATCH_SIZE = 500


def normalize_col(col: str) -> str:
    return col.strip().lower().replace(" ", "_").replace(".", "_").replace("-", "_")


def infer_mysql_type(dtype) -> str:
    if pd.api.types.is_integer_dtype(dtype):
        return "BIGINT"
    if pd.api.types.is_float_dtype(dtype):
        return "DOUBLE"
    return "TEXT"


def filter_successful(df: pd.DataFrame) -> pd.DataFrame:
    if "scrape_status" not in df.columns:
        return df.copy()
    return df[df["scrape_status"] == "success"].copy()


def load_csv(csv_path: str) -> pd.DataFrame:
    if not Path(csv_path).exists():
        sys.exit(f"ERROR: CSV not found: {csv_path}")
    return pd.read_csv(csv_path, dtype=object)


def build_ddl(table: str, df: pd.DataFrame, pk_norm: str) -> str:
    col_defs = []
    for col in df.columns:
        norm = normalize_col(col)
        if norm == pk_norm:
            col_defs.append(f"  `{norm}` VARCHAR(255) NOT NULL")
        else:
            mysql_type = infer_mysql_type(df[col].dtype)
            col_defs.append(f"  `{norm}` {mysql_type}")
    col_defs.append(f"  PRIMARY KEY (`{pk_norm}`)")
    cols_sql = ",\n".join(col_defs)
    return (
        f"CREATE TABLE IF NOT EXISTS `{table}` (\n"
        f"{cols_sql}\n"
        f") DEFAULT CHARSET=utf8mb4"
    )


def connect_db():
    load_dotenv()
    host     = os.getenv("DB_HOST", "localhost")
    port     = int(os.getenv("DB_PORT", "3306"))
    user     = os.getenv("DB_USER")
    password = os.getenv("DB_PASSWORD", "")
    db       = os.getenv("DB_NAME")

    if not user or not db:
        sys.exit(
            "ERROR: DB_USER and DB_NAME must be set.\n"
            "Copy .env.example to .env and fill in your credentials."
        )
    try:
        return pymysql.connect(
            host=host, port=port, user=user,
            password=password, database=db, charset="utf8mb4",
        )
    except pymysql.Error as e:
        sys.exit(f"ERROR: Could not connect to MySQL: {e}")


def upsert_rows(conn, table: str, df: pd.DataFrame, pk_norm: str) -> int:
    norm_cols    = [normalize_col(c) for c in df.columns]
    col_list     = ", ".join(f"`{c}`" for c in norm_cols)
    placeholders = ", ".join(["%s"] * len(norm_cols))
    update_clause = ", ".join(
        f"`{c}`=VALUES(`{c}`)" for c in norm_cols if c != pk_norm
    )
    sql = (
        f"INSERT INTO `{table}` ({col_list}) VALUES ({placeholders}) "
        f"ON DUPLICATE KEY UPDATE {update_clause}"
    )

    records  = df.values.tolist()
    total    = len(records)
    upserted = 0

    with conn.cursor() as cur:
        for i in range(0, total, BATCH_SIZE):
            batch   = records[i : i + BATCH_SIZE]
            cleaned = [
                [None if (isinstance(v, float) and pd.isna(v)) else v for v in row]
                for row in batch
            ]
            cur.executemany(sql, cleaned)
            conn.commit()
            upserted += len(batch)
            print(f"[{upserted}/{total}] upserted...")

    return upserted


def export(state: str):
    config  = STATE_CONFIG[state]
    pk_col  = config["pk_col"]
    pk_norm = normalize_col(pk_col)

    df = load_csv(config["csv_path"])
    df = filter_successful(df)

    null_mask  = df[pk_col].isna() | (df[pk_col].astype(str).str.strip() == "")
    null_count = null_mask.sum()
    if null_count:
        print(f"WARNING: Skipping {null_count} rows with null/empty {pk_col!r}.")
        df = df[~null_mask]

    if df.empty:
        print(f"No successful rows to export from {config['csv_path']}.")
        return

    conn = connect_db()
    try:
        with conn.cursor() as cur:
            cur.execute(build_ddl(config["table"], df, pk_norm))
        conn.commit()
        count = upsert_rows(conn, config["table"], df, pk_norm)
        print(f"\nDone. {count} rows upserted to `{config['table']}`.")
    finally:
        conn.close()


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in STATE_CONFIG:
        valid = ", ".join(STATE_CONFIG.keys())
        sys.exit(f"Usage: python db_export.py <state>\nValid states: {valid}")
    export(sys.argv[1])
