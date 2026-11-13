-- Rule 11. Shifted customer-address rows (state holds a ZIP code) were repaired in staging.
SELECT 'T11' AS rule_id,
       'customer address rows shifted one column (repaired in staging)' AS rule,
       'info' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE customer_address_fixed) AS rows_failed,
       'customers affected: ' || count(DISTINCT customer_id) FILTER (WHERE customer_address_fixed)
         || '; numeric states left after repair: ' || count(*) FILTER (WHERE regexp_matches(customer_state, '^[0-9]+$')) AS detail
FROM staging.order_items;
