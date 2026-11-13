"""Build the star schema from the raw CSV and run the data-quality tests.

    python scripts/build.py            # transcode -> load -> staging -> dims -> fact -> tests -> log
    python scripts/build.py --export   # also write the star schema to data/export/*.csv for Power BI

Exit code is 1 if any rule with severity 'error' fails. Every run rewrites
docs/data_quality_log.md with the column profile and each rule's affected-row count.
"""
from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import duckdb  # noqa: E402

from scdd.db import DB_PATH, RAW_CSV, ROOT, SQL_DIR, UTF8_CSV  # noqa: E402

BUILD_STEPS = ["00_load.sql", "01_staging.sql", "02_dimensions.sql", "03_fact.sql"]
STAR_TABLES = ["fact_order_items", "dim_date", "dim_customer", "dim_product", "dim_geography", "dim_shipping"]
LOG_PATH = ROOT / "docs" / "data_quality_log.md"

# Keep/drop decision for every source column, with the reason. The profile numbers in
# the log are computed on each build; the decisions are reviewed by hand.
COLUMN_DECISIONS: dict[str, tuple[str, str]] = {
    "Type": ("keep", "payment_type -> dim_shipping"),
    "Days for shipping (real)": ("keep", "actual_days"),
    "Days for shipment (scheduled)": ("keep", "scheduled_days; also dim_shipping.promised_days (fixed per mode)"),
    "Benefit per order": ("drop", "identical to Order Profit Per Order (T07)"),
    "Sales per customer": ("drop", "identical to Order Item Total (T07); name is misleading"),
    "Delivery Status": ("keep", "delivery_status"),
    "Late_delivery_risk": ("keep", "late_delivery_risk_src, only to cross-check is_late (T06)"),
    "Category Id": ("drop", "identical to Product Category Id (T07)"),
    "Category Name": ("keep", "dim_product.category_name (trimmed)"),
    "Customer City": ("keep", "dim_customer.city (3 shifted rows repaired, T11)"),
    "Customer Country": ("keep", "dim_customer.country ('EE. UU.' -> 'United States')"),
    "Customer Email": ("drop", "masked: single value 'XXXXXXXXX'"),
    "Customer Fname": ("drop", "personal data, not needed for any KPI"),
    "Customer Id": ("drop", "identical to Order Customer Id (T07)"),
    "Customer Lname": ("drop", "personal data, not needed for any KPI"),
    "Customer Password": ("drop", "masked: single value 'XXXXXXXXX'"),
    "Customer Segment": ("keep", "dim_customer.segment"),
    "Customer State": ("keep", "dim_customer.state (3 rows held a ZIP code, repaired, T11)"),
    "Customer Street": ("drop", "personal data; used only to repair the 3 shifted rows"),
    "Customer Zipcode": ("drop", "not needed; 3 nulls"),
    "Department Id": ("keep", "dim_product.department_id"),
    "Department Name": ("keep", "dim_product.department_name (trimmed)"),
    "Latitude": ("drop", "store coordinates, not used by any question"),
    "Longitude": ("drop", "store coordinates, not used by any question"),
    "Market": ("keep", "dim_geography.market"),
    "Order City": ("keep", "dim_geography.order_city"),
    "Order Country": ("keep", "dim_geography.order_country (Spanish names kept as published)"),
    "Order Customer Id": ("keep", "customer_key"),
    "order date (DateOrders)": ("keep", "order_ts, order_date, order_date_key"),
    "Order Id": ("keep", "order_id (degenerate dimension on the fact)"),
    "Order Item Cardprod Id": ("drop", "identical to Product Card Id (T07)"),
    "Order Item Discount": ("keep", "discount"),
    "Order Item Discount Rate": ("keep", "discount_rate_listed; discount_rate is recomputed (T10)"),
    "Order Item Id": ("keep", "order_item_id (fact grain)"),
    "Order Item Product Price": ("keep", "unit_price; dim_product.list_price"),
    "Order Item Profit Ratio": ("keep", "profit_ratio"),
    "Order Item Quantity": ("keep", "quantity"),
    "Sales": ("keep", "sales (gross = price x qty, T04)"),
    "Order Item Total": ("keep", "item_total (net revenue = sales - discount, T04)"),
    "Order Profit Per Order": ("keep", "profit (item-level despite the name)"),
    "Order Region": ("keep", "dim_geography.order_region (whitespace collapsed)"),
    "Order State": ("keep", "dim_geography.order_state"),
    "Order Status": ("keep", "order_status; drives is_valid_order (T08)"),
    "Order Zipcode": ("drop", "86% null"),
    "Product Card Id": ("keep", "product_key"),
    "Product Category Id": ("keep", "dim_product.category_id"),
    "Product Description": ("drop", "100% empty"),
    "Product Image": ("drop", "image URL, no analytic value"),
    "Product Name": ("keep", "dim_product.product_name (source truncates long names)"),
    "Product Price": ("drop", "identical to Order Item Product Price (T07)"),
    "Product Status": ("drop", "constant 0 on every row"),
    "shipping date (DateOrders)": ("keep", "ship_ts, ship_date_key"),
    "Shipping Mode": ("keep", "dim_shipping.shipping_mode"),
}


