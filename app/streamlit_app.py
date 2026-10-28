import base64
import os
import sys
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

try:  # Streamlit Cloud: key lives in app Secrets, not in the repo
    if "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass

st.set_page_config(page_title="Equity Research Report Generator", layout="wide")
st.title("Equity Research Report Generator")
st.caption("LSEG Stock Reports Plus-style detailed report · AIFA, Goethe University Frankfurt · academic demo")

with st.sidebar:
    ticker = st.text_input("Ticker", "HON", help="Yahoo Finance symbol, e.g. HON, AAPL, SAP.DE").strip().upper()
    offline = st.checkbox("Offline mode (cached data only)", value=False)
    go = st.button("Generate report", type="primary", use_container_width=True)
    ready = sorted(p.stem.replace("_report", "") for p in (ROOT / "output").glob("*_report.pdf"))
    if ready:
        st.markdown("**Prebuilt:** " + ", ".join(ready))
        preload = st.selectbox("Open prebuilt PDF", [""] + ready)
    else:
        preload = ""

os.environ["EQR_OFFLINE"] = "1" if offline else "0"


def show(pdf: Path, ctx: dict | None):
    if ctx:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Average score", f"{ctx['avg_num']:.1f}" if ctx["avg_num"] is not None else "NR")
        c2.metric("Outlook", ctx["outlook"])
        c3.metric("Optimized score", ctx["opt_score"])
        c4.metric("Consensus", ctx["consensus"].split(" (")[0])
        stats = dict(ctx["key_stats"])
        cols = st.columns(len(stats))
        for col, (k, v) in zip(cols, stats.items()):
            col.metric(k, v)
        left, right = st.columns([1, 2])
        with left:
            comp = {k.replace("_", " ").title(): v for k, v in ctx["raw_scores"].items() if not k.startswith("pillar") and v is not None}
            st.bar_chart(comp, horizontal=True)
        with right:
            st.subheader("Highlights")
            for b in ctx["highlights"]:
                st.write("• " + b)
    data = pdf.read_bytes()
    st.download_button("Download PDF", data, file_name=pdf.name, mime="application/pdf")
    b64 = base64.b64encode(data).decode()
    st.markdown(f'<iframe src="data:application/pdf;base64,{b64}" width="100%" height="900"></iframe>', unsafe_allow_html=True)


if go and ticker:
    from eqr.pipeline import run_full
    try:
        with st.status(f"Building report for {ticker}", expanded=True) as status:
            pdf, ctx = run_full(ticker, progress=lambda m: st.write(m))
            status.update(label="Report ready", state="complete")
        show(pdf, ctx)
    except Exception as e:
        st.error(f"Could not build {ticker}: {type(e).__name__}: {e}")
        fallback = ROOT / "output" / f"{ticker}_report.pdf"
        if fallback.exists():
            st.warning("Showing the prebuilt report instead.")
            show(fallback, None)
elif preload:
    show(ROOT / "output" / f"{preload}_report.pdf", None)
else:
    st.info("Enter a ticker and press **Generate report**.")
