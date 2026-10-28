"""ticker -> PDF. Phase 1 renders pages 1, 5, 8, 9 (page numbering follows the LSEG layout in later phases)."""
import sys
from pathlib import Path

import pandas as pd

from .charts.price import multiple_history, perf_bars, price_volume, score_bars
from . import phase3
from .nlg.facts import build_facts
from .nlg.generate import highlights
from .quant import spec
from .quant import scoring, valuation
from .quant.peers import pick_peers
from .universe import UNIVERSE_PATH, price_metrics
from .collectors.yf import collect
from .config import ROOT
from .quant.momentum import momentum_stats
from .quant.ratios import compute_ratios
from .quant.risk import risk_stats
from .render.build import build_context, peer_rows, render_pdf, num


def phase2(d, ratios, close, extra_scores=None) -> dict:
    """Scores, peers and valuation pages; needs data/universe.parquet (scripts/build_universe.py)."""
    info = d["info"]
    uni = pd.read_parquet(UNIVERSE_PATH)
    target = {"ticker": d["ticker"], "market_cap": info.get("marketCap"), "trailing_pe": info.get("trailingPE"),
              "forward_pe": info.get("forwardPE"), "price_to_sales": info.get("priceToSalesTrailing12Months"),
              "price": float(close.iloc[-1]), "sector": None, "industry": None, "name": info.get("longName"), **ratios,
              **price_metrics(close, d["market"]["Close"])}
    match = uni[uni["ticker"] == d["ticker"]]
    sector = match["sector"].iloc[0] if len(match) else {"Industrials": "Industrials"}.get(info.get("sector"), info.get("sector"))
    industry = match["industry"].iloc[0] if len(match) else info.get("industry")
    target["sector"], target["industry"] = sector, industry
    scores = scoring.score_target(uni, target) | (extra_scores or {})
    avg, opt = scoring.average_and_optimized(scores)
    peers = pick_peers(uni, d["ticker"], sector, industry, target["market_cap"])
    prow, rrow = peer_rows(target, peers)

    cur = valuation.current_multiples(info)
    hist = valuation.history(close, d["statements"])
    bench = valuation.benchmark_medians(uni, industry, sector)
    avg5 = {k: float(hist[k].mean()) if len(hist[k]) else float("nan") for k in hist}
    names = {"price_to_sales": "Price / Sales", "trailing_pe": "Trailing P/E", "forward_pe": "Forward P/E"}
    val_rows = [[names[k], num(cur[k]), num(avg5.get(k, float("nan"))), num(bench[k]["industry"]), num(bench[k]["sp500"])] for k in names]
    val_rows.append(["Forward PEG", num(cur["forward_peg"]), "n/a", "n/a", "n/a"])
    chart = lambda k, t: multiple_history(hist.get(k, pd.Series(dtype=float)), t, avg5.get(k), bench[k]["sp500"], bench[k]["industry"], cur[k])
    f = lambda v: "NR" if v is None else f"{v:.1f}"
    return {
        "avg_score": f(avg), "opt_score": f(opt), "outlook": scoring.outlook(avg),
        "n_components": sum(1 for k in scoring.spec.COMPONENTS if scores.get(k) is not None),
        "peer_rows": prow, "peer_risk": rrow, "val_rows": val_rows, "peg": num(cur["forward_peg"]),
        "val_score": f(scores.get("relative_valuation")), "scores": scores,
        "charts": {"score_chart": score_bars(scores), "hist_ps": chart("price_to_sales", "Price to Sales"),
                   "hist_pe": chart("trailing_pe", "Trailing P/E (annual-EPS proxy)"),
                   "hist_fpe": multiple_history(pd.Series(dtype=float), "Forward P/E (current vs benchmarks)", None,
                                                bench["forward_pe"]["sp500"], bench["forward_pe"]["industry"], None)},
    }


def method_context() -> dict:
    return {"pillars": {p.replace("_", " ").title(): list(r.items()) for p, r in spec.FUNDAMENTAL_PILLARS.items()},
            "weights": {"Fundamental pillars": "25% each (renormalised if a pillar is missing; dividend pillar dropped for non-payers)",
                        "Relative Valuation": "Price/Sales, trailing P/E, forward P/E: 33.3% each",
                        "Risk": "Magnitude of returns, volatility, beta, correlation: 25% each",
                        "Price Momentum": "Relative strength 50%, seasonality 50% (seasonality pending in this build)",
                        "Earnings": "Surprises, estimate revisions, recommendation changes: equal weight",
                        "Insider Trading": "Short-term 70%, long-term 30%"},
            "bands": spec.SCORE_BANDS, "surprise_pct": spec.SURPRISE_THRESHOLD * 100,
            "roles": [("CEO", "Chief Executive Officer"), ("CFO", "Chief Financial Officer"), ("COO", "Chief Operating Officer"),
                      ("CB", "Chairman of the Board"), ("VC", "Vice Chairman"), ("P", "President"), ("D", "Director"),
                      ("DO", "Director / Beneficial Owner"), ("GC", "General Counsel"), ("EVP", "Executive Vice President"),
                      ("SVP", "Senior Vice President"), ("VP", "Vice President"), ("O", "Officer"), ("R", "Retired")]}


def run_full(ticker: str, out_dir: Path = ROOT / "output", progress=lambda msg: None) -> tuple[Path, dict]:
    progress("Fetching market data")
    d = collect(ticker)
    qt = d["info"].get("quoteType")
    if qt is None:
        raise ValueError(f"'{ticker}' was not found on Yahoo Finance; check the symbol (e.g. SAP.DE, 7203.T)")
    if qt != "EQUITY":
        raise ValueError(f"{ticker} is type {qt}, not a single stock; reports cover equities only")
    close, vol = d["prices"]["Close"], d["prices"]["Volume"]
    if len(close) < 300:
        raise ValueError(f"{ticker} has only {len(close)} trading days of history; need at least 300")
    progress("Computing ratios, risk and momentum")
    ratios = compute_ratios(d["statements"], d["dividends"], close.iloc[-1])
    risk = risk_stats(close, d["market"]["Close"])
    mom = momentum_stats(close, d["djia"]["Close"])
    monthly = d["prices"].resample("ME").agg({"Close": "last", "Volume": "sum"}).iloc[-60:]
    charts = {
        "chart_1y": price_volume(close.iloc[-252:], vol.iloc[-252:]),
        "chart_5y": price_volume(monthly["Close"], monthly["Volume"], monthly=True),
        "perf_chart": perf_bars(mom["perf"], mom["perf_djia"], d["ticker"]),
    }
    progress("Estimates, insiders and scores")
    p3 = phase3.build(d, float(close.iloc[-1]))
    extra = phase2(d, ratios, close, p3['scores']) | p3['ctx']
    avg, _ = scoring.average_and_optimized(extra["scores"])
    facts = build_facts(d, extra["scores"], avg, scoring.outlook(avg), risk, mom, p3["raw"])
    progress("Writing highlights")
    extra["highlights"], extra["highlights_source"] = highlights(facts)
    extra["method"] = method_context()
    progress("Rendering PDF")
    ctx = build_context(d, ratios, risk, mom, charts | extra.pop("charts"), extra)
    ctx["raw_scores"], ctx["avg_num"] = extra["scores"], avg
    return render_pdf(ctx, out_dir / f"{d['ticker']}_report.pdf"), ctx


def run(ticker: str, out_dir: Path = ROOT / "output") -> Path:
    return run_full(ticker, out_dir)[0]


if __name__ == "__main__":
    print(run(sys.argv[1] if len(sys.argv) > 1 else "HON"))
