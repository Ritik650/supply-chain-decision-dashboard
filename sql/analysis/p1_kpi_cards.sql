-- Page 1 (Executive summary): headline KPI cards for the analysis window
-- (Jan 2015 - Sep 2017), with month-on-month change for the last full month (Sep 2017 vs Aug 2017).
-- Revenue, profit and late rate exclude CANCELED and SUSPECTED_FRAUD (docs/kpi_definitions.md).
WITH base AS (
    SELECT f.*, d.month_start
    FROM fact_order_items f
    JOIN dim_date d ON d.date_key = f.order_date_key
    WHERE f.is_valid_order AND d.in_analysis_window
),
agg AS (
    SELECT
        'window'                                   AS period,
        sum(item_total)                            AS revenue,
        sum(profit)                                AS profit,
        sum(profit) / sum(item_total)              AS profit_margin,
        avg(CAST(is_late AS INTEGER))              AS late_rate,
        count(DISTINCT order_id)                   AS orders,
        sum(item_total) / count(DISTINCT order_id) AS avg_order_value,
        count(*)                                   AS order_items
    FROM base
    UNION ALL
    SELECT
        strftime(month_start, '%Y-%m'),
        sum(item_total), sum(profit), sum(profit) / sum(item_total),
        avg(CAST(is_late AS INTEGER)), count(DISTINCT order_id),
        sum(item_total) / count(DISTINCT order_id), count(*)
    FROM base
    WHERE month_start IN (DATE '2017-08-01', DATE '2017-09-01')
    GROUP BY month_start
)
SELECT * FROM agg ORDER BY period DESC;
