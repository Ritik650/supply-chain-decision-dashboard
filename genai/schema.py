"""Describe the star schema for the prompt: tables, columns, types and example values,
read live from the warehouse so the prompt never drifts from the real schema."""
from __future__ import annotations

import duckdb

STAR_TABLES = ["fact_order_items", "dim_date", "dim_customer", "dim_product", "dim_geography", "dim_shipping"]

COLUMN_NOTES = {
    ("fact_order_items", "order_item_id"): "grain: one row per order item",
    ("fact_order_items", "order_id"): "an order has 1-5 items; count DISTINCT order_id for orders",
    ("fact_order_items", "order_date_key"): "-> dim_date.date_key (yyyymmdd)",
    ("fact_order_items", "ship_date_key"): "-> dim_date.date_key",
    ("fact_order_items", "customer_key"): "-> dim_customer.customer_key",
    ("fact_order_items", "product_key"): "-> dim_product.product_key",
    ("fact_order_items", "geo_key"): "-> dim_geography.geo_key (delivery destination)",
    ("fact_order_items", "shipping_key"): "-> dim_shipping.shipping_key",
    ("fact_order_items", "is_valid_order"): "FALSE for CANCELED and SUSPECTED_FRAUD; KPIs use only TRUE",
    ("fact_order_items", "is_late"): "actual_days > scheduled_days",
    ("fact_order_items", "late_delivery_risk_src"): "source flag, do not use; use is_late",
    ("fact_order_items", "sales"): "gross = unit_price * quantity, before discount",
    ("fact_order_items", "discount"): "currency discount on the line",
    ("fact_order_items", "discount_rate"): "fraction 0-0.25 actually applied (0.10 = 10%)",
    ("fact_order_items", "discount_rate_listed"): "rate printed in the source; prefer discount_rate",
    ("fact_order_items", "item_total"): "NET REVENUE = sales - discount",
    ("fact_order_items", "profit"): "item-level profit in USD (can be negative)",
    ("fact_order_items", "profit_ratio"): "profit / item_total for the line",
    ("fact_order_items", "delay_days"): "actual_days - scheduled_days (negative = early)",
    ("dim_customer", "cohort_month"): "month of first valid order",
    ("dim_date", "in_analysis_window"): "TRUE for Jan 2015 - Sep 2017",
    ("dim_shipping", "promised_days"): "scheduled lead time, fixed per shipping_mode",
}


def describe(con: duckdb.DuckDBPyConnection, max_values: int = 8) -> str:
    lines = []
    for t in STAR_TABLES:
        n = con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        lines.append(f"TABLE {t}  ({n:,} rows)")
        for name, ctype, *_ in con.execute(f"DESCRIBE {t}").fetchall():
            note = COLUMN_NOTES.get((t, name), "")
            example = ""
            if ctype == "VARCHAR":
                k = con.execute(f'SELECT count(DISTINCT "{name}") FROM {t}').fetchone()[0]
                vals = [r[0] for r in con.execute(
                    f'SELECT "{name}", count(*) c FROM {t} GROUP BY 1 ORDER BY c DESC, 1 LIMIT {max_values}').fetchall()]
                shown = ", ".join(repr(v) for v in vals)
                example = f"values: {shown}" + (f" ... ({k} distinct)" if k > max_values else "")
            elif ctype in ("DATE", "TIMESTAMP"):
                lo, hi = con.execute(f'SELECT min("{name}"), max("{name}") FROM {t}').fetchone()
                example = f"range {lo} to {hi}"
            detail = "; ".join(x for x in (note, example) if x)
            lines.append(f"  {name} {ctype}" + (f"  -- {detail}" if detail else ""))
        lines.append("")
    return "\n".join(lines).rstrip()
