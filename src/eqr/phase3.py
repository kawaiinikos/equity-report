"""Pages 3, 4, 10: earnings analysis, EPS/revenue estimates, insiders and holders."""
import numpy as np
import pandas as pd

from . import asof, sources
from .collectors import sec
from .quant import events as EV
from .charts.price import eps_chart, fan_chart, insider_bars, rec_bars
from .collectors.yf import collect_estimates
from .quant import anomalies
from .quant import earnings as E
from .quant import insiders as I
from .render.build import num, pct

NA = float("nan")
LABELS = {"surprises": "Earnings Surprises", "estimate_revisions": "Estimate Revisions", "recommendation_changes": "Recommendation Changes"}


def _g(df, row, col):
    try:
        return float(df.loc[row, col])
    except Exception:
        return NA


def build(d: dict, price: float) -> dict:
    x = collect_estimates(d["ticker"])
    today = asof.today()
    stm = d["statements"]

    tbl = E.surprise_table(x["earnings_dates"])
    summ = E.surprise_summary(tbl)
    rev = E.revision_stats(x["eps_revisions"], x["eps_trend"])
    rc = E.rec_change_stats(x["up_down"], today)
    es = E.earnings_score(summ, rev, rc)

    ins_cite, holdings = "Yahoo Finance insider transactions", None
    om = I.open_market(x["insider_tx"], price)
    if sources.insider_source() == "sec" and sources.status()["sec"][0]:
        try:
            f4 = sec.form4(d["ticker"])
            if len(f4):
                f4 = f4[f4["date"] < today]
                om, holdings, ins_cite = sec.open_market(f4), sec.holdings(f4), "SEC EDGAR Form 4 filings (open-market codes P/S)"
        except Exception:
            pass
    ins_score = I.insider_score(om, today)

    ee, re_, tr = x["earnings_estimate"], x["revenue_estimate"], x["eps_trend"]
    # quarterly EPS: last 4 actual + next 2 consensus
    act = tbl.iloc[:4].iloc[::-1] if len(tbl) else pd.DataFrame()
    q_labels = [i.strftime("%b %y") for i in act.index] + ["Next Q", "Q+2"]
    q_act = list(act["Reported EPS"]) + [NA, NA]
    q_est = [NA] * len(act) + [_g(ee, "0q", "avg"), _g(ee, "+1q", "avg")]
    q_lo = [0] * len(act) + [_g(ee, "0q", "low"), _g(ee, "+1q", "low")]
    q_hi = [0] * len(act) + [_g(ee, "0q", "high"), _g(ee, "+1q", "high")]
    eps_a = stm["a_income"].loc["Diluted EPS"].dropna().sort_index().iloc[-2:] if "Diluted EPS" in stm["a_income"].index else pd.Series(dtype=float)
    a_labels = [f"FY{i.year}" for i in eps_a.index] + ["FY+0", "FY+1"]
    a_act = list(eps_a) + [NA, NA]
    a_est = [NA] * len(eps_a) + [_g(ee, "0y", "avg"), _g(ee, "+1y", "avg")]
    a_lo = [0] * len(eps_a) + [_g(ee, "0y", "low"), _g(ee, "+1y", "low")]
    a_hi = [0] * len(eps_a) + [_g(ee, "0y", "high"), _g(ee, "+1y", "high")]

    names = {"0q": "Current quarter", "+1q": "Next quarter", "0y": "Current year", "+1y": "Next year"}
    trend_rows = []
    for k, n in names.items():
        if tr is not None and k in tr.index:
            c, d30, d90 = tr.loc[k, "current"], tr.loc[k, "30daysAgo"], tr.loc[k, "90daysAgo"]
            trend_rows.append([n, num(c), num(d30), num(d90), pct(c / d90 - 1)])
    est_rows = [[n, num(_g(ee, k, "avg")), num(_g(ee, k, "low")), num(_g(ee, k, "high")), str(int(_g(ee, k, "numberOfAnalysts")) if _g(ee, k, "numberOfAnalysts") == _g(ee, k, "numberOfAnalysts") else "n/a")] for k, n in names.items()]

    an = sources.analyst(d["ticker"], yahoo_x=x)
    rec = {k: an["rec"].get(k, 0) for k in ("Strong Buy", "Buy", "Hold", "Sell", "Strong Sell")} if an.get("rec") else {}
    n_an = sum(rec.values())
    mean_rec = an.get("rec_mean") or (sum(w * v for w, v in zip((1, 2, 3, 4, 5), rec.values())) / n_an if n_an else NA)
    label = "n/a" if n_an == 0 else ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"][int(np.clip(round(mean_rec) - 1, 0, 4))]

    pt = {"mean": an.get("pt_mean"), "high": an.get("pt_high"), "low": an.get("pt_low")}
    if not pt["mean"] and an["source"] != sources.yahoo.SOURCE:  # source without targets: keep Yahoo's, say so
        pt = x["price_targets"] or {}
        an["note"] += " Price targets from Yahoo Finance."
    fan = fan_chart(price, pt["mean"], pt["high"], pt["low"]) if pt.get("mean") else ""
    a_rev = stm["a_income"].loc["Total Revenue"].dropna().sort_index().iloc[-2:] if "Total Revenue" in stm["a_income"].index else pd.Series(dtype=float)
    rev_rows = [[f"FY{i.year} (actual)", num(v / 1e9, 2)] for i, v in a_rev.items()] + \
               [[f"{n} (est.)", num(_g(re_, k, "avg") / 1e9, 2)] for k, n in (("0y", "Current year"), ("+1y", "Next year"))]

    surprise_rows = [[i.strftime("%Y-%m-%d"), num(r["Reported EPS"]), num(r["EPS Estimate"]), pct(r["Surprise"]), r["Category"]] for i, r in tbl.iloc[:6].iterrows()]

    om90 = om[om["date"] >= today - pd.Timedelta(days=90)].head(10)
    recent = [[r["date"].strftime("%Y-%m-%d"), r["insider"].title(), r["position"], r["side"], f"{int(r['shares']):,}", f"${r['value']:,.0f}"] for _, r in om90.iterrows()]
    s6 = I.summary(om, today)
    holders = x["inst_holders"]
    inst = [[r["Holder"], pct(r["pctHeld"], 2), f"{int(r['Shares']):,}", pd.Timestamp(r["Date Reported"]).strftime("%Y-%m-%d")] for _, r in holders.head(5).iterrows()] if holders is not None else []
    ro = x["roster"]
    execs, exec_cite = [], "Yahoo Finance insider roster (direct holdings only)"
    if holdings is not None and len(holdings):
        top = holdings.head(5)
        execs = [[r["insider"].title(), r["role"], f"{int(r['direct']):,}", f"{int(r['indirect']):,}", f"${r['total'] * price:,.0f}", pd.Timestamp(r["as_of"]).strftime("%Y-%m-%d")] for _, r in top.iterrows()]
        exec_cite = "SEC EDGAR Form 4 (shares owned after each insider's latest reported transaction; indirect = trusts, family, LLCs)"
    elif ro is not None and len(ro):
        top = ro.dropna(subset=["Shares Owned Directly"]).sort_values("Shares Owned Directly", ascending=False).head(5)
        execs = [[r["Name"].title(), r["Position"], f"{int(r['Shares Owned Directly']):,}", "n/a", f"${r['Shares Owned Directly'] * price:,.0f}", pd.Timestamp(r["Position Direct Date"]).strftime("%Y-%m-%d")] for _, r in top.iterrows()]

    broker = []
    ud = x["up_down"]
    if ud is not None and len(ud):
        u = ud.copy()
        u.index = pd.to_datetime(u.index).tz_localize(None)
        u = u[u.index >= today - pd.Timedelta(days=120)].sort_index(ascending=False)
        act = {"up": "Upgrade", "down": "Downgrade", "main": "Maintain", "init": "Initiate", "reit": "Reiterate"}
        for dt_, r in u.head(12).iterrows():
            ptxt = ""
            if r.get("currentPriceTarget") and r["currentPriceTarget"] == r["currentPriceTarget"] and r["currentPriceTarget"] > 0:
                prior = r.get("priorPriceTarget")
                ptxt = (f"{prior:,.0f} → " if prior and prior == prior and prior > 0 else "") + f"{r['currentPriceTarget']:,.0f}"
            rating = r["ToGrade"] if not r["FromGrade"] or r["FromGrade"] == r["ToGrade"] else f"{r['FromGrade']} → {r['ToGrade']}"
            broker.append([dt_.strftime("%Y-%m-%d"), r["Firm"], act.get(str(r["Action"]).lower(), r["Action"]), rating, ptxt or "–"])

    f = lambda v: "NR" if v is None else f"{v:.0f}"
    raw = {"price_target_mean": pt.get("mean"), "price_target_upside": (pt["mean"] / price - 1) if pt.get("mean") else None,
           "consensus": label, "surprise_pos4": summ.get("pos4"), "insider_net_shares_6m": s6["net"],
           "ltg": float(x["growth"].loc["LTG", "stockTrend"]) if x.get("growth") is not None and "LTG" in x["growth"].index else NA}
    return {
        "raw": raw, "events": EV.from_sources(d["ticker"], x["earnings_dates"], x["up_down"], om), "scores": {"earnings": es["score"], "insider_trading": ins_score},
        "ctx": {
            "restated_notes": anomalies.restated_quarters(x["earnings_dates"]), "earn_score": f(es["score"]), "earn_factors": [[LABELS[k], f(v)] for k, v in es["factors"].items()],
            "surp_summary": summ, "rev_stats": rev, "rc_stats": rc, "pt": pt,
            "pt_vs_current": pct(pt["mean"] / price - 1) if pt.get("mean") else "n/a", "n_analysts": n_an, "fan_chart": fan,
            "eps_q_chart": eps_chart(q_labels, q_act, q_est, q_lo, q_hi, "Quarterly EPS"),
            "eps_a_chart": eps_chart(a_labels, a_act, a_est, a_lo, a_hi, "Annual EPS"),
            "est_rows": est_rows, "trend_rows": trend_rows, "rec_chart": rec_bars(rec) if rec else "", "rev_rows": rev_rows,
            "surprise_rows": surprise_rows, "consensus": f"{label} ({num(mean_rec, 2)}, {n_an} analysts)" if n_an else "n/a",
            "ins_score": f(ins_score), "ins_recent": recent, "ins_sum": s6, "ins_chart": insider_bars(I.monthly(om, today)),
            "inst_rows": inst, "exec_rows": execs, "exec_cite": exec_cite, "ins_cite": ins_cite, "broker_rows": broker,
            "an_cite": an["source"], "an_note": an.get("note", ""), "mean_rec": mean_rec,
        },
    }
