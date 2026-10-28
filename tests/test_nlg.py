from eqr.nlg.generate import template_highlights
from eqr.nlg.validate import ungrounded_numbers

FACTS = {"name": "X Corp", "avg_score": 6.2, "outlook": "Neutral", "scores": {"risk": 7.0, "fundamental": 3.0},
         "price_target_mean": 253.91, "price_target_upside": 0.1604, "consensus": "Buy", "surprise_pos4": 4, "beta": 0.6955, "volatility": 0.2597}


def test_template_is_grounded():
    assert not [b for t in template_highlights(FACTS) for b in ungrounded_numbers(t, FACTS)]


def test_invented_number_is_caught():
    assert ungrounded_numbers("Revenue grew 37.5% last year.", FACTS) == ["37.5"]
