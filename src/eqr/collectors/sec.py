"""SEC EDGAR (free, no key): Form 4 insider filings and XBRL company facts for US filers.

Fair-access rules: <=10 requests/s and a User-Agent naming the requester. Set SEC_USER_AGENT in .env to
"Your Name your@email"; without it SEC data is skipped."""
import os
import re
import time
import xml.etree.ElementTree as ET

import pandas as pd
import requests

from .. import config  # noqa: F401  (loads .env)
from ..cache import cached

SOURCE = "SEC EDGAR (Form 4 filings, XBRL company facts)"
_last = [0.0]


def _get(url: str, as_json=True):
    wait = 0.12 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    _last[0] = time.time()
    ua = os.environ.get("SEC_USER_AGENT")
    if not ua:
        raise RuntimeError("SEC_USER_AGENT is not set in .env (format: \"Name email@domain\")")
    r = requests.get(url, headers={"User-Agent": ua, "Accept-Encoding": "gzip, deflate"}, timeout=30)
    r.raise_for_status()
    return r.json() if as_json else r.text


def cik(ticker: str) -> str | None:
    m = cached("sec_tickers", lambda: _get("https://www.sec.gov/files/company_tickers.json"), ttl_hours=24 * 7)
    t = ticker.upper().replace("-", ".")
    for v in m.values():
        if v["ticker"].upper() in (t, ticker.upper()):
            return f"{int(v['cik_str']):010d}"
    return None


def _text(node, path):
    x = node.find(path)
    return x.text.strip() if x is not None and x.text else None


def _num(node, path):
    v = _text(node, path)
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _parse_form4(xml: str, filed: str) -> list[dict]:
    root = ET.fromstring(xml)
    owners = []
    for ro in root.findall("reportingOwner"):
        rel = ro.find("reportingOwnerRelationship")
        roles = []
        if rel is not None:
            if _text(rel, "isDirector") in ("1", "true"):
                roles.append("Director")
            if _text(rel, "isOfficer") in ("1", "true"):
                roles.append(_text(rel, "officerTitle") or "Officer")
            if _text(rel, "isTenPercentOwner") in ("1", "true"):
                roles.append("10% Owner")
        owners.append((_text(ro, "reportingOwnerId/rptOwnerName"), ", ".join(roles)))
    name, role = owners[0] if owners else (None, "")
    rows = []
    for t in root.findall("nonDerivativeTable/nonDerivativeTransaction") + root.findall("nonDerivativeTable/nonDerivativeHolding"):
        rows.append({
            "insider": name, "role": role, "filed": filed,
            "date": _text(t, "transactionDate/value") or filed,
            "code": _text(t, "transactionCoding/transactionCode"),
            "shares": _num(t, "transactionAmounts/transactionShares/value"),
            "price": _num(t, "transactionAmounts/transactionPricePerShare/value"),
            "acq_disp": _text(t, "transactionAmounts/transactionAcquiredDisposedCode/value"),
            "owned_after": _num(t, "postTransactionAmounts/sharesOwnedFollowingTransaction/value"),
            "direct": _text(t, "ownershipNature/directOrIndirectOwnership/value"),
            "nature": _text(t, "ownershipNature/natureOfOwnership/value"),
        })
    return rows


def form4(ticker: str, months: int = 36, max_filings: int = 260) -> pd.DataFrame:
    """One row per non-derivative line of every Form 4 filed in the last `months` (cached 24h)."""
    c = cik(ticker)
    if c is None:
        return pd.DataFrame()

    def load():
        sub = _get(f"https://data.sec.gov/submissions/CIK{c}.json")["filings"]["recent"]
        f = pd.DataFrame(sub)
        f = f[(f["form"] == "4") & (pd.to_datetime(f["filingDate"]) >= pd.Timestamp.today() - pd.DateOffset(months=months))]
        rows = []
        for _, x in f.head(max_filings).iterrows():
            doc = x["primaryDocument"].split("/")[-1]  # strip the xsl rendering folder -> raw XML
            url = f"https://www.sec.gov/Archives/edgar/data/{int(c)}/{x['accessionNumber'].replace('-', '')}/{doc}"
            try:
                rows += _parse_form4(_get(url, as_json=False), x["filingDate"])
            except Exception:
                continue
        return pd.DataFrame(rows)

    df = cached(f"{ticker}_sec_form4", load)
    if len(df):
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    return df


