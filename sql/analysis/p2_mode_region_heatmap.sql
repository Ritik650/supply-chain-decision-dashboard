-- Page 2: late rate by shipping mode x order region (the heatmap). Cells with
-- fewer than 200 items are dropped so a few orders can't paint a cell red.
SELECT s.shipping_mode,
       g.order_region,
       count(*)                               AS order_items,
       avg(CAST(f.is_late AS INTEGER))        AS late_rate,
       avg(f.actual_days - f.scheduled_days)  AS avg_delay_days
FROM fact_order_items f
JOIN dim_shipping s USING (shipping_key)
JOIN dim_geography g USING (geo_key)
WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
GROUP BY 1, 2
HAVING count(*) >= 200
ORDER BY late_rate DESC;
