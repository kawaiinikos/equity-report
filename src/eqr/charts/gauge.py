"""LSEG-style indicator gauges: one vertical positive/neutral/negative band per factor, target and peers placed at their 1-10 score."""
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from .style import NAVY, to_svg

BANDS = [(-0.4, 0.4, "#e0e0e0"), (0.5, 3.5, "#a6a6a6"), (3.5, 7.5, "#f8a880"), (7.5, 10.5, "#f38150")]


def gauge(factors: list[dict], target: str, w=7.4, h=3.0) -> str:
    """factors = [{'title': 'Volatility', 'weight': '25% weight', 'scores': {ticker: score or None}}, ...]"""
    n = len(factors)
    fig, axes = plt.subplots(1, n, figsize=(w, h), sharey=True, squeeze=False)
    fig.subplots_adjust(left=0.1, right=0.96, top=0.8, bottom=0.03, wspace=0.05)
    for k, (ax, f) in enumerate(zip(axes[0], factors)):
        ax.set_xlim(0, 1); ax.set_ylim(-0.7, 11); ax.axis("off")
        for lo, hi, col in BANDS:
            ax.add_patch(Rectangle((0.08, lo), 0.07, hi - lo, color=col, lw=0, zorder=2))
        for y in range(0, 11):
            ax.plot([0.02, 0.98], [y, y], color="#cccccc", ls=":", lw=0.5, zorder=1)
        ax.text(0.5, 12.0, f["title"], ha="center", va="bottom", fontsize=7.5, weight="bold", clip_on=False)
        if f.get("weight"):
            ax.text(0.5, 11.1, f["weight"], ha="center", va="bottom", fontsize=6, color="#555", clip_on=False)
        groups: dict[int, list[str]] = {}
        for t, s in f["scores"].items():
            groups.setdefault(0 if s is None else int(round(s)), []).append(t)
        for s, ts in sorted(groups.items()):
            hit = target in ts
            ax.add_patch(Rectangle((0.15, s - 0.32), 0.1, 0.64, color=NAVY if hit else "#555555", zorder=4))
            ax.text(0.2, s, "NR" if s == 0 else str(s), color="white", fontsize=6, weight="bold", ha="center", va="center", zorder=5)
            ax.plot([0.25, 0.3], [s, s], color="#555555", lw=0.6, zorder=3)
            ts = sorted(ts, key=lambda t: t != target)
            for i, t in enumerate(ts):
                y = s + ((len(ts) - 1) / 2 - i) * 0.55
                ax.plot([0.25, 0.3], [s, y], color="#555555", lw=0.5, zorder=3)
                if t == target:
                    ax.add_patch(Rectangle((0.3, y - 0.25), 0.3, 0.5, color=NAVY, zorder=4))
                    ax.text(0.32, y, t, color="white", fontsize=5.3, weight="bold", ha="left", va="center", zorder=5)
                else:
                    ax.text(0.31, y, t, fontsize=5.3, ha="left", va="center", zorder=5)
        if k == 0:
            for y, lab in ((9, "Positive"), (5.5, "Neutral"), (2, "Negative"), (0, "No Rating")):
                ax.text(-0.02, y, lab, fontsize=6.5, ha="right", va="center", clip_on=False)
        if k == n - 1:
            for y in range(0, 11):
                ax.text(1.0, y, "NR" if y == 0 else str(y), fontsize=5.5, ha="left", va="center", color="#555", clip_on=False)
    return to_svg(fig)
