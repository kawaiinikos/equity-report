"""Plain-language notes that explain why a reported number looks unusually high or low.

Every rule reads the same as-of statements the report uses; a note is only emitted when the rule fires, so a clean
company gets no notes. Sections: overview, earnings, fundamental, valuation, risk."""
import numpy as np
import pandas as pd

UNUSUAL_SHARE = 0.20  # unusual items above 20% of pre-tax income distort earnings-based ratios

UNUSUAL_KINDS = [  # (row, plain-language description)
    ("Gain On Sale Of Security", "the revaluation or sale of investments (e.g. equity stakes)"),
    ("Gain On Sale Of Business", "the sale or spin-off of a business"),
    ("Gain On Sale Of Ppe", "the sale of property and equipment"),
    ("Impairment Of Capital Assets", "asset impairments"),
    ("Write Off", "write-offs"),
    ("Restructuring And Mergern Acquisition", "restructuring and M&A costs"),
    ("Special Income Charges", "special items (restructuring, impairments, litigation)"),
]


def _row(df, name):
    if df is None or name not in df.index:
        return pd.Series(dtype=float)
    return df.loc[name].astype(float).dropna()


def _ttm(df, name):
    s = _row(df, name)
    return float(s.iloc[:4].sum()) if len(s) >= 4 else np.nan


def _bn(x):
    return f"${x / 1e9:,.1f}bn" if abs(x) >= 1e9 else f"${x / 1e6:,.0f}m"


def detect(d: dict, ratios: dict, risk: dict, peer_median_pe: float | None = None) -> dict[str, list[str]]:
    st, info = d["statements"], d["info"]
    q, qb = st["q_income"], st["q_balance"]
    name = d["ticker"]
    notes: dict[str, list[str]] = {k: [] for k in ("overview", "earnings", "fundamental", "valuation", "risk")}
    price = float(d["prices"]["Close"].iloc[-1])

    pretax, unusual = _ttm(q, "Pretax Income"), _ttm(q, "Total Unusual Items")
    ni, norm, rev = _ttm(q, "Net Income Common Stockholders"), _ttm(q, "Normalized Income"), _ttm(q, "Total Revenue")
    shares = _row(q, "Diluted Average Shares")
    shares = float(shares.iloc[0]) if len(shares) else np.nan

    # 1. one-off items inside trailing earnings
    if pretax == pretax and unusual == unusual and pretax != 0 and abs(unusual) / abs(pretax) > UNUSUAL_SHARE:
        kinds = []
        for row, desc in UNUSUAL_KINDS:
            v = _ttm(q, row)
            if v == v and abs(v) >= 0.25 * abs(unusual):
                kinds.append((abs(v), desc, v))
        what = max(kinds)[1] if kinds else "non-recurring items"
        sign = "boosted" if unusual > 0 else "depressed"
        q_hit = _row(q, "Total Unusual Items")
        big = q_hit[q_hit.abs() == q_hit.iloc[:4].abs().max()]
        when = f" (mostly in the quarter ending {pd.Timestamp(big.index[0]).strftime('%b %Y')})" if len(big) else ""
        txt = (f"Trailing earnings are {sign} by {_bn(abs(unusual))} of one-off items, mainly from {what}{when}, "
               f"{abs(unusual) / abs(pretax):.0%} of trailing pre-tax income.")
        if norm == norm and rev == rev and rev > 0:
            txt += f" Net margin is {ni / rev:.1%} as reported but {norm / rev:.1%} on Yahoo's normalized income (excluding these items)."
        notes["fundamental"].append(txt)
        if norm == norm and norm > 0 and shares == shares:
            pe_norm = price / (norm / shares)
            pe_rep = info.get("trailingPE")
            rep = f"{pe_rep:.1f}" if pe_rep else "n/a"
            notes["valuation"].append(f"The trailing P/E of {rep} uses reported EPS, which is {sign} by {what}; "
                                      f"on normalized earnings it would be about {pe_norm:.1f}.")
        notes["earnings"].append(f"Reported quarterly EPS includes one-off items from {what}{when}, so it is not comparable with the analysts' "
                                 f"consensus, which excludes such items.")
        notes["overview"].append(txt)

    # 2. discontinued operations / spin-offs
    disc = _ttm(q, "Net Income Discontinuous Operations")
    if disc == disc and ni == ni and ni != 0 and abs(disc) > 0.1 * abs(ni):
        notes["fundamental"].append(f"Trailing net income includes {_bn(disc)} from discontinued operations (a divested or "
                                    f"spun-off business), so year-over-year comparisons mix old and new company perimeters.")

    # 3. ROE distorted by thin or negative equity
    eq, assets = _row(qb, "Stockholders Equity"), _row(qb, "Total Assets")
    roe = ratios.get("return_on_equity")
    if len(eq) and len(assets):
        e, a = float(eq.iloc[0]), float(assets.iloc[0])
        if e <= 0:
            notes["fundamental"].append("Shareholders' equity is negative (typically after large buybacks), so Return on "
                                        "Equity is not meaningful.")
        elif roe is not None and roe == roe and roe > 0.4 and e / a < 0.3:
            notes["fundamental"].append(f"Return on Equity of {roe:.0%} is high partly because book equity is only {e / a:.0%} "
                                        f"of total assets (buybacks, spin-offs or high leverage shrink the denominator).")

    # 4. revenue jumps
    g = ratios.get("revenue_growth")
    if g is not None and g == g and abs(g) > 0.25:
        notes["fundamental"].append(f"Revenue growth of {g:+.0%} is unusually {'high' if g > 0 else 'low'}; check for an "
                                    f"acquisition, divestiture or spin-off in the period.")

    # 5. trailing vs forward P/E gap
    tpe, fpe = info.get("trailingPE"), info.get("forwardPE")
    if tpe and fpe and tpe > 0 and fpe > 0:
        if tpe < 0.6 * fpe:
            notes["valuation"].append(f"Trailing P/E ({tpe:.1f}) is far below forward P/E ({fpe:.1f}): past earnings were "
                                      f"unusually high (often one-off gains) or analysts expect earnings to fall.")
        elif tpe > 1.7 * fpe:
            notes["valuation"].append(f"Trailing P/E ({tpe:.1f}) is far above forward P/E ({fpe:.1f}): past earnings were "
                                      f"depressed (one-off charges) or analysts expect strong earnings growth.")
    if peer_median_pe and not notes["valuation"] and tpe and tpe > 0 and (tpe < 0.4 * peer_median_pe or tpe > 2.5 * peer_median_pe):
        notes["valuation"].append(f"The trailing P/E of {tpe:.1f} differs strongly from the peer median of "
                                  f"{peer_median_pe:.1f}; read the valuation score with the notes above in mind.")

    # 6. dividends
    payout = ratios.get("dividend_funding")
    if payout is not None and payout == payout and payout > 1:
        notes["fundamental"].append(f"Dividends exceed operating cash flow ({payout:.0%}); the payout is being funded from "
                                    f"the balance sheet and may not be sustainable.")

    # 7. risk oddities
    beta = risk.get("beta")
    if beta is not None and beta == beta and beta < 0:
        notes["risk"].append(f"{name} has a negative 1-year beta ({beta:.2f}): it tended to move against the S&P 500 over "
                             f"the past year (common for defensive stocks during sector rotation).")
    return notes
