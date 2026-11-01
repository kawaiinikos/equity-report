"""WRDS (Wharton Research Data Services) via the wrds library; needs a university WRDS account with I/B/E/S access.

One-time login: run `python scripts/wrds_login.py` in Terminal (you type your password there; it is saved to ~/.pgpass,
never in this project). Then put WRDS_USERNAME=... in .env. I/B/E/S summary statistics are point-in-time by statistical
period, so consensus and recommendation history can be rebuilt for any cut-off date."""
import os

import numpy as np
import pandas as pd

SOURCE = "WRDS: I/B/E/S summary history (statsum_epsus, recdsum), point-in-time"
_db = {}


def available():
    if not os.environ.get("WRDS_USERNAME"):
        return False, "set WRDS_USERNAME in .env and run scripts/wrds_login.py once"
    try:
        import wrds  # noqa: F401
    except ImportError:
        return False, "pip install wrds (start.py does this when WRDS_USERNAME is set)"
    return True, "configured"


def _conn():
    import wrds
    if "c" not in _db:
        _db["c"] = wrds.Connection(wrds_username=os.environ["WRDS_USERNAME"])
    return _db["c"]


def _ibes_ticker(ticker: str) -> str | None:
    df = _conn().raw_sql("select ticker from ibes.idsum where oftic = %(t)s and usfirm = 1 order by sdates desc limit 1",
                         params={"t": ticker.replace("-", ".")})
    return df["ticker"].iloc[0] if len(df) else None


def analyst(ticker: str) -> dict:
    from .. import asof
    it = _ibes_ticker(ticker)
    if it is None:
        return {}
    d = (asof.as_of() or pd.Timestamp.today()).strftime("%Y-%m-%d")
    c = _conn()
    eps = c.raw_sql("""select fpi, meanest, numest, numup, numdown from ibes.statsum_epsus
                       where ticker = %(t)s and measure = 'EPS' and fpi in ('1','2') and statpers < %(d)s
                       order by statpers desc limit 4""", params={"t": it, "d": d})
    rec = c.raw_sql("""select meanrec, numrec, buypct, holdpct, sellpct from ibes.recdsum
                       where ticker = %(t)s and statpers < %(d)s order by statpers desc limit 1""", params={"t": it, "d": d})
    out = {"rec": {}, "n_analysts": 0, "pt_mean": None, "pt_high": None, "pt_low": None, "eps_fy1": np.nan, "eps_fy2": np.nan,
           "source": SOURCE, "note": f"I/B/E/S statistics before {d} (point-in-time)."}
    for k, fpi in (("eps_fy1", "1"), ("eps_fy2", "2")):
        r = eps[eps["fpi"] == fpi]
        if len(r):
            out[k] = float(r["meanest"].iloc[0])
    if len(rec):
        r = rec.iloc[0]
        n = int(r["numrec"])
        out.update(n_analysts=n, rec_mean=float(r["meanrec"]),
                   rec={"Buy": round(n * r["buypct"] / 100), "Hold": round(n * r["holdpct"] / 100), "Sell": round(n * r["sellpct"] / 100)})
    return out


def fundamentals(ticker: str) -> dict:
    return {}


def forward_eps_history(ticker: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.Series:
    """Monthly I/B/E/S FY1 mean EPS (statistical period), for a real Forward P/E history."""
    it = _ibes_ticker(ticker)
    if it is None:
        return pd.Series(dtype=float)
    df = _conn().raw_sql("""select statpers, meanest from ibes.statsum_epsus where ticker = %(t)s and measure = 'EPS'
                            and fpi = '1' and statpers between %(a)s and %(b)s order by statpers""",
                         params={"t": it, "a": start.strftime("%Y-%m-%d"), "b": end.strftime("%Y-%m-%d")})
    return pd.Series(df["meanest"].astype(float).values, index=pd.to_datetime(df["statpers"]))
