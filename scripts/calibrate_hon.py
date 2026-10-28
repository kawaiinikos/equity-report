"""Compare our live HON metrics with the LSEG benchmark (report date 2026-Oct-15). Prices/dates differ, so read as sanity check."""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr.collectors.yf import collect
from eqr.pipeline import phase2
from eqr.quant.ratios import compute_ratios

BENCH = {"trailing_pe": 7.7, "forward_pe": 22.7, "dividend_yield_%": 1.4, "roe_%": 47.4, "net_margin_%": 22.7,
         "market_cap_B": 65.8, "average_score": 6, "optimized_score": 4}

d = collect("HON")
close = d["prices"]["Close"]
r = compute_ratios(d["statements"], d["dividends"], close.iloc[-1])
x = phase2(d, r, close)
info = d["info"]
ours = {"trailing_pe": info.get("trailingPE"), "forward_pe": info.get("forwardPE"), "dividend_yield_%": r["dividend_yield"] * 100,
        "roe_%": r["return_on_equity"] * 100, "net_margin_%": r["net_margin"] * 100, "market_cap_B": info["marketCap"] / 1e9,
        "average_score": float(x["avg_score"]), "optimized_score": float(x["opt_score"])}
t = pd.DataFrame({"LSEG": BENCH, "ours": ours})
t["diff"] = t["ours"] - t["LSEG"]
print(t.round(2).to_string())
print("\ncomponent scores:", {k: v for k, v in x["scores"].items() if not k.startswith("pillar")})
