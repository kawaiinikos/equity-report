# Equity Research Report Generator (LSEG Stock Reports Plus-style)

Ticker in, ~11-page PDF out. Data from Yahoo Finance (yfinance); scores re-implemented from the LSEG methodology (approximations noted in the report).

## Quick start (macOS, no terminal skills needed)
1. Unzip the folder. Do NOT use any `.venv` from someone else's machine (it is rebuilt automatically).
2. Right-click `Start Report App.command` -> Open -> Open (first time only, macOS security).
   If macOS still refuses, open Terminal once and run: `xattr -dr com.apple.quarantine <unzipped folder>` then `chmod +x "<folder>/Start Report App.command"`.
3. First run installs Python/pango/dependencies (needs internet + Homebrew, ~5 min). Later runs start in seconds and the browser opens automatically.
Keep the Terminal window open while using the app; close it to stop.

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
