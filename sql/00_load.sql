-- 00_load.sql
-- Land the raw CSV untouched (every column as text) in its own schema.
-- The source file is latin-1; scripts/build.py transcodes it to UTF-8 first
-- (DuckDB's latin-1 reader rejects this file) and sets the `raw_csv` variable.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE OR REPLACE TABLE raw.dataco AS
SELECT *
FROM read_csv(getvariable('raw_csv'), header = true, all_varchar = true);
