-- Page 3: category drill-down. Margin and quantity at or below vs above a 10% discount,
-- for categories with at least 1,000 items in the window.
SELECT
    p.category_name,
    count(*)                                                                   AS order_items,
    sum(f.profit) FILTER (WHERE f.discount_rate <= 0.10)
      / sum(f.item_total) FILTER (WHERE f.discount_rate <= 0.10)               AS margin_at_or_below_10,
    sum(f.profit) FILTER (WHERE f.discount_rate > 0.10)
      / sum(f.item_total) FILTER (WHERE f.discount_rate > 0.10)                AS margin_above_10,
    avg(f.quantity) FILTER (WHERE f.discount_rate <= 0.10)                     AS qty_at_or_below_10,
    avg(f.quantity) FILTER (WHERE f.discount_rate > 0.10)                      AS qty_above_10,
    sum((f.discount_rate - 0.10) * f.sales) FILTER (WHERE f.discount_rate > 0.10) AS discount_above_10_cap
FROM fact_order_items f
JOIN dim_product p USING (product_key)
WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
GROUP BY 1
HAVING count(*) >= 1000
ORDER BY discount_above_10_cap DESC;
