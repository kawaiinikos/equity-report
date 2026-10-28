import re

import numpy as np
import pandas as pd


def open_market(tx: pd.DataFrame | None, price: float) -> pd.DataFrame:
    """Open-market buys/sells only (derivative conversions, awards, gifts excluded), with $ value."""
    if tx is None or tx.empty:
        return pd.DataFrame({"date": pd.Series(dtype="datetime64[ns]"), "insider": pd.Series(dtype=str), "position": pd.Series(dtype=str),
                             "side": pd.Series(dtype=str), "shares": pd.Series(dtype=float), "value": pd.Series(dtype=float)})
    d = tx.copy()
    txt = d["Text"].fillna("").str.lower()
    d["side"] = np.where(txt.str.startswith("sale"), "Sell", np.where(txt.str.startswith(("purchase", "buy")), "Buy", ""))
    d = d[d["side"] != ""].copy()
    px = d["Text"].str.extract(r"price ([\d.,]+)")[0].str.replace(",", "").astype(float)
    d["value"] = d["Value"].fillna(px * d["Shares"]).fillna(price * d["Shares"])
    d["date"] = pd.to_datetime(d["Start Date"])
    d["Shares"] = d["Shares"].astype(float)
    return d.rename(columns={"Insider": "insider", "Position": "position", "Shares": "shares"})[
        ["date", "insider", "position", "side", "shares", "value"]].sort_values("date", ascending=False)


def summary(om: pd.DataFrame, today: pd.Timestamp, months: int = 6) -> dict:
    w = om[om["date"] >= today - pd.DateOffset(months=months)]
    acq, disp = w.loc[w["side"] == "Buy", "shares"].sum(), w.loc[w["side"] == "Sell", "shares"].sum()
    return {"acquired": int(acq), "disposed": int(disp), "net": int(acq - disp)}


def monthly(om: pd.DataFrame, today: pd.Timestamp) -> pd.DataFrame:
    idx = pd.period_range(end=today.to_period("M"), periods=12, freq="M")
    w = om.assign(m=om["date"].dt.to_period("M")).pivot_table(index="m", columns="side", values="value", aggfunc="sum").reindex(idx).fillna(0.0)
    for c in ("Buy", "Sell"):
        if c not in w:
            w[c] = 0.0
    return w[["Buy", "Sell"]]


def _net_score(buys: float, sells: float) -> float | None:
    tot = buys + sells
    return None if tot == 0 else float(np.clip(round(5.5 + 3.5 * (buys - sells) / tot), 1, 10))


def insider_score(om: pd.DataFrame, today: pd.Timestamp) -> float | None:
    """Short-term (90d) 70% / long-term (12m) 30%; missing leg -> the other leg carries full weight."""
    def leg(days):
        w = om[om["date"] >= today - pd.Timedelta(days=days)]
        return _net_score(w.loc[w["side"] == "Buy", "value"].sum(), w.loc[w["side"] == "Sell", "value"].sum())
    st, lt = leg(90), leg(365)
    parts = [(0.7, st), (0.3, lt)]
    parts = [(w, v) for w, v in parts if v is not None]
    return None if not parts else float(np.clip(round(sum(w * v for w, v in parts) / sum(w for w, _ in parts)), 1, 10))
