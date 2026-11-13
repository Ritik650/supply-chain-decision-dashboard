-- Page 4 (Customers, Q3): RFM scores and segments as of 2017-10-01 (end of the window).
-- R = days since last valid order, F = distinct valid orders, M = revenue. Scores are
-- quintiles (5 = best); ties are broken by customer_key so the split is deterministic.
WITH c AS (
    SELECT customer_key,
           max(order_date)                AS last_order_date,
           count(DISTINCT order_id)       AS frequency,
           sum(item_total)                AS monetary
    FROM fact_order_items
    WHERE is_valid_order AND order_date < DATE '2017-10-01'
    GROUP BY customer_key
),
scored AS (
    SELECT *,
           date_diff('day', last_order_date, DATE '2017-10-01')                                AS recency_days,
           ntile(5) OVER (ORDER BY date_diff('day', last_order_date, DATE '2017-10-01') DESC, customer_key) AS r_score,
           ntile(5) OVER (ORDER BY frequency, customer_key)                                    AS f_score,
           ntile(5) OVER (ORDER BY monetary, customer_key)                                     AS m_score
    FROM c
)
SELECT *,
       CASE
           WHEN r_score >= 4 AND (f_score + m_score) / 2.0 >= 4   THEN 'Champions'
           WHEN r_score >= 3 AND (f_score + m_score) / 2.0 >= 3   THEN 'Loyal'
           WHEN r_score >= 4                                      THEN 'New & promising'
           WHEN r_score <= 2 AND (f_score + m_score) / 2.0 >= 3.5 THEN 'At risk'
           WHEN r_score <= 2 AND (f_score + m_score) / 2.0 < 2.5  THEN 'Hibernating'
           ELSE 'Needs attention'
       END AS rfm_segment
FROM scored
ORDER BY customer_key;
