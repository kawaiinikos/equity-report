import numpy as np
import pandas as pd

from eqr.quant.momentum import rsi
from eqr.quant.risk import risk_stats


def _series(n=800, seed=0):
    r = np.random.default_rng(seed).normal(0, 0.01, n)
    return pd.Series(100 * np.exp(np.cumsum(r)), index=pd.bdate_range("2023-01-02", periods=n))


def test_rsi_bounds_and_trend():
    up = pd.Series(np.arange(1, 300, dtype=float))
    assert rsi(up, 14) == 100.0
    assert 0 <= rsi(_series(), 10) <= 100


def test_beta_of_market_is_one():
    m = _series()
    s = risk_stats(m, m)
    assert abs(s["beta"] - 1) < 1e-9 and abs(s["corr"] - 1) < 1e-9
