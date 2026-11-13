-- Rule 14. No rows lost or duplicated between raw, staging and fact.
SELECT 'T14' AS rule_id,
       'raw, staging and fact row counts match' AS rule,
       'error' AS severity,
       (SELECT count(*) FROM raw.dataco) AS rows_checked,
       abs((SELECT count(*) FROM raw.dataco) - (SELECT count(*) FROM fact_order_items))
         + abs((SELECT count(*) FROM raw.dataco) - (SELECT count(*) FROM staging.order_items)) AS rows_failed,
       'raw=' || (SELECT count(*) FROM raw.dataco) || ', staging=' || (SELECT count(*) FROM staging.order_items)
         || ', fact=' || (SELECT count(*) FROM fact_order_items) AS detail;
