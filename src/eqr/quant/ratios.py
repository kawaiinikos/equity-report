"""16 LSEG fundamental ratios (formulas in spec.FUNDAMENTAL_PILLARS) from yfinance statements."""
import numpy as np
import pandas as pd

NAN = float("nan")


def _row(df: pd.DataFrame, *names: str) -> pd.Series:
    for n in names:
        if n in df.index:
            return df.loc[n].astype(float)
    return pd.Series(dtype=float)


def _ttm(df, *names) -> float:
    s = _row(df, *names).dropna()
    return float(s.iloc[:4].sum()) if len(s) >= 4 else NAN


def _last(df, *names) -> float:
    s = _row(df, *names).dropna()
    return float(s.iloc[0]) if len(s) else NAN


def _div(a, b):
    return a / b if b and not np.isnan(a) and not np.isnan(b) else NAN


def compute_ratios(stmts: dict, dividends: pd.Series, price: float) -> dict:
    qi, ai, qb, qc, ac = stmts["q_income"], stmts["a_income"], stmts["q_balance"], stmts["q_cash"], stmts["a_cash"]
    rev = _ttm(qi, "Total Revenue")
    gp = _ttm(qi, "Gross Profit")
    ni = _ttm(qi, "Net Income", "Net Income Common Stockholders")
    ebit = _ttm(qi, "EBIT", "Operating Income")
    intexp = abs(_ttm(qi, "Interest Expense"))
    pretax = _ttm(qi, "Pretax Income")
    cogs = _ttm(qi, "Cost Of Revenue")
    cfo = _ttm(qc, "Operating Cash Flow")
    cfi = _ttm(qc, "Investing Cash Flow")
    divs = abs(_ttm(qc, "Cash Dividends Paid", "Common Stock Dividend Paid"))

    ar = _row(ai, "Total Revenue").dropna()
    rev_growth = _div(ar.iloc[0] - ar.iloc[1], ar.iloc[1]) if len(ar) >= 2 else NAN

    equity = _last(qb, "Stockholders Equity", "Common Stock Equity")
    cur_a, cur_l = _last(qb, "Current Assets"), _last(qb, "Current Liabilities")
    debt = _last(qb, "Total Debt")
    cap = debt + equity if not np.isnan(debt + equity) else NAN
    inv, recv = _last(qb, "Inventory"), _last(qb, "Accounts Receivable", "Receivables")
    assets, liabs = _last(qb, "Total Assets"), _last(qb, "Total Liabilities Net Minority Interest")
    noa = assets - liabs if not np.isnan(assets + liabs) else NAN

    d = dividends.dropna()
    yr = d.groupby(d.index.year).sum()
    full = yr.iloc[:-1] if len(yr) > 2 else yr  # drop partial current year
    div_growth = _div(full.iloc[-1] - full.iloc[-2], full.iloc[-2]) if len(full) >= 2 else NAN
    dps = float(d[d.index > d.index.max() - pd.Timedelta(days=365)].sum()) if len(d) else 0.0

    pays_dividend = dps > 0
    r = {
        "revenue_growth": rev_growth,
        "gross_margin": _div(gp, rev),
        "return_on_equity": _div(ni, equity),
        "net_margin": _div(ni, rev),
        "current_ratio": _div(cur_a, cur_l),
        "debt_to_capital": _div(debt, cap),
        "interest_funding": _div(intexp, cfo),
        "interest_coverage": _div(ebit, intexp),
        "operating_cash_yield": _div(cfo - ni, ni),
        "accruals": _div(ni - cfo - cfi, noa),
        "days_sales_inventory": _div(365, _div(cogs, inv)),
        "days_sales_receivables": _div(365, _div(rev, recv)),
        "dividend_growth": div_growth if pays_dividend else NAN,
        "dividend_funding": _div(divs, cfo) if pays_dividend else NAN,
        "dividend_coverage": _div(pretax + intexp, intexp + divs) if pays_dividend else NAN,
        "dividend_yield": _div(dps, price) if pays_dividend else NAN,
    }
    return r
