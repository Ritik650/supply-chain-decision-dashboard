"""Ask your data: plain-English question -> DuckDB SQL -> result table + one-line answer.

    python genai/ask.py "What was the late-delivery rate by shipping mode in 2016?"
    python genai/ask.py --no-summary "Top 5 products by profit"

Pipeline (docs/architecture.md):
1. The prompt (genai/prompt.md) holds the live schema, KPI definitions and worked examples.
2. The model returns SQL only. Anything that is not a single SELECT is rejected before it runs,
   and the database is opened read-only with external file access disabled.
3. The SQL runs with a 5-second timeout. On an error, the error goes back to the model once
   for a self-correction attempt.
4. The answer is the result table, the SQL (always shown), and a one-sentence summary written
   from the result rows only.
"""
from __future__ import annotations

import argparse
import re
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import duckdb
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from genai.llm import LLM  # noqa: E402
from genai.schema import describe  # noqa: E402
from scdd.db import DB_PATH  # noqa: E402

PROMPT_PATH = Path(__file__).with_name("prompt.md")
TIMEOUT_S = 5.0
MAX_ROWS = 1000

# Statement-level check uses DuckDB's own parser; the keyword list is a second line of defence
# (external access is also disabled on the connection, which blocks file-reading functions).
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|export|import|install|load|pragma|"
    r"set|reset|call|checkpoint|vacuum|truncate|grant|revoke|replace\s+into)\b|"
    r"\b(read_csv\w*|read_json\w*|read_parquet|read_text|read_blob|parquet_scan|glob|sniff_csv|getenv)\s*\(",
    re.IGNORECASE,
)


class UnsafeSQL(ValueError):
    pass


def extract_sql(text: str) -> str:
    """Strip markdown fences or a leading 'SQL:' that models sometimes add."""
    m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
    sql = m.group(1) if m else text
    sql = re.sub(r"^\s*sql\s*:\s*", "", sql, flags=re.I)
    return sql.strip().rstrip(";").strip()


def check_sql(sql: str) -> str:
    """Raise UnsafeSQL unless `sql` is exactly one read-only SELECT statement."""
    if not sql:
        raise UnsafeSQL("empty SQL")
    try:
        statements = duckdb.extract_statements(sql)
    except duckdb.Error as e:
        raise UnsafeSQL(f"does not parse: {e}") from e
    if len(statements) != 1:
        raise UnsafeSQL(f"expected 1 statement, got {len(statements)}")
    if statements[0].type != duckdb.StatementType.SELECT:
        raise UnsafeSQL(f"only SELECT is allowed, got {statements[0].type.name}")
    # Ignore string literals so a value like 'Set' doesn't trip the keyword check.
    scrubbed = re.sub(r"'(?:[^']|'')*'", "''", sql)
    bad = FORBIDDEN.search(scrubbed)
    if bad:
        raise UnsafeSQL(f"forbidden keyword: {bad.group(0).strip()}")
    return sql


_BASE: duckdb.DuckDBPyConnection | None = None


def open_readonly() -> duckdb.DuckDBPyConnection:
    """A read-only connection with file access disabled and the configuration locked.
    DuckDB shares one database instance per file within a process, so the locked base
    connection is created once and each caller gets its own cursor on it."""
    global _BASE
    if _BASE is None:
        _BASE = duckdb.connect(str(DB_PATH), read_only=True)
        _BASE.execute("SET enable_external_access = false")
        _BASE.execute("SET lock_configuration = true")
    return _BASE.cursor()


def run_sql(con: duckdb.DuckDBPyConnection, sql: str, timeout: float = TIMEOUT_S) -> pd.DataFrame:
    """Run with a wall-clock timeout: a watchdog interrupts the query if it overruns."""
    check_sql(sql)
    timer = threading.Timer(timeout, con.interrupt)
    timer.start()
    try:
        return con.execute(f"SELECT * FROM ({sql}) AS _q LIMIT {MAX_ROWS}").df()
    except duckdb.InterruptException as e:
        raise TimeoutError(f"query exceeded {timeout:.0f}s") from e
    finally:
        timer.cancel()


@dataclass
class Answer:
    question: str
    sql: str = ""
    result: pd.DataFrame | None = None
    summary: str = ""
    error: str = ""
    attempts: int = 0
    self_corrected: bool = False
    first_error: str = ""
    latency_s: float = 0.0
    raw_outputs: list[str] = field(default_factory=list)


class Asker:
    def __init__(self, llm: LLM | None = None, prompt_path: Path = PROMPT_PATH):
        self.llm = llm or LLM.from_env()
        self.con = open_readonly()
        self.system = prompt_path.read_text(encoding="utf-8").replace("{schema}", describe(self.con))

    def ask(self, question: str, summarise: bool = True) -> Answer:
        ans = Answer(question)
        t0 = time.perf_counter()
        user = f"Q: {question}\nSQL:"
        for attempt in (1, 2):
            ans.attempts = attempt
            raw = self.llm.complete(self.system, user)
            ans.raw_outputs.append(raw)
            ans.sql = extract_sql(raw)
            try:
                ans.result = run_sql(self.con, ans.sql)
                ans.error = ""
                ans.self_corrected = attempt == 2
                break
            except (duckdb.Error, UnsafeSQL, TimeoutError) as e:
                ans.error = f"{type(e).__name__}: {e}"
                if attempt == 1:
                    ans.first_error = ans.error
                    user = (f"Q: {question}\nYour previous SQL was:\n{ans.sql}\n\nIt failed with:\n{ans.error}\n\n"
                            "Return a corrected single SELECT statement only.\nSQL:")
        if summarise and ans.result is not None:
            ans.summary = self.summarise(question, ans.result)
        ans.latency_s = time.perf_counter() - t0
        return ans

    def summarise(self, question: str, result: pd.DataFrame) -> str:
        """One sentence written from the result rows only, never from the model's memory."""
        if result.empty:
            return "The query returned no rows."
        table = result.head(20).to_markdown(index=False, floatfmt=".4g")
        system = ("You write one plain-English sentence answering a business question. Use ONLY numbers that "
                  "appear in the result table. If the table cannot answer the question, say so. Fractions such as "
                  "0.573 may be stated as percentages (57.3%).")
        text = self.llm.complete(system, f"Question: {question}\n\nResult table:\n{table}\n\nOne sentence:")
        return text.strip().split("\n")[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Ask a business question of the supply-chain star schema.")
    ap.add_argument("question", nargs="+")
    ap.add_argument("--no-summary", action="store_true", help="skip the one-sentence summary")
    ap.add_argument("--provider"), ap.add_argument("--model")
    args = ap.parse_args()
    asker = Asker(LLM.from_env(args.provider, args.model))
    ans = asker.ask(" ".join(args.question), summarise=not args.no_summary)
    print("SQL:\n" + ans.sql + "\n")
    if ans.error:
        print(f"Failed after {ans.attempts} attempt(s): {ans.error}")
        return 1
    with pd.option_context("display.width", 160, "display.max_columns", 20):
        print(ans.result.to_string(index=False, max_rows=25))
    if ans.summary:
        print("\n" + ans.summary)
    print(f"\n({ans.latency_s:.1f}s, {ans.attempts} attempt(s){', self-corrected' if ans.self_corrected else ''})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
