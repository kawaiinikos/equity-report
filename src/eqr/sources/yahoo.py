"""Yahoo Finance via yfinance (default; no key). Analyst data are Yahoo's latest snapshot (not point-in-time)."""
import numpy as np

SOURCE = "Yahoo Finance (yfinance): analyst estimates, price targets, recommendation counts"


def available():
    return True, "ready"


def analyst(ticker: str, x: dict | None = None) -> dict:
    from ..collectors.yf import collect_estimates
    x = x or collect_estimates(ticker)
    rec = {}
    rs = x.get("rec_summary")
    if rs is not None and len(rs):
        r0 = rs.iloc[0]
        rec = {"Strong Buy": int(r0["strongBuy"]), "Buy": int(r0["buy"]), "Hold": int(r0["hold"]), "Sell": int(r0["sell"]), "Strong Sell": int(r0["strongSell"])}
    pt = x.get("price_targets") or {}
    ee = x.get("earnings_estimate")
    g = lambda k: float(ee.loc[k, "avg"]) if ee is not None and k in ee.index else np.nan
    return {"rec": rec, "n_analysts": sum(rec.values()), "pt_mean": pt.get("mean"), "pt_high": pt.get("high"), "pt_low": pt.get("low"),
            "eps_fy1": g("0y"), "eps_fy2": g("+1y"), "source": SOURCE, "note": "Latest Yahoo snapshot; not rewound to the cut-off date."}


def fundamentals(ticker: str, d: dict | None = None) -> dict:
    if d is None:
        return {}
    from ..quant.anomalies import _ttm
    st, info = d["statements"], d["info"]
    q, b = st["q_income"], st["q_balance"]
    rev, ni = _ttm(q, "Total Revenue"), _ttm(q, "Net Income Common Stockholders")
    eq = float(b.loc["Stockholders Equity"].dropna().iloc[0]) if "Stockholders Equity" in b.index else np.nan
    eps = _ttm(q, "Diluted EPS")
    px = float(d["prices"]["Close"].iloc[-1])
    return {"revenue_ttm": rev, "net_income_ttm": ni, "equity": eq, "roe": ni / eq if eq else np.nan,
            "net_margin": ni / rev if rev else np.nan, "eps_ttm": eps, "pe_ttm": px / eps if eps and eps > 0 else np.nan,
            "cite": "Yahoo Finance quarterly statements (sum of last 4 quarters)"}
