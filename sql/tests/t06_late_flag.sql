-- Rule 6. Late flag: our is_late (actual > scheduled days) agrees with the
-- source's Late_delivery_risk. Mismatches are logged, not fatal.
SELECT 'T06' AS rule_id,
       'is_late agrees with source Late_delivery_risk' AS rule,
       'warn' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE CAST(is_late AS INTEGER) <> late_delivery_risk_src) AS rows_failed,
       'mismatches by delivery_status: '
         || coalesce(string_agg(DISTINCT delivery_status, ', ') FILTER (WHERE CAST(is_late AS INTEGER) <> late_delivery_risk_src), 'none')
         || '; mismatches on valid orders: '
         || count(*) FILTER (WHERE CAST(is_late AS INTEGER) <> late_delivery_risk_src AND is_valid_order) AS detail
FROM fact_order_items;
