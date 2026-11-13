-- 01_staging.sql
-- One row per order item. Types are cast explicitly, names are snake_case,
-- whitespace is trimmed, and columns that are masked, empty, constant or exact
-- copies are dropped (see docs/data_quality_log.md for the evidence behind each drop).
--
-- Dropped:  Customer Email, Customer Password      masked: one value 'XXXXXXXXX'
--           Customer Fname, Customer Lname, Street personal data, not needed for any KPI
--           Customer Zipcode, Order Zipcode        not needed; Order Zipcode is 86% null
--           Product Description                     100% empty
--           Product Image                           URL, no analytic value
--           Product Status                          constant 0
--           Latitude, Longitude                     store coordinates, not used
--           Benefit per order                       = Order Profit Per Order (tested in sql/tests)
--           Sales per customer                      = Order Item Total
--           Product Price                           = Order Item Product Price
--           Category Id                             = Product Category Id
--           Customer Id                             = Order Customer Id
--           Order Item Cardprod Id                  = Product Card Id

CREATE SCHEMA IF NOT EXISTS staging;

CREATE OR REPLACE TABLE staging.order_items AS
WITH typed AS (
    SELECT
        CAST("Order Item Id" AS INTEGER)                              AS order_item_id,
        CAST("Order Id" AS INTEGER)                                   AS order_id,
        strptime("order date (DateOrders)", '%m/%d/%Y %H:%M')         AS order_ts,
        strptime("shipping date (DateOrders)", '%m/%d/%Y %H:%M')      AS ship_ts,

        CAST("Order Customer Id" AS INTEGER)                          AS customer_id,
        trim("Customer Segment")                                      AS customer_segment,
        trim("Customer City")                                         AS customer_city_src,
        trim("Customer State")                                        AS customer_state_src,
        trim("Customer Street")                                       AS customer_street_src,
        CASE trim("Customer Country")
            WHEN 'EE. UU.' THEN 'United States' ELSE trim("Customer Country")
        END                                                           AS customer_country,

        CAST("Product Card Id" AS INTEGER)                            AS product_id,
        trim("Product Name")                                          AS product_name,
        CAST("Product Category Id" AS INTEGER)                        AS category_id,
        trim("Category Name")                                         AS category_name,
        CAST("Department Id" AS INTEGER)                              AS department_id,
        trim("Department Name")                                       AS department_name,

        trim("Market")                                                AS market,
        regexp_replace(trim("Order Region"), '\s+', ' ', 'g')         AS order_region,
        trim("Order Country")                                         AS order_country,
        trim("Order State")                                           AS order_state,
        trim("Order City")                                            AS order_city,

        trim("Shipping Mode")                                         AS shipping_mode,
        trim("Type")                                                  AS payment_type,
        trim("Order Status")                                          AS order_status,
        trim("Delivery Status")                                       AS delivery_status,
        CAST("Late_delivery_risk" AS TINYINT)                         AS late_delivery_risk_src,
        CAST("Days for shipping (real)" AS SMALLINT)                  AS actual_days,
        CAST("Days for shipment (scheduled)" AS SMALLINT)             AS scheduled_days,

        CAST("Order Item Quantity" AS SMALLINT)                       AS quantity,
        ROUND(CAST("Order Item Product Price" AS DOUBLE), 2)          AS unit_price,
        ROUND(CAST("Sales" AS DOUBLE), 2)                             AS sales,
        ROUND(CAST("Order Item Discount" AS DOUBLE), 2)               AS discount,
        ROUND(CAST("Order Item Discount Rate" AS DOUBLE), 2)          AS discount_rate_listed,
        ROUND(CAST("Order Item Total" AS DOUBLE), 2)                  AS item_total,
        -- Despite its name this is item-level profit: profit_ratio x item_total reproduces it on every row.
        ROUND(CAST("Order Profit Per Order" AS DOUBLE), 2)            AS profit,
        ROUND(CAST("Order Item Profit Ratio" AS DOUBLE), 4)           AS profit_ratio
    FROM raw.dataco
)
SELECT
    * EXCLUDE (customer_city_src, customer_state_src, customer_street_src),
    -- 3 rows (2 customers) are shifted one column left: city holds the state code,
    -- state holds a ZIP code, street holds the city. Shift them back.
    CASE WHEN regexp_matches(customer_state_src, '^[0-9]+$')
         THEN customer_street_src ELSE customer_city_src END          AS customer_city,
    CASE WHEN regexp_matches(customer_state_src, '^[0-9]+$')
         THEN customer_city_src ELSE customer_state_src END           AS customer_state,
    regexp_matches(customer_state_src, '^[0-9]+$')                    AS customer_address_fixed,
    -- The listed 6% rate was applied at 5.5% on all of its rows; use the rate actually applied.
    ROUND(discount / NULLIF(sales, 0), 3)                             AS discount_rate
FROM typed;
