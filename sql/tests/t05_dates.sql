-- Rule 5. Dates: ship date on or after order date, no future dates, and the
-- day difference matches the source's "Days for shipping (real)".
SELECT 'T05' AS rule_id,
       'ship_ts >= order_ts, no future dates, ship - order days = actual_days' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE ship_ts < order_ts OR order_ts > current_timestamp OR ship_ts > current_timestamp
                          OR date_diff('day', CAST(order_ts AS DATE), CAST(ship_ts AS DATE)) <> actual_days) AS rows_failed,
       'order dates ' || CAST(min(order_date) AS VARCHAR) || ' to ' || CAST(max(order_date) AS VARCHAR)
         || '; ship dates to ' || CAST(CAST(max(ship_ts) AS DATE) AS VARCHAR) AS detail
FROM fact_order_items;
