"""Universe metric table (one row per constituent) that the decile scorer ranks against."""
import numpy as np
import pandas as pd
import yfinance as yf

from .config import ROOT
from .quant.momentum import rsi
from .quant.ratios import compute_ratios

UNIVERSE_PATH = ROOT / "data" / "universe.parquet"


def price_metrics(close: pd.Series, mkt: pd.Series) -> dict:
    """Cheap price-only factors; same definitions as quant.risk / quant.momentum."""
    d, md = close.pct_change().dropna(), mkt.pct_change().dropna()
    j = pd.concat([d, md], axis=1).dropna().iloc[-252:]
    d90 = d.iloc[-90:]
    beta = np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / j.iloc[:, 1].var() if len(j) > 60 else np.nan
    return {
        "volatility": d.iloc[-252:].std() * np.sqrt(252), "beta": beta,
        "correlation": j.iloc[:, 0].corr(j.iloc[:, 1]) if len(j) > 60 else np.nan,
        "magnitude_of_returns": d90.max() - d90.min(),
        "rsi_10": rsi(close, 10), "rsi_50": rsi(close, 50), "rsi_200": rsi(close, 200),
        "ret_3m": close.iloc[-1] / close.iloc[-64] - 1, "ret_6m": close.iloc[-1] / close.iloc[-127] - 1,
        "ret_1m": close.iloc[-1] / close.iloc[-22] - 1,
    }


def one(sym: str, close: pd.Series, mkt: pd.Series) -> dict:
    t = yf.Ticker(sym)
    info = t.info
    stm = {"q_income": t.quarterly_financials, "a_income": t.financials, "q_balance": t.quarterly_balance_sheet,
           "a_balance": t.balance_sheet, "q_cash": t.quarterly_cashflow, "a_cash": t.cashflow}
    row = {"ticker": sym, "market_cap": info.get("marketCap"), "trailing_pe": info.get("trailingPE"),
           "forward_pe": info.get("forwardPE"), "price_to_sales": info.get("priceToSalesTrailing12Months"),
           "net_margin_info": info.get("profitMargins"), "price": float(close.iloc[-1])}
    row.update(compute_ratios(stm, t.dividends.tz_localize(None), float(close.iloc[-1])))
    row.update(price_metrics(close, mkt))
    return row
