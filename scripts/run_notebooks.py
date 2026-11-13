"""Turn the percent-format sources in notebooks/src/ into executed .ipynb notebooks.

    python scripts/run_notebooks.py            # all four
    python scripts/run_notebooks.py q2         # just the ones whose name contains "q2"

Sources use `# %%` for code cells and `# %% [markdown]` for markdown cells, so they diff
cleanly in git; the executed notebooks (with outputs and charts) are what GitHub renders.
"""
from __future__ import annotations

import re
import sys
import time
from pathlib import Path

import nbformat
from nbconvert.preprocessors import ExecutePreprocessor

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "notebooks" / "src"
OUT = ROOT / "notebooks"


def to_notebook(text: str) -> nbformat.NotebookNode:
    nb = nbformat.v4.new_notebook()
    nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
    parts = re.split(r"^# %%(.*)$", text, flags=re.M)
    # parts = [preamble, header1, body1, header2, body2, ...]
    for header, body in zip(parts[1::2], parts[2::2]):
        body = body.strip("\n")
        if "[markdown]" in header:
            md = "\n".join(line[2:] if line.startswith("# ") else line.lstrip("#") for line in body.splitlines())
            nb.cells.append(nbformat.v4.new_markdown_cell(md))
        elif body.strip():
            nb.cells.append(nbformat.v4.new_code_cell(body))
    return nb


def main() -> int:
    pattern = sys.argv[1] if len(sys.argv) > 1 else ""
    sources = sorted(p for p in SRC.glob("q*.py") if pattern in p.stem)
    for src in sources:
        t = time.time()
        nb = to_notebook(src.read_text(encoding="utf-8"))
        ExecutePreprocessor(timeout=900, kernel_name="python3").preprocess(nb, {"metadata": {"path": str(OUT)}})
        dest = OUT / f"{src.stem}.ipynb"
        nbformat.write(nb, dest)
        print(f"  {dest.relative_to(ROOT)}  ({time.time() - t:.0f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
