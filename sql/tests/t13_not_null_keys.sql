-- Rule 13. No NULLs in keys, dates or measures of the fact table.
SELECT 'T13' AS rule_id,
       'no NULL keys, dates or measures in fact_order_items' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE order_item_id IS NULL OR order_id IS NULL OR customer_key IS NULL OR product_key IS NULL
                          OR geo_key IS NULL OR shipping_key IS NULL OR order_ts IS NULL OR ship_ts IS NULL
                          OR sales IS NULL OR item_total IS NULL OR profit IS NULL OR discount IS NULL
                          OR actual_days IS NULL OR scheduled_days IS NULL) AS rows_failed,
       'checked 14 columns' AS detail
FROM fact_order_items;
