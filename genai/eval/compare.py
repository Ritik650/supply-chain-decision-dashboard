"""Execution-accuracy comparison: does the model's result set equal the gold result set?

Rules (also stated in results.md):
* Row order is ignored unless the question is answered by a single row (then it is trivially ordered).
* Column names are ignored. Every gold column must be matched by some predicted column with the
  same values; extra predicted columns are allowed (a model may add a helpful count).
* Floats are rounded to 4 significant digits; dates and timestamps compare by date; booleans
  and integers compare exactly. A rate returned as a percentage (57.3 vs 0.573) is a mismatch,
  because the KPI definitions say rates are fractions.
"""
from __future__ import annotations

import datetime as dt
import decimal
import math
from collections import Counter
from itertools import permutations

import pandas as pd


def norm(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    if isinstance(v, (pd.Timestamp, dt.datetime)):
        return pd.Timestamp(v).date().isoformat() if pd.Timestamp(v).time() == dt.time(0) else pd.Timestamp(v).isoformat()
    if isinstance(v, dt.date):
        return v.isoformat()
    if isinstance(v, bool):
        return v
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, (float, decimal.Decimal)):
        f = float(v)
        if f == 0:
            return 0.0
        return float(f"{f:.4g}")
    if hasattr(v, "item"):  # numpy scalar
        return norm(v.item())
    return str(v).strip()


def column(df: pd.DataFrame, i: int) -> list:
    return [norm(v) for v in df.iloc[:, i].tolist()]


def results_match(gold: pd.DataFrame, pred: pd.DataFrame) -> tuple[bool, str]:
    if pred is None:
        return False, "no result"
    if len(gold) != len(pred):
        return False, f"row count {len(pred)} vs gold {len(gold)}"
    gcols = [column(gold, i) for i in range(gold.shape[1])]
    pcols = [column(pred, i) for i in range(pred.shape[1])]
    if len(pcols) < len(gcols):
        return False, f"{len(pcols)} columns vs gold {len(gcols)}"
    # candidate predicted columns for each gold column: same multiset of values
    cands = [[j for j, pc in enumerate(pcols) if Counter(map(repr, pc)) == Counter(map(repr, gc))] for gc in gcols]
    missing = [i for i, c in enumerate(cands) if not c]
    if missing:
        return False, f"gold column(s) {[gold.columns[i] for i in missing]} not found in prediction"
    # choose an injective assignment whose rows match as a multiset
    gold_rows = Counter(tuple(repr(gcols[i][r]) for i in range(len(gcols))) for r in range(len(gold)))
    for combo in _assignments(cands):
        pred_rows = Counter(tuple(repr(pcols[j][r]) for j in combo) for r in range(len(pred)))
        if pred_rows == gold_rows:
            return True, "match"
    return False, "values match per column but rows are paired differently"


def _assignments(cands: list[list[int]], limit: int = 2000):
    """Injective choices of one predicted column per gold column (bounded)."""
    count = 0

    def rec(i, used, acc):
        nonlocal count
        if count >= limit:
            return
        if i == len(cands):
            count += 1
            yield tuple(acc)
            return
        for j in cands[i]:
            if j not in used:
                yield from rec(i + 1, used | {j}, acc + [j])

    yield from rec(0, frozenset(), [])


__all__ = ["results_match", "norm", "permutations"]