def transcode() -> None:
    """The source is latin-1 (e.g. 'Ciudad de Almat\\xfd'); DuckDB's reader rejects it, so write a UTF-8 copy."""
    if not RAW_CSV.exists():
        sys.exit(f"{RAW_CSV} not found. Run `python scripts/download_data.py` first.")
    if UTF8_CSV.exists() and UTF8_CSV.stat().st_mtime >= RAW_CSV.stat().st_mtime:
        return
    UTF8_CSV.parent.mkdir(parents=True, exist_ok=True)
    with RAW_CSV.open(encoding="latin-1", newline="") as src, UTF8_CSV.open("w", encoding="utf-8", newline="") as dst:
        for chunk in iter(lambda: src.read(1 << 22), ""):
            dst.write(chunk)


def run_sql_file(con: duckdb.DuckDBPyConnection, path: Path) -> None:
    con.execute(path.read_text(encoding="utf-8"))


def profile_columns(con: duckdb.DuckDBPyConnection) -> list[dict]:
    cols = [r[0] for r in con.execute("DESCRIBE raw.dataco").fetchall()]
    typed = dict(
        con.execute(
            "SELECT column_name, column_type FROM (DESCRIBE SELECT * FROM read_csv(getvariable('raw_csv'), header=true))"
        ).fetchall()
    )
    n = con.execute("SELECT count(*) FROM raw.dataco").fetchone()[0]
    rows = []
    for c in cols:
        nulls, distinct = con.execute(
            f'SELECT count(*) FILTER (WHERE "{c}" IS NULL OR trim("{c}") = \'\'), count(DISTINCT "{c}") FROM raw.dataco'
        ).fetchone()
        decision, reason = COLUMN_DECISIONS.get(c, ("?", "no decision recorded"))
        rows.append(
            dict(column=c.strip(), type=typed.get(c, "?"), null_pct=100 * nulls / n, distinct=distinct,
                 decision=decision, reason=reason)
        )
    return rows


def day1_facts(con: duckdb.DuckDBPyConnection) -> dict:
    one = lambda sql: con.execute(sql).fetchone()  # noqa: E731
    f = {}
    f["rows"], f["orders"], f["customers"], f["products"] = one(
        "SELECT count(*), count(DISTINCT order_id), count(DISTINCT customer_key), count(DISTINCT product_key) FROM fact_order_items"
    )
    f["min_date"], f["max_date"] = one("SELECT min(order_date), max(order_date) FROM fact_order_items")
    f["neg_rows"], f["neg_profit"], f["neg_share"] = one(
        "SELECT count(*) FILTER (WHERE profit < 0), sum(profit) FILTER (WHERE profit < 0), "
        "count(*) FILTER (WHERE profit < 0) / count(*) FROM fact_order_items WHERE is_valid_order"
    )
    f["status"] = con.execute(
        "SELECT order_status, count(*), round(sum(item_total)) FROM fact_order_items GROUP BY 1 ORDER BY 2 DESC"
    ).fetchall()
    f["months"] = con.execute(
        """SELECT d.year_month, count(*) AS items, count(DISTINCT f.order_id) AS orders,
                  round(sum(f.item_total)) AS revenue, count(DISTINCT g.market) AS markets,
                  string_agg(DISTINCT g.market, ', ' ORDER BY g.market) AS market_list
           FROM fact_order_items f JOIN dim_date d ON d.date_key = f.order_date_key
           JOIN dim_geography g USING (geo_key)
           GROUP BY 1 ORDER BY 1"""
    ).fetchall()
    f["new_customer_share_after"] = one(
        """SELECT count(DISTINCT f.customer_key) FILTER (WHERE c.cohort_month >= DATE '2017-10-01')
                  / count(DISTINCT f.customer_key)
           FROM fact_order_items f JOIN dim_customer c USING (customer_key)
           WHERE f.order_date >= DATE '2017-10-01' AND f.is_valid_order"""
    )[0]
    f["market_month_share"] = one(
        """WITH m AS (SELECT d.year_month, g.market, count(*) n FROM fact_order_items f
                      JOIN dim_date d ON d.date_key = f.order_date_key JOIN dim_geography g USING (geo_key) GROUP BY 1, 2),
                t AS (SELECT year_month, max(n) / sum(n) AS top_share FROM m GROUP BY 1)
           SELECT avg(top_share), min(top_share) FROM t"""
    )
    return f


