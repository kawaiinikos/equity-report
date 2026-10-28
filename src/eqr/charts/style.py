import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

NAVY, BLUE, LIGHT, ORANGE, GREY, GREEN, RED = "#0b2a4a", "#1f6fb5", "#9cc3e6", "#f28c28", "#8a97a6", "#2e9d5b", "#c8393b"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8, "axes.edgecolor": GREY, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": "#e3e8ee", "grid.linewidth": 0.6,
})


def to_svg(fig) -> str:
    import io
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    s = buf.getvalue()
    return s[s.index("<svg"):]
