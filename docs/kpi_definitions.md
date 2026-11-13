# KPI definitions

One set of definitions for the SQL, the web dashboard, the Power BI measures and the text-to-SQL prompt.
All KPIs live on `fact_order_items` (one row per order item) and are sliced by the dimensions.

| KPI | Definition | SQL |
|---|---|---|
| Revenue | Sum of order item total (net of discount), excluding cancelled and suspected-fraud orders | `SUM(item_total) WHERE is_valid_order` |
| Profit | Sum of order item profit, same exclusions | `SUM(profit) WHERE is_valid_order` |
| Profit margin % | Profit ÷ revenue | `SUM(profit) / SUM(item_total)` |
| Orders | Distinct orders among valid order items | `COUNT(DISTINCT order_id)` |
| Avg order value | Revenue ÷ orders | |
| Late-delivery rate | Order items where actual shipping days > scheduled days ÷ all valid order items | `AVG(is_late::INT) WHERE is_valid_order` |
| On-time % | 1 − late-delivery rate (includes early) | |
| Avg delay days | Mean of (actual − scheduled) days over late items only | `AVG(delay_days) WHERE is_late AND is_valid_order` |
| Discount spend | Sum of order item discount | `SUM(discount) WHERE is_valid_order` |
| Discount rate | The rate actually applied, discount ÷ gross sales (the source's listed 6% was applied at 5.5%) | `discount_rate` |
| Month-3 retention | Share of a monthly cohort's customers (cohort = month of first valid order) with a valid order in the third month after the cohort month | `sql/analysis/p4_month3_retention.sql` |
| Profit share of top 20% products | Profit of the top 20% of products ranked by profit ÷ total profit | `sql/analysis/p5_kpis.sql` |
| Loss-making products | Products whose total profit is negative | `sql/analysis/p5_kpis.sql` |

## Rules behind the definitions

- **Excluded statuses.** `CANCELED` (3,692 items) and `SUSPECTED_FRAUD` (4,062) are excluded from every KPI,
  through `fact_order_items.is_valid_order`. Their `Delivery Status` is "Shipping canceled", so they never shipped.
  Pending, processing, on-hold and payment-review items count as booked revenue.
- **Negative profit stays in.** 18.7% of valid lines lose money; they are real losses, not errors.
- **Late means late against the promise.** `is_late = actual_days > scheduled_days`. On valid orders it agrees
  with the source's `Late_delivery_risk` on every row (rule T06 logs the 4,423 cancelled rows where it doesn't).
- **Analysis window.** The dashboard default, the notebooks and the memo use January 2015 – September 2017
  (33 full months). From October 2017 every order has one item, the catalogue changes and 99% of buyers are new,
  so trends and cohorts would mix two different businesses. The full range stays in the warehouse and the
  dashboard's date filter reaches it.
- **Annualising.** Per-year figures = window total × 12 / 33.
- **Currency.** The data dictionary names no currency; values are treated as USD and not converted.
