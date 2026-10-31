"""yfinance collector: everything the Phase 1 pages need, as one plain dict."""
import pandas as pd
import yfinance as yf

from .. import asof
from ..cache import cached
from ..config import DJIA, MARKET_INDEX


def _prices(symbol: str, period: str = "10y") -> pd.DataFrame:
    df = yf.Ticker(symbol).history(period=period, auto_adjust=True)
    df.index = pd.to_datetime(df.index).tz_localize(None)
    return df[["Open", "High", "Low", "Close", "Volume"]]


def _frames(t: yf.Ticker) -> dict:
    return {
        "q_income": t.quarterly_financials, "a_income": t.financials,
        "q_balance": t.quarterly_balance_sheet, "a_balance": t.balance_sheet,
        "q_cash": t.quarterly_cashflow, "a_cash": t.cashflow,
    }


def collect(ticker: str) -> dict:
    t = yf.Ticker(ticker)
    data = {
        "ticker": ticker.upper(),
        "info": cached(f"{ticker}_info", lambda: t.info),
        "prices": cached(f"{ticker}_px", lambda: _prices(ticker)),
        "market": cached("gspc_px", lambda: _prices(MARKET_INDEX)),
        "djia": cached("dji_px", lambda: _prices(DJIA)),
        "statements": cached(f"{ticker}_stmts", lambda: _frames(t)),
    }
    try:
        data["dividends"] = cached(f"{ticker}_div", lambda: t.dividends.tz_localize(None))
    except Exception:
        data["dividends"] = pd.Series(dtype=float)
    return asof.apply(data)


def collect_estimates(ticker: str) -> dict:
    """Analyst/insider/holder tables; each fetched and cached independently so one failure doesn't sink the report."""
    t = yf.Ticker(ticker)
    getters = {
        "earnings_estimate": lambda: t.earnings_estimate, "revenue_estimate": lambda: t.revenue_estimate,
        "eps_trend": lambda: t.eps_trend, "eps_revisions": lambda: t.eps_revisions,
        "price_targets": lambda: t.analyst_price_targets, "rec_summary": lambda: t.recommendations_summary,
        "earnings_dates": lambda: t.get_earnings_dates(limit=16), "growth": lambda: t.growth_estimates,
        "up_down": lambda: t.upgrades_downgrades, "insider_tx": lambda: t.insider_transactions,
        "roster": lambda: t.insider_roster_holders, "inst_holders": lambda: t.institutional_holders,
    }
    out = {}
    for k, fn in getters.items():
        try:
            out[k] = asof.cut_estimates(k, cached(f"{ticker}_{k}", fn))
        except Exception:
            out[k] = None
    return out
