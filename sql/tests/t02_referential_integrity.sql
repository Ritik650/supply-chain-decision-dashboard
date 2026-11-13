-- Rule 2. Referential integrity: every fact key exists in its dimension.
SELECT 'T02' AS rule_id,
       'every fact key exists in its dimension' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE c.customer_key IS NULL OR p.product_key IS NULL OR g.geo_key IS NULL
                          OR s.shipping_key IS NULL OR od.date_key IS NULL OR sd.date_key IS NULL) AS rows_failed,
       'orphans: customer=' || count(*) FILTER (WHERE c.customer_key IS NULL)
         || ', product=' || count(*) FILTER (WHERE p.product_key IS NULL)
         || ', geo=' || count(*) FILTER (WHERE g.geo_key IS NULL)
         || ', shipping=' || count(*) FILTER (WHERE s.shipping_key IS NULL)
         || ', order_date=' || count(*) FILTER (WHERE od.date_key IS NULL)
         || ', ship_date=' || count(*) FILTER (WHERE sd.date_key IS NULL) AS detail
FROM fact_order_items f
LEFT JOIN dim_customer  c  ON c.customer_key = f.customer_key
LEFT JOIN dim_product   p  ON p.product_key  = f.product_key
LEFT JOIN dim_geography g  ON g.geo_key      = f.geo_key
LEFT JOIN dim_shipping  s  ON s.shipping_key = f.shipping_key
LEFT JOIN dim_date      od ON od.date_key    = f.order_date_key
LEFT JOIN dim_date      sd ON sd.date_key    = f.ship_date_key;
