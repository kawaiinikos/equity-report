import numpy as np
import pandas as pd


def rsi(close: pd.Series, n: int) -> float:
    """Wilder RSI over n days."""
    delta = close.diff().dropna()
    up, down = delta.clip(lower=0), -delta.clip(upper=0)
    au = up.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    ad = down.ewm(alpha=1 / n, adjust=False).mean().iloc[-1]
    return float(100 - 100 / (1 + au / ad)) if ad else 100.0


def seasonality(close: pd.Series, years: int = 10) -> pd.DataFrame:
    """Average monthly return per calendar month over the last `years` years."""
    m = close.resample("ME").last().pct_change().dropna()
    m = m[m.index > m.index.max() - pd.DateOffset(years=years)]
    g = m.groupby(m.index.month)
    return pd.DataFrame({"avg_return": g.mean(), "pct_positive": g.apply(lambda s: (s > 0).mean())})


def perf(close: pd.Series) -> dict:
    last, now = close.iloc[-1], close.index[-1]
    def at(delta):
        s = close[close.index <= now - delta]
        return float(last / s.iloc[-1] - 1) if len(s) else np.nan
    ytd = close[close.index < pd.Timestamp(now.year, 1, 1)]
    return {
        "1W": at(pd.Timedelta(days=7)), "1M": at(pd.DateOffset(months=1)),
        "3M": at(pd.DateOffset(months=3)), "6M": at(pd.DateOffset(months=6)),
        "YTD": float(last / ytd.iloc[-1] - 1) if len(ytd) else np.nan,
        "1Y": at(pd.DateOffset(years=1)),
    }


def momentum_stats(close: pd.Series, djia: pd.Series) -> dict:
    return {
        "rsi_10": rsi(close, 10), "rsi_50": rsi(close, 50), "rsi_200": rsi(close, 200),
        "sma_50": float(close.iloc[-50:].mean()), "sma_200": float(close.iloc[-200:].mean()),
        "perf": perf(close), "perf_djia": perf(djia),
        "seasonality": seasonality(close),
    }
