"""Generate a Power BI Project (PBIP) for the dashboard: semantic model (TMDL) + report (PBIR).

    python scripts/build.py --export     # CSVs the model loads
    python scripts/make_pbip.py          # writes dashboard/powerbi/supply_chain_dashboard.pbip and its two folders

Open dashboard/powerbi/supply_chain_dashboard.pbip in Power BI Desktop and click Refresh. The CSV folder is the model parameter `DataFolder`
(Transform data > Edit parameters) and defaults to this repo's data/export/.

Everything is written from the specs below, so the model, measures and visuals stay reviewable in git.
Filtering that would normally need visual-level filters (top N, minimum sizes) is done inside measures,
which keeps the report JSON simple and the logic visible in one place.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dashboard" / "powerbi"
NAME = "supply_chain_dashboard"
SM = OUT / f"{NAME}.SemanticModel"
RP = OUT / f"{NAME}.Report"
EXPORT = ROOT / "data" / "export"
NS = uuid.UUID("6f1c2a3e-4b5d-4e6f-8a9b-0c1d2e3f4a5b")
M = "_Measures"
ACTIVE = sys.argv[sys.argv.index("--active") + 1] if "--active" in sys.argv else None
FIT = "--fit" in sys.argv   # whole page in view (used for screenshots); default scrolls tall pages

INK, INK2, MUTED, GREY, GREY_DARK, BAD = "#111110", "#6B6A65", "#9B9A95", "#A8A69F", "#52514E", "#D03B3B"
PCT1, PCT0 = "0.0%;-0.0%;0.0%", "0%;-0%;0%"
USD0, USD2 = r"\$#,0;-\$#,0;\$#,0", r"\$#,0.00;-\$#,0.00;\$#,0.00"
INT, DEC2, DEC1 = "#,0", "0.00", "0.0"


def tag(*parts: str) -> str:
    return str(uuid.uuid5(NS, "/".join(parts)))


def qn(name: str) -> str:
    """Quote a TMDL object name when it isn't a plain identifier."""
    return name if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) else "'" + name.replace("'", "''") + "'"


# =====================================================================================
# Semantic model spec
# =====================================================================================
# column: (name, tmdl dataType, M type, options)
T_INT, T_DBL, T_DEC, T_STR, T_BOOL, T_DATE = "int64", "double", "decimal", "string", "boolean", "dateTime"
MTYPE = {T_INT: "Int64.Type", T_DBL: "type number", T_DEC: "Currency.Type", T_STR: "type text",
         T_BOOL: "type logical", T_DATE: "type date"}


def c(name, dtype, hidden=False, fmt=None, summarize=None, sort_by=None, key=False, desc=None):
    return dict(name=name, dtype=dtype, hidden=hidden, fmt=fmt, summarize=summarize, sort_by=sort_by, key=key, desc=desc)


TABLES = {
    "fact_order_items": dict(desc="One row per order item (the grain). Use the measures in _Measures, not these columns.", cols=[
        c("order_item_id", T_INT, hidden=True, summarize="none"),
        c("order_id", T_INT, hidden=True, summarize="none"),
        c("order_date_key", T_INT, hidden=True, summarize="none"),
        c("ship_date_key", T_INT, hidden=True, summarize="none"),
        c("customer_key", T_INT, hidden=True, summarize="none"),
        c("product_key", T_INT, hidden=True, summarize="none"),
        c("geo_key", T_INT, hidden=True, summarize="none"),
        c("shipping_key", T_INT, hidden=True, summarize="none"),
        c("order_status", T_STR),
        c("delivery_status", T_STR),
        c("is_valid_order", T_BOOL, hidden=True, desc="FALSE for CANCELED and SUSPECTED_FRAUD; every KPI uses TRUE only"),
        c("is_late", T_BOOL, hidden=True, desc="actual_days > scheduled_days"),
        c("quantity", T_INT, hidden=True),
        c("unit_price", T_DEC, hidden=True, fmt=USD2),
        c("sales", T_DEC, hidden=True, fmt=USD0, desc="gross = unit_price x quantity"),
        c("discount", T_DEC, hidden=True, fmt=USD0),
        c("discount_rate", T_DBL, hidden=True, fmt=PCT1, desc="rate actually applied = discount / sales"),
        c("item_total", T_DEC, hidden=True, fmt=USD0, desc="net revenue = sales - discount"),
        c("profit", T_DEC, hidden=True, fmt=USD0),
        c("actual_days", T_INT, summarize="none", desc="actual shipping days"),
        c("scheduled_days", T_INT, hidden=True, summarize="none"),
        c("delay_days", T_INT, hidden=True),
    ], derived=[
        ("Discount Band", T_STR,
         'each if [discount_rate] < 0.05 then "0-5%" else if [discount_rate] < 0.10 then "5-10%" '
         'else if [discount_rate] < 0.15 then "10-15%" else if [discount_rate] < 0.20 then "15-20%" else "20-25%"'),
        ("Discount Band Order", T_INT,
         "each if [discount_rate] < 0.05 then 1 else if [discount_rate] < 0.10 then 2 "
         "else if [discount_rate] < 0.15 then 3 else if [discount_rate] < 0.20 then 4 else 5"),
    ], derived_opts={"Discount Band": dict(sort_by="Discount Band Order"),
                     "Discount Band Order": dict(hidden=True, summarize="none")}),
    "dim_date": dict(desc="Calendar, marked as the date table.", date_table=True, cols=[
        c("date_key", T_INT, hidden=True, summarize="none"),
        c("date", T_DATE, key=True, fmt="yyyy-mm-dd"),
        c("year", T_INT, summarize="none", fmt="0"),
        c("quarter", T_INT, summarize="none"),
        c("month", T_INT, hidden=True, summarize="none"),
        c("month_name", T_STR, sort_by="month"),
        c("month_start", T_DATE, fmt="mmm yyyy"),
        c("year_month", T_STR),
        c("weekday_num", T_INT, hidden=True, summarize="none"),
        c("weekday_name", T_STR, sort_by="weekday_num"),
        c("is_weekend", T_BOOL),
        c("in_analysis_window", T_BOOL, desc="TRUE for Jan 2015 - Sep 2017 (the report-level default filter)"),
    ]),
    "dim_customer": dict(desc="Customers (store location; personal data dropped).", cols=[
        c("customer_key", T_INT, hidden=True, summarize="none"),
        c("segment", T_STR), c("city", T_STR), c("state", T_STR), c("country", T_STR),
        c("first_order_date", T_DATE, fmt="yyyy-mm-dd"),
        c("cohort_month", T_DATE, fmt="mmm yyyy", desc="month of first valid order"),
    ]),
    "dim_product": dict(desc="Products with category and department.", cols=[
        c("product_key", T_INT, hidden=True, summarize="none"),
        c("product_name", T_STR),
        c("category_id", T_INT, hidden=True, summarize="none"),
        c("category_name", T_STR),
        c("department_id", T_INT, hidden=True, summarize="none"),
        c("department_name", T_STR),
        c("list_price", T_DEC, fmt=USD2, summarize="none"),
    ]),
    "dim_geography": dict(desc="Delivery destination: market > region > country > state > city.", cols=[
        c("geo_key", T_INT, hidden=True, summarize="none"),
        c("market", T_STR), c("order_region", T_STR), c("order_country", T_STR), c("order_state", T_STR),
        c("order_city", T_STR),
    ]),
    "dim_shipping": dict(desc="Shipping mode x payment type; promised_days is fixed per mode.", cols=[
        c("shipping_key", T_INT, hidden=True, summarize="none"),
        c("shipping_mode", T_STR),
        c("promised_days", T_INT, summarize="none"),
        c("payment_type", T_STR),
    ]),
    "rfm_segments": dict(desc="RFM scores per customer as of 2017-10-01 (sql/analysis/p4_rfm_segments.sql).", cols=[
        c("customer_key", T_INT, hidden=True, summarize="none"),
        c("last_order_date", T_DATE, fmt="yyyy-mm-dd"),
        c("frequency", T_INT), c("monetary", T_DEC, fmt=USD0), c("recency_days", T_INT),
        c("r_score", T_INT, summarize="none"), c("f_score", T_INT, summarize="none"), c("m_score", T_INT, summarize="none"),
        c("rfm_segment", T_STR),
    ]),
    "cohort_retention": dict(desc="Cohort x month retention for the analysis window (p4_cohort_retention.sql). Not filterable.", cols=[
        c("cohort_month", T_DATE, fmt="mmm yy"),
        c("cohort_size", T_INT, summarize="none"),
        c("month_index", T_INT, summarize="none"),
        c("active_customers", T_INT),
        c("retention", T_DBL, fmt=PCT0, summarize="none"),
    ]),
    "rfm_validation": dict(desc="Does RFM predict? Segments scored to Mar 2017 vs orders Apr-Sep 2017 (p4_rfm_validation.sql).", cols=[
        c("rfm_segment", T_STR),
        c("customers", T_INT),
        c("share_ordering_next_6m", T_DBL, fmt=PCT1, summarize="none"),
        c("next_6m_revenue_per_customer", T_DEC, fmt=USD0, summarize="none"),
        c("past_revenue_per_customer", T_DEC, fmt=USD0, summarize="none"),
    ]),
}

