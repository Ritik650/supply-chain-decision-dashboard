-- Page 5: "sells well, loses money". Products in the top half by revenue whose margin is
-- below 10% (vs ~12% overall), plus every loss-making product regardless of revenue.
WITH prod AS (
    SELECT p.product_name, p.category_name,
           sum(f.item_total)                    AS revenue,
           sum(f.profit)                        AS profit,
           sum(f.profit) / sum(f.item_total)    AS profit_margin,
           count(*)                             AS order_items,
           avg(CAST(f.profit < 0 AS INTEGER))   AS loss_line_share,
           sum(f.profit) FILTER (WHERE f.profit < 0) AS loss_from_negative_lines
    FROM fact_order_items f
    JOIN dim_product p USING (product_key)
    WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
    GROUP BY 1, 2
),
ranked AS (
    SELECT *, percent_rank() OVER (ORDER BY revenue DESC) AS revenue_pct_rank FROM prod
)
SELECT product_name, category_name, revenue, profit, profit_margin, order_items,
       loss_line_share, loss_from_negative_lines,
       CASE WHEN profit < 0 THEN 'loss-making'
            ELSE 'top-half revenue, margin < 10%' END AS flag
FROM ranked
WHERE profit < 0 OR (revenue_pct_rank < 0.5 AND profit_margin < 0.10)
ORDER BY revenue DESC;
