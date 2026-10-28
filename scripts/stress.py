"""Run the pipeline over a varied ticker set; report time, pages and how many fields fell back to n/a."""
import sys
import time
from pathlib import Path

import pdfplumber

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr.pipeline import run

SET = ["HON", "AAPL", "TSLA", "PLTR", "COIN", "LLY", "XOM", "JPM", "NEE", "O", "BRK-B", "SAP.DE", "NESN.SW", "7203.T", "RIVN", "GME", "SPY", "ZZZZ"]
rows = []
for t in sys.argv[1:] or SET:
    t0 = time.time()
    try:
        pdf = run(t)
        pg = pdfplumber.open(pdf)
        txt = "\n".join(p.extract_text() or "" for p in pg.pages)
        rows.append((t, "OK", f"{time.time()-t0:.0f}s", len(pg.pages), txt.count("n/a") + txt.count("NR"), ""))
    except Exception as e:
        rows.append((t, "FAIL", f"{time.time()-t0:.0f}s", 0, 0, f"{type(e).__name__}: {str(e)[:90]}"))
    print(rows[-1], flush=True)
