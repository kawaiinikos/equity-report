"""How many of LSEG's published peers does each peer method recover? (benchmark reports: HON 2026-10-15, AMZN)

  python scripts/evaluate_peers.py          overlap per method and per single signal
  python scripts/evaluate_peers.py --grid   also search blend weights (small sample: read as a sanity check only)"""
import itertools
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr.collectors import sec
from eqr.config import ROOT
from eqr.quant import peers as P
from eqr.quant import similarity as S

LSEG = {"HON": ["RTX", "ETN", "EMR", "MMM", "NOC", "GRMN", "ROK", "ZBRA", "MSA", "CC"],
        "AMZN": ["MSFT", "META", "GOOGL", "AAPL", "WMT"]}
N = 10

uni = pd.read_parquet(ROOT / "data" / "universe.parquet")
tables = {}
for tk, ref in LSEG.items():
    row = uni[uni["ticker"] == tk].iloc[0].to_dict()
    old = P.by_size(uni, tk, row["sector"], row["industry"], row["market_cap"], N)
    tab = P.similarity_table(uni, row, profile=sec.business_profile(tk, pd.Timestamp("2026-10-15")))
    tables[tk] = tab
    reach = [t for t in ref if t in set(uni["ticker"])]
    hit = lambda picks: sorted(set(picks) & set(ref))
    print(f"\n{tk}: LSEG lists {len(ref)} peers, {len(reach)} of them are in our S&P 500 universe")
    print(f"  old method (industry + size)  {len(hit(old['ticker'])):>2}/{len(reach)}  {hit(old['ticker'])}")
    print(f"  new similarity blend          {len(hit(tab.index[:N])):>2}/{len(reach)}  {hit(tab.index[:N])}")
    print(f"  new top {N}: {list(tab.index[:N])}")
    for k in S.WEIGHTS:
        top = tab[k].dropna().sort_values(ascending=False).index[:N]
        print(f"    {k:<15} alone {len(hit(top)):>2}/{len(reach)}")
    print("  where LSEG's peers rank in the blend:", {t: int(tab.index.get_loc(t)) + 1 for t in reach if t in tab.index})

if "--grid" in sys.argv:
    steps = [0, 0.1, 0.2, 0.3, 0.4]
    best = []
    for w in itertools.product(steps, repeat=len(S.WEIGHTS)):
        if abs(sum(w) - 1) > 1e-9:
            continue
        wd = dict(zip(S.WEIGHTS, w))
        score = 0
        for tk, tab in tables.items():
            blend = (tab[list(wd)].fillna(0) * pd.Series(wd)).sum(axis=1) / tab[list(wd)].notna().mul(pd.Series(wd)).sum(axis=1)
            score += len(set(blend.sort_values(ascending=False).index[:N]) & set(LSEG[tk]))
        best.append((score, wd))
    best.sort(key=lambda x: -x[0])
    print("\nbest weight sets (total hits over HON + AMZN):")
    for s, wd in best[:8]:
        print(s, {k: v for k, v in wd.items() if v})
