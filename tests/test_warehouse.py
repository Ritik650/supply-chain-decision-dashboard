"""The built warehouse satisfies every data-quality rule and the KPI rules hold.
Run `python scripts/build.py` first."""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scdd.db import DB_PATH, connect  # noqa: E402

pytestmark = pytest.mark.skipif(not DB_PATH.exists(), reason="warehouse not built")
TESTS = sorted((ROOT / "sql" / "tests").glob("t*.sql"))


@pytest.mark.parametrize("path", TESTS, ids=[p.stem for p in TESTS])
def test_data_quality_rule(path):
    con = connect()
    cur = con.execute(path.read_text(encoding="utf-8"))
    row = dict(zip([d[0] for d in cur.description], cur.fetchone()))
    if row["severity"] == "error":
        assert row["rows_failed"] == 0, row["detail"]


def test_star_schema_tables_exist():
    con = connect()
    names = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'").fetchall()}
    assert {"fact_order_items", "dim_date", "dim_customer", "dim_product", "dim_geography", "dim_shipping"} <= names


def test_every_analysis_query_runs():
    con = connect()
    for path in sorted((ROOT / "sql" / "analysis").glob("*.sql")):
        assert len(con.execute(path.read_text(encoding="utf-8")).fetchall()) > 0, path.name


def test_late_rate_matches_source_flag_on_valid_orders():
    con = connect()
    mismatches = con.execute(
        "SELECT count(*) FROM fact_order_items WHERE is_valid_order AND CAST(is_late AS INT) <> late_delivery_risk_src"
    ).fetchone()[0]
    assert mismatches == 0
