-- Page 3 (Discounts and margin, Q2): profit margin, quantity and discount spend by
-- discount band. Bands use the discount rate actually applied (discount / sales).
SELECT
    CASE WHEN f.discount_rate < 0.05 THEN '0-5%'
         WHEN f.discount_rate < 0.10 THEN '5-10%'
         WHEN f.discount_rate < 0.15 THEN '10-15%'
         WHEN f.discount_rate < 0.20 THEN '15-20%'
         ELSE '20-25%' END                        AS discount_band,
    min(f.discount_rate)                          AS min_rate,
    max(f.discount_rate)                          AS max_rate,
    count(*)                                      AS order_items,
    sum(f.sales)                                  AS gross_sales,
    sum(f.discount)                               AS discount_spend,
    sum(f.item_total)                             AS revenue,
    sum(f.profit)                                 AS profit,
    sum(f.profit) / sum(f.item_total)             AS profit_margin,
    sum(f.profit) / sum(f.sales)                  AS profit_per_gross_sales,
    avg(f.quantity)                               AS avg_quantity
FROM fact_order_items f
WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
GROUP BY 1
ORDER BY min_rate;
