import numpy as np
import pandas as pd


def _beta_corr(r: pd.Series, m: pd.Series) -> tuple[float, float]:
    j = pd.concat([r, m], axis=1).dropna()
    if len(j) < 20:
        return np.nan, np.nan
    cov = np.cov(j.iloc[:, 0], j.iloc[:, 1])
    return cov[0, 1] / cov[1, 1], j.iloc[:, 0].corr(j.iloc[:, 1])


def risk_stats(px: pd.Series, mkt: pd.Series) -> dict:
    """Daily stats over 90 days, monthly stats over 60 months, beta/corr vs index (1Y daily)."""
    d = px.pct_change().dropna()
    md = mkt.pct_change().dropna()
    d90 = d.iloc[-90:]
    mo = px.resample("ME").last().pct_change().dropna().iloc[-60:]
    mmo = mkt.resample("ME").last().pct_change().dropna().iloc[-60:]
    d1y, m1y = d.iloc[-252:], md.iloc[-252:]
    out = {
        "best_day_90d": d90.max(), "worst_day_90d": d90.min(),
        "std_daily_90d": d90.std(), "avg_daily_90d": d90.mean(),
        "best_month_60m": mo.max(), "worst_month_60m": mo.min(),
        "std_monthly_60m": mo.std(), "avg_monthly_60m": mo.mean(),
        "volatility_ann": d1y.std() * np.sqrt(252),
    }
    out["beta"], out["corr"] = _beta_corr(d1y, m1y)
    j = pd.concat([d1y, m1y], axis=1).dropna()
    pos, neg = j[j.iloc[:, 1] > 0], j[j.iloc[:, 1] < 0]
    out["beta_pos"], out["corr_pos"] = _beta_corr(pos.iloc[:, 0], pos.iloc[:, 1])
    out["beta_neg"], out["corr_neg"] = _beta_corr(neg.iloc[:, 0], neg.iloc[:, 1])
    out["beta_monthly_60m"], out["corr_monthly_60m"] = _beta_corr(mo, mmo)
    return {k: float(v) for k, v in out.items()}
