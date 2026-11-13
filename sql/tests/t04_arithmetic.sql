-- Rule 4. Arithmetic: sales = unit_price x quantity and item_total = sales - discount,
-- within 2 cents (the source stores 7-digit floats).
SELECT 'T04' AS rule_id,
       'sales = price x qty and item_total = sales - discount (+/- 0.02)' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE abs(sales - unit_price * quantity) > 0.02
                          OR abs(item_total - (sales - discount)) > 0.02) AS rows_failed,
       'max |sales - price*qty| = ' || round(max(abs(sales - unit_price * quantity)), 4)
         || ', max |total - (sales - discount)| = ' || round(max(abs(item_total - (sales - discount))), 4) AS detail
FROM fact_order_items;
