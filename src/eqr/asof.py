"""Data cut-off ('as of') so a report can be reproduced for a past date, e.g. the LSEG benchmark date.

The date is the report date; data runs through the previous close (LSEG's 2026-Oct-15 report uses the 14 Oct close).
Set EQR_AS_OF=YYYY-MM-DD (default DEFAULT_AS_OF) or EQR_AS_OF=live for no cut-off. Prices, dividends, financial statements
(reporting lag applied), earnings dates, broker actions and insider trades are truncated to the date. Yahoo only serves the
latest snapshot of analyst estimates, price targets, recommendation counts, holders and key ratios, so those are not rewound;
valuation multiples and market cap are re-priced to the cut-off date."""
import os

import numpy as np
import pandas as pd

DEFAULT_AS_OF = "2026-10-15"
REPORTING_LAG_DAYS = 60  # a fiscal period ending after (as_of - lag) is assumed not yet reported


def as_of() -> pd.Timestamp | None:
    v = os.environ.get("EQR_AS_OF", DEFAULT_AS_OF).strip().lower()
    return None if v in ("", "live", "none") else pd.Timestamp(v)


def today() -> pd.Timestamp:
    return as_of() or pd.Timestamp.today().normalize()


def _cut_index(df, ts: pd.Timestamp):
    if df is None or not hasattr(df, "index") or not len(df):
        return df
    idx = pd.to_datetime(df.index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    return df[idx < ts]  # data through the close before the report date, like LSEG


def cut_estimates(key: str, df):
    """Truncate dated analyst/insider tables; snapshot tables are returned unchanged."""
    ts = as_of()
    if ts is None or df is None:
        return df
    if key in ("earnings_dates", "up_down"):
        return _cut_index(df, ts)
    if key == "insider_tx" and "Start Date" in df:
        return df[pd.to_datetime(df["Start Date"]) < ts]
    return df


def _cut_statements(frames: dict, ts: pd.Timestamp) -> dict:
    lim = ts - pd.Timedelta(days=REPORTING_LAG_DAYS)
    out = {}
    for k, df in frames.items():
        if df is not None and hasattr(df, "columns") and len(df.columns):
            keep = [c for c in df.columns if pd.Timestamp(c).tz_localize(None) <= lim]
            df = df[keep]
        out[k] = df
    return out


def _ttm(df, row):
    if df is None or row not in getattr(df, "index", []):
        return np.nan
    s = df.loc[row].astype(float).dropna()
    return float(s.iloc[:4].sum()) if len(s) >= 4 else np.nan


def apply(d: dict) -> dict:
    """Return the collected-data dict truncated and re-priced to the cut-off date."""
    ts = as_of()
    if ts is None:
        return d
    live_px = float(d["prices"]["Close"].iloc[-1])
    for k in ("prices", "market", "djia"):
        d[k] = _cut_index(d[k], ts)
    d["dividends"] = d["dividends"][pd.to_datetime(d["dividends"].index) < ts] if len(d["dividends"]) else d["dividends"]
    d["statements"] = _cut_statements(d["statements"], ts)
    px = d["prices"]
    last = float(px["Close"].iloc[-1])
    r = last / live_px
    info = dict(d["info"])
    st = d["statements"]
    eps, rev = _ttm(st["q_income"], "Diluted EPS"), _ttm(st["q_income"], "Total Revenue")
    mcap = (info.get("marketCap") or np.nan) * r
    info["marketCap"] = mcap if mcap == mcap else info.get("marketCap")
    info["trailingPE"] = last / eps if eps == eps and eps > 0 else (info.get("trailingPE") * r if info.get("trailingPE") else None)
    info["priceToSalesTrailing12Months"] = mcap / rev if rev == rev and rev > 0 and mcap == mcap else (
        info.get("priceToSalesTrailing12Months") * r if info.get("priceToSalesTrailing12Months") else None)
    info["forwardPE"] = info["forwardPE"] * r if info.get("forwardPE") else None
    info["trailingPegRatio"] = info["trailingPegRatio"] * r if info.get("trailingPegRatio") else None
    yr = px.iloc[-252:]
    info["fiftyTwoWeekHigh"], info["fiftyTwoWeekLow"] = float(yr["High"].max()), float(yr["Low"].min())
    info["currentPrice"] = info["regularMarketPrice"] = last
    d["info"] = info
    return d


def universe_at(uni: pd.DataFrame, prices: pd.DataFrame) -> pd.DataFrame:
    """Re-price the S&P 500 universe table (price factors, price, market cap, multiples) to the cut-off date."""
    ts = as_of()
    if ts is None:
        return uni
    from .quant.history import factor_panels
    close = _cut_index(prices, ts)
    mkt = close["^GSPC"]
    f = factor_panels(close, mkt)
    uni = uni.copy().set_index("ticker")
    last = close.iloc[-1]
    ratio = (last / prices.iloc[-1]).reindex(uni.index)
    for c, p in f.items():
        uni[c] = p.iloc[-1].reindex(uni.index)
    for c, n in (("ret_1m", 21), ("ret_3m", 63), ("ret_6m", 126)):
        uni[c] = (close.iloc[-1] / close.iloc[-1 - n] - 1).reindex(uni.index)
    uni["price"] = last.reindex(uni.index)
    for c in ("market_cap", "trailing_pe", "forward_pe", "price_to_sales"):
        uni[c] = uni[c] * ratio
    return uni.reset_index()
