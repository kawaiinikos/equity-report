# AIFA Group 5 · Equity Scorecard

Ticker in, 12-page PDF out, page-for-page comparable with the LSEG Stock Reports Plus "Detailed Stock Report".
Scores re-implement the LSEG methodology on an S&P 500 universe; every block in the PDF names its data source.

## Data cut-off
By default every report is built as of **2026-10-15** (data through the 14 Oct close), matching the LSEG benchmark. Prices, dividends, statements (60-day reporting lag), earnings dates, broker actions and insider trades are truncated; multiples and market cap are re-priced. Yahoo only serves the latest analyst estimates, price targets, recommendation counts and holders, so those are not rewound. Use `EQR_AS_OF=live` (or the checkbox in the app) for current data, or `EQR_AS_OF=YYYY-MM-DD` for another date.

## Data sources
| Source | What it adds | Setup (put keys in `.env`, never in chat or git) |
|---|---|---|
| Yahoo Finance (yfinance) | prices, statements, estimates, broker actions | none (default) |
| SEC EDGAR | Form 4 insider trades and holdings (incl. indirect), XBRL fundamentals as filed | `SEC_USER_AGENT="Name email"` |
| Finnhub | monthly recommendation trends (point-in-time), basic financials | free key at finnhub.io → `FINNHUB_API_KEY=` |
| Financial Modeling Prep | grades consensus, price-target consensus, TTM ratios | free key at financialmodelingprep.com → `FMP_API_KEY=` |
| LSEG Workspace | point-in-time I/B/E/S consensus, price targets, forward P/E history, TRBC industry | Workspace → App Key Generator → `LSEG_APP_KEY=`; keep Workspace running |
| WRDS | point-in-time I/B/E/S history (consensus, recommendations), forward P/E history | `WRDS_USERNAME=` then run `python scripts/wrds_login.py` once in Terminal (you type the password there) |

`python start.py` installs `lseg-data` / `wrds` automatically when their key is in `.env`. In the app, pick the analyst
and insider source in the sidebar; the "Source cross-check" tab and page 12 of the PDF compare the same figures across
every configured source. On Streamlit Cloud, put the keys in the app's Secrets instead of `.env`.

Market-wide data (rebuild with internet, both resumable): `scripts/build_universe_history.py` (10 years of S&P 500
prices: 3-year score history, seasonality) and `scripts/build_market_events.py` (EPS surprises, broker actions and
insider trades for every S&P 500 stock: Earnings / Insider sector and index averages).

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