RELATIONSHIPS = [
    ("fact_order_items", "order_date_key", "dim_date", "date_key", {}),
    ("fact_order_items", "ship_date_key", "dim_date", "date_key", {"isActive": "false"}),
    ("fact_order_items", "customer_key", "dim_customer", "customer_key", {}),
    ("fact_order_items", "product_key", "dim_product", "product_key", {}),
    ("fact_order_items", "geo_key", "dim_geography", "geo_key", {}),
    ("fact_order_items", "shipping_key", "dim_shipping", "shipping_key", {}),
    ("rfm_segments", "customer_key", "dim_customer", "customer_key",
     {"fromCardinality": "one", "crossFilteringBehavior": "bothDirections"}),
]

# What-if parameter tables: (table, min, max, step, default, format)
PARAMS = [
    ("Max Discount", 0, 0.25, 0.01, 0.10, PCT0),
    ("First Class Promise", 1, 2, 1, 2, "0"),
    ("Second Class Promise", 2, 6, 1, 4, "0"),
]


def mm(name, expr, fmt=None, folder=None, desc=None):
    return dict(name=name, expr=expr.strip(), fmt=fmt, folder=folder, desc=desc)


VALID = "fact_order_items[is_valid_order] = TRUE ()"
VALID_ROW = "fact_order_items[is_valid_order]"


def mom(base, kind):
    """Last month in the current filter vs the month before (REMOVEFILTERS on dim_date keeps the slicer out of it)."""
    body = f"""
VAR m = [Last Month Start]
VAR cur = CALCULATE ( [{base}], REMOVEFILTERS ( dim_date ), dim_date[month_start] = m )
VAR prev = CALCULATE ( [{base}], REMOVEFILTERS ( dim_date ), dim_date[month_start] = EDATE ( m, -1 ) )
RETURN
"""
    return body + ("    DIVIDE ( cur - prev, prev )" if kind == "pct" else "    cur - prev")


def share_mode(mode):
    return f'CALCULATE ( [Share of Mode Items], dim_shipping[shipping_mode] = "{mode}" )'


def bar_color(mode):
    return f"""
VAR promise =
    CALCULATE ( MAX ( dim_shipping[promised_days] ), REMOVEFILTERS ( dim_shipping ), dim_shipping[shipping_mode] = "{mode}" )
RETURN
    IF ( SELECTEDVALUE ( fact_order_items[actual_days] ) > promise, "{BAD}", "{GREY}" )
"""


def cap_filter(cap_var="cap"):
    return f"FILTER ( fact_order_items, {VALID_ROW} && fact_order_items[discount_rate] > {cap_var} + 0.000001 )"


