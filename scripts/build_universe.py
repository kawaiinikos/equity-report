"""Build/extend data/universe.parquet for the S&P 500. Resumable, throttled, checkpoints every CHECKPOINT rows."""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr import config
from eqr.universe import UNIVERSE_PATH, one

WORKERS, CHECKPOINT, PAUSE = 2, 20, 0.4
PX_PATH = config.ROOT / "data" / "universe_prices.parquet"

cons = pd.read_csv(config.ROOT / "data" / "sp500_constituents.csv")
cons["Symbol"] = cons["Symbol"].str.replace(".", "-", regex=False)
meta = cons.rename(columns={"Symbol": "ticker", "GICS Sector": "sector", "GICS Sub-Industry": "industry", "Security": "name"})[["ticker", "name", "sector", "industry"]]
syms = cons["Symbol"].tolist()


def with_retry(fn, tries=6):
    for i in range(tries):
        try:
            return fn()
        except Exception as e:
            wait = 60 if "RateLimit" in type(e).__name__ or "Too Many" in str(e) else 3 * (i + 1)
            print(f"  retry {i+1}: {type(e).__name__} (sleep {wait}s)", flush=True)
            time.sleep(wait)
    raise RuntimeError("gave up")


def load_prices() -> pd.DataFrame:
    px = pd.read_parquet(PX_PATH) if PX_PATH.exists() else pd.DataFrame()
    need = [s for s in syms + ["^GSPC"] if s not in px.columns or px[s].dropna().empty]
    for i in range(0, len(need), 50):
        chunk = need[i:i + 50]
        got = with_retry(lambda: yf.download(chunk, period="2y", auto_adjust=True, progress=False, threads=False)["Close"])
        if isinstance(got, pd.Series):
            got = got.to_frame(chunk[0])
        px = got.combine_first(px) if len(px) else got
        time.sleep(PAUSE)
    px.to_parquet(PX_PATH)
    return px


px = load_prices()
mkt = px["^GSPC"].dropna()
done = pd.read_parquet(UNIVERSE_PATH) if UNIVERSE_PATH.exists() else pd.DataFrame()
todo = [s for s in syms if s not in set(done.get("ticker", [])) and s in px.columns and px[s].dropna().size > 260]
print(len(todo), "to fetch;", len(done), "already done", flush=True)


def fetch(s):
    time.sleep(PAUSE)
    try:
        return with_retry(lambda: one(s, px[s].dropna(), mkt), tries=4)
    except Exception:
        print("skip", s, flush=True)


def save(rows):
    global done
    if rows:
        new = pd.DataFrame(rows).merge(meta, on="ticker")
        done = pd.concat([done, new], ignore_index=True).drop_duplicates("ticker", keep="last")
        done.to_parquet(UNIVERSE_PATH)


buf = []
with ThreadPoolExecutor(WORKERS) as ex:
    for n, r in enumerate(ex.map(fetch, todo), 1):
        if r:
            buf.append(r)
        if len(buf) >= CHECKPOINT:
            save(buf); buf = []
            print(f"checkpoint {n}/{len(todo)} total={len(done)}", flush=True)
save(buf)
print("saved", done.shape, flush=True)
