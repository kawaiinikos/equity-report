import matplotlib.dates as mdates
import numpy as np
import matplotlib.pyplot as plt

from .style import BLUE, GREY, GREEN, LIGHT, ORANGE, RED, to_svg


def price_volume(close, volume, monthly=False, w=3.6, h=2.4):
    fig, (ax, av) = plt.subplots(2, 1, figsize=(w, h), sharex=True, gridspec_kw={"height_ratios": [3, 1], "hspace": 0.05})
    ax.plot(close.index, close.values, color=BLUE, lw=1.1)
    ax.fill_between(close.index, close.values, close.values.min(), color=LIGHT, alpha=0.35)
    av.bar(volume.index, volume.values, width=20 if monthly else 1, color=GREY)
    av.yaxis.set_major_formatter(lambda v, _: f"{v/1e6:.0f}M")
    av.xaxis.set_major_formatter(mdates.DateFormatter("%Y" if monthly else "%b %y"))
    return to_svg(fig)


def perf_bars(stock: dict, index: dict, name: str, idx_name="DJIA"):
    keys = ["1W", "1M", "3M", "YTD", "1Y"]
    x = np.arange(len(keys))
    fig, ax = plt.subplots(figsize=(3.6, 2.2))
    ax.bar(x - .2, [stock[k] * 100 for k in keys], .4, color=BLUE, label=name)
    ax.bar(x + .2, [index[k] * 100 for k in keys], .4, color=ORANGE, label=idx_name)
    ax.set_xticks(x, keys); ax.axhline(0, color=GREY, lw=.6); ax.legend(frameon=False, fontsize=7)
    ax.set_ylabel("%")
    return to_svg(fig)


def score_bars(scores: dict):
    from .style import NAVY
    names = {"earnings": "Earnings", "fundamental": "Fundamental", "relative_valuation": "Rel. Valuation",
             "risk": "Risk", "price_momentum": "Price Momentum", "insider_trading": "Insider Trading"}
    vals = [scores.get(k) for k in names]
    fig, ax = plt.subplots(figsize=(3.8, 2.4))
    ax.barh(list(names.values()), [v or 0 for v in vals], color=[BLUE if v else LIGHT for v in vals])
    for i, v in enumerate(vals):
        ax.text((v or 0) + .15, i, f"{v:.0f}" if v else "NR", va="center", fontsize=8, color=NAVY)
    ax.set_xlim(0, 11); ax.invert_yaxis(); ax.grid(axis="y", visible=False)
    return to_svg(fig)


def multiple_history(series, title, avg=None, sp=None, ind=None, current=None):
    fig, ax = plt.subplots(figsize=(3.6, 2.0))
    if len(series):
        ax.plot(series.index, series.values, color=BLUE, lw=1.2, label="Company")
    for v, lab, col in ((avg, "5Y avg (proxy)", ORANGE), (sp, "S&P 500 median", GREY), (ind, "Industry median", GREEN)):
        if v == v and v is not None:
            ax.axhline(v, color=col, ls="--", lw=1, label=lab)
    if len(series) and current is not None and current == current:
        ax.scatter([series.index[-1]], [current], color=RED, zorder=5, s=14, label="Current")
    ax.set_title(title, fontsize=9, loc="left"); ax.legend(frameon=False, fontsize=6, ncol=2)
    return to_svg(fig)


def eps_chart(labels, actual, est, lo=None, hi=None, title=""):
    fig, ax = plt.subplots(figsize=(3.6, 2.0))
    x = np.arange(len(labels))
    ax.bar(x, [a if a == a else 0 for a in actual], .55, color=BLUE, label="Actual")
    est_x = [i for i, e in enumerate(est) if e == e]
    ax.bar(est_x, [est[i] for i in est_x], .55, color=LIGHT, label="Consensus")
    if lo is not None:
        for i in est_x:
            ax.plot([i, i], [lo[i], hi[i]], color=ORANGE, lw=1.4)
    ax.set_xticks(x, labels, fontsize=6.5); ax.set_title(title, fontsize=9, loc="left"); ax.legend(frameon=False, fontsize=6)
    return to_svg(fig)


def fan_chart(current, mean, high, low):
    fig, ax = plt.subplots(figsize=(3.8, 2.3))
    xs = [0, 12]
    ax.fill_between(xs, [current, low], [current, high], color=LIGHT, alpha=.45)
    for v, lab, col in ((high, f"High {high:.0f}", GREEN), (mean, f"Mean {mean:.0f}", BLUE), (low, f"Low {low:.0f}", RED)):
        ax.plot(xs, [current, v], color=col, lw=1.4); ax.text(12.2, v, lab, fontsize=7, va="center", color=col)
    ax.scatter([0], [current], color=ORANGE, zorder=5); ax.text(0, current, f" Current {current:.0f}", fontsize=7, va="bottom")
    ax.set_xlim(-.5, 15); ax.set_xlabel("months ahead")
    return to_svg(fig)


def rec_bars(counts: dict):
    names = ["Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"]
    cols = [GREEN, "#7cc49a", GREY, "#e08a8c", RED]
    fig, ax = plt.subplots(figsize=(3.6, 2.0))
    v = [counts.get(k, 0) for k in names]
    ax.bar(names, v, color=cols)
    for i, n in enumerate(v):
        ax.text(i, n + .2, str(n), ha="center", fontsize=8)
    ax.tick_params(axis="x", labelsize=6.5)
    return to_svg(fig)


def insider_bars(monthly):
    fig, ax = plt.subplots(figsize=(3.8, 2.2))
    x = np.arange(len(monthly))
    ax.bar(x - .2, monthly["Buy"] / 1e6, .4, color=GREEN, label="Buys")
    ax.bar(x + .2, monthly["Sell"] / 1e6, .4, color=RED, label="Sells")
    ax.set_xticks(x, [str(p)[2:] for p in monthly.index], fontsize=6, rotation=45)
    ax.set_ylabel("$ millions"); ax.legend(frameon=False, fontsize=7)
    return to_svg(fig)
