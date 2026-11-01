import pandas as pd

from eqr.quant import anomalies
from eqr.quant import events as EV
from eqr.quant.valuation import history


def _stmts(unusual_q):
    cols = pd.to_datetime(["2026-06-30", "2026-03-31", "2025-12-31", "2025-09-30"])
    q = pd.DataFrame({c: {"Pretax Income": 10.0 + u, "Total Unusual Items": u, "Gain On Sale Of Security": u,
                          "Net Income Common Stockholders": 8.0 + u, "Normalized Income": 8.0, "Total Revenue": 40.0,
                          "Diluted EPS": 1.0 + u / 10, "Diluted Average Shares": 10.0} for c, u in zip(cols, unusual_q)})
    a = q.iloc[:, :1].copy()
    return {"q_income": q, "a_income": a, "q_balance": pd.DataFrame({cols[0]: {"Stockholders Equity": 50.0, "Total Assets": 100.0}}),
            "a_balance": pd.DataFrame(), "q_cash": pd.DataFrame(), "a_cash": pd.DataFrame()}


def _d(stmts):
    px = pd.Series(100.0, index=pd.bdate_range("2025-01-01", "2026-10-14"))
    return {"ticker": "TST", "statements": stmts, "info": {"trailingPE": 10.0, "forwardPE": 25.0}, "prices": pd.DataFrame({"Close": px})}


def test_one_off_gain_explained():
    notes = anomalies.detect(_d(_stmts([20.0, 0, 0, 0])), {}, {})
    assert notes["fundamental"] and "investments" in notes["fundamental"][0]
    assert any("normalized" in n for n in notes["valuation"])


def test_clean_company_gets_no_notes():
    notes = anomalies.detect(_d(_stmts([0, 0, 0, 0])), {}, {})
    assert not notes["fundamental"] and not notes["overview"]


def test_trailing_pe_line_ends_at_current():
    st = _stmts([0, 0, 0, 0])
    px = pd.Series(100.0, index=pd.bdate_range("2021-01-01", "2026-10-14"))
    h = history(px, st)["trailing_pe"]
    assert abs(h.iloc[-1] - 100.0 / 4.0) < 1e-9  # latest close / TTM EPS (4 quarters x 1.0)


def test_event_scores():
    ev = pd.DataFrame({"ticker": "X", "kind": ["surprise"] * 4 + ["rec", "rec", "insider"],
                       "date": pd.to_datetime(["2026-01-30", "2026-04-30", "2026-07-30", "2025-10-30", "2026-09-01", "2026-09-15", "2026-09-20"]),
                       "value": [0.05, 0.05, 0.05, 0.05, 1, 1, -1e6]})
    score, f = EV.earnings_at(ev, pd.Timestamp("2026-10-15"))
    assert f["recommendation_changes"] == 10 and score >= 8
    s, st_, lt = EV.insider_at(ev, pd.Timestamp("2026-10-15"))
    assert st_ == 2 and s == 2


def test_restated_quarter_flagged():
    ed = pd.DataFrame({"EPS Estimate": [5.07, 4.64, 1.82], "Reported EPS": [5.18, 4.90, 1.95]},
                      index=pd.to_datetime(["2026-01-29", "2026-04-23", "2026-07-23"]))
    notes = anomalies.restated_quarters(ed)
    assert len(notes) == 1 and "2026-07-23" in notes[0]
    assert not anomalies.restated_quarters(ed.iloc[:2])
