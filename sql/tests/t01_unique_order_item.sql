-- Rule 1. Uniqueness: order_item_id is unique in the fact table (the declared grain).
SELECT 'T01' AS rule_id,
       'order_item_id is unique in fact_order_items' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) - count(DISTINCT order_item_id) AS rows_failed,
       'duplicate order_item_id values' AS detail
FROM fact_order_items;
