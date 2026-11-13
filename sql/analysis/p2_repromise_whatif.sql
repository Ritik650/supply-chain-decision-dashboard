-- Page 2 / memo recommendation 2: late rate if First Class were promised in 2 days and
-- Second Class in 4 days, holding actual shipping days as observed.
WITH w AS (
    SELECT f.actual_days, f.scheduled_days, s.shipping_mode,
           CASE s.shipping_mode WHEN 'First Class' THEN 2 WHEN 'Second Class' THEN 4
                ELSE f.scheduled_days END AS new_promise
    FROM fact_order_items f
    JOIN dim_shipping s USING (shipping_key)
    WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
)
SELECT 'current promise'                                                  AS scenario,
       avg(CAST(actual_days > scheduled_days AS INTEGER))                 AS late_rate
FROM w
UNION ALL
SELECT 'First Class promised 2 days',
       avg(CAST(actual_days > CASE WHEN shipping_mode = 'First Class' THEN 2 ELSE scheduled_days END AS INTEGER))
FROM w
UNION ALL
SELECT 'First Class 2 days + Second Class 4 days',
       avg(CAST(actual_days > new_promise AS INTEGER))
FROM w;
