"""ticker -> PDF (11 pages)."""
import sys
from pathlib import Path

import pandas as pd

from .charts.price import multiple_history, perf_bars, price_volume, score_bars
from . import asof, phase3, sources, trend
from .nlg.facts import build_facts
from .nlg.generate import highlights
from .quant import spec
from .quant import anomalies, scoring, valuation
from .quant.peers import pick_peers
from .universe import UNIVERSE_PATH, price_metrics
from .collectors.yf import collect
from .config import ROOT
from .quant.momentum import momentum_stats
from .quant.ratios import compute_ratios
from .quant.risk import risk_stats
from .render import sections
from .render.build import build_context, peer_rows, render_pdf, num


def phase2(d, ratios, close, extra_scores=None) -> dict:
    """Scores, peers and valuation pages; needs data/universe.parquet (scripts/build_universe.py)."""
    info = d["info"]
    hist = valuation.history(close, d["statements"])
    for k, key in (("trailing_pe", "trailingPE"), ("price_to_sales", "priceToSalesTrailing12Months")):
        if len(hist[k]):  # one definition everywhere: latest close / TTM from reported statements
            info[key] = float(hist[k].iloc[-1])
    uni = asof.universe_at(pd.read_parquet(UNIVERSE_PATH), pd.read_parquet(ROOT / "data" / "universe_prices.parquet"))
    target = {"ticker": d["ticker"], "market_cap": info.get("marketCap"), "trailing_pe": info.get("trailingPE"),
              "forward_pe": info.get("forwardPE"), "price_to_sales": info.get("priceToSalesTrailing12Months"),
              "price": float(close.iloc[-1]), "sector": None, "industry": None, "name": info.get("longName"), **ratios,
              **price_metrics(close, d["market"]["Close"])}
    match = uni[uni["ticker"] == d["ticker"]]
    sector = match["sector"].iloc[0] if len(match) else {"Industrials": "Industrials"}.get(info.get("sector"), info.get("sector"))
    industry = match["industry"].iloc[0] if len(match) else info.get("industry")
    target["sector"], target["industry"] = sector, industry
    try:  # Price Momentum seasonality factor: 10Y average return of the current calendar month
        seas = trend.seasonality_now(d["ticker"], d["prices"]["Close"])
        uni["seasonality"], target["seasonality"] = uni["ticker"].map(seas).values, seas.get(d["ticker"])
    except Exception:
        pass
    scores = scoring.score_target(uni, target) | (extra_scores or {})
    avg, opt = scoring.average_and_optimized(scores)
    peers = pick_peers(uni, d["ticker"], sector, industry, target["market_cap"])
    prow, rrow = peer_rows(target, peers)

    cur = valuation.current_multiples(info)
    bench = valuation.benchmark_medians(uni, industry, sector)
    avg5 = {k: float(hist[k].mean()) if len(hist[k]) else float("nan") for k in hist}
    names = {"price_to_sales": "Price / Sales", "trailing_pe": "Trailing P/E", "forward_pe": "Forward P/E"}
    val_rows = [[names[k], num(cur[k]), num(avg5.get(k, float("nan"))), num(bench[k]["industry"]), num(bench[k]["sp500"])] for k in names]
    val_rows.append(["Forward PEG", num(cur["forward_peg"]), "n/a", "n/a", "n/a"])
    cols = ["ticker", "name", "price", "ret_1m", "ret_3m", "market_cap", "trailing_pe", "forward_pe", "dividend_yield", "net_margin"]
    peer_table_raw = pd.concat([pd.DataFrame([target]), peers], ignore_index=True)[cols].to_dict("records")
    val_cards = []
    for k, nm in names.items():
        c, a5, sp = cur[k], avg5.get(k, float("nan")), bench[k]["sp500"]
        rel = lambda x, y: (x / y - 1) if x == x and y == y and y else float("nan")
        val_cards.append({"name": nm, "current": num(c, 1), "avg5": num(a5, 1), "rel5": rel(c, a5), "rel5_num": rel(c, a5),
                          "sp": num(sp, 1), "relsp": rel(c, sp), "ind": num(bench[k]["industry"], 1), "relind": rel(c, bench[k]["industry"])})
    fpe_chart, fpe_cite = "", ""
    src = sources.analyst_source()
    if src in ("lseg", "wrds"):
        try:
            mod = sources._provider(src)
            if mod.available()[0]:
                fe = mod.forward_eps_history(d["ticker"], close.index[-1] - pd.DateOffset(years=5), close.index[-1])
                fpe = (close.reindex(fe.index, method="ffill") / fe).dropna()
                fpe = fpe[fpe > 0]
                if len(fpe):
                    fpe_chart = multiple_history(fpe, "Forward P/E (I/B/E/S)", float(fpe.mean()), bench["forward_pe"]["sp500"], bench["forward_pe"]["industry"], cur["forward_pe"])
                    fpe_cite = sources.ANALYST_SOURCES[src]
        except Exception:
            pass
    chart = lambda k, t: multiple_history(hist.get(k, pd.Series(dtype=float)), t, avg5.get(k), bench[k]["sp500"], bench[k]["industry"], cur[k])
    f = lambda v: "NR" if v is None else f"{v:.1f}"
    return {
        "avg_score": f(avg), "opt_score": f(opt), "outlook": scoring.outlook(avg),
        "n_components": sum(1 for k in scoring.spec.COMPONENTS if scores.get(k) is not None),
        "peer_rows": prow, "peer_risk": rrow, "peer_table_raw": peer_table_raw, "val_cards": val_cards, "fpe_chart": fpe_chart, "fpe_cite": fpe_cite, "val_rows": val_rows, "peg": num(cur["forward_peg"]),
        "val_score": f(scores.get("relative_valuation")), "scores": scores,
        "_internal": {"uni": uni, "target": target, "peers": peers},
        "charts": {"score_chart": score_bars(scores), "hist_ps": chart("price_to_sales", "Price to Sales"),
                   "hist_pe": chart("trailing_pe", "Trailing P/E (price / TTM diluted EPS)"),
                   },
    }


