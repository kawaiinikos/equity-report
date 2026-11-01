import numpy as np
import pandas as pd

REPORT_LAG_DAYS = 60  # annual figures assumed known ~2 months after fiscal year-end


def _row(df, row: str) -> pd.Series:
    if df is None or row not in df.index:
        return pd.Series(dtype=float)
    s = df.loc[row].astype(float).dropna()
    s.index = pd.to_datetime(s.index).tz_localize(None)
    return s.sort_index()


def ttm_series(stmts: dict, row: str, per_share: bool = False) -> pd.Series:
    """Trailing-12-month value at each fiscal period end: annual figures at year ends, rolling 4-quarter sums where
    quarterly data exist (quarterly wins on the same date). per_share divides by diluted average shares."""
    a = _row(stmts["a_income"], row)
    q = _row(stmts["q_income"], row)
    if per_share and row != "Diluted EPS":
        a = a / _row(stmts["a_income"], "Diluted Average Shares")
        qs = _row(stmts["q_income"], "Diluted Average Shares")
        q = q.rolling(4).sum() / qs if len(q) >= 4 else pd.Series(dtype=float)
    else:
        q = q.rolling(4).sum() if len(q) >= 4 else pd.Series(dtype=float)
    q = q.dropna()
    return pd.concat([a[~a.index.isin(q.index)], q]).dropna().sort_index()


def history(close: pd.Series, stmts: dict) -> dict:
    """Weekly trailing P/E and P/S over 5 years: price / TTM EPS (sales per share) known at each date.

    A period counts as known REPORT_LAG_DAYS after it ends. The last point uses the same TTM base as the current value."""
    eps = ttm_series(stmts, "Diluted EPS")
    sps = ttm_series(stmts, "Total Revenue", per_share=True)
    w = close.resample("W-FRI").last().dropna().iloc[-260:]

    def ratio(base: pd.Series) -> pd.Series:
        out = {}
        for d, px in w.items():
            known = base[base.index + pd.Timedelta(days=REPORT_LAG_DAYS) <= d]
            if len(known) and known.iloc[-1] > 0:
                out[d] = px / known.iloc[-1]
        return pd.Series(out, dtype=float)

    out = {"trailing_pe": ratio(eps), "price_to_sales": ratio(sps)}
    last_d = close.index[-1]
    for k, base in (("trailing_pe", eps), ("price_to_sales", sps)):  # end the line at the latest close
        known = base[base.index + pd.Timedelta(days=REPORT_LAG_DAYS) <= last_d]
        if len(known) and known.iloc[-1] > 0:
            out[k].loc[last_d] = float(close.iloc[-1]) / known.iloc[-1]
    return out


def current_multiples(info: dict) -> dict:
    g = lambda k: float(info[k]) if info.get(k) is not None else float("nan")
    return {"price_to_sales": g("priceToSalesTrailing12Months"), "trailing_pe": g("trailingPE"),
            "forward_pe": g("forwardPE"), "forward_peg": g("trailingPegRatio")}


def benchmark_medians(universe: pd.DataFrame, industry: str, sector: str) -> dict:
    cols = {"price_to_sales": "price_to_sales", "trailing_pe": "trailing_pe", "forward_pe": "forward_pe"}
    out = {}
    ind = universe[universe["industry"] == industry]
    if len(ind) < 5:
        ind = universe[universe["sector"] == sector]
    for k, c in cols.items():
        pos = lambda s: s[s > 0]
        out[k] = {"sp500": float(pos(universe[c]).median()), "industry": float(pos(ind[c]).median())}
    return out
