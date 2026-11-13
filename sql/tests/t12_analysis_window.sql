-- Rule 12. Items outside the analysis window (orders from Oct 2017 on), where the
-- source changes regime: every order has one item and the product mix changes.
SELECT 'T12' AS rule_id,
       'items after the analysis window (order_date >= 2017-10-01)' AS rule,
       'info' AS severity,
       count(*) AS rows_checked,
       count(*) FILTER (WHERE NOT d.in_analysis_window) AS rows_failed,
       'items/order inside window=' || round(count(*) FILTER (WHERE d.in_analysis_window)
                                      / count(DISTINCT f.order_id) FILTER (WHERE d.in_analysis_window), 2)
         || ', after=' || round(count(*) FILTER (WHERE NOT d.in_analysis_window)
                                / count(DISTINCT f.order_id) FILTER (WHERE NOT d.in_analysis_window), 2)
         || '; products sold after window=' || count(DISTINCT f.product_key) FILTER (WHERE NOT d.in_analysis_window) AS detail
FROM fact_order_items f
JOIN dim_date d ON d.date_key = f.order_date_key;