MEASURES = [
    # ---- core ----
    mm("Valid Items", f"CALCULATE ( COUNTROWS ( fact_order_items ), {VALID} )", INT, "1 Core KPIs",
       "Order items excluding cancelled and suspected-fraud"),
    mm("Revenue", f"CALCULATE ( SUM ( fact_order_items[item_total] ), {VALID} )", USD0, "1 Core KPIs",
       "Net revenue: sum of item_total over valid order items"),
    mm("Profit", f"CALCULATE ( SUM ( fact_order_items[profit] ), {VALID} )", USD0, "1 Core KPIs"),
    mm("Profit Margin %", "DIVIDE ( [Profit], [Revenue] )", PCT1, "1 Core KPIs", "Profit / revenue"),
    mm("Orders", f"CALCULATE ( DISTINCTCOUNT ( fact_order_items[order_id] ), {VALID} )", INT, "1 Core KPIs"),
    mm("Avg Order Value", "DIVIDE ( [Revenue], [Orders] )", USD2, "1 Core KPIs"),
    mm("Discount Spend", f"CALCULATE ( SUM ( fact_order_items[discount] ), {VALID} )", USD0, "1 Core KPIs"),
    mm("Avg Units per Line", f"CALCULATE ( AVERAGE ( fact_order_items[quantity] ), {VALID} )", DEC2, "1 Core KPIs"),
    mm("Customers", f"CALCULATE ( DISTINCTCOUNT ( fact_order_items[customer_key] ), {VALID} )", INT, "1 Core KPIs"),
    mm("Months Selected", f"COUNTROWS ( SUMMARIZE ( FILTER ( fact_order_items, {VALID_ROW} ), dim_date[month_start] ) )",
       INT, "1 Core KPIs", "Months with valid orders in the current filter (used to annualise)"),
    # ---- month on month ----
    mm("Last Month Start", f"CALCULATE ( MAX ( dim_date[month_start] ), FILTER ( fact_order_items, {VALID_ROW} ) )",
       "mmm yyyy", "2 Month on month"),
    mm("Revenue MoM %", mom("Revenue", "pct"), PCT1, "2 Month on month"),
    mm("Profit MoM %", mom("Profit", "pct"), PCT1, "2 Month on month"),
    mm("Margin MoM pts", mom("Profit Margin %", "diff"), PCT1, "2 Month on month"),
    mm("Late Rate MoM pts", mom("Late Rate %", "diff"), PCT1, "2 Month on month"),
    mm("Orders MoM %", mom("Orders", "pct"), PCT1, "2 Month on month"),
    mm("AOV MoM %", mom("Avg Order Value", "pct"), PCT1, "2 Month on month"),
    mm("MoM Suffix", '" vs " & FORMAT ( EDATE ( [Last Month Start], -1 ), "mmm yy" )', None, "2 Month on month"),
    mm("Revenue MoM", 'FORMAT ( [Revenue MoM %], "+0.0%;-0.0%" ) & [MoM Suffix]', None, "2 Month on month"),
    mm("Profit MoM", 'FORMAT ( [Profit MoM %], "+0.0%;-0.0%" ) & [MoM Suffix]', None, "2 Month on month"),
    mm("Margin MoM", 'FORMAT ( [Margin MoM pts] * 100, "+0.0;-0.0" ) & " pts" & [MoM Suffix]', None, "2 Month on month"),
    mm("Late Rate MoM", 'FORMAT ( [Late Rate MoM pts] * 100, "+0.0;-0.0" ) & " pts" & [MoM Suffix]', None, "2 Month on month"),
    mm("Orders MoM", 'FORMAT ( [Orders MoM %], "+0.0%;-0.0%" ) & [MoM Suffix]', None, "2 Month on month"),
    mm("AOV MoM", 'FORMAT ( [AOV MoM %], "+0.0%;-0.0%" ) & [MoM Suffix]', None, "2 Month on month"),
    # ---- delivery ----
    mm("Late Items", f"CALCULATE ( COUNTROWS ( fact_order_items ), {VALID}, fact_order_items[is_late] = TRUE () )",
       INT, "3 Delivery"),
    mm("Late Rate %", "DIVIDE ( [Late Items], [Valid Items] )", PCT1, "3 Delivery",
       "Items delivered after the promised day / valid items"),
    mm("On-time %", "1 - [Late Rate %]", PCT1, "3 Delivery"),
    mm("Avg Delay Days (late items)",
       f"CALCULATE ( AVERAGE ( fact_order_items[delay_days] ), {VALID}, fact_order_items[is_late] = TRUE () )",
       DEC2, "3 Delivery", "Mean of actual - scheduled days over late items only"),
    mm("Avg Actual Days", f"CALCULATE ( AVERAGE ( fact_order_items[actual_days] ), {VALID} )", DEC2, "3 Delivery"),
    mm("Promised Days", "MAX ( dim_shipping[promised_days] )", "0", "3 Delivery"),
    mm("Late Rate % (heatmap)", "IF ( [Valid Items] >= 200, [Late Rate %] )", PCT0, "3 Delivery",
       "Blank for mode x region cells with fewer than 200 items"),
    mm("Heatmap Color", """
VAR v = [Late Rate % (heatmap)]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( v ), BLANK (),
        v < 0.35, "#F6E3E2",
        v < 0.45, "#F2B8B5",
        v < 0.55, "#EC9592",
        v < 0.70, "#E5716E",
        v < 0.90, "#D03B3B",
        "#7F1D1D"
    )""", None, "3 Delivery"),
    mm("Heatmap Font Color", f'IF ( [Late Rate % (heatmap)] >= 0.55, "#FFFFFF", "{INK}" )', None, "3 Delivery"),
    mm("Share of Mode Items",
       "DIVIDE ( [Valid Items], CALCULATE ( [Valid Items], REMOVEFILTERS ( fact_order_items[actual_days] ) ) )",
       PCT0, "3 Delivery"),
    *[mm(f"Share of Items ({m})", share_mode(m), PCT0, "3 Delivery")
      for m in ("Same Day", "First Class", "Second Class", "Standard Class")],
    *[mm(f"Bar Color ({m})", bar_color(m), None, "3 Delivery")
      for m in ("Same Day", "First Class", "Second Class", "Standard Class")],
    # ---- discounts ----
    mm("Margin at or below 10%", "CALCULATE ( [Profit Margin %], fact_order_items[discount_rate] <= 0.10 )", PCT1, "4 Discounts"),
    mm("Margin above 10%", "CALCULATE ( [Profit Margin %], fact_order_items[discount_rate] > 0.10 )", PCT1, "4 Discounts"),
    mm("Margin Gap pts", "( [Margin above 10%] - [Margin at or below 10%] ) * 100", "+0.0;-0.0;0.0", "4 Discounts"),
    mm("Units at or below 10%", "CALCULATE ( [Avg Units per Line], fact_order_items[discount_rate] <= 0.10 )", DEC2, "4 Discounts"),
    mm("Units above 10%", "CALCULATE ( [Avg Units per Line], fact_order_items[discount_rate] > 0.10 )", DEC2, "4 Discounts"),
    mm("Discount Above 10%",
       f"SUMX ( {cap_filter('0.10')}, ( fact_order_items[discount_rate] - 0.10 ) * fact_order_items[sales] )",
       USD0, "4 Discounts", "Discount given above a 10% rate in the current filter"),
    mm("Discount Above 10% per Year", "DIVIDE ( [Discount Above 10%] * 12, [Months Selected] )", USD0, "4 Discounts"),
    mm("Cat Items", "IF ( [Valid Items] >= 500, [Valid Items] )", INT, "4 Discounts"),
    mm("Cat Margin at or below 10%", "IF ( [Valid Items] >= 500, [Margin at or below 10%] )", PCT1, "4 Discounts"),
    mm("Cat Margin above 10%", "IF ( [Valid Items] >= 500, [Margin above 10%] )", PCT1, "4 Discounts"),
    mm("Cat Margin Gap pts", "IF ( [Valid Items] >= 500, [Margin Gap pts] )", "+0.0;-0.0;0.0", "4 Discounts"),
    mm("Cat Units at or below 10%", "IF ( [Valid Items] >= 500, [Units at or below 10%] )", DEC2, "4 Discounts"),
    mm("Cat Units above 10%", "IF ( [Valid Items] >= 500, [Units above 10%] )", DEC2, "4 Discounts"),
    mm("Cat Discount Above 10%", "IF ( [Valid Items] >= 500, [Discount Above 10%] )", USD0, "4 Discounts"),
    mm("Gap Font Color", f'IF ( [Cat Margin Gap pts] < -1, "{BAD}", "{INK}" )', None, "4 Discounts"),
    # ---- what-if ----
    mm("Elasticity (central)", "0", "0.000", "8 What-if",
       "Within-product elasticity from notebooks/q2_discounts.ipynb: -0.006 (95% CI -0.057 to +0.044), floored at 0"),
    mm("Items Above Cap", "VAR cap = [Max Discount Value] RETURN CALCULATE ( [Valid Items], fact_order_items[discount_rate] > cap + 0.000001 )",
       INT, "8 What-if"),
    mm("Profit Recovered per Year (volume holds)", f"""
VAR cap = [Max Discount Value]
VAR uplift =
    SUMX ( {cap_filter()}, ( fact_order_items[discount_rate] - cap ) * fact_order_items[sales] )
RETURN
    DIVIDE ( uplift * 12, [Months Selected] )""", USD0, "8 What-if",
       "HIGH: items above the cap re-priced at the cap, unit cost fixed, volume holds"),
    mm("Profit Recovered per Year (central)", f"""
VAR cap = [Max Discount Value]
VAR beta = [Elasticity (central)]
VAR delta =
    SUMX (
        {cap_filter()},
        VAR r = fact_order_items[discount_rate]
        VAR newp = fact_order_items[profit] + ( r - cap ) * fact_order_items[sales]
        RETURN newp * EXP ( beta * ( cap - r ) ) - fact_order_items[profit]
    )
RETURN
    DIVIDE ( delta * 12, [Months Selected] )""", USD0, "8 What-if",
       "CENTRAL: volume responds with the elasticity measured in the data"),
    mm("Profit Recovered per Year (low)", f"""
VAR cap = [Max Discount Value]
VAR delta =
    SUMX (
        {cap_filter()},
        VAR r = fact_order_items[discount_rate]
        VAR newp = fact_order_items[profit] + ( r - cap ) * fact_order_items[sales]
        VAR keep = MAX ( 0, 1 - 1.5 * ( r - cap ) / ( 1 - r ) )
        RETURN newp * keep - fact_order_items[profit]
    )
RETURN
    DIVIDE ( delta * 12, [Months Selected] )""", USD0, "8 What-if",
       "LOW: stress case, an ASSUMED price elasticity of -1.5 (not estimated from this data)"),
    mm("Break-even Volume Loss %", f"""
VAR cap = [Max Discount Value]
VAR affected = {cap_filter()}
VAR uplift = SUMX ( affected, ( fact_order_items[discount_rate] - cap ) * fact_order_items[sales] )
VAR profitNow = SUMX ( affected, fact_order_items[profit] )
RETURN
    DIVIDE ( uplift, profitNow + uplift )""", PCT1, "8 What-if",
       "Share of the capped items' volume that could be lost before the cap stops paying"),
    mm("Late Rate % (what-if promises)", f"""
VAR p1 = [First Class Promise Value]
VAR p2 = [Second Class Promise Value]
VAR lateCount =
    SUMX (
        FILTER ( fact_order_items, {VALID_ROW} ),
        VAR mode = RELATED ( dim_shipping[shipping_mode] )
        VAR promise = SWITCH ( mode, "First Class", p1, "Second Class", p2, RELATED ( dim_shipping[promised_days] ) )
        RETURN IF ( fact_order_items[actual_days] > promise, 1, 0 )
    )
RETURN
    DIVIDE ( lateCount, [Valid Items] )""", PCT1, "8 What-if",
       "Late rate if First and Second Class promised the selected days; actual days as observed"),
    mm("Late Rate Change (what-if)", "[Late Rate % (what-if promises)] - [Late Rate %]", "+0.0%;-0.0%;0.0%", "8 What-if"),
    # ---- customers ----
    mm("Segment Revenue Share", "DIVIDE ( [Revenue], CALCULATE ( [Revenue], ALLSELECTED ( rfm_segments[rfm_segment] ) ) )",
       PCT0, "5 Customers"),
    mm("Segment Customer Share", "DIVIDE ( [Customers], CALCULATE ( [Customers], ALLSELECTED ( rfm_segments[rfm_segment] ) ) )",
       PCT0, "5 Customers"),
    mm("Avg Orders per Customer", "AVERAGE ( rfm_segments[frequency] )", DEC1, "5 Customers"),
    mm("Champions Revenue Share", """
DIVIDE (
    CALCULATE ( [Revenue], rfm_segments[rfm_segment] = "Champions" ),
    CALCULATE ( [Revenue], REMOVEFILTERS ( rfm_segments ) )
)""", PCT0, "5 Customers"),
    mm("Month-3 Retention", """
DIVIDE (
    CALCULATE ( SUM ( cohort_retention[active_customers] ), cohort_retention[month_index] = 3 ),
    CALCULATE (
        SUM ( cohort_retention[active_customers] ),
        cohort_retention[month_index] = 0,
        cohort_retention[cohort_month] <= DATE ( 2017, 6, 1 )
    )
)""", PCT1, "5 Customers", "Pooled over cohorts Jan 2015 - Jun 2017; the cohort table ignores slicers"),
    mm("Next 6m Buyers Range", """
FORMAT ( MIN ( rfm_validation[share_ordering_next_6m] ), "0%" ) & " to "
    & FORMAT ( MAX ( rfm_validation[share_ordering_next_6m] ), "0%" )""", None, "5 Customers"),
    mm("RFM Next 6m Share", "AVERAGE ( rfm_validation[share_ordering_next_6m] )", PCT0, "5 Customers"),
    mm("RFM Past Revenue per Customer", "AVERAGE ( rfm_validation[past_revenue_per_customer] )", USD0, "5 Customers"),
    mm("Cohort Retention (shown)", """
VAR k = MAX ( cohort_retention[month_index] )
RETURN
    IF ( k >= 1 && k <= 24 && MAX ( cohort_retention[cohort_size] ) >= 50, AVERAGE ( cohort_retention[retention] ) )""",
       PCT0, "5 Customers", "Months 1-24 for cohorts of at least 50 customers"),
    mm("Cohort Color", """
VAR v = [Cohort Retention (shown)]
RETURN
    SWITCH (
        TRUE (),
        ISBLANK ( v ), BLANK (),
        v < 0.09, "#ECEBE7",
        v < 0.11, "#D6D4CE",
        v < 0.13, "#B9B7B0",
        v < 0.15, "#8A8984",
        v < 0.18, "#6B6A65",
        "#3F3E3B"
    )""", None, "5 Customers"),
    mm("Cohort Font Color", f'IF ( [Cohort Retention (shown)] >= 0.15, "#FFFFFF", "{INK}" )', None, "5 Customers"),
    # ---- products ----
    mm("Product Profit Rank", "IF ( NOT ISBLANK ( [Profit] ), RANKX ( ALLSELECTED ( dim_product[product_name] ), [Profit], , DESC, DENSE ) )",
       INT, "6 Products"),
    mm("Cumulative Profit Share", """
VAR p = [Profit]
VAR cum =
    SUMX ( FILTER ( ALLSELECTED ( dim_product[product_name] ), [Profit] >= p ), [Profit] )
RETURN
    IF ( NOT ISBLANK ( p ), DIVIDE ( cum, CALCULATE ( [Profit], ALLSELECTED ( dim_product[product_name] ) ) ) )""",
       PCT0, "6 Products"),
    mm("ABC Class", """
VAR own = DIVIDE ( [Profit], CALCULATE ( [Profit], ALLSELECTED ( dim_product[product_name] ) ) )
VAR priorShare = [Cumulative Profit Share] - own
RETURN
    IF ( NOT ISBLANK ( [Revenue] ), SWITCH ( TRUE (), priorShare < 0.80, "A", priorShare < 0.95, "B", "C" ) )""",
       None, "6 Products", "A = first 80% of cumulative profit, B = next 15%, C = the rest"),
    mm("A-class Products", 'COUNTROWS ( FILTER ( ALLSELECTED ( dim_product[product_name] ), [ABC Class] = "A" ) )',
       "0", "6 Products"),
    mm("Profit Share Top 20% Products", """
VAR sold = FILTER ( ALLSELECTED ( dim_product[product_name] ), NOT ISBLANK ( [Revenue] ) )
VAR n = ROUNDUP ( 0.2 * COUNTROWS ( sold ), 0 )
VAR topSet = TOPN ( n, sold, [Profit], DESC )
RETURN
    DIVIDE ( SUMX ( topSet, [Profit] ), SUMX ( sold, [Profit] ) )""", PCT1, "6 Products"),
    mm("Loss-making Products", "COUNTROWS ( FILTER ( ALLSELECTED ( dim_product[product_name] ), [Profit] < 0 ) ) + 0",
       "0", "6 Products"),
    mm("Loss-making Line Share", "DIVIDE ( CALCULATE ( [Valid Items], fact_order_items[profit] < 0 ), [Valid Items] )",
       PCT1, "6 Products"),
    mm("Pareto Share (top 30)", "IF ( [Product Profit Rank] <= 30, [Cumulative Profit Share] )", PCT0, "6 Products"),
    mm("Top15 Revenue", "IF ( [Product Profit Rank] <= 15, [Revenue] )", USD0, "6 Products"),
    mm("Top15 Profit", "IF ( [Product Profit Rank] <= 15, [Profit] )", USD0, "6 Products"),
    mm("Top15 Margin", "IF ( [Product Profit Rank] <= 15, [Profit Margin %] )", PCT1, "6 Products"),
    mm("Top15 Cumulative Share", "IF ( [Product Profit Rank] <= 15, [Cumulative Profit Share] )", PCT0, "6 Products"),
    mm("Top15 Class", 'IF ( [Product Profit Rank] <= 15, [ABC Class] )', None, "6 Products"),
    mm("Watch List Flag", """
VAR sold = FILTER ( ALLSELECTED ( dim_product[product_name] ), NOT ISBLANK ( [Revenue] ) )
VAR revRank = RANKX ( sold, [Revenue], , DESC )
RETURN
    IF (
        NOT ISBLANK ( [Revenue] )
            && ( [Profit] < 0 || ( revRank <= COUNTROWS ( sold ) / 2 && [Profit Margin %] < 0.10 ) ),
        1,
        0
    )""", "0", "6 Products", "1 for top-half-revenue products with margin under 10%, or any loss-maker"),
    mm("Watch Revenue", "IF ( [Watch List Flag] = 1, [Revenue] )", USD0, "6 Products"),
    mm("Watch Profit", "IF ( [Watch List Flag] = 1, [Profit] )", USD0, "6 Products"),
    mm("Watch Margin", "IF ( [Watch List Flag] = 1, [Profit Margin %] )", PCT1, "6 Products"),
    mm("Watch Lines", "IF ( [Watch List Flag] = 1, [Valid Items] )", INT, "6 Products"),
    mm("Watch Font Color", f'IF ( [Profit] < 0, "{BAD}", "{INK}" )', None, "6 Products"),
    # ---- text ----
    mm("Alert 1", """
"First Class late on "
    & FORMAT ( CALCULATE ( [Late Rate %], dim_shipping[shipping_mode] = "First Class" ), "0%" )
    & " of items: promises 1 day, always takes 2"
""", None, "7 Text"),
    mm("Alert 2", """
FORMAT ( [Discount Above 10% per Year], "$#,0" ) & " a year discounted above 10%; those items sell "
    & FORMAT ( [Units above 10%], "0.00" ) & " units per line vs " & FORMAT ( [Units at or below 10%], "0.00" )
""", None, "7 Text"),
    mm("Alert 3", """
FORMAT ( [Loss-making Line Share], "0.0%" ) & " of order lines lose money, spread evenly across products"
""", None, "7 Text"),
    mm("Takeaway Summary", """
FORMAT ( [Late Rate %], "0%" ) & " of items arrive late, and discounts above 10% cost "
    & FORMAT ( [Discount Above 10% per Year], "$#,0" ) & " a year without selling more units."
""", None, "7 Text"),
    mm("Takeaway Delivery", """
"First Class is late on "
    & FORMAT ( CALCULATE ( [Late Rate %], dim_shipping[shipping_mode] = "First Class" ), "0%" )
    & " of items: it always ships in 2 days against a 1-day promise. Fix the promise per mode, not per region."
""", None, "7 Text"),
    mm("Takeaway Discounts", """
"Items discounted above 10% sell " & FORMAT ( [Units above 10%], "0.00" ) & " units per line vs "
    & FORMAT ( [Units at or below 10%], "0.00" ) & " at or below: the extra discount buys no volume."
""", None, "7 Text"),
    mm("Takeaway Customers", """
"About " & FORMAT ( [Month-3 Retention], "0%" )
    & " of a cohort orders again in any month, and RFM segments reorder at the same rate: test retention, don't target it."
""", None, "7 Text"),
    mm("Takeaway Products", """
FORMAT ( [A-class Products], "0" ) & " products earn 80% of profit, the same products that earn the revenue; only "
    & FORMAT ( [Loss-making Products], "0" ) & " small products lose money."
""", None, "7 Text"),
]


