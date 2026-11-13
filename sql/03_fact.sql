-- 03_fact.sql
-- fact_order_items: grain = one row per order item (order_item_id).
-- Measures are additive except the rates; flags carry the KPI rules so every
-- consumer (Power BI, the web dashboard, the text-to-SQL prompt) applies them the same way.

CREATE OR REPLACE TABLE fact_order_items AS
SELECT
    s.order_item_id,
    s.order_id,
    CAST(strftime(s.order_ts, '%Y%m%d') AS INTEGER)            AS order_date_key,
    CAST(strftime(s.ship_ts,  '%Y%m%d') AS INTEGER)            AS ship_date_key,
    CAST(s.order_ts AS DATE)                                   AS order_date,
    s.order_ts,
    s.ship_ts,
    s.customer_id                                              AS customer_key,
    s.product_id                                               AS product_key,
    g.geo_key,
    sh.shipping_key,

    s.order_status,
    s.delivery_status,
    -- KPI rule: cancelled and suspected-fraud items are excluded from every revenue,
    -- profit and delivery KPI. Negative-profit items are real losses and stay in.
    s.order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')      AS is_valid_order,
    s.actual_days > s.scheduled_days                           AS is_late,
    s.late_delivery_risk_src,

    s.quantity,
    s.unit_price,
    s.sales,                     -- gross: unit_price x quantity
    s.discount,                  -- currency discount on the line
    s.discount_rate,             -- discount / sales as actually applied
    s.discount_rate_listed,      -- the rate printed in the source file
    s.item_total,                -- net revenue: sales - discount
    s.profit,
    s.profit_ratio,
    s.actual_days,
    s.scheduled_days,
    s.actual_days - s.scheduled_days                           AS delay_days
FROM staging.order_items s
JOIN dim_geography g
  ON  g.market = s.market AND g.order_region = s.order_region AND g.order_country = s.order_country
  AND g.order_state = s.order_state AND g.order_city = s.order_city
JOIN dim_shipping sh
  ON  sh.shipping_mode = s.shipping_mode AND sh.payment_type = s.payment_type
ORDER BY s.order_item_id;
