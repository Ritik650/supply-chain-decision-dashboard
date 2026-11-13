# Architecture

```mermaid
flowchart LR
    subgraph Source["Source"]
        M[("Mendeley Data v5<br/>DataCo CSV, latin-1")]
    end
    subgraph Build["python scripts/build.py (one command, about 6 s)"]
        T["transcode to UTF-8"] --> L["00_load.sql<br/>raw.dataco"]
        L --> S["01_staging.sql<br/>types, renames, drops, fixes"]
        S --> D["02_dimensions.sql<br/>5 dimensions"]
        D --> F["03_fact.sql<br/>fact_order_items"]
        F --> Q["sql/tests: 15 rules<br/>data_quality_log.md"]
    end
    M -->|"download_data.py<br/>SHA-256 checked"| T
    F --> W[("DuckDB<br/>supply_chain.duckdb")]
    W --> A["sql/analysis<br/>one query per number"]
    A --> N["notebooks Q1-Q4<br/>stats tests"]
    N --> J["outputs/findings<br/>JSON per question"]
    J --> MEMO["memo/decision_memo.pdf"]
    A --> X["export_dashboard.py<br/>items.bin + reference.json"]
    X --> WEB["dashboard/web<br/>static, GitHub Pages"]
    WEB -.->|"check_dashboard.py<br/>39 numbers vs SQL"| A
    W --> PBI["data/export<br/>CSV per table"]
    PBI --> PBIP["make_pbip.py<br/>Power BI project"]
    W --> G["genai/ask.py<br/>text-to-SQL, read-only"]
    G --> E["genai/eval<br/>40 gold questions"]
```

## Star schema

```mermaid
erDiagram
    fact_order_items }o--|| dim_date : "order_date_key / ship_date_key"
    fact_order_items }o--|| dim_customer : customer_key
    fact_order_items }o--|| dim_product : product_key
    fact_order_items }o--|| dim_geography : geo_key
    fact_order_items }o--|| dim_shipping : shipping_key
    fact_order_items {
        int order_item_id PK "grain: one row per order item"
        int order_id "degenerate dimension"
        bool is_valid_order "false for CANCELED, SUSPECTED_FRAUD"
        bool is_late "actual_days > scheduled_days"
        double sales "gross"
        double discount
        double discount_rate "applied rate"
        double item_total "net revenue"
        double profit
        smallint quantity
        smallint actual_days
        smallint scheduled_days
    }
    dim_date {
        int date_key PK
        date date
        date month_start
        bool in_analysis_window
    }
    dim_customer {
        int customer_key PK
        varchar segment
        date cohort_month "first valid order"
    }
    dim_product {
        int product_key PK
        varchar product_name
        varchar category_name
        varchar department_name
        double list_price
    }
    dim_geography {
        int geo_key PK
        varchar market
        varchar order_region
        varchar order_country
        varchar order_city
    }
    dim_shipping {
        int shipping_key PK
        varchar shipping_mode
        int promised_days
        varchar payment_type
    }
```

## Why these choices

- **DuckDB, one file, plain SQL in numbered files.** 180k rows build in about six seconds with no server; each
  step is a reviewable SQL file. dbt was left out on purpose: the plan's first cut when time is short.
- **Star schema at order-item grain.** Clear grain, reusable dimensions, simpler BI measures and a smaller,
  more legible schema for the text-to-SQL prompt. Order-level counts use `COUNT(DISTINCT order_id)`; rule T15
  checks that order-level attributes are constant across an order's items, so that count is well defined.
- **The KPI rules live in the fact table** (`is_valid_order`, `is_late`, `discount_rate`), so SQL, DAX,
  JavaScript and the LLM prompt cannot drift apart on what "revenue" or "late" means.
- **The web dashboard filters in the browser.** Valid order items ship as one 4.8 MB columnar binary
  (1.6 MB gzipped), so every filter combination gives exact KPIs, including distinct orders and cohorts,
  without a server. `scripts/check_dashboard.py` confirms its default-view numbers equal the SQL.
- **Text-to-SQL safety in three layers:** DuckDB's parser must see exactly one SELECT; a keyword screen blocks
  file-reading functions; the connection is read-only with external access disabled and its configuration
  locked. A watchdog interrupts any query after 5 seconds.
