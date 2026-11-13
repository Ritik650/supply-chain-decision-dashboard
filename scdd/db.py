"""Paths, KPI constants and a read-only DuckDB connection shared by the notebooks,
the dashboard export, the memo and the text-to-SQL app."""
from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW_CSV = ROOT / "data" / "raw" / "DataCoSupplyChainDataset.csv"
UTF8_CSV = ROOT / "data" / "interim" / "dataco_utf8.csv"
DB_PATH = ROOT / "data" / "warehouse" / "supply_chain.duckdb"
SQL_DIR = ROOT / "sql"
ANALYSIS_SQL_DIR = SQL_DIR / "analysis"
OUTPUTS = ROOT / "outputs"

# KPI rules (docs/kpi_definitions.md). Every query that feeds a reported number uses these.
EXCLUDED_STATUSES = ("CANCELED", "SUSPECTED_FRAUD")
WINDOW_START = "2015-01-01"
WINDOW_END_EXCLUSIVE = "2017-10-01"   # Jan 2015 - Sep 2017: 33 full months
WINDOW_MONTHS = 33


def connect(read_only: bool = True) -> duckdb.DuckDBPyConnection:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"{DB_PATH} not found. Run `python scripts/build.py` first.")
    return duckdb.connect(str(DB_PATH), read_only=read_only)


def q(sql: str, con: duckdb.DuckDBPyConnection | None = None, **params) -> pd.DataFrame:
    """Run SQL and return a DataFrame. Pass params for $name placeholders."""
    own = con is None
    con = con or connect()
    try:
        return con.execute(sql, params or None).df()
    finally:
        if own:
            con.close()


def analysis_sql(name: str) -> str:
    """Load a query from sql/analysis/ so notebook figures trace back to a file."""
    return (ANALYSIS_SQL_DIR / name).read_text(encoding="utf-8")


def run_analysis(name: str, con: duckdb.DuckDBPyConnection | None = None) -> pd.DataFrame:
    return q(analysis_sql(name), con)