# ---------- TMDL writers ----------
def expr_block(expr: str, indent: int) -> str:
    """Single-line expressions stay inline; multi-line ones go on following lines, indented."""
    lines = expr.strip("\n").splitlines()
    if len(lines) == 1:
        return " " + lines[0].strip()
    pad = "\t" * indent
    return "\n" + "\n".join(pad + ln if ln.strip() else "" for ln in lines)


def write_table(name: str, spec: dict) -> str:
    L = []
    if spec.get("desc"):
        L.append(f"/// {spec['desc']}")
    L.append(f"table {qn(name)}")
    L.append(f"\tlineageTag: {tag('table', name)}")
    if spec.get("date_table"):
        L.append("\tdataCategory: Time")
    L.append("")
    cols = list(spec["cols"])
    for dname, dtype, _ in spec.get("derived", []):
        cols.append(c(dname, dtype, **spec.get("derived_opts", {}).get(dname, {})))
    for col in cols:
        if col["desc"]:
            L.append(f"\t/// {col['desc']}")
        L.append(f"\tcolumn {qn(col['name'])}")
        L.append(f"\t\tdataType: {col['dtype']}")
        if col["key"]:
            L.append("\t\tisKey")
        if col["hidden"]:
            L.append("\t\tisHidden")
        if col["fmt"]:
            L.append(f"\t\tformatString: {col['fmt']}")
        L.append(f"\t\tlineageTag: {tag('column', name, col['name'])}")
        summarize = col["summarize"] or ("sum" if col["dtype"] in (T_INT, T_DBL, T_DEC) else "none")
        L.append(f"\t\tsummarizeBy: {summarize}")
        L.append(f"\t\tsourceColumn: {col['name']}")
        if col["sort_by"]:
            L.append(f"\t\tsortByColumn: {qn(col['sort_by'])}")
        L.append("")
        L.append("\t\tannotation SummarizationSetBy = User")
        L.append("")
    # Power Query partition
    src = [c_["name"] for c_ in spec["cols"]]
    types = ", ".join(f'{{"{c_["name"]}", {MTYPE[c_["dtype"]]}}}' for c_ in spec["cols"])
    m = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        "    Selected = Table.SelectColumns(Promoted, {" + ", ".join(f'"{s}"' for s in src) + "}),",
        f'    Typed = Table.TransformColumnTypes(Selected, {{{types}}}, "en-US")' + ("," if spec.get("derived") else ""),
    ]
    prev = "Typed"
    for i, (dname, dtype, each) in enumerate(spec.get("derived", [])):
        step = f"Added{i}"
        last = i == len(spec["derived"]) - 1
        m.append(f'    {step} = Table.AddColumn({prev}, "{dname}", {each}, {MTYPE[dtype]})' + ("" if last else ","))
        prev = step
    m += ["in", f"    {prev}"]
    L.append(f"\tpartition {qn(name)} = m")
    L.append("\t\tmode: import")
    L.append("\t\tsource =")
    L += ["\t\t\t\t" + ln for ln in m]
    L.append("")
    L.append("\tannotation PBI_ResultType = Table")
    L.append("")
    return "\n".join(L)


