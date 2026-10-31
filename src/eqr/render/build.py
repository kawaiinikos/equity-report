from .. import asof
from pathlib import Path

import jinja2
import weasyprint

from ..quant.spec import FUNDAMENTAL_PILLARS

HERE = Path(__file__).parent
pct = lambda v, d=1: "n/a" if v != v else f"{v*100:.{d}f}%"
num = lambda v, d=2: "n/a" if v != v else f"{v:,.{d}f}"


def build_context(d, ratios, risk, mom, charts, extra=None) -> dict:
    info, px = d["info"], d["prices"]["Close"]
    ret = lambda days: px.iloc[-1] / px.iloc[-days - 1] - 1
    key_stats = [
        ("Last Close", num(px.iloc[-1])), ("52W High", num(info.get("fiftyTwoWeekHigh", float("nan")))),
        ("52W Low", num(info.get("fiftyTwoWeekLow", float("nan")))),
        ("Trailing P/E", num(info.get("trailingPE", float("nan")), 1)), ("Forward P/E", num(info.get("forwardPE", float("nan")), 1)),
        ("Div Yield", pct(ratios["dividend_yield"], 2)),
        ("ROE", pct(info.get("returnOnEquity", float("nan")))),
        ("Mkt Cap (B)", num((info.get("marketCap") or float("nan")) / 1e9, 1)),
        ("Inst. Own", pct(info.get("heldPercentInstitutions", float("nan")))),
        ("1M Return", pct(ret(21))), ("3M Return", pct(ret(63))),
    ]
    fmt = {"pct": pct, "num": num}
    pct_keys = {"revenue_growth", "gross_margin", "return_on_equity", "net_margin", "debt_to_capital", "interest_funding",
                "operating_cash_yield", "accruals", "dividend_growth", "dividend_funding", "dividend_yield"}
    fundamental = {
        p.replace("_", " ").title(): [(k.replace("_", " ").title(), f, pct(ratios[k]) if k in pct_keys else num(ratios[k]))
                                      for k, f in rows.items()]
        for p, rows in FUNDAMENTAL_PILLARS.items()
    }
    r = risk
    risk_rows = [
        ("Best day (90d)", pct(r["best_day_90d"])), ("Worst day (90d)", pct(r["worst_day_90d"])),
        ("Std. dev. daily (90d)", pct(r["std_daily_90d"], 2)), ("Best month (60m)", pct(r["best_month_60m"])),
        ("Worst month (60m)", pct(r["worst_month_60m"])), ("Std. dev. monthly (60m)", pct(r["std_monthly_60m"])),
        ("Annualised volatility (1Y)", pct(r["volatility_ann"])),
        ("Beta vs S&P 500 (1Y)", num(r["beta"])), ("Beta – positive days", num(r["beta_pos"])), ("Beta – negative days", num(r["beta_neg"])),
        ("Correlation (1Y)", num(r["corr"])), ("Correlation – positive days", num(r["corr_pos"])), ("Correlation – negative days", num(r["corr_neg"])),
        ("Beta (60m monthly)", num(r["beta_monthly_60m"])),
    ]
    m = mom
    mom_rows = [("RSI 10-day", num(m["rsi_10"], 1)), ("RSI 50-day", num(m["rsi_50"], 1)), ("RSI 200-day", num(m["rsi_200"], 1)),
                ("50-day moving average", num(m["sma_50"])), ("200-day moving average", num(m["sma_200"]))]
    s = m["seasonality"]
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    return {
        "name": info.get("longName", d["ticker"]), "ticker": d["ticker"], "sector": info.get("industry", info.get("sector", "")),
        "date": asof.today().date().isoformat(), "key_stats": key_stats, "summary": info.get("longBusinessSummary", ""),
        "fundamental": fundamental, "risk": risk_rows, "momentum": mom_rows,
        "season_months": months, "season_avg": [pct(s["avg_return"].get(i, float("nan"))) for i in range(1, 13)],
        "season_pos": [pct(s["pct_positive"].get(i, float("nan")), 0) for i in range(1, 13)], **charts, **(extra or {}),
    }


def render_pdf(context: dict, out: Path) -> Path:
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(HERE / "templates"), autoescape=True)
    html = env.get_template("report.html.j2").render(c=context, css=(HERE / "base.css").read_text())
    out.parent.mkdir(parents=True, exist_ok=True)
    weasyprint.HTML(string=html).write_pdf(out)
    return out


def peer_rows(target: dict, peers) -> tuple[list, list]:
    """Rows for the peer table (target first, then peers, then average) and for the peer risk table."""
    import pandas as pd
    df = pd.concat([pd.DataFrame([target]), peers], ignore_index=True)
    cols = ["ticker", "price", "ret_1m", "ret_3m", "market_cap", "trailing_pe", "forward_pe", "dividend_yield", "net_margin"]
    f = [lambda v: v, num, pct, pct, lambda v: num(v / 1e9, 1), lambda v: num(v, 1), lambda v: num(v, 1), lambda v: pct(v, 2), pct]
    def fmt(row):
        return [fn(row[c]) if c == "ticker" or row[c] == row[c] and row[c] is not None else "n/a" for c, fn in zip(cols, f)]
    avg = df.iloc[1:][cols[1:]].astype(float).median()
    avg_row = ["Peer median"] + [fn(avg[c]) if avg[c] == avg[c] else "n/a" for c, fn in zip(cols[1:], f[1:])]
    risk_cols = ["ticker", "volatility", "beta", "correlation", "magnitude_of_returns"]
    rf = [lambda v: v, pct, num, num, pct]
    risk = [[fn(r[c]) if c == "ticker" or r[c] == r[c] else "n/a" for c, fn in zip(risk_cols, rf)] for _, r in df.iterrows()]
    return [fmt(r) for _, r in df.iterrows()] + [avg_row], risk
