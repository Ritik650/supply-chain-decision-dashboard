-- Page 4 / memo recommendation 3: does RFM predict who buys next? Score customers on data
-- before 2017-04-01, then measure who ordered in the following 6 months (Apr - Sep 2017).
WITH c AS (
    SELECT customer_key, max(order_date) AS last_order_date,
           count(DISTINCT order_id) AS frequency, sum(item_total) AS monetary
    FROM fact_order_items
    WHERE is_valid_order AND order_date < DATE '2017-04-01'
    GROUP BY customer_key
), s AS (
    SELECT *, date_diff('day', last_order_date, DATE '2017-04-01') AS recency_days,
           ntile(5) OVER (ORDER BY date_diff('day', last_order_date, DATE '2017-04-01') DESC, customer_key) AS r_score,
           ntile(5) OVER (ORDER BY frequency, customer_key) AS f_score,
           ntile(5) OVER (ORDER BY monetary, customer_key) AS m_score
    FROM c
), seg AS (
    SELECT *, CASE
           WHEN r_score >= 4 AND (f_score + m_score) / 2.0 >= 4   THEN 'Champions'
           WHEN r_score >= 3 AND (f_score + m_score) / 2.0 >= 3   THEN 'Loyal'
           WHEN r_score >= 4                                      THEN 'New & promising'
           WHEN r_score <= 2 AND (f_score + m_score) / 2.0 >= 3.5 THEN 'At risk'
           WHEN r_score <= 2 AND (f_score + m_score) / 2.0 < 2.5  THEN 'Hibernating'
           ELSE 'Needs attention' END AS rfm_segment
    FROM s
), nxt AS (
    SELECT customer_key, count(DISTINCT order_id) AS next_orders, sum(item_total) AS next_revenue
    FROM fact_order_items
    WHERE is_valid_order AND order_date >= DATE '2017-04-01' AND order_date < DATE '2017-10-01'
    GROUP BY customer_key
)
SELECT seg.rfm_segment,
       count(*)                                               AS customers,
       avg(CAST(coalesce(nxt.next_orders, 0) > 0 AS INTEGER)) AS share_ordering_next_6m,
       avg(coalesce(nxt.next_revenue, 0))                     AS next_6m_revenue_per_customer,
       avg(seg.monetary)                                      AS past_revenue_per_customer
FROM seg
LEFT JOIN nxt USING (customer_key)
GROUP BY seg.rfm_segment
ORDER BY past_revenue_per_customer DESC;
