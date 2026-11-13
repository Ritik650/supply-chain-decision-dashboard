-- Page 5 (Products, Q4): products ranked by profit with cumulative profit and revenue
-- shares, and an ABC class on cumulative profit (A = first 80%, B = next 15%, C = rest).
WITH prod AS (
    SELECT p.product_key, p.product_name, p.category_name,
           sum(f.item_total)                          AS revenue,
           sum(f.profit)                              AS profit,
           count(*)                                   AS order_items,
           avg(CAST(f.profit < 0 AS INTEGER))         AS loss_line_share
    FROM fact_order_items f
    JOIN dim_product p USING (product_key)
    WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
    GROUP BY 1, 2, 3
),
ranked AS (
    SELECT *,
           profit / revenue                                                         AS profit_margin,
           row_number() OVER (ORDER BY profit DESC)                                 AS profit_rank,
           row_number() OVER (ORDER BY revenue DESC)                                AS revenue_rank,
           sum(profit) OVER (ORDER BY profit DESC ROWS UNBOUNDED PRECEDING) / sum(profit) OVER () AS cum_profit_share,
           sum(revenue) OVER (ORDER BY revenue DESC ROWS UNBOUNDED PRECEDING) / sum(revenue) OVER () AS cum_revenue_share_by_revenue_rank
    FROM prod
)
SELECT *,
       CASE WHEN cum_profit_share - profit / sum(profit) OVER () < 0.80 THEN 'A'
            WHEN cum_profit_share - profit / sum(profit) OVER () < 0.95 THEN 'B'
            ELSE 'C' END AS abc_class
FROM ranked
ORDER BY profit_rank;
