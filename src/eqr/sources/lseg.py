"""LSEG Workspace via the lseg-data library (desktop session: Workspace must be running and logged in on this Mac).

Setup: in Workspace open the "App Key Generator", create a key for the Data Library, put LSEG_APP_KEY=... in .env and run
`python start.py` (it installs lseg-data when the key is present). Point-in-time fields use SDate = the report cut-off, so
I/B/E/S consensus, recommendations and price targets are as they stood on that date, not today's snapshot."""
import os

import numpy as np
import pandas as pd

SOURCE = "LSEG Workspace / Data Library: I/B/E/S consensus, TRBC classification, LSEG fundamentals"
_session = {"open": False}


def available():
    if not os.environ.get("LSEG_APP_KEY"):
        return False, "set LSEG_APP_KEY in .env and keep LSEG Workspace running"
    try:
        import lseg.data  # noqa: F401
    except ImportError:
        return False, "pip install lseg-data (start.py does this when LSEG_APP_KEY is set)"
    return True, "configured (needs Workspace running)"


def _ld():
    import lseg.data as ld
    if not _session["open"]:
        ld.open_session(app_key=os.environ["LSEG_APP_KEY"])
        _session["open"] = True
    return ld


def ric(ticker: str) -> str:
    """Yahoo-style ticker -> RIC (tries Nasdaq .O, NYSE .N, then the plain symbol)."""
    ld = _ld()
    for r in (f"{ticker}.O", f"{ticker}.N", ticker.replace("-", ".")):
        df = ld.get_data(r, ["TR.CommonName"])
        if len(df) and isinstance(df.iloc[0, -1], str) and df.iloc[0, -1]:
            return r
    return ticker


def _get(ticker, fields, **params):
    from .. import asof
    ld = _ld()
    if asof.as_of() is not None:
        params.setdefault("SDate", (asof.as_of() - pd.Timedelta(days=1)).strftime("%Y-%m-%d"))
    return ld.get_data(ric(ticker), fields, parameters=params or None)


def analyst(ticker: str) -> dict:
    f = ["TR.NumOfStrongBuy", "TR.NumOfBuy", "TR.NumOfHold", "TR.NumOfSell", "TR.NumOfStrongSell", "TR.PriceTargetMean",
         "TR.PriceTargetHigh", "TR.PriceTargetLow", "TR.EPSMean(Period=FY1)", "TR.EPSMean(Period=FY2)", "TR.RecMean"]
    r = _get(ticker, f).iloc[0]
    v = lambda i: float(r.iloc[i]) if pd.notna(r.iloc[i]) else np.nan
    rec = dict(zip(["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"], [int(v(i)) if v(i) == v(i) else 0 for i in range(1, 6)]))
    return {"rec": rec, "n_analysts": sum(rec.values()), "pt_mean": v(6), "pt_high": v(7), "pt_low": v(8), "eps_fy1": v(9), "eps_fy2": v(10),
            "rec_mean": v(11), "source": SOURCE, "note": "I/B/E/S values as of the report cut-off date (point-in-time)."}


def fundamentals(ticker: str) -> dict:
    f = ["TR.Revenue", "TR.NetIncome", "TR.ReturnonAvgTotEqtyPctNetIncomeBeforeExtraItems", "TR.NetProfitMarginPct",
         "TR.PE", "TR.DividendYield", "TR.TRBCIndustry"]
    r = _get(ticker, f).iloc[0]
    v = lambda i: float(r.iloc[i]) if pd.notna(r.iloc[i]) else np.nan
    return {"revenue_ttm": v(1), "net_income_ttm": v(2), "roe": v(3) / 100, "net_margin": v(4) / 100, "pe_ttm": v(5),
            "dividend_yield": v(6) / 100, "trbc_industry": r.iloc[7], "cite": "LSEG Workspace fundamentals (as of cut-off)"}


def forward_eps_history(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Weekly I/B/E/S next-12-month EPS mean, for a real Forward P/E history."""
    ld = _ld()
    df = ld.get_data(ric(ticker), ["TR.EPSMean(Period=NTM).date", "TR.EPSMean(Period=NTM)"],
                     parameters={"SDate": start.strftime("%Y-%m-%d"), "EDate": end.strftime("%Y-%m-%d"), "Frq": "W"})
    df = df.dropna()
    return pd.Series(df.iloc[:, -1].astype(float).values, index=pd.to_datetime(df.iloc[:, -2]))
