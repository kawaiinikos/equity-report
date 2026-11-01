"""Earnings component (surprises, estimate revisions, recommendation changes) and the page 3/4 tables.

Factor scores use fixed absolute bins (documented approximation); LSEG ranks each factor across the whole market."""
import numpy as np
import pandas as pd

from . import spec


def _clip(x: float) -> float:
    return float(np.clip(round(x), 1, 10))


def surprise_table(ed: pd.DataFrame | None) -> pd.DataFrame:
    if ed is None or ed.empty:
        return pd.DataFrame()
    r = ed.dropna(subset=["Reported EPS"]).copy()
    r.index = pd.to_datetime(r.index).tz_localize(None)
    r = r.sort_index(ascending=False)
    r["Surprise"] = (r["Reported EPS"] - r["EPS Estimate"]) / r["EPS Estimate"].abs()
    r["Category"] = np.where(r["Surprise"].abs() > spec.SURPRISE_OUTLIER, "Not comparable",
                    np.where(r["Surprise"] > spec.SURPRISE_THRESHOLD, "Positive",
                             np.where(r["Surprise"] < -spec.SURPRISE_THRESHOLD, "Negative", "In-line")))
    return r.iloc[:12]


def surprise_summary(tbl: pd.DataFrame) -> dict:
    if tbl.empty:
        return {}
    tbl = tbl[tbl["Category"] != "Not comparable"]
    if tbl.empty:
        return {}
    last4 = tbl.iloc[:4]
    return {"n": len(tbl), "pos": int((tbl["Category"] == "Positive").sum()), "neg": int((tbl["Category"] == "Negative").sum()),
            "inline": int((tbl["Category"] == "In-line").sum()), "pos4": int((last4["Category"] == "Positive").sum()),
            "neg4": int((last4["Category"] == "Negative").sum()), "inline4": int((last4["Category"] == "In-line").sum()),
            "mean4": float(last4["Surprise"].mean())}


def revision_stats(rev: pd.DataFrame | None, trend: pd.DataFrame | None) -> dict:
    out = {}
    if rev is not None and not rev.empty:
        out["up30"], out["down30"] = int(rev["upLast30days"].sum()), int(rev["downLast30days"].sum())
    if trend is not None and not trend.empty:
        out["pct30"] = float((trend["current"] / trend["30daysAgo"] - 1).mean())
        out["pct90"] = float((trend["current"] / trend["90daysAgo"] - 1).mean())
    return out


def rec_change_stats(ud: pd.DataFrame | None, today: pd.Timestamp) -> dict:
    if ud is None or ud.empty:
        return {}
    d = ud.copy()
    d.index = pd.to_datetime(d.index).tz_localize(None)
    d = d[d.index >= today - pd.Timedelta(days=spec.REC_CHANGE_WINDOW_DAYS)]
    act = d["Action"].str.lower()
    return {"up": int((act == "up").sum()), "down": int((act == "down").sum())}


def earnings_score(summary: dict, rev: dict, rc: dict) -> dict:
    f = {}
    if summary:
        f["surprises"] = _clip(5.5 + summary["mean4"] * 100 / 2)
    if rev.get("up30") is not None:
        tot = rev["up30"] + rev["down30"]
        f["estimate_revisions"] = _clip(5.5 + 4.5 * ((rev["up30"] - rev["down30"]) / tot if tot else 0))
    if rc:
        tot = rc["up"] + rc["down"]
        f["recommendation_changes"] = _clip(5.5 + 4.5 * ((rc["up"] - rc["down"]) / tot if tot else 0))
    score = float(np.mean(list(f.values()))) if len(f) >= spec.MIN_EARNINGS_FACTORS else None
    return {"factors": f, "score": None if score is None else _clip(score)}