def write_log(profile: list[dict], tests: list[dict], facts: dict, seconds: float) -> None:
    L: list[str] = []
    w = L.append
    w("# Data-quality log")
    w("")
    w(f"_Generated by `python scripts/build.py` on {datetime.now():%Y-%m-%d %H:%M}. Build took {seconds:.1f}s. "
      "Do not edit by hand: change the SQL or `COLUMN_DECISIONS` in the build script and rebuild._")
    w("")
    w("Source: DataCo Smart Supply Chain, Mendeley Data v5, DOI 10.17632/8gx2fvg2k6.5 (CC BY 4.0).")
    w("")
    w("## 1. Day-1 checks")
    w("")
    w(f"- **Row count.** {facts['rows']:,} order items, {facts['orders']:,} orders, {facts['customers']:,} customers, "
      f"{facts['products']} products. Order dates {facts['min_date']} to {facts['max_date']}.")
    w("- **Encoding.** The CSV is latin-1, not UTF-8 (city names such as `Ciudad de Almatý`). DuckDB's own `latin-1` "
      "reader rejects the file, so the build transcodes it to UTF-8 (`data/interim/`) before loading. Line endings are CRLF.")
    w("- **Masked or empty columns.** `Customer Email` and `Customer Password` hold one value (`XXXXXXXXX`); "
      "`Product Description` is 100% empty; `Product Status` is constant 0; `Order Zipcode` is 86% null. All dropped.")
    w("- **Duplicate measures.** Six column pairs are byte-identical on every row (rule T07), e.g. `Benefit per order` = "
      "`Order Profit Per Order` and `Sales per customer` = `Order Item Total`. One of each pair is dropped. "
      "`Order Profit Per Order` is item-level despite its name: `profit_ratio x item_total` reproduces it.")
    w("- **Discount rate.** Every row listed at 6% was discounted 5.5% (rule T10). The build uses the applied rate "
      "(`discount / sales`) and keeps the listed one as `discount_rate_listed`.")
    neg_share = facts["neg_share"] * 100
    w(f"- **Negative profit.** {facts['neg_rows']:,} valid order items ({neg_share:.1f}%) lose money, "
      f"totalling {facts['neg_profit']:,.0f}. They stay in every KPI: they are real losses, not errors.")
    status = ", ".join(f"{s} {n:,}" for s, n, _ in facts["status"])
    w(f"- **Order status.** {status}. Rule: CANCELED and SUSPECTED_FRAUD are excluded from every revenue, profit and "
      "delivery KPI (their `Delivery Status` is `Shipping canceled`). Pending, processing, on-hold and payment-review "
      "items count as booked revenue; a stricter COMPLETE + CLOSED-only view would drop more than half the data.")
    w(f"- **Late flag.** `actual_days > scheduled_days` agrees with `Late_delivery_risk` except on cancelled shipments "
      "(rule T06), where the source sets risk to 0 even when the days say late. Those rows are excluded from KPIs anyway.")
    w("- **Shifted rows.** 3 customer rows have the city in the street column and a ZIP code in the state column. "
      "Staging moves them back (rule T11).")
    avg_share, min_share = facts["market_month_share"]
    w(f"- **Market rotates with time.** In an average month {avg_share * 100:.0f}% of items go to a single market "
      f"(lowest month: {min_share * 100:.0f}%). Market is confounded with calendar period, so market-level trends are "
      "not comparable and market effects are tested within period where it matters.")
    w(f"- **Regime change from October 2017.** Up to September 2017 an order averages ~3 items; from October 2017 "
      f"every order has exactly one item, the catalogue switches to different products, and "
      f"{facts['new_customer_share_after'] * 100:.0f}% of buyers are first-time customers. Revenue then falls each "
      "month to January 2018. Trends, cohorts and the memo use the **analysis window Jan 2015 to Sep 2017 (33 full "
      "months)**; the full range stays in the warehouse (rule T12).")
    w("")
    w("### Monthly volume (why the window ends in September 2017)")
    w("")
    w("| Month | Items | Orders | Items/order | Revenue (all statuses) | Markets |")
    w("|---|---:|---:|---:|---:|---|")
    for ym, items, orders, rev, _, mlist in facts["months"]:
        w(f"| {ym} | {items:,} | {orders:,} | {items / orders:.2f} | {rev:,.0f} | {mlist} |")
    w("")
    w("## 2. Data-quality rules (run on every build)")
    w("")
    w("| Rule | Check | Severity | Rows checked | Rows affected | Result | Detail |")
    w("|---|---|---|---:|---:|---|---|")
    for t in tests:
        w(f"| {t['rule_id']} | {t['rule']} | {t['severity']} | {t['rows_checked']:,} | {t['rows_failed']:,} | "
          f"{t['result']} | {t['detail']} |")
    w("")
    w("`error` rules fail the build. `warn` rules are known source issues that the model handles. "
      "`info` rules count rows that a KPI rule excludes.")
    w("")
    w("## 3. Column profile and keep/drop decisions")
    w("")
    w("| Source column | Inferred type | Null % | Distinct | Decision | Target / reason |")
    w("|---|---|---:|---:|---|---|")
    for p in profile:
        w(f"| {p['column']} | {p['type']} | {p['null_pct']:.1f} | {p['distinct']:,} | {p['decision']} | {p['reason']} |")
    w("")
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(L), encoding="utf-8")


