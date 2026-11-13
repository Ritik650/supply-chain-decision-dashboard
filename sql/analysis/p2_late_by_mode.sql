-- Page 2 (Delivery performance, Q1): late rate, on-time %, average delay and the
-- promised-vs-actual gap by shipping mode, analysis window, valid orders only.
-- Avg delay days is measured over late items only (KPI definition).
SELECT
    s.shipping_mode,
    any_value(s.promised_days)                                  AS promised_days,
    count(*)                                                    AS order_items,
    avg(CAST(f.is_late AS INTEGER))                             AS late_rate,
    1 - avg(CAST(f.is_late AS INTEGER))                         AS on_time_rate,
    avg(f.delay_days) FILTER (WHERE f.is_late)                  AS avg_delay_days_late_items,
    avg(f.actual_days)                                          AS avg_actual_days,
    min(f.actual_days)                                          AS min_actual_days,
    max(f.actual_days)                                          AS max_actual_days
FROM fact_order_items f
JOIN dim_shipping s USING (shipping_key)
WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
GROUP BY s.shipping_mode
ORDER BY promised_days;
