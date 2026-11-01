"""Page-by-page content for the 12-page layout (mirrors the LSEG Stock Reports Plus page order).

Turns the numbers already computed by the pipeline into display rows, outlook sentences and highlight bullets.
Every highlight is generated from figures in this context (no free text), and data notes from quant.anomalies are
attached to the page they explain."""
import numpy as np
import pandas as pd

from ..charts.gauge import gauge
from ..charts.price import consensus_bar
from ..quant import scoring
from .build import num, pct

COMP_NAMES = {"average": "Average Score", "earnings": "Earnings", "fundamental": "Fundamental", "relative_valuation": "Relative Valuation",
              "risk": "Risk", "price_momentum": "Price Momentum", "insider_trading": "Insider Trading"}
OUTLOOK = {  # (positive, neutral, negative) one-liners, LSEG-style
    "average": ("Positive outlook: the combined indicators are favourable.", "Neutral outlook: the combined score is in line with the market.",
                "Negative outlook: the combined indicators are unfavourable."),
    "earnings": ("Positive outlook: earnings surprises and analyst sentiment are favourable.", "Neutral outlook: mixed earnings expectations and performance.",
                 "Negative outlook: weak surprises or falling analyst sentiment."),
    "fundamental": ("Positive outlook: fundamentals are strong relative to the market.", "Neutral outlook: fundamentals relatively in line with the market.",
                    "Negative outlook: fundamentals are weak relative to the market."),
    "relative_valuation": ("Positive outlook: multiples are attractive (cheap) relative to the sector.", "Neutral outlook: multiples relatively in line with the sector.",
                           "Negative outlook: multiples are expensive relative to the sector."),
    "risk": ("Positive outlook: consistent return patterns (low volatility).", "Neutral outlook: risk relatively in line with the market.",
             "Negative outlook: volatile or highly market-sensitive returns."),
    "price_momentum": ("Positive outlook: strong relative strength and seasonality.", "Neutral outlook: performance relatively in line with the market.",
                       "Negative outlook: weak relative strength or seasonality."),
    "insider_trading": ("Positive outlook: insiders have been net buyers.", "Neutral outlook: mixed transactions by insiders or low volume of trades.",
                        "Negative outlook: insiders have been net sellers."),
}


def _band(v):
    if v is None or v != v:
        return "nr", "Not rated"
    return ("pos", "Positive") if v >= 8 else ("neu", "Neutral") if v >= 4 else ("neg", "Negative")


def _outlook(comp, v):
    b, _ = _band(v)
    if b == "nr":
        return "Not rated: not enough data for this component."
    return OUTLOOK[comp][{"pos": 0, "neu": 1, "neg": 2}[b]]


def _box_val(block, label_start):
    for k, v in block.get("box", []):
        if k.startswith(label_start):
            return v
    return "n/a"


