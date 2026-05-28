"""
MySQL export utility for state procurement scrapers.
Usage:
  python db_export.py <state>   -- export enriched CSV to MySQL

Valid states: pa, cali
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
