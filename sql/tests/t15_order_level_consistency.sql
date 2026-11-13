-- Rule 15. Order-level fields (customer, timestamp, ship mode, status, destination) are
-- identical across the items of one order, so order counts are well defined.
SELECT 'T15' AS rule_id,
       'order-level attributes constant across items of an order' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE n_cust > 1 OR n_ts > 1 OR n_ship > 1 OR n_status > 1 OR n_geo > 1) AS rows_failed,
       'unit: orders' AS detail
FROM (
    SELECT order_id,
           count(DISTINCT customer_key) AS n_cust, count(DISTINCT order_ts) AS n_ts, count(DISTINCT shipping_key) AS n_ship,
           count(DISTINCT order_status) AS n_status, count(DISTINCT geo_key) AS n_geo
    FROM fact_order_items
    GROUP BY order_id
);
