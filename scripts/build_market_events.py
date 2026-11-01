"""Market-wide earnings and insider events for every S&P 500 stock -> data/market_events.parquet.

Compact long table (ticker, kind, date, value) with kinds: surprise (EPS surprise fraction), rec (+1 upgrade / -1 downgrade),
insider (+$ buy / -$ sell, open-market only). Lets the report compute sector / large-cap / S&P 500 averages for the Earnings
and Insider scores at any cut-off date. Throttled and resumable."""
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import yfinance as yf

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr.config import ROOT
from eqr.quant.insiders import open_market

OUT = ROOT / "data" / "market_events.parquet"
DONE = ROOT / "data" / "market_events_done.txt"
WORKERS, PAUSE = 2, 1.0

cons = pd.read_csv(ROOT / "data" / "sp500_constituents.csv")
syms = cons["Symbol"].str.replace(".", "-", regex=False).tolist()
done = set(DONE.read_text().split()) if DONE.exists() else set()
todo = [s for s in syms if s not in done]
print(len(todo), "tickers to fetch", flush=True)


def call(fn):
    for attempt in range(5):
        try:
            return fn()
        except Exception as e:
            if "Too Many" in str(e) or "RateLimit" in type(e).__name__:
                time.sleep(60 * (attempt + 1))
                continue
            return None
    return None


def fetch(sym):
    time.sleep(PAUSE)
    t = yf.Ticker(sym)
    rows = []
    ed = call(lambda: t.get_earnings_dates(limit=20))
    if ed is not None and len(ed):
        r = ed.dropna(subset=["Reported EPS", "EPS Estimate"])
        for d, x in r.iterrows():
            if x["EPS Estimate"]:
                rows.append((sym, "surprise", pd.Timestamp(d).tz_localize(None), (x["Reported EPS"] - x["EPS Estimate"]) / abs(x["EPS Estimate"])))
    ud = call(lambda: t.upgrades_downgrades)
    if ud is not None and len(ud):
        a = ud["Action"].str.lower()
        for d, v in a.items():
            if v in ("up", "down") and pd.Timestamp(d) >= pd.Timestamp("2022-01-01"):
                rows.append((sym, "rec", pd.Timestamp(d).tz_localize(None), 1.0 if v == "up" else -1.0))
    tx = call(lambda: t.insider_transactions)
    if tx is not None and len(tx):
        om = open_market(tx, float("nan"))
        for _, x in om.iterrows():
            v = x["value"]
            if v == v:
                rows.append((sym, "insider", x["date"], v if x["side"] == "Buy" else -v))
    return sym, rows


acc = pd.read_parquet(OUT) if OUT.exists() else pd.DataFrame(columns=["ticker", "kind", "date", "value"])
buf, n = [], 0
with ThreadPoolExecutor(WORKERS) as ex:
    for sym, rows in ex.map(fetch, todo):
        buf += rows
        done.add(sym)
        n += 1
        if n % 25 == 0 or n == len(todo):
            acc = pd.concat([acc, pd.DataFrame(buf, columns=acc.columns)], ignore_index=True)
            acc["date"] = pd.to_datetime(acc["date"])
            acc.to_parquet(OUT)
            DONE.write_text("\n".join(sorted(done)))
            buf = []
            print(f"{n}/{len(todo)} rows={len(acc)}", flush=True)
print("saved", OUT, len(acc), flush=True)
