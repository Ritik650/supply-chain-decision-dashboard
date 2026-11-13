# One command per stage. On Windows without make, run the python lines directly.
PY ?= python

.PHONY: all data build export test notebooks dashboard check memo gif eval-oracle eval

all: build test notebooks dashboard check memo

data:
	$(PY) scripts/download_data.py

build:              ## raw CSV -> star schema + 15 data-quality rules + docs/data_quality_log.md
	$(PY) scripts/build.py

export:             ## star schema CSVs for Power BI (data/export/)
	$(PY) scripts/build.py --export

test:
	$(PY) -m pytest tests -q

notebooks:          ## execute Q1-Q4 notebooks, write outputs/findings and outputs/figures
	$(PY) scripts/run_notebooks.py

dashboard:          ## data for the static web dashboard
	$(PY) scripts/export_dashboard.py

check:              ## dashboard numbers == sql/analysis numbers, plus screenshots
	$(PY) scripts/check_dashboard.py --dark

memo:
	$(PY) memo/build_memo.py

pbip:               ## Power BI project (dashboard/powerbi/supply_chain_dashboard.pbip) + validation
	$(PY) scripts/build.py --export
	$(PY) scripts/make_pbip.py
	$(PY) scripts/validate_pbip.py

gif:
	$(PY) scripts/make_demo_gif.py

eval-oracle:        ## harness self-check, no API key needed
	$(PY) genai/eval/run_eval.py --oracle --set all --tag oracle

eval:               ## needs GEMINI_API_KEY (or an OpenAI-compatible endpoint)
	$(PY) genai/eval/run_eval.py --prompt genai/prompt.md --set test --tag v1 --sleep 4
