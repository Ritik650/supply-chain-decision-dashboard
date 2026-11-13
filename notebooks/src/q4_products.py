# %% [markdown]
# # Q4. Which products make the profit, as opposed to the revenue?
#
# **Decision it informs:** reprice, promote or delist.
#
# **Scope:** valid order items, January 2015 to September 2017 (100 products sold in the window).
#
# **Method:** ABC / Pareto by profit next to Pareto by revenue; a "sells well, loses money" screen; and a check of
# where the loss-making order lines come from.

# %%
import sys; sys.path.insert(0, "..")
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy import stats
from IPython.display import Markdown, display

from scdd.db import connect, q, run_analysis
from scdd import style
from scdd.stats import cramers_v, save_findings

style.apply()
pd.set_option("display.float_format", lambda x: f"{x:,.4f}")
con = connect()

# %% [markdown]
# ## 1. Pareto: profit vs revenue
# Sources: `sql/analysis/p5_product_pareto.sql`, `sql/analysis/p5_kpis.sql`.

# %%
par = run_analysis("p5_product_pareto.sql", con)
kpi = run_analysis("p5_kpis.sql", con).iloc[0]
rev_sorted = par.sort_values("revenue", ascending=False)
abc = par.groupby("abc_class").agg(products=("product_key", "size"), profit=("profit", "sum"), revenue=("revenue", "sum"))
abc["profit_share"] = abc.profit / abc.profit.sum(); abc["revenue_share"] = abc.revenue / abc.revenue.sum()
rho = stats.spearmanr(par.profit_rank, par.revenue_rank)
print(f"{int(kpi.products)} products. Top 20% ({int(kpi.top_20pct_products)}) by profit earn {kpi.top_20pct_profit_share:.1%} of profit; "
      f"top 20% by revenue earn {kpi.top_20pct_revenue_share:.1%} of revenue. Spearman rank correlation of profit "
      f"and revenue ranks: {rho.statistic:.3f}")
display(abc)
par[["profit_rank", "revenue_rank", "product_name", "category_name", "revenue", "profit", "profit_margin",
     "cum_profit_share", "abc_class"]].head(12)

# %%
fig, ax = plt.subplots(figsize=(8.5, 3.4))
x = np.arange(1, len(par) + 1)
ax.plot(x, par.cum_profit_share, color=style.INK_2, lw=2, label="cumulative profit (products ranked by profit)")
ax.plot(x, rev_sorted.cum_revenue_share_by_revenue_rank, color=style.GREY, lw=2,
        label="cumulative revenue (products ranked by revenue)")
n_a = int((par.abc_class == "A").sum())
ax.axvline(n_a + 0.5, color=style.INK_MUTED, lw=0.8)
ax.text(n_a + 1.5, 0.35, f"A class: {n_a} products\n= {abc.loc['A', 'profit_share']:.0%} of profit", fontsize=8.5, color=style.INK_2)
ax.set_xscale("log"); ax.set_xlim(0.9, len(par) + 5)
ax.set_xticks([1, 2, 5, 10, 20, 50, 100], ["1", "2", "5", "10", "20", "50", "100"])
style.pct(ax); ax.set_ylim(0, 1.02)
ax.set_xlabel("number of products (log scale)"); ax.set_ylabel("cumulative share (%)")
ax.set_title("Profit is exactly as concentrated as revenue: the two curves overlap")
ax.legend(loc="lower right")
style.save(fig, "q4_pareto")
plt.show()

# %% [markdown]
# ## 2. "Sells well, loses money"
# Source: `sql/analysis/p5_sells_well_loses_money.sql`. Top-half revenue products with margin under 10%, plus any
# loss-making product.

# %%
swlm = run_analysis("p5_sells_well_loses_money.sql", con)
swlm

# %% [markdown]
# Are the low-margin products genuinely different, or just small samples? Margin per product is noisy when a
# product has a few hundred lines. Compare each flagged product's margin with the overall margin using a bootstrap
# interval.

# %%
lines = q("""
    SELECT p.product_name, f.profit, f.item_total, f.discount_rate, p.category_name
    FROM fact_order_items f JOIN dim_product p USING (product_key)
    WHERE f.is_valid_order AND f.order_date < DATE '2017-10-01'
""", con)
overall_margin = lines.profit.sum() / lines.item_total.sum()
rng = np.random.default_rng(11)
rows = []
for name in swlm.product_name:
    sub = lines[lines.product_name == name]
    boots = [sub.profit.values[i].sum() / sub.item_total.values[i].sum()
             for i in (rng.integers(0, len(sub), len(sub)) for _ in range(400))]
    lo, hi = np.percentile(boots, [2.5, 97.5])
    rows.append({"product_name": name, "lines": len(sub), "margin": sub.profit.sum() / sub.item_total.sum(),
                 "ci_low": lo, "ci_high": hi, "below_overall": hi < overall_margin})