def write_param_table(name, lo, hi, step, default, fmt) -> str:
    return "\n".join([
        f"/// What-if parameter ({lo} to {hi}, step {step}); default {default} when nothing is selected",
        f"table {qn(name)}",
        f"\tlineageTag: {tag('table', name)}",
        "",
        f"\tmeasure {qn(name + ' Value')} = SELECTEDVALUE ( {qn(name)}[{name}], {default} )",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {tag('measure', name, 'value')}",
        "",
        f"\tcolumn {qn(name)}",
        f"\t\tdataType: {'double' if isinstance(step, float) else 'int64'}",
        f"\t\tformatString: {fmt}",
        f"\t\tlineageTag: {tag('column', name, name)}",
        "\t\tsummarizeBy: none",
        "\t\tsourceColumn: [Value]",
        "",
        "\t\tannotation SummarizationSetBy = User",
        "",
        f"\tpartition {qn(name)} = calculated",
        "\t\tmode: import",
        f"\t\tsource = GENERATESERIES ( {lo}, {hi}, {step} )",
        "",
        "\tannotation PBI_Id = " + tag("param", name).replace("-", ""),
        "",
    ])


def write_measures_table() -> str:
    L = ["/// All report measures, grouped by display folder.", f"table {M}", f"\tlineageTag: {tag('table', M)}", ""]
    for x in MEASURES:
        if x["desc"]:
            L.append(f"\t/// {x['desc']}")
        L.append(f"\tmeasure {qn(x['name'])} =" + expr_block(x["expr"], 3))
        if x["fmt"]:
            L.append(f"\t\tformatString: {x['fmt']}")
        if x["folder"]:
            L.append(f"\t\tdisplayFolder: {x['folder']}")
        L.append(f"\t\tlineageTag: {tag('measure', x['name'])}")
        L.append("")
    L += ["\tcolumn Value", "\t\tdataType: int64", "\t\tisHidden", "\t\tformatString: 0",
          f"\t\tlineageTag: {tag('column', M, 'Value')}", "\t\tsummarizeBy: none", "\t\tsourceColumn: [Value]", "",
          "\t\tannotation SummarizationSetBy = User", "",
          f"\tpartition {M} = calculated", "\t\tmode: import", '\t\tsource = ROW ( "Value", 1 )', ""]
    return "\n".join(L)


def build_model(data_folder: str) -> None:
    d = SM / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    (SM / "definition.pbism").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {"qnaEnabled": False}}, indent=2), encoding="utf-8")
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n", encoding="utf-8")
    all_tables = list(TABLES) + [p[0] for p in PARAMS] + [M]
    model = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tdiscourageImplicitMeasures",
        "\tsourceQueryCulture: en-US",
        "\tdataAccessOptions",
        "\t\tlegacyRedirects",
        "\t\treturnErrorValuesAsNull",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
        "annotation PBI_QueryOrder = " + json.dumps(["DataFolder"] + list(TABLES)),
        "",
        'annotation PBI_ProTooling = ["DevMode"]',
        "",
    ] + [f"ref table {qn(t)}" for t in all_tables] + [""]
    (d / "model.tmdl").write_text("\n".join(model), encoding="utf-8")
    folder = data_folder.rstrip("\\/") + "\\"
    (d / "expressions.tmdl").write_text("\n".join([
        "/// Folder holding the CSVs from `python scripts/build.py --export`. Change it in Transform data > Edit parameters.",
        f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]',
        f"\tlineageTag: {tag('expression', 'DataFolder')}",
        "",
        "\tannotation PBI_ResultType = Text",
        "",
    ]), encoding="utf-8")
    rel = []
    for f_t, f_c, t_t, t_c, extra in RELATIONSHIPS:
        rel.append(f"relationship {tag('rel', f_t, f_c, t_t, t_c)}")
        for k, v in extra.items():
            rel.append(f"\t{k}: {v}")
        rel.append(f"\tfromColumn: {qn(f_t)}.{qn(f_c)}")
        rel.append(f"\ttoColumn: {qn(t_t)}.{qn(t_c)}")
        rel.append("")
    (d / "relationships.tmdl").write_text("\n".join(rel), encoding="utf-8")
    for name, spec in TABLES.items():
        (d / "tables" / f"{name}.tmdl").write_text(write_table(name, spec), encoding="utf-8")
    for p in PARAMS:
        (d / "tables" / f"{p[0]}.tmdl").write_text(write_param_table(*p), encoding="utf-8")
    (d / "tables" / f"{M}.tmdl").write_text(write_measures_table(), encoding="utf-8")


# =====================================================================================
# Report (PBIR)
# =====================================================================================
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"
VC = f"{SCHEMA}/visualContainer/2.1.0/schema.json"


def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def solid(hexv):
    return {"solid": {"color": lit(hexv)}}


def mcolor(measure):
    return {"solid": {"color": {"expr": {"Measure": {"Expression": {"SourceRef": {"Entity": M}}, "Property": measure}}}}}


def fcol(entity, prop):
    return {"Column": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def fmeas(prop, entity=M):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": entity}}, "Property": prop}}


def proj(field, display=None, active=False):
    kind = "Column" if "Column" in field else "Measure"
    ent = field[kind]["Expression"]["SourceRef"]["Entity"]
    prop = field[kind]["Property"]
    p = {"field": field, "queryRef": f"{ent}.{prop}", "nativeQueryRef": prop}
    if display:
        p["displayName"] = display
    if active:
        p["active"] = True
    return p


def props(**kw):
    return {"properties": {k: (v if isinstance(v, dict) else lit(v)) for k, v in kw.items()}}


WILDCARD = {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}


class Page:
    def __init__(self, name, display, height=720):
        self.name, self.display, self.height = name, display, height
        self.visuals, self.interactions, self.z = [], [], 0

    def add(self, vname, vtype, x, y, w, h, query=None, objects=None, title=None, subtitle=None, sort=None,
            sync=None, vco=None):
        self.z += 100
        if y >= 190:          # leave room for the taller header
            y += 12
        v = {"visualType": vtype}
        if query:
            v["query"] = {"queryState": query}
            if sort:
                v["query"]["sortDefinition"] = {"sort": sort, "isDefaultSort": True}
        if objects:
            v["objects"] = objects
        vco = dict(vco or {})
        if title is not None:
            vco["title"] = [props(show=True, text=title)]
        else:
            vco.setdefault("title", [props(show=False)])
        if subtitle:
            vco["subTitle"] = [props(show=True, text=subtitle)]
        v["visualContainerObjects"] = vco
        if sync:
            v["syncGroup"] = {"groupName": sync, "fieldChanges": True, "filterChanges": True}
        v["drillFilterOtherVisuals"] = True
        self.visuals.append({"$schema": VC, "name": vname,
                             "position": {"x": x, "y": y, "z": self.z, "width": w, "height": h, "tabOrder": self.z},
                             "visual": v})
        return vname


def textbox(page, vname, x, y, w, h, text, size=10, color=INK2, bold=False):
    run = {"value": text, "textStyle": {"fontFamily": "Segoe UI Semibold" if bold else "Segoe UI",
                                        "fontSize": f"{size}pt", "color": color}}
    page.add(vname, "textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": [{"textRuns": [run]}]}}]},
             vco={"background": [props(show=False)], "border": [props(show=False)],
                  "padding": [props(top=0.0, bottom=0.0, left=0.0, right=0.0)]})


def card(page, vname, x, y, w, h, measures, cols=None, value_size=24, label=True, red=(), title=None, accent=False,
         outline=True):
    objects = {
        "layout": [props(columnCount=f"{cols or len(measures)}L" if False else (cols or len(measures)),
                         style="Cards")],
        "value": [{"properties": {"fontSize": lit(float(value_size)), "fontColor": solid(INK),
                                  "labelDisplayUnits": lit(1.0), "displayUnits": lit(1.0)}, "selector": {"id": "default"}}],
        "outline": [{"properties": {"show": lit(outline)}, "selector": {"id": "default"}}],
        "padding": [{"properties": {"paddingSelection": lit("Narrow" if not outline else "Wide")}, "selector": {"id": "default"}}],
        "label": [{"properties": {"show": lit(label), "fontColor": solid(INK2), "fontSize": lit(9.0)},
                   "selector": {"id": "default"}}],
        "shadowCustom": [{"properties": {"show": lit(False)}, "selector": {"id": "default"}}],
        "accentBar": [{"properties": {"show": lit(accent), **({"color": solid(BAD)} if accent else {})},
                       "selector": {"id": "default"}}],
    }
    for m_ in red:
        objects["value"].append({"properties": {"fontColor": solid(BAD)}, "selector": {"metadata": f"{M}.{m_}"}})
    page.add(vname, "cardVisual", x, y, w, h, query={"Data": {"projections": [proj(fmeas(m_), d) for m_, d in measures]}},
             objects=objects, title=title)


