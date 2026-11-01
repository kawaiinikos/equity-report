"""SEC EDGAR XBRL company facts as filed (US filers only)."""
import os

import numpy as np


def available():
    return (True, "ready") if os.environ.get("SEC_USER_AGENT") else (False, "set SEC_USER_AGENT in .env")


def fundamentals(ticker: str, d: dict | None = None) -> dict:
    from .. import asof
    from ..collectors import sec
    f = sec.ttm_fundamentals(ticker, asof.as_of())
    if not f:
        return {}
    rev, ni, eq, eps = f.get("revenue", np.nan), f.get("net_income", np.nan), f.get("equity", np.nan), f.get("eps_diluted", np.nan)
    px = float(d["prices"]["Close"].iloc[-1]) if d else np.nan
    return {"revenue_ttm": rev, "net_income_ttm": ni, "equity": eq, "roe": ni / eq if eq == eq and eq else np.nan,
            "net_margin": ni / rev if rev == rev and rev else np.nan, "eps_ttm": eps, "pe_ttm": px / eps if eps == eps and eps > 0 else np.nan,
            "cite": "SEC EDGAR XBRL company facts (10-K/10-Q as filed before the cut-off)"}
