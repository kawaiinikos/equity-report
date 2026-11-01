"""10 years of daily closes for the S&P 500 universe (+^GSPC) -> data/universe_prices_10y.parquet.

Feeds the 3-year score history and the seasonality industry rank. Throttled and resumable (re-run to fill gaps)."""
import sys
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr.config import ROOT

OUT = ROOT / "data" / "universe_prices_10y.parquet"
CHUNK, PAUSE = 40, 4

cons = pd.read_csv(ROOT / "data" / "sp500_constituents.csv")
syms = cons["Symbol"].str.replace(".", "-", regex=False).tolist() + ["^GSPC"]
px = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame()
need = [s for s in syms if s not in px.columns or px[s].dropna().size < 500]
print(len(need), "tickers to download", flush=True)
for i in range(0, len(need), CHUNK):
    chunk = need[i:i + CHUNK]
    for attempt in range(5):
        try:
            got = yf.download(chunk, period="10y", auto_adjust=True, progress=False, threads=False)["Close"]
            break
        except Exception as e:
            wait = 60 * (attempt + 1)
            print(f"  {type(e).__name__}: sleeping {wait}s", flush=True)
            time.sleep(wait)
    else:
        continue
    if isinstance(got, pd.Series):
        got = got.to_frame(chunk[0])
    got.index = pd.to_datetime(got.index).tz_localize(None)
    px = got.combine_first(px) if len(px) else got
    px.astype("float32").to_parquet(OUT)
    print(f"{min(i + CHUNK, len(need))}/{len(need)} done, shape {px.shape}", flush=True)
    time.sleep(PAUSE)
print("saved", OUT, px.shape, flush=True)
