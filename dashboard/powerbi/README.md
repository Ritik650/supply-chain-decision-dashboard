# Power BI dashboard

`supply_chain_dashboard.pbip` is a Power BI Project (text-based PBIP: TMDL semantic model + PBIR report) generated
by [`scripts/make_pbip.py`](../../scripts/make_pbip.py) from the same star schema as the web dashboard.

| | |
|---|---|
| Model | 13 tables, 7 relationships, marked date table, auto date/time off, implicit measures off |
| Measures | 106, in display folders with descriptions (core KPIs, month on month, delivery, discounts, customers, products, what-if, text) |
| What-if | Max discount (0–25%), First Class promise (1–2 days), Second Class promise (2–6 days) |
| Report | 6 pages, 91 visuals, synced slicers, report-level filter for the Jan 2015 – Sep 2017 window |
| Theme | `theme.json`: grey marks, one red accent (#D03B3B) for late / loss-making / over-cap |

## Open it

```bash
python scripts/download_data.py && python scripts/build.py --export   # CSVs the model loads
```

1. Open `supply_chain_dashboard.pbip` in Power BI Desktop (December 2025 or later).
2. **Home > Refresh** (about 30 seconds). If the repo is not at the original path, first set
   **Transform data > Edit parameters > DataFolder** to your `data\export\` folder.

## Pages

| Page | Question | Main visuals |
|---|---|---|
| 1 Summary | Where is the business losing money and missing deliveries? | KPI cards with month-on-month change, monthly revenue and profit, top 3 alerts |
| 2 Delivery | What drives late deliveries? (Q1) | Actual-days distribution per mode (red = late), mode × region heatmap, mode table, promise what-if, late-rate trend |
| 3 Discounts | Where do discounts cut into margin? (Q2) | Margin and units by discount band, discount-cap what-if with recovery curve, category drill-down |
| 4 Customers | Who is valuable, and do they come back? (Q3) | RFM segment table, "does RFM predict?" chart, cohort retention heatmap |
| 5 Products | Which products make the profit? (Q4) | Pareto curve, top-15 ranking with ABC class, "sells well, loses money" list |
| Definitions | | KPI definitions and data notes |

## Checks

With the default filter, the report matches the SQL in `sql/analysis/` (verified in Power BI's engine with DAX
queries): revenue $29,463,744 · profit $3,529,946 · margin 12.0% · late rate 57.3% · orders 54,854 ·
avg order value $537.13 · promise what-if 34.1% · 10% cap recovery $371,069 a year (low $239,901, break-even 41.7%) ·
customers 12,296 · month-3 retention 12.7% · top-20% product profit share 96.1%.

`python scripts/validate_pbip.py` checks every report file against Microsoft's PBIR JSON schemas, every field
reference against the model, and parses the model with Microsoft's TmdlSerializer.

## Regenerating

`python scripts/make_pbip.py` rewrites both project folders from the specs in the script. Edits made in Power BI
Desktop are kept only until the next regeneration, so make lasting changes in the generator.

**Publishing:** *Publish to web* needs a Microsoft work or school account with Power BI. The public link for this
project is the web build in `dashboard/web/` on GitHub Pages; the Power BI report ships as this project and its
screenshots.
