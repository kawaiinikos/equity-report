"""Financial Modeling Prep (free key at financialmodelingprep.com; set FMP_API_KEY in .env). Some endpoints need a paid plan."""
import os

import numpy as np
import requests

from ..cache import cached

BASE = "https://financialmodelingprep.com/stable"
SOURCE = "Financial Modeling Prep: analyst grades consensus, price-target consensus, TTM ratios"


def available():
    return (True, "ready") if os.environ.get("FMP_API_KEY") else (False, "set FMP_API_KEY in .env (free at financialmodelingprep.com)")


def _get(path, **params):
    params["apikey"] = os.environ["FMP_API_KEY"]
    r = requests.get(f"{BASE}/{path}", params=params, timeout=20)
    r.raise_for_status()
    j = r.json()
    return j[0] if isinstance(j, list) and j else j


def analyst(ticker: str) -> dict:
    g = cached(f"{ticker}_fmp_grades", lambda: _get("grades-consensus", symbol=ticker)) or {}
    rec = {"Strong Buy": g.get("strongBuy", 0), "Buy": g.get("buy", 0), "Hold": g.get("hold", 0), "Sell": g.get("sell", 0), "Strong Sell": g.get("strongSell", 0)}
    out = {"rec": rec, "n_analysts": sum(rec.values()), "pt_mean": None, "pt_high": None, "pt_low": None, "eps_fy1": np.nan, "eps_fy2": np.nan,
           "source": SOURCE, "note": "Latest FMP consensus; not rewound to the cut-off date."}
    try:
        pt = cached(f"{ticker}_fmp_pt", lambda: _get("price-target-consensus", symbol=ticker)) or {}
        out.update(pt_mean=pt.get("targetConsensus"), pt_high=pt.get("targetHigh"), pt_low=pt.get("targetLow"))
    except Exception:
        pass
    return out if out["n_analysts"] else {}


def fundamentals(ticker: str) -> dict:
    r = cached(f"{ticker}_fmp_ratios", lambda: _get("ratios-ttm", symbol=ticker)) or {}
    k = cached(f"{ticker}_fmp_km", lambda: _get("key-metrics-ttm", symbol=ticker)) or {}
    if not r and not k:
        return {}
    return {"roe": k.get("returnOnEquityTTM", np.nan), "net_margin": r.get("netProfitMarginTTM", np.nan),
            "pe_ttm": r.get("priceToEarningsRatioTTM", np.nan), "dividend_yield": r.get("dividendYieldTTM", np.nan),
            "cite": "FMP TTM ratios / key metrics (latest; not point-in-time)"}
