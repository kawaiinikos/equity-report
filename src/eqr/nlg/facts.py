def build_facts(d: dict, scores: dict, avg, outlook: str, risk: dict, mom: dict, raw: dict) -> dict:
    info = d["info"]
    return {
        "name": info.get("longName", d["ticker"]), "avg_score": avg, "outlook": outlook,
        "scores": {k: v for k, v in scores.items() if not k.startswith("pillar")},
        "beta": risk["beta"], "volatility": risk["volatility_ann"], "rsi_50": mom["rsi_50"],
        "trailing_pe": info.get("trailingPE"), "forward_pe": info.get("forwardPE"), **raw,
    }
