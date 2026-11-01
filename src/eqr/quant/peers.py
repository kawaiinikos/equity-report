import re
import traceback

import pandas as pd

from ..config import ROOT
from . import similarity as S

FEATURES = ROOT / "data" / "peer_features.parquet"


def _base_name(name) -> str:
    return re.sub(r"[\s,.]*(class [a-z]|cl [a-z]|series [a-z])\b", "", str(name).lower()).strip()


def _candidates(universe: pd.DataFrame, ticker: str) -> pd.DataFrame:
    u = universe[universe["ticker"] != ticker].copy()
    me = universe.loc[universe["ticker"] == ticker, "name"]
    if len(me):  # drop other share classes of the same company (GOOG vs GOOGL, FOX vs FOXA, ...)
        u = u[u["name"].map(_base_name) != _base_name(me.iloc[0])]
    return u


def by_size(universe: pd.DataFrame, ticker: str, sector: str, industry: str, mcap: float, n: int = 10) -> pd.DataFrame:
    """Fallback: same sub-industry first, then same sector, ranked by market-cap proximity (log distance)."""
    u = _candidates(universe, ticker)
    u["dist"] = (u["market_cap"].astype(float) / mcap).apply(lambda r: abs(__import__("math").log(r)) if r and r > 0 else 99)
    same_ind = u[u["industry"] == industry].sort_values("dist")
    rest = u[(u["sector"] == sector) & (u["industry"] != industry)].sort_values("dist")
    out = pd.concat([same_ind, rest]).head(n)
    out["why"] = "same industry, size"
    return out


def similarity_table(universe: pd.DataFrame, target: dict, summary: str | None = None,
                     profile: dict | None = None) -> pd.DataFrame:
    """Every candidate scored on the five similarity signals (see quant/similarity.py), best match first."""
    tk = target["ticker"]
    feats = S.load_features(FEATURES)
    cand = _candidates(universe, tk)
    frame = pd.concat([cand, pd.DataFrame([target])], ignore_index=True).set_index("ticker")
    frame = frame[~frame.index.duplicated(keep="last")]
    meta = frame[["sector", "industry"]].join(feats[["sic"]], how="left")
    if profile and profile.get("sic"):
        meta.loc[tk, "sic"] = profile["sic"]
    summaries = feats["summary"].dropna().to_dict()
    if summary:
        summaries[tk] = summary
    lines = feats["lines"].to_dict()
    if profile and profile.get("lines"):
        lines[tk] = profile["lines"]
    keep = list(frame.index)
    signals = {
        "business": S.business({k: v for k, v in summaries.items() if k in keep}, tk),
        "revenue_mix": S.revenue_mix({k: v for k, v in lines.items() if k in keep}, tk),
        "fundamentals": S.fundamentals(frame, tk),
        "size": S.size(frame["market_cap"].drop(index=tk), float(target["market_cap"])),
        "classification": S.classification(meta, tk),
    }
    signals = {k: v.reindex(cand["ticker"]) for k, v in signals.items()}
    out = S.blend(signals)
    base = cand.set_index("ticker")["name"].map(_base_name)
    return out[~base.reindex(out.index).duplicated()]  # one share class per company (GOOGL or GOOG, not both)


def pick_peers(universe: pd.DataFrame, ticker: str, sector: str, industry: str, mcap: float, n: int = 10,
               target: dict | None = None, summary: str | None = None, profile: dict | None = None) -> pd.DataFrame:
    """Most similar companies by the blended similarity score; falls back to industry + size if the inputs are missing."""
    if target is None or not FEATURES.exists():
        return by_size(universe, ticker, sector, industry, mcap, n)
    try:
        sim = similarity_table(universe, target, summary, profile).head(n)
    except Exception:
        traceback.print_exc()
        return by_size(universe, ticker, sector, industry, mcap, n)
    u = universe.set_index("ticker").loc[sim.index].reset_index()
    return u.assign(similarity=sim["similarity"].values, why=sim["why"].values)
