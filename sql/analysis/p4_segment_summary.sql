-- Page 4: the segment table. Customers and revenue share per RFM segment (as of 2017-10-01).
WITH rfm AS (
    -- same scoring as p4_rfm_segments.sql
    WITH c AS (
        SELECT customer_key, max(order_date) AS last_order_date,
               count(DISTINCT order_id) AS frequency, sum(item_total) AS monetary
        FROM fact_order_items
        WHERE is_valid_order AND order_date < DATE '2017-10-01'
        GROUP BY customer_key
    ), s AS (
        SELECT *, date_diff('day', last_order_date, DATE '2017-10-01') AS recency_days,
               ntile(5) OVER (ORDER BY date_diff('day', last_order_date, DATE '2017-10-01') DESC, customer_key) AS r_score,
               ntile(5) OVER (ORDER BY frequency, customer_key) AS f_score,
               ntile(5) OVER (ORDER BY monetary, customer_key) AS m_score
        FROM c
    )
    SELECT *, CASE
           WHEN r_score >= 4 AND (f_score + m_score) / 2.0 >= 4   THEN 'Champions'
           WHEN r_score >= 3 AND (f_score + m_score) / 2.0 >= 3   THEN 'Loyal'
           WHEN r_score >= 4                                      THEN 'New & promising'
           WHEN r_score <= 2 AND (f_score + m_score) / 2.0 >= 3.5 THEN 'At risk'
           WHEN r_score <= 2 AND (f_score + m_score) / 2.0 < 2.5  THEN 'Hibernating'
           ELSE 'Needs attention' END AS rfm_segment
    FROM s
)
SELECT rfm_segment,
       count(*)                                   AS customers,
       count(*) / sum(count(*)) OVER ()           AS customer_share,
       sum(monetary)                              AS revenue,
       sum(monetary) / sum(sum(monetary)) OVER () AS revenue_share,
       median(recency_days)                       AS median_recency_days,
       avg(frequency)                             AS avg_orders,
       avg(monetary)                              AS avg_revenue
FROM rfm
GROUP BY rfm_segment
ORDER BY revenue DESC;
