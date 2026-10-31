"""Average Score Trend + Score Averages (page 2) and Earnings Score Trend + Earnings Score Averages (page 3)."""
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import pandas as pd

from .cache import cached
from .charts.price import sparkline
from .config import ROOT
from .quant import history as H
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


def build(d: dict, internal: dict, scores: dict) -> dict:
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
        for s in syms:
            f = fetched[s]
            e = H.earnings_history(f["earnings_dates"], f["up_down"], dates)
            ins = None
            if f["insider_tx"] is not None:
                px = float(target["price"] if s == tk else uni.set_index("ticker").loc[s, "price"])
                ins = I.insider_score(I.open_market(f["insider_tx"], px), today)
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
        fmt1 = lambda v: "n/a" if v is None or v != v else f"{v:.1f}"
        return {
            "avg_trend": _rows(avg_s, tk), "earn_trend": _rows(earn_s, tk),
            "avg_box": [(k, fmt1(v)) for k, v in avg_box.items()], "earn_box": [(k, fmt1(v)) for k, v in earn_box.items()],
            "trend_n_weeks": int(len(dates)),
        }
    except Exception as e:  # trend blocks are additive; never sink the report
        return {"trend_error": f"{type(e).__name__}: {e}"}
