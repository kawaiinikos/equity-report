# Equity Research Report Generator (LSEG Stock Reports Plus-style)

Ticker in, ~11-page PDF out. Data from Yahoo Finance (yfinance); scores re-implemented from the LSEG methodology (approximations noted in the report).

## Quick start (macOS / Windows / Linux)
```
python start.py
```
(on Windows: `py start.py`, or double-click `start.py`). The first run creates `.venv`, installs the requirements
and opens the app in the browser; later runs start in seconds. If something is missing (Python 3.11+, the Pango
library for the PDF engine, internet) the launcher stops and prints exactly what to install.
Extras: `python start.py --check` verifies the setup only, `python start.py --reinstall` rebuilds `.venv`.

## Setup (once, manual)
```bash
python3.12 -m venv .venv && .venv/bin/pip install -e . lxml requests
.venv/bin/python scripts/build_universe.py   # S&P 500 cohort for decile scores (~20 min, resumable)
```
Optional: copy `.env.example` to `.env` and add `ANTHROPIC_API_KEY` for Claude-written highlights (template fallback otherwise).

## Demo
```bash
.venv/bin/python scripts/prewarm.py HON AAPL MSFT JPM SAP.DE   # with internet: caches data + backup PDFs in output/
.venv/bin/streamlit run app/streamlit_app.py                    # tick "Offline mode" to use cached data only
```
CLI: `.venv/bin/python -m eqr.pipeline HON` · Tests: `.venv/bin/python -m pytest` · Benchmark check: `scripts/calibrate_hon.py`.