def open_market(f4: pd.DataFrame) -> pd.DataFrame:
    """Open-market purchases (code P) and sales (code S) in the same shape as quant.insiders.open_market."""
    if f4 is None or f4.empty:
        return pd.DataFrame(columns=["date", "insider", "position", "side", "shares", "value"])
    d = f4[f4["code"].isin(["P", "S"])].copy()
    d["side"] = d["code"].map({"P": "Buy", "S": "Sell"})
    d["value"] = d["shares"] * d["price"]
    return d.rename(columns={"role": "position"})[["date", "insider", "position", "side", "shares", "value"]].sort_values("date", ascending=False)


def holdings(f4: pd.DataFrame) -> pd.DataFrame:
    """Latest reported holding per insider: direct and indirect (trusts, LLCs, family) shares from their last Form 4."""
    if f4 is None or f4.empty:
        return pd.DataFrame()
    d = f4.dropna(subset=["owned_after"]).sort_values(["date", "filed"])
    d["nature"] = d["nature"].fillna("")
    last = d.groupby(["insider", "direct", "nature"]).tail(1)
    out = last.groupby("insider").apply(lambda g: pd.Series({
        "role": g["role"].iloc[-1],
        "direct": g.loc[g["direct"] == "D", "owned_after"].sum(),
        "indirect": g.loc[g["direct"] == "I", "owned_after"].sum(),
        "as_of": g["date"].max(),
    }), include_groups=False)
    out["total"] = out["direct"] + out["indirect"]
    return out.sort_values("total", ascending=False).reset_index()


