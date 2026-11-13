-- Page 2: monthly late rate by shipping mode (analysis window).
SELECT d.month_start,
       s.shipping_mode,
       count(*)                          AS order_items,
       avg(CAST(f.is_late AS INTEGER))   AS late_rate
FROM fact_order_items f
JOIN dim_date d ON d.date_key = f.order_date_key
JOIN dim_shipping s USING (shipping_key)
WHERE f.is_valid_order AND d.in_analysis_window
GROUP BY 1, 2
ORDER BY 1, 2;
