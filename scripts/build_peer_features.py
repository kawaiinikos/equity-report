"""Business-similarity inputs for peer selection -> data/peer_features.parquet (one row per universe ticker).

  summary   Yahoo Finance business description (text similarity)
  sic       SEC SIC industry code and description
  lines     revenue by business line from the latest 10-K filed before the data cut-off (SEC XBRL), as JSON

Throttled (SEC <= 10 req/s) and resumable: re-running only fetches tickers not yet in the file."""
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr import asof
from eqr.collectors import sec
from eqr.config import ROOT

OUT = ROOT / "data" / "peer_features.parquet"
uni = pd.read_parquet(ROOT / "data" / "universe.parquet")
have = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame(columns=["ticker"])
if "sic" in have:  # retry tickers whose SEC or Yahoo call failed last time
    have = have[have["sic"].notna() & have["summary"].notna()]
todo = [t for t in uni["ticker"] if t not in set(have["ticker"])]
cutoff = asof.as_of() or pd.Timestamp.today()
print(len(todo), "tickers to fetch, cut-off", cutoff.date(), flush=True)


def summary(t: str) -> str | None:
    for attempt in range(4):
        try:
            return yf.Ticker(t).info.get("longBusinessSummary")
        except Exception as e:
            if "Too Many" in str(e) or "RateLimit" in type(e).__name__:
                time.sleep(30 * (attempt + 1))
                continue
            return None
    return None


rows = []
with ThreadPoolExecutor(3) as ex:
    texts = ex.map(summary, todo)
    for i, (t, text) in enumerate(zip(todo, texts), 1):
        try:
            p = sec.business_profile(t, cutoff)
        except Exception as e:
            print(t, "SEC failed:", e, flush=True)
            p = {}
        rows.append({"ticker": t, "summary": text, "sic": p.get("sic"), "sic_desc": p.get("sic_desc"),
                     "fy_end": p.get("fy_end"), "lines": json.dumps(p.get("lines", {}))})
        if i % 25 == 0 or i == len(todo):
            pd.concat([have, pd.DataFrame(rows)], ignore_index=True).to_parquet(OUT)
            print(f"{i}/{len(todo)} saved", flush=True)
print("done")
