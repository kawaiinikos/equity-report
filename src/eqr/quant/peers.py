import re

import pandas as pd


def _base_name(name) -> str:
    return re.sub(r"[\s,.]*(class [a-z]|cl [a-z]|series [a-z])\b", "", str(name).lower()).strip()


def pick_peers(universe: pd.DataFrame, ticker: str, sector: str, industry: str, mcap: float, n: int = 10) -> pd.DataFrame:
    """Same sub-industry first, then same sector, ranked by market-cap proximity (log distance)."""
    u = universe[universe["ticker"] != ticker].copy()
    me = universe.loc[universe["ticker"] == ticker, "name"]
    if len(me):  # drop other share classes of the same company (GOOG vs GOOGL, FOX vs FOXA, ...)
        u = u[u["name"].map(_base_name) != _base_name(me.iloc[0])]
    u["dist"] = (u["market_cap"].astype(float) / mcap).apply(lambda r: abs(__import__("math").log(r)) if r and r > 0 else 99)
    same_ind = u[u["industry"] == industry].sort_values("dist")
    rest = u[(u["sector"] == sector) & (u["industry"] != industry)].sort_values("dist")
    return pd.concat([same_ind, rest]).head(n)
