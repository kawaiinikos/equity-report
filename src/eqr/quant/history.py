"""Score history (peers x -6M/-3M/-1M/-1W/current + 1Y trend) and score averages.

Risk and Price Momentum are re-ranked at every weekly date against the S&P 500 sector cohort using only prices up to
that date. Earnings is rebuilt as-of each date from reported surprises and broker up/downgrades (estimate revisions
have no history in yfinance). Fundamental, Relative Valuation and Insider Trading are held at their latest value.
The result is an approximation of LSEG's stored score history, not a replica."""
import numpy as np
import pandas as pd

from . import spec
from .earnings import _clip, surprise_table

MIN_COHORT = 30
WEEK = 5  # trading days per snapshot
MA_WEEKS = 4
RS = ["rsi_10", "rsi_50", "rsi_200", "ret_3m"]
RISK = ["magnitude_of_returns", "volatility", "beta", "correlation"]
LABELS = {"-6M": 180, "-3M": 90, "-1M": 30, "-1W": 7}


def _rsi_panel(close: pd.DataFrame, n: int) -> pd.DataFrame:
    d = close.diff()
    au = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    ad = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + au / ad.replace(0, np.nan))


def factor_panels(close: pd.DataFrame, mkt: pd.Series) -> dict[str, pd.DataFrame]:
    """Every price factor for every ticker at every date (dates x tickers), same definitions as universe.price_metrics."""
    r = close.pct_change()
    m = mkt.reindex(close.index).ffill().pct_change()
    return {
        "rsi_10": _rsi_panel(close, 10), "rsi_50": _rsi_panel(close, 50), "rsi_200": _rsi_panel(close, 200),
        "ret_3m": close / close.shift(63) - 1,
        "volatility": r.rolling(252, min_periods=126).std() * np.sqrt(252),
        "beta": r.rolling(252, min_periods=126).cov(m).div(m.rolling(252, min_periods=126).var(), axis=0),
        "correlation": r.rolling(252, min_periods=126).corr(m),
        "magnitude_of_returns": r.rolling(90, min_periods=60).max() - r.rolling(90, min_periods=60).min(),
    }


def _decile_panel(panel: pd.DataFrame, sector: pd.Series, lower_better: bool) -> pd.DataFrame:
    """Percentile rank within sector cohort (whole universe if cohort < MIN_COHORT) at each date -> deciles."""
    key = sector.reindex(panel.columns).fillna("?")
    out = pd.DataFrame(np.nan, index=panel.index, columns=panel.columns)
    for sec in key.unique():
        cols = list(key.index[key == sec])
        n = panel[cols].notna().sum(axis=1)
        cohort_rank = panel[cols].rank(axis=1, pct=True, ascending=not lower_better)
        wide_rank = panel.rank(axis=1, pct=True, ascending=not lower_better)[cols]
        ok = pd.DataFrame(np.repeat((n.values >= MIN_COHORT)[:, None], len(cols), axis=1), index=panel.index, columns=cols)
        out[cols] = cohort_rank.where(ok, wide_rank)
    return np.ceil(out * 10).clip(1, 10)


def _to_score(composite: pd.DataFrame) -> pd.DataFrame:
    return np.ceil(composite.rank(axis=1, pct=True) * 10).clip(1, 10)


def price_component_history(close: pd.DataFrame, mkt: pd.Series, sector: pd.Series) -> dict[str, pd.DataFrame]:
    """{'risk': dates x tickers, 'price_momentum': dates x tickers} of 1-10 scores."""
    f = factor_panels(close, mkt)
    risk = pd.concat([_decile_panel(f[c], sector, True) for c in RISK]).groupby(level=0).mean()
    n_ok = pd.concat([_decile_panel(f[c], sector, True).notna() for c in RISK]).groupby(level=0).sum()
    risk = risk.where(n_ok >= spec.MIN_RISK_FACTORS)
    rs = pd.concat([_decile_panel(f[c], sector, False) for c in RS]).groupby(level=0).mean()
    return {"risk": _to_score(risk), "price_momentum": _to_score(rs)}


def weekly_index(idx: pd.DatetimeIndex, min_rows: int = 130) -> pd.DatetimeIndex:
    """Every 5th trading day counted back from the latest date, so the last point is always 'today'."""
    pos = np.arange(len(idx) - 1, min_rows - 1, -WEEK)[::-1]
    return idx[pos]


def earnings_history(ed: pd.DataFrame | None, ud: pd.DataFrame | None, dates: pd.DatetimeIndex) -> pd.Series:
    """Earnings score as of each date: mean of surprise factor and recommendation-change factor (2 of the 3 LSEG factors)."""
    tbl = surprise_table(ed)
    if len(tbl):
        full = ed.dropna(subset=["Reported EPS"]).copy()
        full.index = pd.to_datetime(full.index).tz_localize(None)
        s = ((full["Reported EPS"] - full["EPS Estimate"]) / full["EPS Estimate"].abs()).sort_index()
    else:
        s = pd.Series(dtype=float)
    acts = None
    if ud is not None and len(ud):
        acts = ud["Action"].str.lower().copy()
        acts.index = pd.to_datetime(acts.index).tz_localize(None)
    vals = {}
    for d in dates:
        f = []
        past = s[s.index <= d].tail(4)
        if len(past):
            f.append(_clip(5.5 + past.mean() * 100 / 2))
        if acts is not None:
            w = acts[(acts.index <= d) & (acts.index >= d - pd.Timedelta(days=spec.REC_CHANGE_WINDOW_DAYS))]
            up, dn = int((w == "up").sum()), int((w == "down").sum())
            if up + dn:
                f.append(_clip(5.5 + 4.5 * (up - dn) / (up + dn)))
        vals[d] = float(np.mean(f)) if len(f) >= spec.MIN_EARNINGS_FACTORS else np.nan
    return pd.Series(vals).round()


def average_history(comp: dict[str, pd.Series | float | None], dates: pd.DatetimeIndex) -> pd.Series:
    """Mean of available components per date; NaN when fewer than MIN_COMPONENTS_FOR_AVERAGE are present."""
    cols = {}
    for k in spec.COMPONENTS:
        v = comp.get(k)
        if v is None or (isinstance(v, float) and np.isnan(v)):
            continue
        cols[k] = v.reindex(dates) if isinstance(v, pd.Series) else pd.Series(float(v), index=dates)
    if not cols:
        return pd.Series(np.nan, index=dates)
    df = pd.DataFrame(cols)
    return df.mean(axis=1).where(df.notna().sum(axis=1) >= spec.MIN_COMPONENTS_FOR_AVERAGE)


def smooth(s: pd.Series) -> pd.Series:
    """4-week moving average over weekly points."""
    return s.rolling(MA_WEEKS, min_periods=1).mean()


def snapshots(s: pd.Series) -> dict:
    """{'-6M': .., '-3M': .., '-1M': .., '-1W': .., 'Current': ..} nearest weekly value at or before each lookback."""
    s = s.dropna()
    if s.empty:
        return {k: None for k in [*LABELS, "Current"]}
    last = s.index[-1]
    out = {}
    for k, days in LABELS.items():
        past = s[s.index <= last - pd.Timedelta(days=days)]
        out[k] = float(past.iloc[-1]) if len(past) else None
    out["Current"] = float(s.iloc[-1])
    return out
