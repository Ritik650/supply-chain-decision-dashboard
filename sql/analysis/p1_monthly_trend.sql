-- Page 1: monthly revenue, profit and late rate over the full date range.
-- in_analysis_window marks the months the dashboard and memo use by default.
SELECT
    d.month_start,
    bool_and(d.in_analysis_window)                 AS in_analysis_window,
    sum(f.item_total)                              AS revenue,
    sum(f.profit)                                  AS profit,
    sum(f.profit) / sum(f.item_total)              AS profit_margin,
    avg(CAST(f.is_late AS INTEGER))                AS late_rate,
    count(DISTINCT f.order_id)                     AS orders,
    count(*)                                       AS order_items
FROM fact_order_items f
JOIN dim_date d ON d.date_key = f.order_date_key
WHERE f.is_valid_order
GROUP BY d.month_start
ORDER BY d.month_start;
