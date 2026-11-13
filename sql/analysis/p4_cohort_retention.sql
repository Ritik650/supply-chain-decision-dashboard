-- Page 4: monthly cohort retention matrix. Cohort = month of a customer's first valid order;
-- retention at month k = share of the cohort with a valid order in month k after it.
-- Analysis window only, so the last cohorts have short histories.
WITH o AS (
    SELECT DISTINCT customer_key, CAST(date_trunc('month', order_date) AS DATE) AS order_month
    FROM fact_order_items
    WHERE is_valid_order AND order_date < DATE '2017-10-01'
),
cohort AS (
    SELECT customer_key, min(order_month) AS cohort_month FROM o GROUP BY 1
),
sizes AS (
    SELECT cohort_month, count(*) AS cohort_size FROM cohort GROUP BY 1
)
SELECT c.cohort_month,
       s.cohort_size,
       date_diff('month', c.cohort_month, o.order_month)          AS month_index,
       count(DISTINCT o.customer_key)                             AS active_customers,
       count(DISTINCT o.customer_key) / any_value(s.cohort_size)  AS retention
FROM o
JOIN cohort c USING (customer_key)
JOIN sizes s USING (cohort_month)
GROUP BY 1, 2, 3
ORDER BY 1, 3;