def enrich(ctx: dict, d: dict, ratios: dict, risk: dict, mom: dict, raw: dict) -> dict:
    info, px = d["info"], d["prices"]
    close = px["Close"]
    tk, name = d["ticker"], ctx["name"]
    sc = ctx["raw_scores"]
    avg = ctx.get("avg_num")
    blocks = ctx.get("blocks", {})
    notes = ctx.get("notes", {})
    sector = blocks and next((k for k, _ in blocks["average"]["box"] if k.endswith("sector")), "Sector") or "Sector"

    from .. import asof
    q_end = d["statements"]["q_income"].columns
    ctx.update(gics_sector=info.get("sector", ""), data_to=close.index[-1].strftime("%Y-%m-%d"), currency=info.get("currency", "USD"),
               stmt_lag=asof.REPORTING_LAG_DAYS, stmt_end=pd.Timestamp(max(q_end)).strftime("%Y-%m-%d") if len(q_end) else "n/a",
               peer_names=[(r["ticker"], str(r.get("name") or ""), ctx.get("peer_why", {}).get(r["ticker"], "")) for r in ctx.get("peer_table_raw", [])[1:]])

    # ---- page 1: key stats (two rows, LSEG order) ----
    divs = d["dividends"]
    ann_div = float(divs[divs.index >= close.index[-1] - pd.Timedelta(days=365)].sum()) if len(divs) else 0.0
    a_rev = d["statements"]["a_income"].loc["Total Revenue"].dropna() if "Total Revenue" in d["statements"]["a_income"].index else pd.Series(dtype=float)
    ret = lambda n: close.iloc[-1] / close.iloc[-n - 1] - 1
    ctx["stats_top"] = [("Last Close", num(close.iloc[-1]), close.index[-1].strftime("%Y-%m-%d")), ("Avg Daily Vol", f"{px['Volume'].iloc[-63:].mean() / 1e6:,.1f}M", "3-month"),
                        ("52-Week High", num(info.get("fiftyTwoWeekHigh", np.nan)), ""), ("Trailing PE", num(info.get("trailingPE", np.nan), 1), ""),
                        ("Annual Div", num(ann_div), "TTM"), ("ROE", pct(ratios.get("return_on_equity", np.nan)), ""),
                        ("LTG Forecast", pct(raw.get("ltg", np.nan)), "5-yr EPS growth"), ("1-Mo Return", pct(ret(21)), "")]
    ctx["stats_bot"] = [("Market Cap", f"{(info.get('marketCap') or np.nan) / 1e9:,.1f}B", ""), ("Exchange", info.get("exchange", ""), info.get("currency", "")),
                        ("52-Week Low", num(info.get("fiftyTwoWeekLow", np.nan)), ""), ("Forward PE", num(info.get("forwardPE", np.nan), 1), ""),
                        ("Dividend Yield", pct(ratios.get("dividend_yield", np.nan), 1), ""), ("Annual Rev", f"{a_rev.iloc[0] / 1e9:,.1f}B" if len(a_rev) else "n/a", "last FY"),
                        ("Inst Own", pct(info.get("heldPercentInstitutions", np.nan)), ""), ("3-Mo Return", pct(ret(63)), "")]
    ctx["ret_1y"], ctx["ret_5y"] = pct(ret(252)), pct(close.iloc[-1] / close.iloc[-1261] - 1) if len(close) > 1261 else "n/a"
    ctx["consensus_chart"] = consensus_bar(ctx.get("mean_rec", np.nan))

    # ---- component header blocks (score tile, outlook, averages, 3Y chart, peer trend) ----
    comp_score = {"average": avg, **{k: sc.get(k) for k in COMP_NAMES if k != "average"}}
    ctx["comp"] = {}
    for k, title in COMP_NAMES.items():
        b = blocks.get(k, {})
        v = comp_score.get(k)
        band, band_txt = _band(v)
        ctx["comp"][k] = {"title": title, "score": "NR" if v is None or v != v else f"{v:.0f}" if k != "average" else f"{v:.0f}",
                          "band": band, "band_txt": band_txt, "outlook": _outlook(k, v), "body": (lambda t: t[0].upper() + t[1:])(_outlook(k, v).split(": ", 1)[-1]), "box": b.get("box", []), "chart": b.get("chart", ""),
                          "rows": b.get("rows", []), "gauge": b.get("gauge", ""), "flat": k in ("fundamental", "relative_valuation")}

    # page 2: indicator overview gauge (target only) + peer table
    ctx["overview_gauge"] = gauge([{"title": COMP_NAMES[k], "weight": "", "scores": {tk: sc.get(k)}} for k in COMP_NAMES if k != "average"], tk, w=7.4, h=2.3)
    info_p = ctx.get("peer_info", {})
    rows = []
    for r in ctx.get("peer_table_raw", []):
        s = r["ticker"]
        a = avg if s == tk else info_p.get(s, {}).get("avg", np.nan)
        rows.append({"target": s == tk, "cells": ["NR" if a != a else f"{a:.0f}", s, num(r["price"]), pct(r["ret_1m"]), pct(r["ret_3m"]),
                                                  pct(info_p.get(s, {}).get("ret_1y", np.nan)), f"{r['market_cap'] / 1e9:,.1f}B" if r["market_cap"] == r["market_cap"] else "n/a",
                                                  num(r["trailing_pe"], 1), num(r["forward_pe"], 1), pct(r["dividend_yield"], 1), pct(r["net_margin"], 1)]})
    if rows:
        df = pd.DataFrame(ctx["peer_table_raw"])
        med = lambda c: df[c].astype(float).median()
        ap = [info_p.get(s, {}).get("avg", np.nan) for s in df["ticker"][1:]]
        rows.append({"target": False, "avg": True, "cells": [f"{np.nanmean(ap):.1f}" if len(ap) else "n/a", "Median", num(med("price")), pct(med("ret_1m")), pct(med("ret_3m")),
                                                             pct(np.nanmedian([info_p.get(s, {}).get("ret_1y", np.nan) for s in df["ticker"]])), f"{med('market_cap') / 1e9:,.1f}B",
                                                             num(med("trailing_pe"), 1), num(med("forward_pe"), 1), pct(med("dividend_yield"), 1), pct(med("net_margin"), 1)]})
    ctx["peer_rows2"] = rows

    # ---- highlights per page (generated from figures above; data notes appended) ----
    sec_avg = lambda k: _box_val(blocks.get(k, {}), sector.split(" sector")[0])
    sp_avg = lambda k: _box_val(blocks.get(k, {}), "S&P")
    f0 = lambda v: "NR" if v is None or v != v else f"{v:.0f}"
    hl = {}
    hl["earnings"] = [f"{name} has an Earnings rating of {f0(sc.get('earnings'))}; the {sector} average is {sec_avg('earnings')} and the S&P 500 average is {sp_avg('earnings')}."]
    ss = ctx.get("surp_summary") or {}
    if ss:
        hl["earnings"].append(f"Over the last four comparable quarters the company beat consensus by more than 2% {ss.get('pos4', 0)} times and missed {ss.get('neg4', 0)} times (average surprise {pct(ss.get('mean4', np.nan))}).")
    rc = ctx.get("rc_stats") or {}
    if rc:
        hl["earnings"].append(f"In the last 120 days brokers issued {rc.get('up', 0)} upgrade(s) and {rc.get('down', 0)} downgrade(s).")
    hl["fundamental"] = [f"{name} has a Fundamental rating of {f0(sc.get('fundamental'))}; the {sector} average is {sec_avg('fundamental')} and the S&P 500 average is {sp_avg('fundamental')}."]
    pillars = {p: sc.get(f"pillar_{p}") for p in ("profitability", "debt", "earnings_quality", "dividend")}
    good = [p.replace("_", " ") for p, v in pillars.items() if v is not None and v == v and v >= 7]
    weak = [p.replace("_", " ") for p, v in pillars.items() if v is not None and v == v and v <= 3]
    if good:
        hl["fundamental"].append(f"Strongest pillar(s): {', '.join(good)}.")
    if weak:
        hl["fundamental"].append(f"Weakest pillar(s): {', '.join(weak)}.")
    hl["relative_valuation"] = [f"{name} has a Relative Valuation rating of {f0(sc.get('relative_valuation'))} (10 = cheapest); the S&P 500 average is {sp_avg('relative_valuation')}."]
    for c in ctx.get("val_cards", []):
        if c.get("rel5_num") == c.get("rel5_num") and c.get("rel5_num") is not None:
            hl["relative_valuation"].append(f"{c['name']} of {c['current']} is a {abs(c['rel5_num']):.0%} {'discount' if c['rel5_num'] < 0 else 'premium'} to its 5-year average of {c['avg5']}.")
    hl["risk"] = [f"{name} has a Risk rating of {f0(sc.get('risk'))} (10 = lowest risk); the S&P 500 average is {sp_avg('risk')}.",
                  f"On days when the market is up the stock's beta is {num(risk.get('beta_pos'))}; on down days it is {num(risk.get('beta_neg'))}.",
                  f"Correlation with the S&P 500 over the last year is {num(risk.get('corr'))}."]
    hi, lo = info.get("fiftyTwoWeekHigh"), info.get("fiftyTwoWeekLow")
    last = float(close.iloc[-1])
    hl["price_momentum"] = [f"{name} has a Price Momentum rating of {f0(sc.get('price_momentum'))}; the S&P 500 average is {sp_avg('price_momentum')}."]
    if hi and lo:
        hl["price_momentum"].append(f"On {close.index[-1]:%Y-%m-%d} the stock closed at {last:,.2f}, {1 - last / hi:.1%} below its 52-week high and {last / lo - 1:.1%} above its 52-week low.")
    hl["price_momentum"].append(f"The stock is {abs(last / mom['sma_50'] - 1):.1%} {'above' if last > mom['sma_50'] else 'below'} its 50-day and {abs(last / mom['sma_200'] - 1):.1%} {'above' if last > mom['sma_200'] else 'below'} its 200-day moving average.")
    s6 = ctx.get("ins_sum") or {}
    hl["insider_trading"] = [f"{name} has an Insider Trading rating of {f0(sc.get('insider_trading'))}; the {sector} average is {sec_avg('insider_trading')}."]
    if s6:
        hl["insider_trading"].append(f"Over the last six months insiders acquired {s6.get('acquired', 0):,} and disposed of {s6.get('disposed', 0):,} shares in open-market trades.")
    ctx["hl"] = hl
    ctx["page_notes"] = {"overview": notes.get("overview", []), "earnings": notes.get("earnings", []), "fundamental": notes.get("fundamental", []),
                         "relative_valuation": notes.get("valuation", []), "risk": notes.get("risk", []), "price_momentum": [], "insider_trading": []}

    # ---- risk stat boxes (page 8) ----
    r = risk
    ctx["risk_boxes"] = [
        ("Daily Returns (90 days)", [("Best", pct(r["best_day_90d"])), ("Worst", pct(r["worst_day_90d"]))]),
        ("Standard Deviation", [("Last 90 days (daily)", pct(r["std_daily_90d"], 2)), ("Last 60 months (monthly)", pct(r["std_monthly_60m"], 2))]),
        ("Beta vs S&P 500 (1 year)", [("All days", num(r["beta"])), ("Positive days only", num(r["beta_pos"])), ("Negative days only", num(r["beta_neg"]))]),
        ("Correlation vs S&P 500", [("Last year (daily)", pct(r["corr"], 0)), ("Last 60 months", pct(r.get("corr_monthly_60m", np.nan), 0))]),
        ("Monthly Returns (60 months)", [("Best", pct(r["best_month_60m"])), ("Worst", pct(r["worst_month_60m"]))]),
        ("Volatility", [("Annualised (1 year)", pct(r["volatility_ann"]))]),
    ]
    ctx["risk_rows2"] = [{"target": x["target"], "cells": [x["ticker"], pct(x["best_d"]), pct(x["worst_d"]), str(x["up"]), str(x["down"]), pct(x["best_m"]), pct(x["worst_m"])]}
                         for x in ctx.get("risk_table", [])]

    # ---- momentum tables (page 9) ----
    rs = ctx.get("rsi_sector", {})
    ctx["rsi_rows"] = [(lab, num(mom[k], 0), num(rs.get(k, np.nan), 0)) for lab, k in (("Last 10 days", "rsi_10"), ("Last 50 days", "rsi_50"), ("Last 200 days", "rsi_200"))]
    ctx["season_rows"] = [(x["month"], pct(x["company"]), pct(x["sector"]), f"{x['rank']} of {x['n']}") for x in ctx.get("season_rank", [])]
    djia = d["djia"]["Close"]
    ctx["perf_side"] = [("Close", num(last), num(djia.iloc[-1], 0)), ("52-week high", num(hi or np.nan), num(djia.iloc[-252:].max(), 0)),
                        ("52-week low", num(lo or np.nan), num(djia.iloc[-252:].min(), 0))]

    # ---- cross-check table (page 12) ----
    keys = [("revenue_ttm", "Revenue (TTM)", lambda v: f"${v / 1e9:,.1f}bn"), ("net_income_ttm", "Net income (TTM)", lambda v: f"${v / 1e9:,.2f}bn"),
            ("equity", "Shareholders' equity", lambda v: f"${v / 1e9:,.1f}bn"), ("roe", "Return on equity", lambda v: pct(v)),
            ("net_margin", "Net margin", lambda v: pct(v)), ("eps_ttm", "Diluted EPS (TTM)", lambda v: num(v)), ("pe_ttm", "Trailing P/E", lambda v: num(v, 1))]
    cmp_ = ctx.get("compare", [])
    ctx["cmp_head"] = [c["source"] for c in cmp_]
    ctx["cmp_rows"] = [[lab] + [fmt(c[k]) if c.get(k) is not None and c.get(k) == c.get(k) else "–" for c in cmp_] for k, lab, fmt in keys]
    ctx["cmp_cites"] = [f"{c['source']}: {c['cite']}" for c in cmp_]
    return ctx
