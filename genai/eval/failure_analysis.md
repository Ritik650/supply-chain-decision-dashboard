## Failure analysis

Written by hand after reading the SQL in `runs/*.jsonl`. Model: `openai/gpt-oss-120b` on Groq, temperature 0.

**Prompt v1 on the 30 test questions: 24/30.** The six failures fall into three types:

1. **Date and label representation (3 of 6).** The values were right but the shape was not. H03 and H07 returned
   the month as text (`d.year_month` → `2016-01`) instead of a month date (`2016-01-01`), and H09 did the same.
   Under the strict scorer these count as wrong; a human would accept H03 and H07. On the fresh set the same habit
   reappeared in a new form: F07 recoded `is_weekend` as `'Weekend'`/`'Weekday'` labels.
2. **Status-scope wording (2 of 6).** "Counting every status" (E01) was read as "per status" and grouped by
   `order_status`; "across all statuses" (E07) still got the `is_valid_order` filter that KPI questions need
   (27,489 vs 28,723 items). The KPI rule in the prompt overrode the question's own words.
3. **Grain and window boundaries (2 of 6).** E10 ran `COUNT(*)` on `dim_shipping`, whose grain is
   shipping mode × payment type, so it returned 12 modes instead of 3. H09 computed `LAG` over 2017 only, so
   January had no previous month to compare against.

**The one revision (prompt v2)** adds five general rules: scope words decide the status filter; one row for
"how many" questions; table grain and `COUNT(DISTINCT …)` for dimension counts; months as dates; include the prior
period before applying `LAG`. Rules, not answers: none of them names a test question.

**Before vs after on the same 30 questions: 24/30 → 28/30.** E01, E07, E10, H03 and H07 now pass. This number is
optimistic because v2 was written after reading these failures. Two failures remain:

- H09 still fails: the model expressed the margin in percent (against the "rates are fractions" rule) and again left
  January without a prior month.
- H10 is new: the model named a CTE `pivot`, a reserved word in DuckDB, and the self-correction retry kept the name.
  Prompt v1 had answered H10 correctly, so the longer v2 prompt traded one fix for one new dialect error.

**Honest final score, on 10 fresh questions written before any run and never used for tuning: 9/10.** The miss (F07)
is the label-recoding type above; the numbers in its answer were correct.

**Strict vs tolerant.** Scoring is strict by design (the rule was fixed before the first run). A comparator that
accepted month text and relabelled booleans would give v1 26/30, v2 28/30 and fresh 10/10; the strict figures are the
ones reported everywhere else.

**Latency note.** The free Groq tier rate-limits by tokens per minute; when the limit is hit the client waits and
retries, which is why some questions show about 22 s. Median latency is reported as measured, waits included.
