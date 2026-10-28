"""Run before the demo (with internet): caches data and builds backup PDFs for the demo tickers."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr.pipeline import run

TICKERS = sys.argv[1:] or ["HON", "AAPL", "MSFT", "JPM", "SAP.DE"]
for t in TICKERS:
    try:
        print("OK  ", run(t), flush=True)
    except Exception as e:
        print("FAIL", t, type(e).__name__, e, flush=True)