def export_csv(con: duckdb.DuckDBPyConnection) -> None:
    out = ROOT / "data" / "export"
    out.mkdir(parents=True, exist_ok=True)
    for t in STAR_TABLES:
        con.execute(f"COPY {t} TO '{(out / (t + '.csv')).as_posix()}' (HEADER, DELIMITER ',')")
    # Customer-level outputs that are awkward in DAX: RFM segment per customer and the cohort matrix.
    for name in ("p4_rfm_segments", "p4_cohort_retention", "p4_rfm_validation"):
        sql = (SQL_DIR / "analysis" / f"{name}.sql").read_text(encoding="utf-8").strip().rstrip(";")
        con.execute(f"COPY ({sql}) TO '{(out / (name.split('_', 1)[1] + '.csv')).as_posix()}' (HEADER, DELIMITER ',')")
    print(f"  exported {len(STAR_TABLES)} star tables + rfm_segments, cohort_retention, rfm_validation to {out.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--export", action="store_true", help="write star-schema CSVs for Power BI to data/export/")
    args = ap.parse_args()

    t0 = time.time()
    transcode()
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = DB_PATH.with_suffix(".building.duckdb")
    tmp.unlink(missing_ok=True)
    con = duckdb.connect(str(tmp))
    con.execute(f"SET VARIABLE raw_csv = '{UTF8_CSV.as_posix()}'")
    for step in BUILD_STEPS:
        t = time.time()
        run_sql_file(con, SQL_DIR / step)
        print(f"  {step:<20} {time.time() - t:5.2f}s")
    for tbl in STAR_TABLES:
        print(f"    {tbl:<18} {con.execute(f'SELECT count(*) FROM {tbl}').fetchone()[0]:>8,} rows")

    tests = []
    for path in sorted((SQL_DIR / "tests").glob("t*.sql")):
        cur = con.execute(path.read_text(encoding="utf-8"))
        cols = [d[0] for d in cur.description]
        row = dict(zip(cols, cur.fetchone()))
        failed = row["rows_failed"] > 0
        row["result"] = ("FAIL" if row["severity"] == "error" else row["severity"].upper()) if failed else "pass"
        tests.append(row)
        print(f"  {row['rule_id']} {row['result']:<5} {row['rows_failed']:>7,}  {row['rule']}")

    profile = profile_columns(con)
    facts = day1_facts(con)
    if args.export:
        export_csv(con)
    con.close()
    DB_PATH.unlink(missing_ok=True)
    tmp.replace(DB_PATH)

    write_log(profile, tests, facts, time.time() - t0)
    n_fail = sum(t["result"] == "FAIL" for t in tests)
    print(f"Built {DB_PATH.relative_to(ROOT)} in {time.time() - t0:.1f}s; {len(tests)} rules, {n_fail} failing. "
          f"Log: {LOG_PATH.relative_to(ROOT)}")
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
