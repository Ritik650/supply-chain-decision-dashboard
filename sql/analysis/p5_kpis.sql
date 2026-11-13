-- Page 5 KPIs: profit share of the top 20% of products (ranked by profit), revenue share of
-- the top 20% (ranked by revenue), and the number of loss-making products, analysis window.
WITH prod AS (
    SELECT product_key, sum(item_total) AS revenue, sum(profit) AS profit
    FROM fact_order_items
    WHERE is_valid_order AND order_date < DATE '2017-10-01'
    GROUP BY 1
),
ranked AS (
    SELECT *,
           row_number() OVER (ORDER BY profit DESC)  AS profit_rank,
           row_number() OVER (ORDER BY revenue DESC) AS revenue_rank,
           CAST(ceil(0.2 * count(*) OVER ()) AS INTEGER) AS top_n
    FROM prod
)
SELECT
    count(*)                                                        AS products,
    any_value(top_n)                                                AS top_20pct_products,
    sum(profit) FILTER (WHERE profit_rank <= top_n) / sum(profit)   AS top_20pct_profit_share,
    sum(revenue) FILTER (WHERE revenue_rank <= top_n) / sum(revenue) AS top_20pct_revenue_share,
    count(*) FILTER (WHERE profit < 0)                              AS loss_making_products
FROM ranked;
