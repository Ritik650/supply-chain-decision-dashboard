-- Rule 9. Dimension attributes are constant within their key, so any_value() in
-- 02_dimensions.sql is exact (customer, product, shipping-mode promise).
WITH cust AS (
    SELECT customer_id FROM staging.order_items GROUP BY 1
    HAVING count(DISTINCT customer_segment) > 1 OR count(DISTINCT customer_city) > 1
        OR count(DISTINCT customer_state) > 1 OR count(DISTINCT customer_country) > 1
), prod AS (
    SELECT product_id FROM staging.order_items GROUP BY 1
    HAVING count(DISTINCT product_name) > 1 OR count(DISTINCT category_id) > 1
        OR count(DISTINCT department_id) > 1 OR count(DISTINCT unit_price) > 1
), ship AS (
    SELECT shipping_mode FROM staging.order_items GROUP BY 1 HAVING count(DISTINCT scheduled_days) > 1
)
SELECT 'T09' AS rule_id,
       'customer, product and shipping-mode attributes are constant per key' AS rule,
       'error' AS severity,
       (SELECT count(DISTINCT customer_id) + count(DISTINCT product_id) + count(DISTINCT shipping_mode) FROM staging.order_items) AS rows_checked,
       (SELECT count(*) FROM cust) + (SELECT count(*) FROM prod) + (SELECT count(*) FROM ship) AS rows_failed,
       'keys with varying attributes: customers=' || (SELECT count(*) FROM cust)
         || ', products=' || (SELECT count(*) FROM prod) || ', modes=' || (SELECT count(*) FROM ship) AS detail;
