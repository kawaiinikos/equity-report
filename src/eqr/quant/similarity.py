"""Peer similarity: six signals, each turned into a 0-1 percentile across the candidate universe, then blended.

  business        TF-IDF cosine of the Yahoo business descriptions (what the company says it does)
  revenue_mix     TF-IDF cosine of 10-K business-line names, weighted by each line's revenue share (SEC XBRL)
  returns         correlation of weekly returns over 2 years after removing the market-wide move
  fundamentals    closeness of margin, growth, leverage, working-capital, dividend and risk profiles
  size            market-cap closeness, 1 / (1 + |ln(cap ratio)|)
  classification  same GICS sub-industry / sector, or same SEC SIC code (4, 3 or 2 digits)

A signal missing for a candidate (no 10-K segments, short price history) is left out of that candidate's blend and the
remaining weights are renormalised."""
import json
import math
import re
from collections import Counter

import numpy as np
import pandas as pd

# Chosen with scripts/evaluate_peers.py against LSEG's peer lists for HON and AMZN (4/8 and 3/5 recovered). Revenue mix is
# kept small: 10-K segment names are short and often brand names, so word overlap alone is a noisy signal.
WEIGHTS = {"business": 0.20, "revenue_mix": 0.10, "returns": 0.25, "fundamentals": 0.15, "size": 0.15, "classification": 0.15}
LABELS = {"business": "business description", "revenue_mix": "revenue mix", "returns": "return co-movement",
          "fundamentals": "financial profile", "size": "size", "classification": "industry code"}
FUND_COLS = ["revenue_growth", "gross_margin", "net_margin", "return_on_equity", "debt_to_capital", "current_ratio",
             "days_sales_inventory", "days_sales_receivables", "dividend_yield", "volatility", "beta"]
STOP = set("""the and for with its our are from that this which other also inc corp company corporation companies co ltd plc llc
through including include includes provides provide providing offers offer offering operates operate operating segment segments
segmented business businesses based headquartered founded incorporated formerly known name changed was were has have been
well such into well various range wide worldwide globally global international united states america north south customers customer
products product services service solutions solution under over all both well within across their them they these those than more
one two three four five six seven eight nine ten each per year years new total net member who what where when serves serve serving
sells sell selling markets market""".split())


def _tokens(text: str) -> list[str]:
    words = [w[:-1] if len(w) > 4 and w.endswith("s") and not w.endswith("ss") else w
             for w in re.findall(r"[a-z]{3,}", str(text).lower()) if w not in STOP]
    return words + [f"{a}_{b}" for a, b in zip(words, words[1:])]


def _tfidf(docs: dict[str, Counter], sublinear: bool = True) -> dict[str, dict[str, float]]:
    n = len(docs)
    df = Counter(t for c in docs.values() for t in c)
    idf = {t: math.log((1 + n) / (1 + k)) + 1 for t, k in df.items()}
    out = {}
    for key, c in docs.items():
        v = {t: ((1 + math.log(f)) if sublinear and f >= 1 else f) * idf[t] for t, f in c.items()}
        norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
        out[key] = {t: x / norm for t, x in v.items()}
    return out


def _cosine_to(target: str, vecs: dict[str, dict[str, float]]) -> pd.Series:
    tv = vecs.get(target, {})
    return pd.Series({k: sum(w * tv.get(t, 0.0) for t, w in v.items()) for k, v in vecs.items() if k != target}, dtype=float)


def business(summaries: dict[str, str], target: str) -> pd.Series:
    docs = {k: Counter(_tokens(v)) for k, v in summaries.items() if v}
    return _cosine_to(target, _tfidf(docs)) if target in docs else pd.Series(dtype=float)


def revenue_mix(lines: dict[str, dict], target: str) -> pd.Series:
    """Each business line's words count in proportion to its revenue share (linear, so a 90% line outweighs a 10% one)."""
    docs = {}
    for k, ln in lines.items():
        total = sum(v for v in ln.values() if v > 0)
        if not total:
            continue
        c = Counter()
        for name, rev in ln.items():
            toks = _tokens(name)
            for t in toks:  # split the line's share across its words so long names don't count extra
                c[t] += max(rev, 0) / total / len(toks)
        if c:
            docs[k] = c
    return _cosine_to(target, _tfidf(docs, sublinear=False)) if target in docs else pd.Series(dtype=float)


def returns(prices: pd.DataFrame, target: str, weeks: int = 104) -> pd.Series:
    w = np.log(prices.resample("W-FRI").last()).diff().iloc[-weeks:]
    w = w.loc[:, w.notna().sum() >= weeks * 0.8]
    if target not in w:
        return pd.Series(dtype=float)
    resid = w.sub(w.drop(columns=[target]).mean(axis=1), axis=0)  # strip the common market move
    return resid.drop(columns=[target]).corrwith(resid[target])


def fundamentals(frame: pd.DataFrame, target: str) -> pd.Series:
    cols = [c for c in FUND_COLS if c in frame]
    ranks = frame[cols].astype(float).rank(pct=True)
    diff = (ranks.drop(index=target) - ranks.loc[target]).abs()
    ok = diff.notna().sum(axis=1)
    return (1 - diff.mean(axis=1)).where(ok >= len(cols) // 2)


def size(mcap: pd.Series, target_mcap: float) -> pd.Series:
    r = mcap.astype(float) / target_mcap
    return (1 / (1 + np.log(r.where(r > 0)).abs()))


def classification(meta: pd.DataFrame, target: str) -> pd.Series:
    t = meta.loc[target]
    gics = np.where(meta["industry"] == t["industry"], 1.0, np.where(meta["sector"] == t["sector"], 0.5, 0.0))
    sic = meta["sic"].astype(str).str[:4]
    ts = str(t.get("sic") or "")[:4]
    s = np.zeros(len(meta))
    if ts and ts != "None":
        for n, v in ((2, 0.5), (3, 0.75), (4, 1.0)):
            s = np.where(sic.str[:n] == ts[:n], v, s)
    return pd.Series(np.maximum(gics, s), index=meta.index).drop(index=target)


def blend(signals: dict[str, pd.Series], weights: dict[str, float] = WEIGHTS) -> pd.DataFrame:
    """Percentile-rank each signal over the candidates, weighted mean with renormalisation for missing signals."""
    raw = pd.DataFrame(signals)
    pct = raw.rank(pct=True)
    w = pd.Series({k: weights.get(k, 0.0) for k in raw})
    have = pct.notna().mul(w, axis=1)
    score = pct.fillna(0).mul(w, axis=1).sum(axis=1) / have.sum(axis=1).replace(0, np.nan)
    out = raw.add_prefix("raw_").join(pct).assign(similarity=score)
    out["why"] = pct.apply(lambda r: ", ".join(LABELS[k] for k in r.dropna().sort_values(ascending=False).index[:2]), axis=1)
    return out.sort_values("similarity", ascending=False)


def load_features(path) -> pd.DataFrame:
    f = pd.read_parquet(path).set_index("ticker")
    f["lines"] = f["lines"].map(lambda s: json.loads(s) if isinstance(s, str) else {})
    return f
