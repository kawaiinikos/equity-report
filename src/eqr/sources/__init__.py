"""Pluggable data sources. Each provider returns the same small dict so the report can switch or cross-check sources.

analyst snapshot keys: rec (dict Strong Buy..Strong Sell), n_analysts, pt_mean, pt_high, pt_low, eps_fy1, eps_fy2
fundamentals keys:     revenue_ttm, net_income_ttm, equity, roe, net_margin, eps_ttm, pe_ttm, dividend_yield
Every result carries "source" (a citation string) and "note" (what is / is not point-in-time)."""
import os

from .. import config  # noqa: F401  (loads .env)

ANALYST_SOURCES = {"yahoo": "Yahoo Finance", "finnhub": "Finnhub", "fmp": "Financial Modeling Prep", "lseg": "LSEG Workspace (I/B/E/S)", "wrds": "WRDS (I/B/E/S)"}
INSIDER_SOURCES = {"sec": "SEC EDGAR Form 4", "yahoo": "Yahoo Finance"}


def analyst_source() -> str:
    return os.environ.get("EQR_ANALYST_SOURCE", "yahoo").lower()


def insider_source() -> str:
    return os.environ.get("EQR_INSIDER_SOURCE", "sec").lower()


def _provider(name: str):
    from . import finnhub, fmp, lseg, wrds_src, yahoo
    return {"yahoo": yahoo, "finnhub": finnhub, "fmp": fmp, "lseg": lseg, "wrds": wrds_src}[name]


def status() -> dict[str, tuple[bool, str]]:
    """{source: (usable, reason)} for the app sidebar."""
    out = {}
    for k in ANALYST_SOURCES:
        try:
            out[k] = _provider(k).available()
        except Exception as e:
            out[k] = (False, f"{type(e).__name__}: {e}")
    from ..collectors import sec
    out["sec"] = (bool(os.environ.get("SEC_USER_AGENT")), "ready" if os.environ.get("SEC_USER_AGENT") else "set SEC_USER_AGENT in .env")
    return out


def analyst(ticker: str, source: str | None = None, yahoo_x: dict | None = None) -> dict:
    """Analyst snapshot from the chosen source, falling back to Yahoo (the result says which source was used)."""
    source = source or analyst_source()
    if source != "yahoo":
        try:
            ok, why = _provider(source).available()
            if ok:
                r = _provider(source).analyst(ticker)
                if r:
                    return r
        except Exception as e:
            why = f"{type(e).__name__}: {e}"
        fb = _provider("yahoo").analyst(ticker, yahoo_x)
        fb["note"] = f"{ANALYST_SOURCES[source]} unavailable ({why}); fell back to Yahoo Finance. " + fb.get("note", "")
        return fb
    return _provider("yahoo").analyst(ticker, yahoo_x)


def compare(ticker: str, d: dict | None = None) -> list[dict]:
    """Same fundamentals and analyst figures from every usable source, for the cross-check table."""
    from . import sec_src
    rows = []
    for name, mod in (("Yahoo Finance", _provider("yahoo")), ("SEC EDGAR (as filed)", sec_src), ("Finnhub", _provider("finnhub")),
                      ("Financial Modeling Prep", _provider("fmp")), ("LSEG Workspace", _provider("lseg")), ("WRDS", _provider("wrds"))):
        try:
            ok, why = mod.available()
            if not ok:
                continue
            f = mod.fundamentals(ticker, d) if mod.__name__.endswith(("yahoo", "sec_src")) else mod.fundamentals(ticker)
            if f:
                rows.append({"source": name, **f})
        except Exception:
            continue
    return rows
