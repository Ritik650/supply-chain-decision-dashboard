"""Safety and scoring tests for the text-to-SQL layer (no API key needed)."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai.ask import UnsafeSQL, check_sql, extract_sql, open_readonly, run_sql  # noqa: E402
from genai.eval.compare import results_match  # noqa: E402


@pytest.mark.parametrize("sql", [
    "SELECT 1",
    "WITH a AS (SELECT 1 AS x) SELECT * FROM a",
    "SELECT * FROM dim_product WHERE category_name = 'Set'",   # keyword inside a string is fine
])
def test_allows_single_select(sql):
    assert check_sql(sql) == sql


@pytest.mark.parametrize("sql", [
    "DROP TABLE fact_order_items",
    "INSERT INTO dim_date SELECT * FROM dim_date",
    "SELECT 1; SELECT 2",
    "SELECT 1; DROP TABLE dim_date",
    "COPY fact_order_items TO 'out.csv'",
    "PRAGMA database_list",
    "ATTACH 'other.db'",
    "SELECT * FROM read_csv('data/raw/DataCoSupplyChainDataset.csv')",
    "SELECT getenv('PATH')",
    "",
])
def test_blocks_everything_else(sql):
    with pytest.raises(UnsafeSQL):
        check_sql(sql)


def test_connection_cannot_read_files_or_write():
    con = open_readonly()
    with pytest.raises(Exception):
        con.execute("SELECT * FROM read_csv('data/raw/DescriptionDataCoSupplyChain.csv')").fetchall()
    with pytest.raises(Exception):
        con.execute("CREATE TABLE x AS SELECT 1").fetchall()


def test_timeout_interrupts_long_query():
    con = open_readonly()
    with pytest.raises(TimeoutError):
        run_sql(con, "SELECT sum(a.profit * b.profit) FROM fact_order_items a, fact_order_items b", timeout=1)
    assert run_sql(con, "SELECT 1 AS x").x[0] == 1   # connection still usable


def test_extract_sql_strips_fences():
    assert extract_sql("```sql\nSELECT 1;\n```") == "SELECT 1"
    assert extract_sql("SQL: SELECT 2") == "SELECT 2"


def test_compare_ignores_order_names_and_extra_columns():
    gold = pd.DataFrame({"market": ["A", "B"], "revenue": [1.23456, 2.0]})
    pred = pd.DataFrame({"n": [7, 9], "m": ["B", "A"], "rev": [2.0, 1.234561]})
    assert results_match(gold, pred)[0]


def test_compare_rejects_percent_vs_fraction_and_mispairing():
    gold = pd.DataFrame({"mode": ["X", "Y"], "late_rate": [0.5, 0.25]})
    assert not results_match(gold, pd.DataFrame({"mode": ["X", "Y"], "late_rate": [50.0, 25.0]}))[0]
    assert not results_match(gold, pd.DataFrame({"mode": ["X", "Y"], "late_rate": [0.25, 0.5]}))[0]
    assert not results_match(gold, pd.DataFrame({"mode": ["X"], "late_rate": [0.5]}))[0]
