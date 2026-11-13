"""Small statistics helpers used across the Q1-Q4 notebooks."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from .db import OUTPUTS


def wilson_ci(successes: float, n: float, z: float = 1.96) -> tuple[float, float]:
    """95% Wilson score interval for a proportion (well behaved near 0 and 1)."""
    if n == 0:
        return (np.nan, np.nan)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = z * np.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / denom
    return (centre - half, centre + half)


def two_prop_test(x1: float, n1: float, x2: float, n2: float) -> dict:
    """Two-sided z-test for p1 - p2 with a 95% CI on the difference."""
    p1, p2 = x1 / n1, x2 / n2
    pooled = (x1 + x2) / (n1 + n2)
    se0 = np.sqrt(pooled * (1 - pooled) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se0 if se0 > 0 else np.nan
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    return {"p1": p1, "p2": p2, "diff": p1 - p2, "ci_low": p1 - p2 - 1.96 * se,
            "ci_high": p1 - p2 + 1.96 * se, "z": z, "p_value": 2 * stats.norm.sf(abs(z))}


def cramers_v(ct: pd.DataFrame) -> tuple[float, float, float]:
    """Chi-square test of independence and Cramer's V for a contingency table."""
    chi2, p, _, _ = stats.chi2_contingency(ct)
    n = ct.values.sum()
    v = np.sqrt(chi2 / (n * (min(ct.shape) - 1)))
    return chi2, p, v


def ratio_bootstrap(num: np.ndarray, den: np.ndarray, reps: int = 400, seed: int = 7) -> tuple[float, float]:
    """95% percentile bootstrap CI for sum(num) / sum(den), resampling rows."""
    rng = np.random.default_rng(seed)
    n = len(num)
    out = np.empty(reps)
    for i in range(reps):
        idx = rng.integers(0, n, n)
        out[i] = num[idx].sum() / den[idx].sum()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def auc(scores: np.ndarray, labels: np.ndarray) -> float:
    """ROC AUC via the Mann-Whitney U statistic (0.5 = no better than chance)."""
    labels = np.asarray(labels).astype(bool)
    u = stats.mannwhitneyu(np.asarray(scores)[labels], np.asarray(scores)[~labels]).statistic
    return float(u / (labels.sum() * (~labels).sum()))


def save_findings(name: str, data: dict) -> Path:
    """Write a notebook's headline numbers so the memo and README can cite them."""
    path = OUTPUTS / "findings" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)

    def conv(o):
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, (pd.Timestamp,)):
            return o.isoformat()
        raise TypeError(type(o))

    path.write_text(json.dumps(data, indent=2, default=conv), encoding="utf-8")
    return path
