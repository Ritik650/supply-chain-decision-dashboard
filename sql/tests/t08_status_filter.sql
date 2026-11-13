-- Rule 8. Status filter: count the cancelled and suspected-fraud items excluded
-- from every revenue, profit and delivery KPI.
SELECT 'T08' AS rule_id,
       'items excluded from KPIs (CANCELED, SUSPECTED_FRAUD)' AS rule,
       'info' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE NOT is_valid_order) AS rows_failed,
       'CANCELED=' || count(*) FILTER (WHERE order_status = 'CANCELED')
         || ', SUSPECTED_FRAUD=' || count(*) FILTER (WHERE order_status = 'SUSPECTED_FRAUD')
         || ', excluded revenue=' || round(sum(item_total) FILTER (WHERE NOT is_valid_order), 0) AS detail
FROM fact_order_items;