FACTS = {  # report item -> us-gaap tags tried in order
    "revenue": ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss"],
    "operating_income": ["OperatingIncomeLoss"],
    "equity": ["StockholdersEquity"],
    "assets": ["Assets"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "dividends_per_share": ["CommonStockDividendsPerShareDeclared", "CommonStockDividendsPerShareCashPaid"],
}


def company_facts(ticker: str) -> dict:
    c = cik(ticker)
    if c is None:
        return {}
    return cached(f"{ticker}_sec_facts", lambda: _get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{c}.json"), ttl_hours=24 * 3)


def _series(facts: dict, tags: list[str], unit: str) -> pd.DataFrame:
    """All facts for the first tag family member that is still reported (latest period end wins)."""
    g = facts.get("facts", {}).get("us-gaap", {})
    best = pd.DataFrame()
    for tag in tags:
        if tag in g and unit in g[tag]["units"]:
            df = pd.DataFrame(g[tag]["units"][unit])
            df["end"], df["filed"] = pd.to_datetime(df["end"]), pd.to_datetime(df["filed"])
            df["start"] = pd.to_datetime(df["start"], errors="coerce") if "start" in df else pd.NaT
            if best.empty or df["end"].max() > best["end"].max():
                best = df
    return best


def _quarters(df: pd.DataFrame) -> pd.Series:
    """Discrete quarterly values by period end: reported 3-month facts, Q4 derived as FY minus the first three quarters."""
    df = df.dropna(subset=["start"]).copy()
    df["days"] = (df["end"] - df["start"]).dt.days
    df = df.sort_values("filed").drop_duplicates(["start", "end"], keep="last")
    q = df[df["days"].between(80, 100)].set_index("end")["val"].astype(float)
    for _, fy in df[df["days"].between(350, 380)].iterrows():
        inside = q[(q.index > fy["start"]) & (q.index < fy["end"] - pd.Timedelta(days=20))]
        if fy["end"] not in q.index and len(inside) == 3:
            q.loc[fy["end"]] = float(fy["val"]) - inside.sum()
    return q.sort_index()


REVENUE_TAGS = {"Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax", "RevenueFromContractWithCustomerIncludingAssessedTax",
                "SalesRevenueNet", "SalesRevenueGoodsNet", "RevenuesNetOfInterestExpense"}
BUSINESS_AXES = {"StatementBusinessSegmentsAxis", "ProductOrServiceAxis"}
NEUTRAL_AXES = {"ConsolidationItemsAxis"}  # allowed alongside a business axis when the member is OperatingSegmentsMember
GENERIC_MEMBERS = {"ProductMember", "ServiceMember", "ProductAndServiceOtherMember", "OperatingSegmentsMember", "SegmentReconcilingItemsMember",
                   "CorporateNonSegmentMember", "IntersegmentEliminationMember", "AllOtherSegmentsMember", "OtherSegmentsMember"}
GEO = ("northamerica", "international", "unitedstates", "europe", "asia", "americas", "emea", "apac", "domestic", "foreign",
       "china", "japan", "restofworld", "latinamerica", "canada", "pacific", "middleeast")


def _business_lines(xml: str, cutoff: pd.Timestamp) -> tuple[str | None, dict]:
    """Revenue per business line (segment and product-line members) for the latest fiscal year in a 10-K XBRL instance."""
    root = ET.fromstring(xml)
    ctx = {}
    for cx in root:
        if not cx.tag.endswith("}context"):
            continue
        mem = tuple((m.get("dimension").split(":")[-1], m.text.split(":")[-1]) for m in cx.iter() if m.tag.endswith("explicitMember"))
        sd = [e.text for e in cx.iter() if e.tag.endswith("startDate")]
        ed = [e.text for e in cx.iter() if e.tag.endswith("endDate")]
        if sd and ed and 330 <= (pd.Timestamp(ed[0]) - pd.Timestamp(sd[0])).days <= 400 and pd.Timestamp(ed[0]) < cutoff:
            ctx[cx.get("id")] = (ed[0], mem)
    lines: dict[str, dict] = {}
    for f in root:
        if f.tag.split("}")[-1] not in REVENUE_TAGS or f.get("contextRef") not in ctx or not (f.text or "").strip():
            continue
        end, mem = ctx[f.get("contextRef")]
        axes = {a for a, _ in mem}
        if not mem or not axes & BUSINESS_AXES or axes - BUSINESS_AXES - NEUTRAL_AXES:
            continue
        if any(a in NEUTRAL_AXES and m != "OperatingSegmentsMember" for a, m in mem):
            continue
        for a, m in mem:  # credit every specific business member on the fact; keep the largest value seen per member
            if a in BUSINESS_AXES and m not in GENERIC_MEMBERS and not any(g in m.lower() for g in GEO):
                d = lines.setdefault(end, {})
                d[m] = max(d.get(m, 0.0), float(f.text))
    if not lines:
        return None, {}
    end = max(lines)
    label = lambda m: re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", re.sub(r"(Segment)?Member$", "", m)).strip()
    return end, {label(m): v for m, v in lines[end].items() if v > 0}


def business_profile(ticker: str, cutoff: pd.Timestamp | None = None) -> dict:
    """SIC industry code and revenue by business line from the latest 10-K filed before `cutoff` (cached 30 days)."""
    c = cik(ticker)
    if c is None:
        return {}
    cutoff = cutoff or pd.Timestamp.today()

    def load():
        s = _get(f"https://data.sec.gov/submissions/CIK{c}.json")
        out = {"sic": s.get("sic"), "sic_desc": s.get("sicDescription"), "fy_end": None, "lines": {}}
        r = s["filings"]["recent"]
        k = [i for i, f in enumerate(r["form"]) if f in ("10-K", "20-F", "40-F") and pd.Timestamp(r["filingDate"][i]) < cutoff]
        if not k:
            return out
        base = f"https://www.sec.gov/Archives/edgar/data/{int(c)}/{r['accessionNumber'][k[0]].replace('-', '')}/"
        inst = [x["name"] for x in _get(base + "index.json")["directory"]["item"] if x["name"].endswith("_htm.xml")]
        if inst:
            out["fy_end"], out["lines"] = _business_lines(_get(base + inst[0], as_json=False), cutoff)
        out["filing"] = base
        return out

    return cached(f"{ticker}_sec_profile_{cutoff:%Y%m%d}", load, ttl_hours=24 * 30)


def ttm_fundamentals(ticker: str, as_of: pd.Timestamp | None = None) -> dict:
    """As filed with the SEC before `as_of`: TTM flows (sum of the last four quarters) and latest balance-sheet values."""
    facts = company_facts(ticker)
    if not facts:
        return {}
    as_of = as_of or pd.Timestamp.today()
    out = {}
    for k, tags in FACTS.items():
        unit = "USD/shares" if k in ("eps_diluted", "dividends_per_share") else "USD"
        df = _series(facts, tags, unit)
        if df.empty:
            continue
        df = df[df["filed"] < as_of]
        if df.empty:
            continue
        if k in ("equity", "assets"):
            last = df.sort_values(["end", "filed"]).iloc[-1]
            out[k], out[f"{k}_end"] = float(last["val"]), last["end"]
            continue
        q = _quarters(df)
        if len(q) >= 4 and (q.index[-1] - q.index[-4]).days < 300:
            out[k], out[f"{k}_end"] = float(q.iloc[-4:].sum()), q.index[-1]
    return out