flag_ci = pd.DataFrame(rows)
print(f"Overall margin {overall_margin:.2%}. Flagged products whose 95% interval sits wholly below it: "
      f"{int(flag_ci.below_overall.sum())} of {len(flag_ci)}")
flag_ci

# %% [markdown]
# ## 3. Where do loss-making lines come from?
# Almost a fifth of order lines lose money. If some products or discount bands produced most of them, delisting or
# repricing would help. Test whether the loss-line share differs by product (products with ≥ 200 lines), by
# category and by discount band.

# %%
lines["loss"] = lines.profit < 0
big = lines.groupby("product_name").filter(lambda d: len(d) >= 200)
tests = {}
for label, frame, col in [("product", big, "product_name"), ("category", lines, "category_name")]:
    chi2, p, v = cramers_v(pd.crosstab(frame[col], frame.loss))
    tests[label] = {"p_value": p, "cramers_v": v, "min": frame.groupby(col).loss.mean().min(), "max": frame.groupby(col).loss.mean().max()}
lines["band"] = pd.cut(lines.discount_rate, [-0.001, 0.0499, 0.0999, 0.1499, 0.1999, 0.26],
                       labels=["0-5%", "5-10%", "10-15%", "15-20%", "20-25%"])
chi2, p, v = cramers_v(pd.crosstab(lines.band, lines.loss))
tests["discount band"] = {"p_value": p, "cramers_v": v, "min": lines.groupby("band", observed=True).loss.mean().min(),
                          "max": lines.groupby("band", observed=True).loss.mean().max()}
loss_share = lines.loss.mean()
print(f"Loss-making lines: {loss_share:.1%} of valid lines, losing ${-lines.loc[lines.loss, 'profit'].sum():,.0f} in the window")
pd.DataFrame(tests).T

# %% [markdown]
# ## Finding → number → decision

# %%
loss_products = par[par.profit < 0]
findings = {
    "products": int(kpi.products),
    "top20_profit_share": kpi.top_20pct_profit_share, "top20_revenue_share": kpi.top_20pct_revenue_share,
    "a_class_products": n_a, "a_class_profit_share": abc.loc["A", "profit_share"],
    "spearman_profit_revenue_rank": rho.statistic,
    "loss_making_products": int(kpi.loss_making_products),
    "loss_making_products_detail": loss_products[["product_name", "revenue", "profit", "order_items"]].to_dict(orient="records"),
    "flagged_low_margin": int(len(swlm)), "flagged_below_overall_ci": int(flag_ci.below_overall.sum()),
    "overall_margin": overall_margin,
    "loss_line_share": loss_share, "loss_line_amount": -lines.loc[lines.loss, "profit"].sum(),
    "loss_line_tests": tests,
    "a_class_list": par.loc[par.abc_class == "A", ["product_name", "profit", "profit_margin"]].to_dict(orient="records"),
}
save_findings("q4", findings)
display(Markdown(f"""
**Finding.** Profit is exactly as concentrated as revenue. The top {int(kpi.top_20pct_products)} products ({kpi.top_20pct_profit_share:.1%} of profit
vs {kpi.top_20pct_revenue_share:.1%} of revenue) are near-identical lists (rank correlation {rho.statistic:.2f}), and the **{n_a} A-class products
earn {abc.loc['A', 'profit_share']:.0%} of profit**. No high-revenue product loses money: only {int(kpi.loss_making_products)} products do, with
${-loss_products.profit.sum():,.0f} of losses between them. The {loss_share:.1%} of order lines that lose money are spread evenly across products,
categories and discount bands (Cramér's V ≤ {max(t['cramers_v'] for t in tests.values()):.3f}).

**Number.** {len(swlm)} products are flagged as "sells well, low margin", but {'none' if flag_ci.below_overall.sum() == 0 else int(flag_ci.below_overall.sum())}
{'has' if flag_ci.below_overall.sum() == 1 else 'have'} a margin interval wholly below the {overall_margin:.1%} average; the rest are small-sample noise.

**Decision.** No delisting or repricing case at product level beyond the {int(kpi.loss_making_products)} loss-making ellipticals (immaterial).
Product mix is not the profit lever; the discount policy (Q2) is. Run the discount-cap test on the {n_a} A-class products first,
where {abc.loc['A', 'profit_share']:.0%} of profit is at stake and volume is large enough to read a result in four weeks.
"""))