def method_context() -> dict:
    return {"pillars": {p.replace("_", " ").title(): list(r.items()) for p, r in spec.FUNDAMENTAL_PILLARS.items()},
            "weights": {"Fundamental pillars": "25% each (renormalised if a pillar is missing; dividend pillar dropped for non-payers)",
                        "Relative Valuation": "Price/Sales, trailing P/E, forward P/E: 33.3% each",
                        "Risk": "Magnitude of returns, volatility, beta, correlation: 25% each",
                        "Price Momentum": "Relative strength 50%, seasonality 50% (this build scores relative strength only)",
                        "Earnings": "Surprises, estimate revisions, recommendation changes: equal weight",
                        "Insider Trading": "Short-term 70%, long-term 30%"},
            "bands": spec.SCORE_BANDS, "surprise_pct": spec.SURPRISE_THRESHOLD * 100, "surprise_outlier": int(spec.SURPRISE_OUTLIER * 100),
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
    pm = extra["_internal"]["peers"]["trailing_pe"].astype(float)
    extra["notes"] = anomalies.detect(d, ratios, risk, float(pm[pm > 0].median()) if (pm > 0).any() else None)
    progress("Score history")
    tf = {k: (None if v == "NR" else float(v)) for k, v in (extra.get("earn_factors") or [])}
    names = {v: k for k, v in phase3.LABELS.items()}
    extra |= trend.build(d, extra.pop("_internal"), extra["scores"], p3["events"], {names[k]: v for k, v in tf.items() if v is not None})
    extra["compare"] = sources.compare(d["ticker"], d)
    facts = build_facts(d, extra["scores"], avg, scoring.outlook(avg), risk, mom, p3["raw"])
    progress("Writing highlights")
    extra["highlights"], extra["highlights_source"] = highlights(facts)
    extra["method"] = method_context()
    progress("Rendering PDF")
    ctx = build_context(d, ratios, risk, mom, charts | extra.pop("charts"), extra)
    ctx["raw_scores"], ctx["avg_num"] = extra["scores"], avg
    ctx = sections.enrich(ctx, d, ratios, risk, mom, p3["raw"])
    return render_pdf(ctx, out_dir / f"{d['ticker']}_report.pdf"), ctx


def run(ticker: str, out_dir: Path = ROOT / "output") -> Path:
    return run_full(ticker, out_dir)[0]


if __name__ == "__main__":
    print(run(sys.argv[1] if len(sys.argv) > 1 else "HON"))
