"""Export the star schema for the static web dashboard (dashboard/web/).

The dashboard filters and aggregates in the browser, so it needs order-item rows, not
pre-baked totals. Valid order items (cancelled / suspected-fraud excluded, as every KPI
does) are written as one columnar binary file, ~4.5 MB, with dictionaries in meta.json.
reference.json holds the sql/analysis/ results for the default view, so
scripts/check_dashboard.py can confirm the browser's numbers match the SQL.

    python scripts/export_dashboard.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scdd.db import ROOT, WINDOW_MONTHS, connect, run_analysis  # noqa: E402

OUT = ROOT / "dashboard" / "web" / "data"
FINDINGS = ROOT / "outputs" / "findings"

# Column order matters: 4-byte types first so every typed-array view is aligned.
COLUMNS = [
    ("sales", "float32"), ("item_total", "float32"), ("profit", "float32"), ("order", "uint32"),
    ("customer", "uint16"),
    ("month", "uint8"), ("market", "uint8"), ("segment", "uint8"), ("category", "uint8"), ("product", "uint8"),
    ("mode", "uint8"), ("region", "uint8"), ("quantity", "uint8"), ("rate_milli", "uint8"), ("actual_days", "uint8"),
]


def main() -> int:
    con = connect()
    df = con.execute("""
        SELECT f.order_id, f.customer_key, d.month_start, g.market, c.segment, p.category_name, p.product_key,
               s.shipping_mode, g.order_region, f.quantity, f.discount_rate, f.actual_days,
               f.sales, f.item_total, f.profit
        FROM fact_order_items f
        JOIN dim_date d ON d.date_key = f.order_date_key
        JOIN dim_geography g USING (geo_key)
        JOIN dim_customer c USING (customer_key)
        JOIN dim_product p USING (product_key)
        JOIN dim_shipping s USING (shipping_key)
        WHERE f.is_valid_order
        ORDER BY f.order_id, f.order_item_id
    """).df()

    months = sorted(df.month_start.unique())
    dicts = {
        "months": [str(m)[:7] for m in months],
        "markets": sorted(df.market.unique()),
        "segments": sorted(df.segment.unique()),
        "categories": sorted(df.category_name.unique()),
        "regions": sorted(df.order_region.unique()),
    }
    modes = con.execute("SELECT DISTINCT shipping_mode, promised_days FROM dim_shipping ORDER BY promised_days").fetchall()
    dicts["modes"] = [m for m, _ in modes]
    promised = {m: d for m, d in modes}
    prods = con.execute("SELECT product_key, product_name, category_name FROM dim_product ORDER BY product_key").fetchall()
    prod_index = {k: i for i, (k, _, _) in enumerate(prods)}

    code = lambda col, values: df[col].map({v: i for i, v in enumerate(values)}).to_numpy()  # noqa: E731
    order_codes = df.order_id.rank(method="dense").to_numpy() - 1
    cols = {
        "sales": df.sales.to_numpy(np.float32),
        "item_total": df.item_total.to_numpy(np.float32),
        "profit": df.profit.to_numpy(np.float32),
        "order": order_codes.astype(np.uint32),
        "customer": df.customer_key.to_numpy(np.uint16),
        "month": df.month_start.map({m: i for i, m in enumerate(months)}).to_numpy(np.uint8),
        "market": code("market", dicts["markets"]).astype(np.uint8),
        "segment": code("segment", dicts["segments"]).astype(np.uint8),
        "category": code("category_name", dicts["categories"]).astype(np.uint8),
        "product": df.product_key.map(prod_index).to_numpy(np.uint8),
        "mode": code("shipping_mode", dicts["modes"]).astype(np.uint8),
        "region": code("order_region", dicts["regions"]).astype(np.uint8),
        "quantity": df.quantity.to_numpy(np.uint8),
        "rate_milli": np.round(df.discount_rate.to_numpy() * 1000).astype(np.uint8),
        "actual_days": df.actual_days.to_numpy(np.uint8),
    }
    assert df.customer_key.max() < 65536 and len(prods) < 256 and (df.discount_rate.max() * 1000) < 256

    OUT.mkdir(parents=True, exist_ok=True)
    layout, offset = [], 0
    with (OUT / "items.bin").open("wb") as fh:
        for name, dtype in COLUMNS:
            arr = cols[name].astype(dtype)
            layout.append({"name": name, "dtype": dtype, "offset": offset})
            b = arr.tobytes()
            fh.write(b)
            offset += len(b)
            pad = (-offset) % 4
            fh.write(b"\0" * pad)
            offset += pad

    # RFM segment per customer (as of the window end) for the Customers page.
    rfm = run_analysis("p4_rfm_segments.sql", con)
    seg_names = ["Champions", "Loyal", "New & promising", "Needs attention", "At risk", "Hibernating"]
    rfm_by_customer = {int(k): seg_names.index(s) for k, s in zip(rfm.customer_key, rfm.rfm_segment)}
    max_cust = int(df.customer_key.max())
    rfm_arr = [rfm_by_customer.get(i, 255) for i in range(max_cust + 1)]

    q2 = json.loads((FINDINGS / "q2.json").read_text(encoding="utf-8"))
    rfm_val = run_analysis("p4_rfm_validation.sql", con)[
        ["rfm_segment", "customers", "share_ordering_next_6m", "past_revenue_per_customer"]].to_dict(orient="records")
    meta = {
        "rows": len(df),
        "layout": layout,
        "dicts": dicts,
        "products": [{"name": n, "category": c} for _, n, c in prods],
        "promised_days": [promised[m] for m in dicts["modes"]],
        "rfm_segments": seg_names,
        "rfm_by_customer": rfm_arr,
        "rfm_validation": rfm_val,
        "window": {"start": "2015-01", "end": "2017-09", "months": WINDOW_MONTHS},
        "whatif": {"beta_central": max(q2["elasticity_beta"], 0.0), "beta_estimate": q2["elasticity_beta"],
                   "beta_ci": q2["elasticity_ci"], "price_elasticity_low": -1.5},
    }
    (OUT / "meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")

    def records(name):
        d = run_analysis(name, con)
        for c in d.columns:
            if str(d[c].dtype).startswith("datetime") or d[c].dtype == object:
                d[c] = d[c].astype(str)
        return d.to_dict(orient="records")

    reference = {n: records(n + ".sql") for n in [
        "p1_kpi_cards", "p2_late_by_mode", "p3_margin_by_band", "p3_whatif_cap", "p4_segment_summary",
        "p4_month3_retention", "p5_kpis", "p2_repromise_whatif"]}
    (OUT / "reference.json").write_text(json.dumps(reference, indent=1, default=float), encoding="utf-8")
    con.close()
    print(f"  {len(df):,} rows -> {OUT.relative_to(ROOT)}/items.bin ({offset / 1e6:.1f} MB), meta.json, reference.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
