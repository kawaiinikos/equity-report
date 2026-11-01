import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# AIFA Group 5 palette: Frankfurt ink + Main-river teal, amber accents (deliberately not LSEG orange/blue)
INK, TEAL, MINT, AMBER, SLATE, GREEN, CORAL = "#0E1B2C", "#0F8B8D", "#A8DADC", "#F4A259", "#8D99AE", "#2A9D8F", "#E76F51"
NAVY, BLUE, LIGHT, ORANGE, GREY, RED = INK, TEAL, MINT, AMBER, SLATE, CORAL  # legacy names used by older chart code
BAND_NEG, BAND_NEU, BAND_POS, BAND_NR = "#C9D1DB", "#BFE6E2", "#1FA39A", "#ECEFF3"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 7.5, "axes.edgecolor": SLATE, "axes.spines.top": False,
    "axes.spines.right": False, "axes.grid": True, "grid.color": "#E6EAF0", "grid.linewidth": 0.6,
    "axes.labelcolor": INK, "xtick.color": "#4A5568", "ytick.color": "#4A5568", "axes.titlecolor": INK,
})


def to_svg(fig) -> str:
    import io
    buf = io.StringIO()
    fig.savefig(buf, format="svg", bbox_inches="tight")
    plt.close(fig)
    s = buf.getvalue()
    return s[s.index("<svg"):]
