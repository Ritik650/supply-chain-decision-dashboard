-- Rule 10. The listed discount rate matches the discount actually applied
-- (discount / sales). Logged, not fatal: the build uses the applied rate.
SELECT 'T10' AS rule_id,
       'listed discount rate = discount / sales (+/- 0.001)' AS rule,
       'warn' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE abs(discount_rate_listed - discount_rate) > 0.001) AS rows_failed,
       'mismatching listed rates: '
         || coalesce(string_agg(DISTINCT CAST(discount_rate_listed AS VARCHAR) || ' applied as ' || CAST(discount_rate AS VARCHAR), '; ')
                     FILTER (WHERE abs(discount_rate_listed - discount_rate) > 0.001), 'none') AS detail
FROM fact_order_items;
