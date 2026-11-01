"""Scorecard blocks for every component page: 3-year score history chart, peer trend table (-6M..Current + 1Y sparkline),
Score Averages (group / sector / large cap / S&P 500) and the indicator gauges.

History method: Risk and Price Momentum are re-ranked weekly against the S&P 500 sector cohort using prices up to each
date; Earnings and Insider Trading are rebuilt as of each date from dated events (surprises, broker up/downgrades,
open-market insider trades); Fundamental and Relative Valuation are held at their current value (no point-in-time
statements for the whole universe)."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from . import asof
from .cache import cached
from .charts.gauge import gauge
from .charts.price import score_area, sparkline
from .config import ROOT
from .quant import events as EV
from .quant import history as H
from .quant import scoring, spec

PRICES_10Y = ROOT / "data" / "universe_prices_10y.parquet"
PRICES_2Y = ROOT / "data" / "universe_prices.parquet"
N_PEERS = 5
WEEKS = 160  # 3 years + 4-week MA warm-up
COMPS = ["average", "earnings", "fundamental", "relative_valuation", "risk", "price_momentum", "insider_trading"]


def universe_prices() -> pd.DataFrame:
    p = pd.read_parquet(PRICES_10Y if PRICES_10Y.exists() else PRICES_2Y).astype(float)
    p.index = pd.to_datetime(p.index)
    if asof.as_of() is not None:
        p = p[p.index < asof.as_of()]
    return p


def seasonality_now(tk: str, own: pd.Series) -> pd.Series:
    """10-year average return of the current calendar month for every universe ticker plus the target."""
    p = universe_prices()
    p[tk] = own.reindex(p.index).ffill() if tk not in p else p[tk]
    return H.seasonality_at(H.monthly_returns(p), asof.today())


def _fetch(sym: str) -> dict:
    """Yahoo earnings dates, broker actions and insider trades for a ticker missing from the market events file."""
    import yfinance as yf
    from .quant.insiders import open_market
    t = yf.Ticker(sym)
    out = {}
    for k, fn in {"earnings_dates": lambda: t.get_earnings_dates(limit=16), "up_down": lambda: t.upgrades_downgrades,
                  "insider_tx": lambda: t.insider_transactions}.items():
        try:
            out[k] = asof.cut_estimates(k, cached(f"{sym}_{k}", fn))
        except Exception:
            out[k] = None
    om = open_market(out["insider_tx"], float("nan")) if out["insider_tx"] is not None else None
    return EV.from_sources(sym, out["earnings_dates"], out["up_down"], om)


def _rows(series: dict[str, pd.Series], target: str):
    rows = []
    for sym, s in series.items():
        sm = H.smooth(s)
        snap = H.snapshots(sm)
        fmt = lambda v: "NR" if v is None or v != v else f"{v:.0f}"
        rows.append({"ticker": sym, "target": sym == target, "vals": [fmt(snap[k]) for k in ("-6M", "-3M", "-1M", "-1W", "Current")],
                     "spark": sparkline(sm.dropna().iloc[-52:].values)})
    return rows


def _mean(v):
    ok = [x for x in v if x is not None and x == x]
    return float(np.mean(ok)) if ok else None


def build(d: dict, internal: dict, scores: dict, target_events: pd.DataFrame | None = None, target_earn: dict | None = None) -> dict:
    try:
        return _build(d, internal, scores, target_events, target_earn)
    except Exception as e:  # scorecard blocks are additive; never sink the report
        import traceback
        traceback.print_exc()
        return {"trend_error": f"{type(e).__name__}: {e}"}


def _build(d, internal, scores, target_events, target_earn):
    uni, target, peers = internal["uni"], internal["target"], internal["peers"].head(N_PEERS)
    tk, today = d["ticker"], asof.today()
    sector = pd.concat([uni.set_index("ticker")["sector"], pd.Series({tk: target["sector"]})])
    sector = sector[~sector.index.duplicated(keep="last")]

    close = universe_prices()
    close[tk] = d["prices"]["Close"].reindex(close.index).ffill()
    close = close.loc[:, close.columns.isin(sector.index)]
    mkt = d["market"]["Close"].reindex(close.index).ffill()
    dates = H.weekly_index(close.index, min_rows=260)[-WEEKS:]
    window = close[close.index >= dates[0] - pd.Timedelta(days=420)]
    risk_p = H.price_component_history(window, mkt.reindex(window.index), sector)["risk"].reindex(dates)
    mom_p = H.momentum_history(close[close.index >= dates[0] - pd.DateOffset(years=10, days=40)], mkt, sector, dates)
    season = H.seasonality_table(close, sector, tk, today)

    syms = [tk] + list(peers["ticker"])
    market = EV.load_market()
    have = set(market["ticker"]) if len(market) else set()
    missing = [s for s in syms[1:] if s not in have]
    with ThreadPoolExecutor(4) as ex:
        fetched = dict(zip(missing, ex.map(_fetch, missing)))
    ev = {s: market[market["ticker"] == s] if s in have else fetched.get(s, pd.DataFrame(columns=market.columns)) for s in syms[1:]}
    ev[tk] = target_events if target_events is not None else market[market["ticker"] == tk]

    frame = scoring.score_frame(pd.concat([uni[uni["ticker"] != tk], pd.DataFrame([target])], ignore_index=True)).set_index("ticker")
    fs = scoring.factor_scores(pd.concat([uni[uni["ticker"] != tk], pd.DataFrame([target])], ignore_index=True))

    hist = {c: {} for c in COMPS}
    g_earn = {k: {} for k in ("surprises", "estimate_revisions", "recommendation_changes")}
    g_ins = {"short": {}, "long": {}}
    for s in syms:
        e = EV.series(ev[s], dates, "earnings")
        i = EV.series(ev[s], dates, "insider")
        flat = lambda k: scores.get(k) if s == tk else (frame.loc[s, k] if s in frame.index else None)
        c = {"earnings": e, "insider_trading": i, "fundamental": flat("fundamental"), "relative_valuation": flat("relative_valuation"),
             "risk": risk_p[s] if s in risk_p else None, "price_momentum": mom_p[s] if s in mom_p else None}
        for k in COMPS[1:]:
            v = c[k]
            hist[k][s] = v if isinstance(v, pd.Series) else pd.Series(np.nan if v is None else float(v), index=dates)
        hist["average"][s] = H.average_history(c, dates)
        ef = target_earn if (s == tk and target_earn) else EV.earnings_at(ev[s], today)[1]
        for k in g_earn:
            g_earn[k][s] = ef.get(k)
        _, g_ins["short"][s], g_ins["long"][s] = EV.insider_at(ev[s], today)

    # Score Averages: peer group, sector, top-100 market cap and S&P 500, every component as of the cut-off
    mk = EV.market_scores(market, today) if len(market) else pd.DataFrame(columns=["earnings", "insider_trading"])
    allc = frame[["fundamental", "relative_valuation", "risk", "price_momentum"]].join(mk, how="left")
    have_n = allc.notna().sum(axis=1)
    allc["average"] = allc.mean(axis=1).where(have_n >= spec.MIN_COMPONENTS_FOR_AVERAGE)
    meta = pd.concat([uni.set_index("ticker")[["sector", "market_cap"]],
                      pd.DataFrame({"sector": [target["sector"]], "market_cap": [target["market_cap"]]}, index=[tk])])
    meta = meta[~meta.index.duplicated(keep="last")].join(allc, how="inner")
    in_sector, large = meta[meta["sector"] == target["sector"]], meta.nlargest(100, "market_cap")
    fmt1 = lambda v: "n/a" if v is None or v != v else f"{v:.1f}"

    blocks = {}
    for k in COMPS:
        cur = [H.snapshots(H.smooth(hist[k][s]))["Current"] for s in syms]
        mk_ok = k not in ("earnings", "insider_trading") or len(mk)
        box = [("Peer group", fmt1(_mean(cur))),
               (f"{target['sector']} sector", fmt1(in_sector[k].mean()) if mk_ok else "n/a"),
               ("Large market cap (top 100)", fmt1(large[k].mean()) if mk_ok else "n/a"),
               ("S&P 500 index", fmt1(meta[k].mean()) if mk_ok else "n/a")]
        blocks[k] = {"rows": _rows(hist[k], tk), "box": box,
                     "chart": score_area(H.smooth(hist[k][tk]).iloc[-156:], w=3.4, h=1.25)}

    sc = lambda col: {s: (None if s not in fs.index or pd.isna(fs.loc[s, col]) else float(fs.loc[s, col])) for s in syms}
    gauges = {
        "earnings": [{"title": t, "weight": "(33.3% weight)", "scores": g_earn[k]} for k, t in
                     (("surprises", "Earnings Surprises"), ("estimate_revisions", "Estimate Revisions"), ("recommendation_changes", "Recommendation Changes"))],
        "fundamental": [{"title": p.replace("_", " ").title(), "weight": "(25% weight)", "scores": sc(p)} for p in scoring.FUND_COLS],
        "relative_valuation": [{"title": t, "weight": "(33.3% weight)", "scores": sc(c)} for c, t in
                               (("price_to_sales", "Price to Sales"), ("trailing_pe", "Trailing P/E"), ("forward_pe", "Forward P/E"))],
        "risk": [{"title": t, "weight": "(25% weight)", "scores": sc(c)} for c, t in
                 (("magnitude_of_returns", "Magnitude of Returns"), ("volatility", "Volatility"), ("beta", "Beta (1-year)"), ("correlation", "Correlation"))],
        "price_momentum": [{"title": "Relative Strength", "weight": "(50% weight)", "scores": sc("relative_strength")},
                           {"title": "Seasonality", "weight": "(50% weight)", "scores": sc("seasonality")}],
        "insider_trading": [{"title": "Short-Term Insider", "weight": "(70% weight)", "scores": g_ins["short"]},
                            {"title": "Long-Term Insider", "weight": "(30% weight)", "scores": g_ins["long"]}],
    }
    for k, v in gauges.items():
        blocks[k]["gauge"] = gauge(v, tk, w=7.4 if len(v) > 2 else 5.4, h=1.95)
    # peer table extras: average score and 1-year return for target + all peers; risk analysis table; sector RSI averages
    all_peers = [tk] + list(internal["peers"]["ticker"])
    px_all = close
    ret1y = (px_all.iloc[-1] / px_all.iloc[-253] - 1) if len(px_all) > 253 else pd.Series(dtype=float)
    peer_info = {s: {"avg": allc["average"].get(s, np.nan) if s != tk else np.nan, "ret_1y": float(ret1y.get(s, np.nan))} for s in all_peers}
    risk_tbl = []
    for s in syms + ["^GSPC"]:
        src = px_all[s] if s in px_all else (mkt if s == "^GSPC" else None)
        if s == "^GSPC":
            src = mkt
        if src is None:
            continue
        dd = src.pct_change().dropna().iloc[-90:]
        mo = src.resample("ME").last().pct_change().dropna().iloc[-60:]
        risk_tbl.append({"ticker": "S&P 500" if s == "^GSPC" else s, "target": s == tk, "best_d": dd.max(), "worst_d": dd.min(),
                         "up": int((dd > 0).sum()), "down": int((dd < 0).sum()), "best_m": mo.max(), "worst_m": mo.min()})
    sec_rows = uni[uni["sector"] == target["sector"]]
    rsi_sector = {c: float(sec_rows[c].mean()) for c in ("rsi_10", "rsi_50", "rsi_200") if c in sec_rows}
    return {"blocks": blocks, "season_rank": season, "peer_info": peer_info, "risk_table": risk_tbl, "rsi_sector": rsi_sector, "market_events_n": int(market["ticker"].nunique()) if len(market) else 0,
            "history_years": round((dates[-1] - dates[0]).days / 365.25, 1)}
