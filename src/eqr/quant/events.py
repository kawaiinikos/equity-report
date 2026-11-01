"""Dated earnings/insider events -> Earnings and Insider scores at any date.

One long format (ticker, kind, date, value) shared by data/market_events.parquet (whole S&P 500, built by
scripts/build_market_events.py) and per-ticker live data. kinds: surprise (EPS surprise fraction), rec (+1 upgrade /
-1 downgrade), insider (+$ open-market buy / -$ sale)."""
import numpy as np
import pandas as pd

from ..config import ROOT
from . import spec
from .earnings import _clip
from .insiders import _net_score

EVENTS_PATH = ROOT / "data" / "market_events.parquet"


def load_market() -> pd.DataFrame:
    if not EVENTS_PATH.exists():
        return pd.DataFrame(columns=["ticker", "kind", "date", "value"])
    ev = pd.read_parquet(EVENTS_PATH)
    ev["date"] = pd.to_datetime(ev["date"])
    return ev


def from_sources(sym: str, ed=None, ud=None, om: pd.DataFrame | None = None) -> pd.DataFrame:
    """Events for one ticker from Yahoo earnings dates, Yahoo broker actions and an open-market insider table."""
    rows = []
    if ed is not None and len(ed):
        r = ed.dropna(subset=["Reported EPS", "EPS Estimate"])
        for d, x in r.iterrows():
            if x["EPS Estimate"]:
                rows.append((sym, "surprise", pd.Timestamp(d).tz_localize(None), (x["Reported EPS"] - x["EPS Estimate"]) / abs(x["EPS Estimate"])))
    if ud is not None and len(ud):
        for d, v in ud["Action"].str.lower().items():
            if v in ("up", "down"):
                rows.append((sym, "rec", pd.Timestamp(d).tz_localize(None), 1.0 if v == "up" else -1.0))
    if om is not None and len(om):
        for _, x in om.iterrows():
            if x["value"] == x["value"]:
                rows.append((sym, "insider", pd.Timestamp(x["date"]), x["value"] if x["side"] == "Buy" else -x["value"]))
    return pd.DataFrame(rows, columns=["ticker", "kind", "date", "value"])


def earnings_at(ev: pd.DataFrame, d: pd.Timestamp) -> tuple[float | None, dict]:
    """(score, factors) as of d from surprises (last 4 comparable quarters) and up/downgrades (last 120 days)."""
    f = {}
    s = ev[(ev["kind"] == "surprise") & (ev["date"] < d)].sort_values("date")
    s = s[s["value"].abs() <= spec.SURPRISE_OUTLIER].tail(4)
    if len(s):
        f["surprises"] = _clip(5.5 + s["value"].mean() * 100 / 2)
    r = ev[(ev["kind"] == "rec") & (ev["date"] < d) & (ev["date"] >= d - pd.Timedelta(days=spec.REC_CHANGE_WINDOW_DAYS))]
    up, dn = int((r["value"] > 0).sum()), int((r["value"] < 0).sum())
    if up + dn:
        f["recommendation_changes"] = _clip(5.5 + 4.5 * (up - dn) / (up + dn))
    score = _clip(np.mean(list(f.values()))) if len(f) >= spec.MIN_EARNINGS_FACTORS else None
    return score, f


def insider_at(ev: pd.DataFrame, d: pd.Timestamp) -> tuple[float | None, float | None, float | None]:
    """(score, short-term 90d, long-term 12m) as of d."""
    x = ev[(ev["kind"] == "insider") & (ev["date"] < d)]

    def leg(days):
        w = x[x["date"] >= d - pd.Timedelta(days=days)]["value"]
        return _net_score(float(w[w > 0].sum()), float(-w[w < 0].sum()))
    st, lt = leg(90), leg(365)
    parts = [(w, v) for w, v in ((0.7, st), (0.3, lt)) if v is not None]
    score = None if not parts else float(np.clip(round(sum(w * v for w, v in parts) / sum(w for w, _ in parts)), 1, 10))
    return score, st, lt


def series(ev: pd.DataFrame, dates: pd.DatetimeIndex, kind: str) -> pd.Series:
    fn = (lambda d: earnings_at(ev, d)[0]) if kind == "earnings" else (lambda d: insider_at(ev, d)[0])
    return pd.Series({d: fn(d) for d in dates}, dtype=float)


def market_scores(ev: pd.DataFrame, d: pd.Timestamp) -> pd.DataFrame:
    """Earnings and Insider score for every ticker in the market file as of d (for sector / index averages)."""
    rows = {}
    for sym, g in ev.groupby("ticker"):
        rows[sym] = {"earnings": earnings_at(g, d)[0], "insider_trading": insider_at(g, d)[0]}
    return pd.DataFrame.from_dict(rows, orient="index", dtype=float)
