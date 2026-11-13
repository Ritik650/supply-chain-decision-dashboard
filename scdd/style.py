"""One chart style for notebooks, README figures and the memo.

Design rule from the project plan: one accent colour for "bad" (late, loss-making),
grey for everything else, no pie charts, no dual axes, axis titles carry units.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap

from .db import OUTPUTS

BAD = "#d03b3b"          # the one accent: late, loss-making, over-cap
GREY = "#a8a69f"         # every other mark
GREY_DARK = "#52514e"    # secondary series / reference marks
INK = "#0b0b0b"
INK_2 = "#52514e"
INK_MUTED = "#8a8984"
GRID = "#e8e7e3"
SURFACE = "#fcfcfb"

# Single-hue sequential ramp in the "bad" hue, for late-rate heatmaps (light = good).
BAD_RAMP = LinearSegmentedColormap.from_list("bad_ramp", ["#f6f5f2", "#f2b8b5", "#e5716e", BAD, "#7f1d1d"])
# Neutral ramp for magnitudes that are not "bad" (e.g. retention).
GREY_RAMP = LinearSegmentedColormap.from_list("grey_ramp", ["#f6f5f2", "#cfcdc6", "#8a8984", "#3f3e3b"])

FIG_DIR = OUTPUTS / "figures"


def apply() -> None:
    mpl.rcParams.update({
        "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
        "axes.edgecolor": GRID, "axes.labelcolor": INK_2, "axes.titlecolor": INK,
        "axes.titlesize": 11, "axes.titleweight": "bold", "axes.titlelocation": "left",
        "axes.labelsize": 9, "axes.spines.top": False, "axes.spines.right": False,
        "axes.grid": True, "axes.grid.axis": "y", "grid.color": GRID, "grid.linewidth": 0.8,
        "xtick.color": INK_MUTED, "ytick.color": INK_MUTED, "xtick.labelsize": 8.5, "ytick.labelsize": 8.5,
        "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "Inter", "Helvetica", "Arial", "DejaVu Sans"],
        "legend.frameon": False, "legend.fontsize": 8.5, "figure.dpi": 110, "savefig.dpi": 160,
        "savefig.bbox": "tight",
    })


def save(fig: plt.Figure, name: str) -> Path:
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    path = FIG_DIR / f"{name}.png"
    fig.savefig(path)
    return path


def pct(ax, axis: str = "y", decimals: int = 0) -> None:
    fmt = mpl.ticker.PercentFormatter(1.0, decimals=decimals)
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(fmt)


def money(ax, axis: str = "y") -> None:
    def f(x, _):
        if abs(x) >= 1e6:
            return f"${x / 1e6:.1f}M"
        if abs(x) >= 1e3:
            return f"${x / 1e3:.0f}k"
        return f"${x:.0f}"
    (ax.yaxis if axis == "y" else ax.xaxis).set_major_formatter(mpl.ticker.FuncFormatter(f))
