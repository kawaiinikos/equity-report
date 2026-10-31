"""Average Score Trend + Score Averages (page 2) and Earnings Score Trend + Earnings Score Averages (page 3)."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .cache import cached
from .charts.gauge import gauge
from .charts.price import sparkline
from .config import ROOT
from .quant import history as H
from .quant import earnings as E
from .quant import insiders as I
from .quant import scoring, spec
from .render.build import num

PRICES_PATH = ROOT / "data" / "universe_prices.parquet"
N_PEERS = 5
QUANT = ["fundamental", "relative_valuation", "risk", "price_momentum"]


def _fetch(sym: str) -> dict:
    """Earnings dates, broker actions and insider trades for one ticker (cache keys shared with collect_estimates)."""
    import yfinance as yf
    t = yf.Ticker(sym)
    out = {}
    for k, fn in {"earnings_dates": lambda: t.get_earnings_dates(limit=16), "up_down": lambda: t.upgrades_downgrades,
                  "insider_tx": lambda: t.insider_transactions}.items():
        try:
            out[k] = cached(f"{sym}_{k}", fn)
        except Exception:
            out[k] = None
    return out


def _rows(series: dict[str, pd.Series], target: str, decimals=0):
    rows = []
    for sym, s in series.items():
        snap = H.snapshots(H.smooth(s))
        spark = sparkline(H.smooth(s).dropna().iloc[-52:].values)
        fmt = lambda v: "NR" if v is None or v != v else f"{v:.{decimals}f}"
        rows.append({"ticker": sym, "target": sym == target, "vals": [fmt(snap[k]) for k in ("-6M", "-3M", "-1M", "-1W", "Current")], "spark": spark})
    return rows


def build(d: dict, internal: dict, scores: dict, target_earn: dict | None = None) -> dict:
    """Needs data/universe_prices.parquet; returns {} (page blocks hidden) if anything essential is missing."""
    try:
        uni, target, peers = internal["uni"], internal["target"], internal["peers"].head(N_PEERS)
        tk = d["ticker"]
        prices = pd.read_parquet(PRICES_PATH)
        prices.index = pd.to_datetime(prices.index)
        close = prices.copy()
        own = d["prices"]["Close"]
        close[tk] = own.reindex(close.index).ffill()
        mkt = d["market"]["Close"].reindex(close.index).ffill()
        sector = pd.concat([uni.set_index("ticker")["sector"], pd.Series({tk: target["sector"]})])
        sector = sector[~sector.index.duplicated(keep="last")]
        close = close.loc[:, close.columns.isin(sector.index)]

        comp = H.price_component_history(close, mkt, sector)
        dates = H.weekly_index(close.index)
        syms = [tk] + list(peers["ticker"])
        with ThreadPoolExecutor(4) as ex:
            fetched = dict(zip(syms, ex.map(_fetch, syms)))

        frame = scoring.score_frame(pd.concat([uni[uni["ticker"] != tk], pd.DataFrame([target])], ignore_index=True)).set_index("ticker")
        today = pd.Timestamp.today().normalize()
        avg_s, earn_s, cur_comp = {}, {}, {}
        fs = scoring.factor_scores(pd.concat([uni[uni["ticker"] != tk], pd.DataFrame([target])], ignore_index=True))
        g_earn = {k: {} for k in ("surprises", "estimate_revisions", "recommendation_changes")}
        g_ins = {"short": {}, "long": {}}
        for s in syms:
            f = fetched[s]
            e = H.earnings_history(f["earnings_dates"], f["up_down"], dates)
            ins = None
            g_ins["short"][s] = g_ins["long"][s] = None
            if f["insider_tx"] is not None:
                px = float(target["price"] if s == tk else uni.set_index("ticker").loc[s, "price"])
                om = I.open_market(f["insider_tx"], px)
                ins = I.insider_score(om, today)
                g_ins["short"][s], g_ins["long"][s] = I.insider_legs(om, today)
            if s == tk and target_earn is not None:
                ef = target_earn
            else:
                ef = E.earnings_score(E.surprise_summary(E.surprise_table(f["earnings_dates"])), {}, E.rec_change_stats(f["up_down"], today))["factors"]
            for k in g_earn:
                g_earn[k][s] = ef.get(k)
            c = {"earnings": e, "risk": comp["risk"][s].reindex(dates) if s in comp["risk"] else None,
                 "price_momentum": comp["price_momentum"][s].reindex(dates) if s in comp["price_momentum"] else None,
                 "fundamental": scores.get("fundamental") if s == tk else frame.loc[s, "fundamental"],
                 "relative_valuation": scores.get("relative_valuation") if s == tk else frame.loc[s, "relative_valuation"],
                 "insider_trading": ins}
            avg_s[s], earn_s[s] = H.average_history(c, dates), e
            cur_comp[s] = c

        # Score Averages: group = the peer set shown; sector / index from the four rankable components only
        quant = frame[QUANT].mean(axis=1)
        meta = pd.concat([uni.set_index("ticker")[["sector", "market_cap"]],
                          pd.DataFrame({"sector": [target["sector"]], "market_cap": [target["market_cap"]]}, index=[tk])])
        meta = meta[~meta.index.duplicated(keep="last")].join(quant.rename("q"), how="inner")
        cur = {s: H.snapshots(H.smooth(avg_s[s]))["Current"] for s in syms}
        e_cur = {s: H.snapshots(H.smooth(earn_s[s]))["Current"] for s in syms}
        def mean(v):
            ok = [x for x in v if x is not None and x == x]
            return float(np.mean(ok)) if ok else None
        
        avg_box = {"Group (peers shown)": mean(cur.values()), f"{target['sector']} sector (4 quant. components)": float(meta.loc[meta.sector == target["sector"], "q"].mean()),
                   "Large Market Cap (top 100)": float(meta.nlargest(100, "market_cap")["q"].mean()), "S&P 500 Index (4 quant. components)": float(meta["q"].mean())}
        earn_box = {"Group (peers shown)": mean(e_cur.values())}
        sc = lambda col: {s: (None if s not in fs.index or pd.isna(fs.loc[s, col]) else float(fs.loc[s, col])) for s in syms}
        W = lambda n: f"{100 / n:.1f}% weight".replace(".0%", "%")
        gauges = {
            "gauge_earnings": [{"title": t, "weight": "(33.3% weight)", "scores": g_earn[k]} for k, t in
                               (("surprises", "Earnings Surprises"), ("estimate_revisions", "Estimate Revisions"), ("recommendation_changes", "Recommendation Changes"))],
            "gauge_fundamental": [{"title": p.replace("_", " ").title(), "weight": "(25% weight)", "scores": sc(p)} for p in scoring.FUND_COLS],
            "gauge_valuation": [{"title": t, "weight": "(33.3% weight)", "scores": sc(c)} for c, t in (("price_to_sales", "Price to Sales"), ("trailing_pe", "Trailing P/E"), ("forward_pe", "Forward P/E"))],
            "gauge_risk": [{"title": t, "weight": "(25% weight)", "scores": sc(c)} for c, t in (("magnitude_of_returns", "Magnitude of Returns"), ("volatility", "Volatility"), ("beta", "Beta (1-year)"), ("correlation", "Correlation"))],
            "gauge_momentum": [{"title": "Relative Strength", "weight": "(RSI 10/50/200 + 3M return)", "scores": sc("relative_strength")}],
            "gauge_insider": [{"title": "Short-Term Insider", "weight": "(70% weight)", "scores": g_ins["short"]}, {"title": "Long-Term Insider", "weight": "(30% weight)", "scores": g_ins["long"]}],
        }
        gauges = {k: gauge(v, tk, w=7.4 if len(v) > 2 else 4.2 if len(v) == 1 else 5.0) for k, v in gauges.items()}
        risk_s = {s: comp["risk"][s].reindex(dates) for s in syms if s in comp["risk"]}
        mom_s = {s: comp["price_momentum"][s].reindex(dates) for s in syms if s in comp["price_momentum"]}
        fmt1 = lambda v: "n/a" if v is None or v != v else f"{v:.1f}"
        return {
            "avg_trend": _rows(avg_s, tk), "earn_trend": _rows(earn_s, tk), "risk_trend": _rows(risk_s, tk), "mom_trend": _rows(mom_s, tk), **gauges,
            "avg_box": [(k, fmt1(v)) for k, v in avg_box.items()], "earn_box": [(k, fmt1(v)) for k, v in earn_box.items()],
            "trend_n_weeks": int(len(dates)),
        }
    except Exception as e:  # trend blocks are additive; never sink the report
        return {"trend_error": f"{type(e).__name__}: {e}"}
