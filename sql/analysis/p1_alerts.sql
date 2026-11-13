-- Page 1: the three alerts shown on the executive summary, one row each.
WITH w AS (
    SELECT f.*, s.shipping_mode
    FROM fact_order_items f
    JOIN dim_shipping s USING (shipping_key)
    WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
),
mode_late AS (
    SELECT shipping_mode, avg(CAST(is_late AS INTEGER)) AS late_rate, count(*) AS items
    FROM w GROUP BY 1
)
SELECT 1 AS alert_rank,
       'First Class late rate' AS alert,
       (SELECT late_rate FROM mode_late WHERE shipping_mode = 'First Class') AS value,
       'share of First Class items delivered after the promised date' AS meaning
UNION ALL
SELECT 2,
       'Discount spend above a 10% cap',
       (SELECT sum((discount_rate - 0.10) * sales) FROM w WHERE discount_rate > 0.10),
       'currency given away above 10% in the window; no matching volume gain (page 3)'
UNION ALL
SELECT 3,
       'Loss-making order lines',
       (SELECT avg(CAST(profit < 0 AS INTEGER)) FROM w),
       'share of valid order items with negative profit'
ORDER BY alert_rank;
