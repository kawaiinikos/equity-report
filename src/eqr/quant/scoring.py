"""Decile scoring (1-10, 10 = best). The target is appended to the universe so every score is a rank within one frame."""
import numpy as np
import pandas as pd

from . import spec

MIN_COHORT = 30
HIGHER_BETTER_RISK = False  # all four risk factors: lower = better

FUND_COLS = {p: list(r) for p, r in spec.FUNDAMENTAL_PILLARS.items()}
RISK_COLS = list(spec.RISK)
VAL_COLS = list(spec.RELATIVE_VALUATION)
RS_COLS = ["rsi_10", "rsi_50", "rsi_200", "ret_3m"]


def _pct_rank(df: pd.DataFrame, col: str, lower_better: bool) -> pd.Series:
    """Percentile rank within sector cohort (whole universe if cohort < MIN_COHORT); NaN stays NaN."""
    s = df[col].replace([np.inf, -np.inf], np.nan)
    if col in ("trailing_pe", "forward_pe", "price_to_sales"):
        s = s.where(s > 0)  # loss-making / meaningless multiples are unranked
    out = pd.Series(np.nan, index=df.index)
    for _, idx in df.groupby("sector").groups.items():
        cohort = s.loc[idx] if s.loc[idx].notna().sum() >= MIN_COHORT else s
        r = cohort.rank(pct=True, ascending=not lower_better)  # best value -> highest pct
        out.loc[idx] = r.reindex(idx).values
    return out


def _decile(p: pd.Series) -> pd.Series:
    return np.ceil(p * 10).clip(1, 10)


def _to_score(composite: pd.Series) -> pd.Series:
    """Re-rank a composite across the universe into deciles."""
    return _decile(composite.rank(pct=True))


def score_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    d = {c: _decile(_pct_rank(df, c, c in spec.LOWER_IS_BETTER)) for cols in FUND_COLS.values() for c in cols}
    pillars = pd.DataFrame({p: pd.concat([d[c] for c in cols], axis=1).mean(axis=1, skipna=True) for p, cols in FUND_COLS.items()})
    ok = pillars.notna().sum(axis=1) >= spec.MIN_FUNDAMENTAL_PILLARS
    out = df[["ticker"]].copy()
    out["fundamental"] = _to_score(pillars.mean(axis=1).where(ok))  # equal 25% weights, renormalised over present pillars

    val = pd.concat([_decile(_pct_rank(df, c, True)) for c in VAL_COLS], axis=1)
    out["relative_valuation"] = _to_score(val.mean(axis=1).where(val.notna().any(axis=1)))

    risk = pd.concat([_decile(_pct_rank(df, c, True)) for c in RISK_COLS], axis=1)
    out["risk"] = _to_score(risk.mean(axis=1).where(risk.notna().sum(axis=1) >= spec.MIN_RISK_FACTORS))

    rs = pd.concat([_decile(_pct_rank(df, c, False)) for c in RS_COLS], axis=1)
    out["price_momentum"] = _to_score(rs.mean(axis=1))  # relative strength only; seasonality added when 10Y history is cached
    return out.join(pillars.add_prefix("pillar_"))


def score_target(universe: pd.DataFrame, target_row: dict) -> dict:
    t = target_row["ticker"]
    base = universe[universe["ticker"] != t]
    scores = score_frame(pd.concat([base, pd.DataFrame([target_row])], ignore_index=True))
    row = scores[scores["ticker"] == t].iloc[0].to_dict()
    row.pop("ticker")
    return {k: (None if pd.isna(v) else float(v)) for k, v in row.items()}


# Our approximation: LSEG's Verus factor blend by market cap is proprietary.
OPTIMIZED_WEIGHTS = {"earnings": .20, "fundamental": .20, "relative_valuation": .15, "risk": .15, "price_momentum": .20, "insider_trading": .10}


def average_and_optimized(comp: dict) -> tuple[float | None, float | None]:
    have = {k: v for k, v in comp.items() if k in spec.COMPONENTS and v is not None}
    if not have:
        return None, None
    avg = sum(have.values()) / len(have)
    w = sum(OPTIMIZED_WEIGHTS[k] for k in have)
    return avg, sum(OPTIMIZED_WEIGHTS[k] * v for k, v in have.items()) / w


def outlook(score: float | None) -> str:
    if score is None:
        return "NR"
    lo, hi = spec.SCORE_BANDS["positive"][0], spec.SCORE_BANDS["neutral"][0]
    return "Positive" if score >= lo else "Neutral" if score >= hi else "Negative"