def text_card(page, vname, x, y, w, h, measure, size=11, tint=False, color=INK):
    """Classic card for sentence-length text measures: wraps instead of truncating."""
    vco = {"background": [props(show=True, color=solid("#F4F3EF"), transparency=0.0)]} if tint else {}
    page.add(vname, "card", x, y, w, h, query={"Values": {"projections": [proj(fmeas(measure))]}}, vco=vco, objects={
        "labels": [props(color=solid(color), fontSize=float(size))],
        "categoryLabels": [props(show=False)],
        "wordWrap": [props(show=True)],
    })


def header(page, takeaway_measure):
    textbox(page, "title", 24, 6, 600, 42, "Supply Chain Decision Dashboard", size=16, color=INK, bold=True)
    textbox(page, "subtitle", 24, 44, 620, 28,
            "DataCo orders · default window Jan 2015 – Sep 2017 (report filter) · cancelled and suspected-fraud orders excluded",
            size=9)
    page.add("nav", "pageNavigator", 640, 14, 616, 36, objects={
        "fill": [{"properties": {"show": lit(True), "fillColor": solid("#FFFFFF")}, "selector": {"id": "default"}},
                 {"properties": {"fillColor": solid(INK)}, "selector": {"id": "selected"}}],
        "text": [{"properties": {"fontColor": solid(INK2), "fontSize": lit(9.0)}, "selector": {"id": "default"}},
                 {"properties": {"fontColor": solid("#FFFFFF")}, "selector": {"id": "selected"}}],
        "outline": [{"properties": {"show": lit(True), "lineColor": solid("#E2E1DC"), "roundEdge": lit(8.0)},
                     "selector": {"id": "default"}}],
    })
    slicer(page, "s_month", 24, 74, 330, 64, fcol("dim_date", "month_start"), "Month", "Between", "month")
    slicer(page, "s_market", 368, 74, 220, 64, fcol("dim_geography", "market"), "Market", "Dropdown", "market")
    slicer(page, "s_segment", 602, 74, 220, 64, fcol("dim_customer", "segment"), "Segment", "Dropdown", "segment")
    slicer(page, "s_category", 836, 74, 300, 64, fcol("dim_product", "category_name"), "Category", "Dropdown", "category")
    text_card(page, "takeaway", 24, 144, 1232, 56, takeaway_measure, size=14, tint=True)


def slicer(page, vname, x, y, w, h, field, label, mode, sync):
    page.add(vname, "slicer", x, y, w, h, query={"Values": {"projections": [proj(field, label, active=True)]}},
             objects={"data": [props(mode=mode)], "header": [props(show=True, fontColor=solid(INK2), textSize=9.0)]},
             sync=sync)


def column_chart(page, vname, x, y, w, h, cat, y_measure, title, subtitle=None, color_measure=None, labels=True,
                 sort=None, tooltips=()):
    q = {"Category": {"projections": [proj(cat, active=True)]}, "Y": {"projections": [proj(fmeas(y_measure))]}}
    if tooltips:
        q["Tooltips"] = {"projections": [proj(fmeas(t)) for t in tooltips]}
    dp = [{"properties": {"fill": mcolor(color_measure)}, "selector": WILDCARD}] if color_measure else \
         [{"properties": {"fill": solid(GREY)}, "selector": {"metadata": f"{M}.{y_measure}"}}]
    page.add(vname, "clusteredColumnChart", x, y, w, h, query=q, title=title, subtitle=subtitle, sort=sort, objects={
        "dataPoint": dp,
        "labels": [props(show=labels, color=solid(INK2), fontSize=9.0)],
        "valueAxis": [props(show=True, start=0.0, showAxisTitle=True, gridlineShow=True)],
        "categoryAxis": [props(show=True, showAxisTitle=True, axisType="Categorical")],
    })


def line_chart(page, vname, x, y, w, h, cat, series, title, subtitle=None, legend=None, sort=None, tooltips=(),
               y_start=0.0, y_end=None, ref_line=None, y_title=None):
    q = {"Category": {"projections": [proj(cat, active=True)]},
         "Y": {"projections": [proj(fmeas(m_), d) for m_, d, _ in series]}}
    if legend:
        q["Series"] = {"projections": [proj(legend)]}
    if tooltips:
        q["Tooltips"] = {"projections": [proj(fmeas(t)) for t in tooltips]}
    objects = {
        "dataPoint": [{"properties": {"fill": solid(col)}, "selector": {"metadata": f"{M}.{m_}"}} for m_, _, col in series if col],
        "lineStyles": [props(strokeWidth=2, showMarker=False)],
        "legend": [props(show=bool(len(series) > 1 or legend), position="Top")],
        "valueAxis": [props(show=True, start=y_start, showAxisTitle=bool(y_title), **({"titleText": y_title} if y_title else {}),
                            **({"end": y_end} if y_end is not None else {}))],
        "categoryAxis": [props(show=True)],
    }
    if ref_line is not None:
        objects["y1AxisReferenceLine"] = [{"properties": {"show": lit(True), "value": lit(float(ref_line[0])),
                                                          "lineColor": solid(INK2), "dataLabelShow": lit(True),
                                                          "displayName": lit(ref_line[1])}, "selector": {"id": "1"}}]
    page.add(vname, "lineChart", x, y, w, h, query=q, objects=objects, title=title, subtitle=subtitle, sort=sort)


def table(page, vname, x, y, w, h, cols, title, subtitle=None, sort=None, value_formats=()):
    objects = {"total": [props(totals=False)], "values": list(value_formats)}
    page.add(vname, "tableEx", x, y, w, h, query={"Values": {"projections": cols}}, objects=objects,
             title=title, subtitle=subtitle, sort=sort)


def matrix(page, vname, x, y, w, h, rows, cols_field, value, back_measure, font_measure, title, subtitle=None):
    page.add(vname, "pivotTable", x, y, w, h, title=title, subtitle=subtitle,
             query={"Rows": {"projections": [proj(rows, active=True)]},
                    "Columns": {"projections": [proj(cols_field, active=True)]},
                    "Values": {"projections": [proj(fmeas(value))]}},
             objects={
                 "subTotals": [props(rowSubtotals=False, columnSubtotals=False)],
                 "values": [{"properties": {"backColor": mcolor(back_measure), "fontColor": mcolor(font_measure)},
                             "selector": {**WILDCARD, "metadata": f"{M}.{value}"}}],
             })


