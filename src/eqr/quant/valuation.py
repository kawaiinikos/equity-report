import numpy as np
import pandas as pd

REPORT_LAG_DAYS = 60  # annual figures assumed known ~2 months after fiscal year-end


def _annual(stmts: dict, row: str) -> pd.Series:
    df = stmts["a_income"]
    if row not in df.index:
        return pd.Series(dtype=float)
    return df.loc[row].astype(float).dropna().sort_index()


def history(close: pd.Series, stmts: dict) -> dict:
    """Monthly P/E and P/S proxies from annual statements (yfinance exposes only ~4 fiscal years)."""
    eps, rev = _annual(stmts, "Diluted EPS"), _annual(stmts, "Total Revenue")
    sh = _annual(stmts, "Diluted Average Shares")
    sps = (rev / sh).dropna()
    m = close.resample("ME").last().iloc[-60:]

    def ratio(base: pd.Series) -> pd.Series:
        out = {}
        for d, px in m.items():
            known = base[base.index + pd.Timedelta(days=REPORT_LAG_DAYS) <= d]
            if len(known) and known.iloc[-1] > 0:
                out[d] = px / known.iloc[-1]
        return pd.Series(out, dtype=float)

    return {"trailing_pe": ratio(eps), "price_to_sales": ratio(sps)}


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
