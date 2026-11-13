-- Rule 3. Valid ranges: quantity > 0, price > 0, discount rate in [0, 1].
SELECT 'T03' AS rule_id,
       'quantity > 0, unit_price > 0, 0 <= discount_rate <= 1' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE quantity <= 0 OR unit_price <= 0 OR discount_rate NOT BETWEEN 0 AND 1
                          OR quantity IS NULL OR unit_price IS NULL OR discount_rate IS NULL) AS rows_failed,
       'qty<=0: ' || count(*) FILTER (WHERE quantity <= 0)
         || ', price<=0: ' || count(*) FILTER (WHERE unit_price <= 0)
         || ', rate out of range: ' || count(*) FILTER (WHERE discount_rate NOT BETWEEN 0 AND 1) AS detail
FROM fact_order_items;