def build_pages() -> list[Page]:
    pages = []

    # ---------------- 1 Summary ----------------
    p = Page("summary", "1 Summary", 720)
    header(p, "Takeaway Summary")
    kpis = [("Revenue", "Revenue"), ("Profit", "Profit"), ("Profit Margin %", "Profit margin"),
            ("Late Rate %", "Late-delivery rate"), ("Orders", "Orders"), ("Avg Order Value", "Avg order value")]
    card(p, "kpis", 24, 194, 1232, 84, kpis, value_size=24, red=("Late Rate %",))
    card(p, "kpis_mom", 24, 278, 1232, 34,
         [("Revenue MoM", ""), ("Profit MoM", ""), ("Margin MoM", ""), ("Late Rate MoM", ""), ("Orders MoM", ""),
          ("AOV MoM", "")], value_size=9, label=False, outline=False)
    line_chart(p, "trend", 24, 318, 820, 390, fcol("dim_date", "month_start"),
               [("Revenue", "Revenue", GREY_DARK), ("Profit", "Profit", GREY)],
               "Monthly revenue and profit (USD)", "Valid orders · p1_monthly_trend.sql", y_title="USD per month")
    textbox(p, "alerts_title", 860, 318, 396, 34, "Top 3 alerts", size=13, color=INK, bold=True)
    for i in (1, 2, 3):
        textbox(p, f"alert_n{i}", 860, 380 + (i - 1) * 118, 30, 44, str(i), size=18, color=BAD, bold=True)
        text_card(p, f"alert_{i}", 896, 352 + (i - 1) * 118, 360, 110, f"Alert {i}", size=11)
    pages.append(p)

    # ---------------- 2 Delivery ----------------
    p = Page("delivery", "2 Delivery", 1300)
    header(p, "Takeaway Delivery")
    card(p, "kpis", 24, 194, 1232, 88, [("Late Rate %", "Late-delivery rate"), ("On-time %", "On time or early"),
                                         ("Avg Delay Days (late items)", "Avg delay, late items (days)"),
                                         ("Late Rate % (what-if promises)", "Late rate with new promises")],
         red=("Late Rate %",))
    for i, (mode, promise) in enumerate([("Same Day", 0), ("First Class", 1), ("Second Class", 2), ("Standard Class", 4)]):
        column_chart(p, f"dist_{i}", 24 + i * 312, 294, 296, 250, fcol("fact_order_items", "actual_days"),
                     f"Share of Items ({mode})", f"{mode}: promise {promise} day{'s' if promise != 1 else ''}",
                     "Share of items by actual shipping days; red = late", color_measure=f"Bar Color ({mode})",
                     sort=[{"field": fcol("fact_order_items", "actual_days"), "direction": "Ascending"}])
    matrix(p, "heatmap", 24, 556, 720, 540, fcol("dim_geography", "order_region"), fcol("dim_shipping", "shipping_mode"),
           "Late Rate % (heatmap)", "Heatmap Color", "Heatmap Font Color",
           "Late rate by shipping mode and region: columns differ, rows barely do",
           "Cells under 200 items blank · p2_mode_region_heatmap.sql")
    table(p, "modes", 760, 556, 496, 220, [
        proj(fcol("dim_shipping", "shipping_mode"), "Mode"), proj(fmeas("Promised Days"), "Promise (days)"),
        proj(fmeas("Avg Actual Days"), "Actual (days)"), proj(fmeas("On-time %"), "On time"),
        proj(fmeas("Late Rate %"), "Late"), proj(fmeas("Valid Items"), "Items")],
        "On-time and late rates by mode", "p2_late_by_mode.sql",
        sort=[{"field": fmeas("Promised Days"), "direction": "Ascending"}],
        value_formats=[{"properties": {"fontColor": solid(BAD)}, "selector": {"metadata": f"{M}.Late Rate %"}}])
    textbox(p, "whatif_title", 760, 790, 496, 30, "What if the promise matched reality?", size=13, color=INK, bold=True)
    slicer(p, "s_first", 760, 822, 240, 56, fcol("First Class Promise", "First Class Promise"), "First Class promise (days)",
           "Dropdown", "p_first")
    slicer(p, "s_second", 1016, 822, 240, 56, fcol("Second Class Promise", "Second Class Promise"),
           "Second Class promise (days)", "Dropdown", "p_second")
    card(p, "whatif", 760, 890, 496, 96, [("Late Rate %", "Late rate today"),
                                           ("Late Rate % (what-if promises)", "With these promises"),
                                           ("Late Rate Change (what-if)", "Change")], value_size=20)
    textbox(p, "whatif_note", 760, 994, 496, 60,
            "Defaults (2 and 4 days) take the late rate from 57.3% to 34.1% with no operational change. "
            "Actual shipping days held as observed. p2_repromise_whatif.sql", size=9)
    line_chart(p, "trend", 24, 1108, 1232, 176, fcol("dim_date", "month_start"), [("Late Rate %", "Late rate", None)],
               "Monthly late rate by mode: flat for 33 months, so the problem is structural",
               "p2_late_trend.sql", legend=fcol("dim_shipping", "shipping_mode"), y_end=1.0)
    pages.append(p)

    # ---------------- 3 Discounts ----------------
    p = Page("discounts", "3 Discounts", 1480)
    header(p, "Takeaway Discounts")
    card(p, "kpis", 24, 194, 1232, 88, [("Profit Margin %", "Profit margin"), ("Discount Spend", "Discount spend"),
                                         ("Discount Above 10%", "Discount above 10%"),
                                         ("Units above 10%", "Units/line above 10%"),
                                         ("Units at or below 10%", "Units/line at or below 10%")],
         red=("Discount Above 10%",))
    band_sort = [{"field": fcol("fact_order_items", "Discount Band"), "direction": "Ascending"}]
    column_chart(p, "margin_band", 24, 294, 608, 290, fcol("fact_order_items", "Discount Band"), "Profit Margin %",
                 "Profit margin by discount band (% of net revenue)", "Flat bands: the discount bought nothing extra · p3_margin_by_band.sql",
                 sort=band_sort)
    column_chart(p, "units_band", 648, 294, 608, 290, fcol("fact_order_items", "Discount Band"), "Avg Units per Line",
                 "Units per order line by discount band", "If discounts drove volume these would rise to the right",
                 sort=band_sort)
    textbox(p, "cap_title", 24, 598, 400, 30, "What-if: cap discounts at a maximum rate", size=13, color=INK, bold=True)
    slicer(p, "s_cap", 24, 630, 400, 56, fcol("Max Discount", "Max Discount"), "Max discount rate (default 10%)",
           "Dropdown", "p_cap")
    card(p, "cap_cards", 24, 694, 400, 250, [
        ("Items Above Cap", "Items above the cap"),
        ("Profit Recovered per Year (volume holds)", "High · volume holds ($/yr)"),
        ("Profit Recovered per Year (central)", "Central · data elasticity ($/yr)"),
        ("Profit Recovered per Year (low)", "Low · elasticity −1.5 ($/yr)"),
        ("Break-even Volume Loss %", "Break-even volume loss")], cols=1, value_size=14)
    textbox(p, "cap_note", 24, 950, 400, 110,
            "Items above the cap are re-priced at the cap with unit cost fixed. High assumes volume holds; central "
            "applies the elasticity measured in the data (none detected); low assumes a price elasticity of −1.5, "
            "standing in for orders that would not happen without the discount. Annualised over the selected months.",
            size=9)
    cap_axis = fcol("Max Discount", "Max Discount")
    line_chart(p, "cap_curve", 440, 598, 816, 462, cap_axis, [
        ("Profit Recovered per Year (volume holds)", "High · volume holds", GREY),
        ("Profit Recovered per Year (central)", "Central", GREY_DARK),
        ("Profit Recovered per Year (low)", "Low · elasticity −1.5", "#CFCDC6")],
        "Profit recovered per year by discount cap (USD)", "p3_whatif_cap.sql",
        sort=[{"field": cap_axis, "direction": "Ascending"}])
    p.interactions.append({"source": "s_cap", "target": "cap_curve", "type": "NoFilter"})
    table(p, "categories", 24, 1072, 1232, 392, [
        proj(fcol("dim_product", "category_name"), "Category"), proj(fmeas("Cat Items"), "Items"),
        proj(fmeas("Cat Margin at or below 10%"), "Margin ≤10%"), proj(fmeas("Cat Margin above 10%"), "Margin >10%"),
        proj(fmeas("Cat Margin Gap pts"), "Gap (pts)"), proj(fmeas("Cat Units at or below 10%"), "Units ≤10%"),
        proj(fmeas("Cat Units above 10%"), "Units >10%"), proj(fmeas("Cat Discount Above 10%"), "Discount above 10%")],
        "Category drill-down: at or below vs above a 10% discount",
        "Categories with 500+ items · only Women's Apparel's gap survives a Holm correction · p3_category_band.sql",
        sort=[{"field": fmeas("Cat Discount Above 10%"), "direction": "Descending"}],
        value_formats=[
            {"properties": {"fontColor": mcolor("Gap Font Color")}, "selector": {**WILDCARD, "metadata": f"{M}.Cat Margin Gap pts"}},
            {"properties": {"dataBars": {"positiveColor": solid(BAD), "negativeColor": solid(BAD), "axisColor": solid("#FFFFFF"),
                                         "reverseDirection": lit(False), "hideText": lit(False)}},
             "selector": {"metadata": f"{M}.Cat Discount Above 10%"}}])
    pages.append(p)

    # ---------------- 4 Customers ----------------
    p = Page("customers", "4 Customers", 1260)
    header(p, "Takeaway Customers")
    card(p, "kpis", 24, 194, 1232, 88, [("Customers", "Customers"), ("Month-3 Retention", "Month-3 retention"),
                                         ("Champions Revenue Share", "Champions' revenue share"),
                                         ("Next 6m Buyers Range", "Reorder in next 6 months, by segment")])
    table(p, "segments", 24, 294, 740, 300, [
        proj(fcol("rfm_segments", "rfm_segment"), "RFM segment"), proj(fmeas("Customers"), "Customers"),
        proj(fmeas("Segment Customer Share"), "Share"), proj(fmeas("Revenue"), "Revenue"),
        proj(fmeas("Segment Revenue Share"), "Revenue share"), proj(fmeas("Avg Orders per Customer"), "Orders / customer")],
        "RFM segments as of 1 Oct 2017", "Revenue for the filtered orders · p4_segment_summary.sql",
        sort=[{"field": fmeas("Revenue"), "direction": "Descending"}],
        value_formats=[{"properties": {"dataBars": {"positiveColor": solid(GREY), "negativeColor": solid(GREY),
                                                    "axisColor": solid("#FFFFFF"), "reverseDirection": lit(False),
                                                    "hideText": lit(False)}},
                        "selector": {"metadata": f"{M}.Segment Revenue Share"}}])
    column_chart(p, "rfm_valid", 780, 294, 476, 300, fcol("rfm_validation", "rfm_segment"), "RFM Next 6m Share",
                 "Does RFM predict? Share ordering in the next 6 months",
                 "Scored on data to Mar 2017, outcome Apr–Sep 2017 · not affected by filters",
                 sort=[{"field": fmeas("RFM Past Revenue per Customer"), "direction": "Descending"}],
                 tooltips=("RFM Past Revenue per Customer",))
    matrix(p, "cohorts", 24, 606, 1232, 640, fcol("cohort_retention", "cohort_month"), fcol("cohort_retention", "month_index"),
           "Cohort Retention (shown)", "Cohort Color", "Cohort Font Color",
           "Monthly cohort retention: about 1 in 8 customers orders in any month, with no decay",
           "Rows: first-order month (cohorts of 50+). Columns: months since first order. Not affected by filters · p4_cohort_retention.sql")
    pages.append(p)

    # ---------------- 5 Products ----------------
    p = Page("products", "5 Products", 1060)
    header(p, "Takeaway Products")
    card(p, "kpis", 24, 194, 1232, 88, [("Profit Share Top 20% Products", "Profit share, top 20% of products"),
                                         ("A-class Products", "A-class products (80% of profit)"),
                                         ("Loss-making Products", "Loss-making products"),
                                         ("Loss-making Line Share", "Loss-making order lines")],
         red=("Loss-making Products", "Loss-making Line Share"))
    line_chart(p, "pareto", 24, 294, 1232, 300, fcol("dim_product", "product_name"),
               [("Pareto Share (top 30)", "Cumulative profit share", GREY_DARK)],
               "Pareto: cumulative share of profit, top 30 products by profit",
               "Profit is as concentrated as revenue · p5_product_pareto.sql",
               sort=[{"field": fmeas("Profit"), "direction": "Descending"}], tooltips=("Profit", "Revenue"),
               y_end=1.0, ref_line=(0.8, "80% of profit"))
    table(p, "ranking", 24, 606, 760, 440, [
        proj(fcol("dim_product", "product_name"), "Product"), proj(fcol("dim_product", "category_name"), "Category"),
        proj(fmeas("Top15 Revenue"), "Revenue"), proj(fmeas("Top15 Profit"), "Profit"),
        proj(fmeas("Top15 Margin"), "Margin"), proj(fmeas("Top15 Cumulative Share"), "Cum. profit"),
        proj(fmeas("Top15 Class"), "Class")],
        "Top 15 products by profit", "A = first 80% of cumulative profit, B = next 15%, C = rest",
        sort=[{"field": fmeas("Top15 Profit"), "direction": "Descending"}],
        value_formats=[{"properties": {"dataBars": {"positiveColor": solid(GREY), "negativeColor": solid(BAD),
                                                    "axisColor": solid("#FFFFFF"), "reverseDirection": lit(False),
                                                    "hideText": lit(False)}},
                        "selector": {"metadata": f"{M}.Top15 Profit"}}])
    table(p, "watch", 800, 606, 456, 440, [
        proj(fcol("dim_product", "product_name"), "Product"), proj(fmeas("Watch Revenue"), "Revenue"),
        proj(fmeas("Watch Profit"), "Profit"), proj(fmeas("Watch Margin"), "Margin"), proj(fmeas("Watch Lines"), "Lines")],
        '"Sells well, loses money" watch list', "Top-half revenue with margin < 10%, or loss-making · p5_sells_well_loses_money.sql",
        sort=[{"field": fmeas("Watch Revenue"), "direction": "Descending"}],
        value_formats=[{"properties": {"fontColor": mcolor("Watch Font Color")}, "selector": {**WILDCARD, "metadata": f"{M}.Watch Profit"}},
                       {"properties": {"fontColor": mcolor("Watch Font Color")}, "selector": {**WILDCARD, "metadata": f"{M}.Watch Margin"}}])
    pages.append(p)

    # ---------------- Definitions ----------------
    p = Page("definitions", "Definitions", 720)
    textbox(p, "title", 24, 10, 620, 34, "Definitions and data notes", size=18, color=INK, bold=True)
    lines = [
        "Revenue: sum of order item total (net of discount), excluding cancelled and suspected-fraud orders.",
        "Profit margin %: profit ÷ revenue.   Orders: distinct order ids.   Avg order value: revenue ÷ orders.",
        "Late-delivery rate: items with actual shipping days > scheduled days ÷ valid items.   Avg delay: actual − scheduled, late items only.",
        "Discount spend: sum of item discount. Discount rate = discount ÷ gross sales (the listed 6% was applied at 5.5%).",
        "Month-3 retention: share of a monthly cohort that orders again in the third month after its first order.",
        "",
        "Default window: a report-level filter keeps Jan 2015 – Sep 2017 (in_analysis_window). From Oct 2017 every order has one item,",
        "the catalogue changes and almost all buyers are new. Remove the filter in the Filters pane to see the full range.",
        "Market rotates with time in this dataset, so market comparisons are also period comparisons.",
        "Every comparison is an association, not a cause. Each visual's subtitle names its query in sql/analysis/.",
        "Source: DataCo Smart Supply Chain (Constante, Silva & Pereira, 2019), Mendeley Data v5, doi:10.17632/8gx2fvg2k6.5, CC BY 4.0.",
    ]
    for i, ln in enumerate(lines):
        if ln:
            textbox(p, f"line{i}", 24, 60 + i * 34, 1232, 32, ln, size=11, color=INK)
    pages.append(p)
    return pages


