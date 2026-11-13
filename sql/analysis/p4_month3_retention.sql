-- Page 4 KPI: month-3 retention, pooled over every cohort that has a full month 3 inside
-- the window (cohorts Jan 2015 - Jun 2017).
WITH o AS (
    SELECT DISTINCT customer_key, CAST(date_trunc('month', order_date) AS DATE) AS order_month
    FROM fact_order_items
    WHERE is_valid_order AND order_date < DATE '2017-10-01'
),
cohort AS (
    SELECT customer_key, min(order_month) AS cohort_month FROM o GROUP BY 1
)
SELECT count(*)                                                                       AS cohort_customers,
       count(*) FILTER (WHERE EXISTS (
           SELECT 1 FROM o WHERE o.customer_key = cohort.customer_key
                             AND o.order_month = cohort.cohort_month + INTERVAL 3 MONTH)) AS active_in_month_3,
       active_in_month_3 / cohort_customers                                           AS month3_retention
FROM cohort
WHERE cohort_month <= DATE '2017-06-01';
