import numpy as np
import pandas as pd

from eqr.collectors.sec import _business_lines
from eqr.quant import similarity as S


def test_business_text_ranks_same_business_first():
    docs = {"T": "Aircraft engines, avionics and defense electronics for commercial aviation",
            "A": "Commercial aviation avionics and aircraft engine aftermarket services and defense systems",
            "B": "Retail grocery stores selling food and household goods"}
    s = S.business(docs, "T")
    assert s["A"] > s["B"]


def test_revenue_mix_weights_by_revenue_share():
    lines = {"T": {"Aerospace": 90, "Building Automation": 10},
             "A": {"Aerospace": 80, "Retail": 20},
             "B": {"Building Automation": 90, "Aerospace": 10}}
    s = S.revenue_mix(lines, "T")
    assert s["A"] > s["B"]  # the big aerospace line dominates the mix


def test_returns_removes_market_move():
    idx = pd.bdate_range("2023-01-02", periods=600)
    rng = np.random.default_rng(0)
    mkt, ind = rng.normal(0, .01, 600), rng.normal(0, .01, 600)
    px = pd.DataFrame({k: 100 * np.exp(np.cumsum(mkt + w * ind + rng.normal(0, .005, 600)))
                       for k, w in {"T": 1, "A": 1, "B": 0, "C": 0, "D": -1}.items()}, index=idx)
    s = S.returns(px, "T")
    assert s["A"] > 0.5 and s["A"] > s["B"]


def test_blend_renormalises_missing_signal():
    sig = {"business": pd.Series({"A": .9, "B": .1}), "revenue_mix": pd.Series({"A": np.nan, "B": .5})}
    out = S.blend(sig, {"business": .5, "revenue_mix": .5})
    assert out.index[0] == "A" and out.loc["A", "similarity"] == 1.0


def test_business_lines_from_xbrl():
    xml = """<xbrl xmlns="http://www.xbrl.org/2003/instance" xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:us-gaap="http://fasb.org/us-gaap/2024">
    <context id="c1"><entity><segment><xbrldi:explicitMember dimension="us-gaap:StatementBusinessSegmentsAxis">x:AerospaceTechnologiesMember</xbrldi:explicitMember></segment></entity><period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
    <context id="c2"><entity><segment><xbrldi:explicitMember dimension="srt:ProductOrServiceAxis">us-gaap:ProductMember</xbrldi:explicitMember></segment></entity><period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
    <context id="c3"><entity><segment><xbrldi:explicitMember dimension="srt:StatementGeographicalAxis">x:EuropeMember</xbrldi:explicitMember></segment></entity><period><startDate>2025-01-01</startDate><endDate>2025-12-31</endDate></period></context>
    <us-gaap:Revenues contextRef="c1">100</us-gaap:Revenues><us-gaap:Revenues contextRef="c2">60</us-gaap:Revenues><us-gaap:Revenues contextRef="c3">40</us-gaap:Revenues>
    </xbrl>"""
    end, lines = _business_lines(xml, pd.Timestamp("2026-10-15"))
    assert end == "2025-12-31" and lines == {"Aerospace Technologies": 100.0}