def build_report() -> None:
    d = RP / "definition"
    (d / "pages").mkdir(parents=True, exist_ok=True)
    (RP / "definition.pbir").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
        "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}}, indent=2), encoding="utf-8")
    (d / "pages").mkdir(parents=True, exist_ok=True)
    (d / "version.json").write_text(json.dumps({"$schema": f"{SCHEMA}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"},
                                               indent=2), encoding="utf-8")
    ver = {"visual": "1.8.97", "report": "2.0.97", "page": "1.3.97"}
    report = {
        "$schema": f"{SCHEMA}/report/3.0.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": "CY24SU10", "reportVersionAtImport": ver, "type": "SharedResources"},
            "customTheme": {"name": "SupplyChainTheme.json", "reportVersionAtImport": ver, "type": "RegisteredResources"},
        },
        "filterConfig": {"filters": [{
            "name": "analysisWindow",
            "displayName": "Analysis window (Jan 2015 – Sep 2017)",
            "field": fcol("dim_date", "in_analysis_window"),
            "type": "Categorical",
            "filter": {"Version": 2, "From": [{"Name": "d", "Entity": "dim_date", "Type": 0}],
                       "Where": [{"Condition": {"In": {
                           "Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "d"}}, "Property": "in_analysis_window"}}],
                           "Values": [[{"Literal": {"Value": "true"}}]]}}}]},
        }]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": "CY24SU10", "path": "BaseThemes/CY24SU10.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "SupplyChainTheme.json", "path": "SupplyChainTheme.json", "type": "CustomTheme"}]},
        ],
        "settings": {"useStylableVisualContainerHeader": True, "defaultFilterActionIsDataFilter": True,
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True,
                     "allowInlineExploration": True, "useEnhancedTooltips": True},
    }
    (d / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    pages = build_pages()
    (d / "pages" / "pages.json").write_text(json.dumps({
        "$schema": f"{SCHEMA}/pagesMetadata/1.0.0/schema.json",
        "pageOrder": [p.name for p in pages], "activePageName": ACTIVE or pages[0].name}, indent=2), encoding="utf-8")
    for p in pages:
        pd_ = d / "pages" / p.name
        (pd_ / "visuals").mkdir(parents=True, exist_ok=True)
        page = {"$schema": f"{SCHEMA}/page/1.4.0/schema.json", "name": p.name, "displayName": p.display,
                "displayOption": "FitToWidth" if p.height > 720 and not FIT else "FitToPage", "height": p.height, "width": 1280,
                "objects": {"background": [props(color=solid("#FCFCFB"), transparency=0.0)],
                            "outspace": [props(color=solid("#FCFCFB"))]}}
        if p.interactions:
            page["visualInteractions"] = p.interactions
        (pd_ / "page.json").write_text(json.dumps(page, indent=2, ensure_ascii=False), encoding="utf-8")
        for v in p.visuals:
            vd = pd_ / "visuals" / v["name"]
            vd.mkdir(parents=True, exist_ok=True)
            (vd / "visual.json").write_text(json.dumps(v, indent=2, ensure_ascii=False), encoding="utf-8")
    res = RP / "StaticResources"
    (res / "RegisteredResources").mkdir(parents=True, exist_ok=True)
    (res / "SharedResources" / "BaseThemes").mkdir(parents=True, exist_ok=True)
    shutil.copy(OUT / "theme.json", res / "RegisteredResources" / "SupplyChainTheme.json")
    shutil.copy(ROOT / "scripts" / "assets" / "CY24SU10.json", res / "SharedResources" / "BaseThemes" / "CY24SU10.json")


def main() -> int:
    for path in (SM, RP):
        if path.exists():
            shutil.rmtree(path)
    build_model(str(EXPORT))
    build_report()
    (OUT / f"{NAME}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
        "settings": {"enableAutoRecovery": True}}, indent=2), encoding="utf-8")
    n_vis = sum(1 for _ in RP.rglob("visual.json"))
    print(f"  {OUT.relative_to(ROOT)}/{NAME}.pbip: {len(TABLES) + len(PARAMS) + 1} tables, {len(MEASURES) + len(PARAMS)} measures, "
          f"{len(RELATIONSHIPS)} relationships, {n_vis} visuals")
    return 0


if __name__ == "__main__":
    sys.exit(main())
