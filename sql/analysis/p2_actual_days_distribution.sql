-- Page 2: scheduled vs actual days. Share of each mode's items by actual shipping days,
-- next to the promised days. Shows that Second Class ships no faster than Standard.
SELECT s.shipping_mode,
       any_value(s.promised_days)                                            AS promised_days,
       f.actual_days,
       count(*)                                                              AS order_items,
       count(*) / sum(count(*)) OVER (PARTITION BY s.shipping_mode)          AS share_of_mode
FROM fact_order_items f
JOIN dim_shipping s USING (shipping_key)
WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
GROUP BY s.shipping_mode, f.actual_days
ORDER BY promised_days, f.actual_days;
