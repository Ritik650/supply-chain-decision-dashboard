-- Rule 7. Duplicate columns: confirm suspected copies are equal before dropping one.
-- Runs on the raw text so nothing is hidden by casting.
SELECT 'T07' AS rule_id,
       '6 suspected duplicate column pairs are identical in raw data' AS rule,
       'error' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE "Benefit per order" IS DISTINCT FROM "Order Profit Per Order"
                          OR "Sales per customer" IS DISTINCT FROM "Order Item Total"
                          OR "Product Price" IS DISTINCT FROM "Order Item Product Price"
                          OR "Category Id" IS DISTINCT FROM "Product Category Id"
                          OR "Customer Id" IS DISTINCT FROM "Order Customer Id"
                          OR "Product Card Id" IS DISTINCT FROM "Order Item Cardprod Id") AS rows_failed,
       'pairs: Benefit per order=Order Profit Per Order; Sales per customer=Order Item Total; '
         || 'Product Price=Order Item Product Price; Category Id=Product Category Id; '
         || 'Customer Id=Order Customer Id; Product Card Id=Order Item Cardprod Id' AS detail
FROM raw.dataco;
