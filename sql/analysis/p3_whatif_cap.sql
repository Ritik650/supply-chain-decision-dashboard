-- Page 3 what-if: profit recovered if every discount above a cap were cut to the cap,
-- for caps 0% - 25% in 1-point steps, assuming volume holds (the upper bound).
-- Unit cost is held fixed, so each currency unit of discount removed is a unit of profit.
-- The central and low estimates apply a volume response on top (notebooks/q2_discounts.ipynb).
WITH caps AS (
    SELECT CAST(c AS DOUBLE) / 100 AS cap FROM range(0, 26) AS t(c)
),
w AS (
    SELECT discount_rate, sales, profit, item_total
    FROM fact_order_items
    WHERE is_valid_order AND order_date < DATE '2017-10-01'
)
SELECT
    caps.cap,
    count(w.sales)                                                  AS items_above_cap,
    coalesce(sum((w.discount_rate - caps.cap) * w.sales), 0)        AS profit_recovered_window,
    coalesce(sum((w.discount_rate - caps.cap) * w.sales), 0) * 12 / 33 AS profit_recovered_per_year,
    coalesce(sum(w.profit), 0)                                      AS current_profit_affected_items,
    -- break-even: the share of the affected items' volume that could be lost before the cap stops paying
    coalesce(sum((w.discount_rate - caps.cap) * w.sales)
             / nullif(sum(w.profit + (w.discount_rate - caps.cap) * w.sales), 0), 0) AS breakeven_volume_loss
FROM caps
LEFT JOIN w ON w.discount_rate > caps.cap + 1e-9
GROUP BY caps.cap
ORDER BY caps.cap;
