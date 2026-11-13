"""Score the text-to-SQL assistant on hand-written gold questions (execution accuracy).

    # 1) baseline prompt on the 30 test questions
    python genai/eval/run_eval.py --prompt genai/prompt.md --set test --tag v1

    # 2) after ONE prompt revision, score the revised prompt on the 30 (for before/after)
    #    and on the 10 held-back fresh questions (the honest final number)
    python genai/eval/run_eval.py --prompt genai/prompt_v2.md --set test --tag v2
    python genai/eval/run_eval.py --prompt genai/prompt_v2.md --set fresh --tag v2

    # plumbing check without any API key: the "model" returns the gold SQL (must score 100%)
    python genai/eval/run_eval.py --oracle --set all --tag oracle

Each run writes genai/eval/runs/<tag>_<set>.jsonl (one line per question, with SQL, error,
latency and match reason) and regenerates genai/eval/results.md from every run on disk.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from genai.ask import Asker, open_readonly, run_sql  # noqa: E402
from genai.eval.compare import results_match  # noqa: E402
from genai.llm import LLM  # noqa: E402

EVAL = Path(__file__).resolve().parent
RUNS = EVAL / "runs"
SETS = {"test": ["questions.yaml"], "fresh": ["questions_fresh.yaml"], "all": ["questions.yaml", "questions_fresh.yaml"]}


def load(set_name: str) -> list[dict]:
    qs = []
    for f in SETS[set_name]:
        qs += yaml.safe_load((EVAL / f).read_text(encoding="utf-8"))
    return qs


class Oracle:
    """Stands in for the LLM: answers each question with its gold SQL."""
    provider, model = "oracle", "gold-sql"

    def __init__(self, questions):
        self.gold = {q["question"]: q["gold"] for q in questions}

    def complete(self, system: str, user: str) -> str:
        q = user.split("\n", 1)[0].removeprefix("Q: ").strip()
        return self.gold[q]


def tag_failure(q: dict, ans, reason: str) -> str:
    """First-pass failure label from simple rules; review by hand in results.md."""
    sql = (ans.sql or "").lower()
    gold = q["gold"].lower()
    if ans.error:
        return "SQL error after retry"
    if "is_valid_order" in gold and "is_valid_order" not in sql and "order_status" not in sql:
        return "missing cancelled/fraud filter"
    if "item_total" in gold and "item_total" not in sql and "sales" in sql:
        return "wrong revenue definition (sales vs item_total)"
    if "filter (where f.is_late)" in gold.replace("  ", " ") and "is_late" not in sql.split("avg(f.actual_days", 1)[-1]:
        return "KPI definition (delay over late items only)"
    if ("date_trunc" in gold or "interval" in gold or "year(" in gold or "quarter" in gold) and "row count" in reason:
        return "date bucketing / period"
    if "limit" in gold and "limit" not in sql:
        return "missing top-N limit"
    if "not found" in reason:
        return "wrong value (aggregation or units)"
    if "row count" in reason:
        return "wrong grouping or filter"
    return "other"


def run(args) -> int:
    questions = load(args.set)
    if args.only:
        questions = [q for q in questions if q["id"] in args.only.split(",")]
    llm = Oracle(questions) if args.oracle else LLM.from_env(args.provider, args.model)
    asker = Asker(llm, Path(args.prompt))
    gold_con = open_readonly()
    RUNS.mkdir(parents=True, exist_ok=True)
    out = RUNS / f"{args.tag}_{args.set}.jsonl"
    rows = []
    for q in questions:
        gold = run_sql(gold_con, q["gold"])
        try:
            ans = asker.ask(q["question"], summarise=False)
        except Exception as e:  # API failure: record it, don't crash the run
            rows.append({"id": q["id"], "difficulty": q["difficulty"], "question": q["question"], "correct": False,
                         "reason": f"API error: {e}", "sql": "", "error": str(e), "attempts": 0, "self_corrected": False,
                         "latency_s": None, "failure_type": "API error"})
            print(f"  {q['id']}  API ERROR  {e}")
            continue
        ok, reason = results_match(gold, ans.result) if not ans.error else (False, ans.error)
        row = {"id": q["id"], "difficulty": q["difficulty"], "question": q["question"], "correct": ok, "reason": reason,
               "sql": ans.sql, "error": ans.error, "first_error": ans.first_error, "attempts": ans.attempts,
               "self_corrected": ans.self_corrected, "latency_s": round(ans.latency_s, 3),
               "failure_type": "" if ok else tag_failure(q, ans, reason)}
        rows.append(row)
        print(f"  {q['id']}  {'PASS' if ok else 'FAIL'}  {ans.latency_s:5.1f}s  {'' if ok else reason[:90]}")
        if args.sleep:
            time.sleep(args.sleep)
    meta = {"tag": args.tag, "set": args.set, "prompt": args.prompt, "provider": llm.provider, "model": llm.model,
            "run_at": datetime.now().isoformat(timespec="seconds")}
    with out.open("w", encoding="utf-8") as fh:
        fh.write(json.dumps({"meta": meta}) + "\n")
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    n_ok = sum(r["correct"] for r in rows)
    print(f"{args.tag}/{args.set}: {n_ok}/{len(rows)} correct -> {out.relative_to(ROOT)}")
    write_results_md()
    return 0


def summarise(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    meta = json.loads(lines[0])["meta"]
    rows = [json.loads(x) for x in lines[1:]]
    by = {}
    for d in ("easy", "medium", "hard"):
        sub = [r for r in rows if r["difficulty"] == d]
        if sub:
            by[d] = (sum(r["correct"] for r in sub), len(sub))
    lat = [r["latency_s"] for r in rows if r["latency_s"] is not None]
    return {"meta": meta, "rows": rows, "correct": sum(r["correct"] for r in rows), "n": len(rows), "by": by,
            "self_corrected": sum(r["self_corrected"] for r in rows),
            "self_corrected_ok": sum(r["self_corrected"] and r["correct"] for r in rows),
            "first_try_errors": sum(bool(r.get("first_error")) for r in rows),
            "median_latency": statistics.median(lat) if lat else None}


def write_results_md() -> None:
    runs = sorted(RUNS.glob("*.jsonl"))
    real = [summarise(p) for p in runs if not p.name.startswith("oracle")]
    oracle = [summarise(p) for p in runs if p.name.startswith("oracle")]
    L = ["# Text-to-SQL evaluation results", "",
         "_Generated by `genai/eval/run_eval.py` from the run files in `genai/eval/runs/`. Numbers are reported as "
         "measured; nothing here is edited by hand except the failure analysis section._", "",
         "**Scoring.** Execution accuracy: the model's result set must equal the gold result set "
         "(row order ignored, column names ignored, extra columns allowed, floats rounded to 4 significant digits). "
         "Rates must be fractions, as the KPI definitions say. See `genai/eval/compare.py`.", "",
         "**Protocol.** Prompt v1 is scored on the 30 test questions. The prompt is revised once after reading those "
         "failures (v2), then scored on the same 30 (before vs after, optimistic because v2 was written after seeing "
         "them) and on 10 fresh questions written in advance and never used for tuning (the honest final number).", ""]
    if not real:
        L += ["## Status: not run yet", "",
              "No model run is recorded. Set `GEMINI_API_KEY` (or an OpenAI-compatible endpoint, see `genai/llm.py`) "
              "and run the commands at the top of `genai/eval/run_eval.py`. This file is rewritten after each run.", ""]
    else:
        L += ["## Results", "", "| Run | Prompt | Model | Set | Accuracy | Easy | Medium | Hard | Self-corrected after an error | Median latency |",
              "|---|---|---|---|---:|---:|---:|---:|---:|---:|"]
        for s in real:
            m = s["meta"]
            cell = lambda d: f"{s['by'][d][0]}/{s['by'][d][1]}" if d in s["by"] else "–"  # noqa: E731
            L.append(f"| {m['tag']} | `{m['prompt']}` | {m['provider']}:{m['model']} | {m['set']} | "
                     f"**{s['correct']}/{s['n']}** ({s['correct'] / s['n']:.0%}) | {cell('easy')} | {cell('medium')} | {cell('hard')} | "
                     f"{s['self_corrected_ok']} of {s['first_try_errors']} first-try errors | "
                     f"{s['median_latency']:.1f}s |")
        L += ["", "## Failures by type (automatic first-pass labels)", ""]
        for s in real:
            fails = [r for r in s["rows"] if not r["correct"]]
            if not fails:
                continue
            m = s["meta"]
            L += [f"### {m['tag']} / {m['set']}", "", "| Id | Difficulty | Label | Reason | Question |", "|---|---|---|---|---|"]
            for r in fails:
                L.append(f"| {r['id']} | {r['difficulty']} | {r['failure_type']} | {r['reason'][:80]} | {r['question']} |")
            L.append("")
        L += ["## Failure analysis (write by hand after reading the SQL in runs/*.jsonl)", "",
              "1. _Most common failure type, with one example question and the wrong SQL fragment._",
              "2. _Second._", "3. _Third._", "", "**Prompt change made for v2:** _describe the one revision._", ""]
    if oracle:
        s = oracle[-1]
        L += ["## Harness self-check", "",
              f"Oracle run (the model is replaced by the gold SQL): **{s['correct']}/{s['n']}** on `{s['meta']['set']}`, "
              f"{s['meta']['run_at']}. Anything below 100% would mean a bug in the harness, not in a model.", ""]
    (EVAL / "results.md").write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prompt", default=str(Path("genai") / "prompt.md"))
    ap.add_argument("--set", choices=list(SETS), default="test")
    ap.add_argument("--tag", default="v1")
    ap.add_argument("--provider"), ap.add_argument("--model")
    ap.add_argument("--oracle", action="store_true", help="use gold SQL as the model output (harness check)")
    ap.add_argument("--only", help="comma-separated question ids")
    ap.add_argument("--sleep", type=float, default=0.0, help="seconds between questions (free-tier rate limits)")
    ap.add_argument("--report-only", action="store_true", help="just rebuild results.md from runs/")
    args = ap.parse_args()
    if args.report_only:
        write_results_md()
        return 0
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
