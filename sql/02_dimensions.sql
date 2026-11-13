-- 02_dimensions.sql
-- Five dimensions for the star schema. Keys are natural ids where the source has a
-- stable one (customer, product) and surrogate integers otherwise.

-- dim_date: one row per calendar day from the first order to the last shipment.
-- in_analysis_window marks Jan 2015 - Sep 2017. From Oct 2017 the source changes regime
-- (one item per order, a different product catalogue, every customer new), so trends,
-- cohorts and the memo use the window; the full range stays available.
CREATE OR REPLACE TABLE dim_date AS
WITH bounds AS (
    SELECT CAST(min(order_ts) AS DATE) AS lo, CAST(max(ship_ts) AS DATE) AS hi
    FROM staging.order_items
),
days AS (
    SELECT CAST(r.d AS DATE) AS d
    FROM bounds, range(bounds.lo, bounds.hi + INTERVAL 1 DAY, INTERVAL 1 DAY) AS r(d)
)
SELECT
    CAST(strftime(d, '%Y%m%d') AS INTEGER)       AS date_key,
    d                                            AS date,
    year(d)                                      AS year,
    quarter(d)                                   AS quarter,
    month(d)                                     AS month,
    strftime(d, '%b')                            AS month_name,
    CAST(date_trunc('month', d) AS DATE)         AS month_start,
    strftime(d, '%Y-%m')                         AS year_month,
    isodow(d)                                    AS weekday_num,
    strftime(d, '%a')                            AS weekday_name,
    isodow(d) >= 6                               AS is_weekend,
    d < DATE '2017-10-01'                        AS in_analysis_window
FROM days
ORDER BY d;

-- dim_customer: attributes are constant per customer (tested), so any_value is exact.
-- cohort_month is the month of the customer's first valid (not cancelled, not
-- suspected-fraud) order; it is NULL for customers with no valid order.
CREATE OR REPLACE TABLE dim_customer AS
SELECT
    customer_id                                                    AS customer_key,
    any_value(customer_segment)                                    AS segment,
    any_value(customer_city)                                       AS city,
    any_value(customer_state)                                      AS state,
    any_value(customer_country)                                    AS country,
    CAST(min(order_ts) FILTER (WHERE order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD')) AS DATE)
                                                                   AS first_order_date,
    CAST(date_trunc('month', min(order_ts) FILTER (WHERE order_status NOT IN ('CANCELED', 'SUSPECTED_FRAUD'))) AS DATE)
                                                                   AS cohort_month
FROM staging.order_items
GROUP BY customer_id
ORDER BY customer_id;

-- dim_product: name, category, department and list price are constant per product (tested).
CREATE OR REPLACE TABLE dim_product AS
SELECT
    product_id                  AS product_key,
    any_value(product_name)     AS product_name,
    any_value(category_id)      AS category_id,
    any_value(category_name)    AS category_name,
    any_value(department_id)    AS department_id,
    any_value(department_name)  AS department_name,
    any_value(unit_price)       AS list_price
FROM staging.order_items
GROUP BY product_id
ORDER BY product_id;

-- dim_geography: the delivery destination. Market > region > country > state > city.
CREATE OR REPLACE TABLE dim_geography AS
SELECT
    CAST(row_number() OVER (ORDER BY market, order_region, order_country, order_state, order_city) AS INTEGER) AS geo_key,
    market, order_region, order_country, order_state, order_city
FROM (
    SELECT DISTINCT market, order_region, order_country, order_state, order_city
    FROM staging.order_items
);

-- dim_shipping: shipping mode x payment type. promised_days is the scheduled lead
-- time, which is fixed per mode in this data (tested).
CREATE OR REPLACE TABLE dim_shipping AS
SELECT
    CAST(row_number() OVER (ORDER BY promised_days, shipping_mode, payment_type) AS INTEGER) AS shipping_key,
    shipping_mode, promised_days, payment_type
FROM (
    SELECT shipping_mode, payment_type, any_value(scheduled_days) AS promised_days
    FROM staging.order_items
    GROUP BY shipping_mode, payment_type
);
