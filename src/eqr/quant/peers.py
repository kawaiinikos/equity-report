import pandas as pd


def pick_peers(universe: pd.DataFrame, ticker: str, sector: str, industry: str, mcap: float, n: int = 10) -> pd.DataFrame:
    """Same sub-industry first, then same sector, ranked by market-cap proximity (log distance)."""
    u = universe[universe["ticker"] != ticker].copy()
    u["dist"] = (u["market_cap"].astype(float) / mcap).apply(lambda r: abs(__import__("math").log(r)) if r and r > 0 else 99)
    same_ind = u[u["industry"] == industry].sort_values("dist")
    rest = u[(u["sector"] == sector) & (u["industry"] != industry)].sort_values("dist")
    return pd.concat([same_ind, rest]).head(n)
