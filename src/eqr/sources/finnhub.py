"""Finnhub (free key at finnhub.io; set FINNHUB_API_KEY in .env).

Free tier: monthly recommendation trends (point-in-time by month), basic financial metrics. Price targets may need a paid plan."""
import os

import numpy as np
import pandas as pd
import requests

from ..cache import cached

BASE = "https://finnhub.io/api/v1"
SOURCE = "Finnhub: recommendation trends (sell-side brokers, monthly), basic financials"


def available():
    return (True, "ready") if os.environ.get("FINNHUB_API_KEY") else (False, "set FINNHUB_API_KEY in .env (free at finnhub.io)")


def _get(path, **params):
    params["token"] = os.environ["FINNHUB_API_KEY"]
    r = requests.get(f"{BASE}/{path}", params=params, timeout=20)
    r.raise_for_status()
    return r.json()


def analyst(ticker: str) -> dict:
    from .. import asof
    recs = cached(f"{ticker}_finnhub_rec", lambda: _get("stock/recommendation", symbol=ticker))
    df = pd.DataFrame(recs)
    if df.empty:
        return {}
    df["period"] = pd.to_datetime(df["period"])
    if asof.as_of() is not None:
        df = df[df["period"] <= asof.as_of()]
    r = df.sort_values("period").iloc[-1]
    rec = {"Strong Buy": int(r["strongBuy"]), "Buy": int(r["buy"]), "Hold": int(r["hold"]), "Sell": int(r["sell"]), "Strong Sell": int(r["strongSell"])}
    out = {"rec": rec, "n_analysts": sum(rec.values()), "pt_mean": None, "pt_high": None, "pt_low": None, "eps_fy1": np.nan, "eps_fy2": np.nan,
           "source": SOURCE, "note": f"Recommendation counts for {r['period']:%B %Y} (point-in-time by month)."}
    try:
        pt = cached(f"{ticker}_finnhub_pt", lambda: _get("stock/price-target", symbol=ticker))
        out.update(pt_mean=pt.get("targetMean"), pt_high=pt.get("targetHigh"), pt_low=pt.get("targetLow"))
    except Exception:
        out["note"] += " Price targets need a paid Finnhub plan."
    return out


def fundamentals(ticker: str) -> dict:
    m = cached(f"{ticker}_finnhub_metric", lambda: _get("stock/metric", symbol=ticker, metric="all")).get("metric", {})
    if not m:
        return {}
    pct = lambda k: m[k] / 100 if m.get(k) is not None else np.nan
    return {"roe": pct("roeTTM"), "net_margin": pct("netProfitMarginTTM"), "eps_ttm": m.get("epsTTM", np.nan),
            "pe_ttm": m.get("peTTM", np.nan), "dividend_yield": pct("dividendYieldIndicatedAnnual"),
            "cite": "Finnhub basic financials (latest; not point-in-time)"}
