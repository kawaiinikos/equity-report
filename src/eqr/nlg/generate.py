"""Highlights + outlook text. Claude when ANTHROPIC_API_KEY is set; deterministic template otherwise (and on any validation failure)."""
import json
import os

from ..config import ROOT
from .validate import ungrounded_numbers

MODEL = "claude-sonnet-5-5"
SYSTEM = (
    "You write the 'Highlights' of an institutional equity research report in a formal, neutral editorial tone. "
    "Use ONLY the numbers in the provided JSON facts; never invent or compute new figures, never give investment advice. "
    "Return a JSON array of 3 to 5 strings, each one sentence, no markdown."
)


def _load_env():
    f = ROOT / ".env"
    if f.exists() and not os.environ.get("ANTHROPIC_API_KEY"):
        for line in f.read_text().splitlines():
            if line.startswith("ANTHROPIC_API_KEY="):
                os.environ["ANTHROPIC_API_KEY"] = line.split("=", 1)[1].strip()


def template_highlights(f: dict) -> list[str]:
    out = [f"{f['name']} carries an Average Score of {f['avg_score']:.1f} on a 1-10 scale, a {f['outlook'].lower()} outlook relative to the market."]
    comp = {k: v for k, v in f["scores"].items() if v is not None}
    if comp:
        best, worst = max(comp, key=comp.get), min(comp, key=comp.get)
        nm = lambda k: k.replace("_", " ")
        out.append(f"The strongest component is {nm(best)} ({comp[best]:.0f}) and the weakest is {nm(worst)} ({comp[worst]:.0f}).")
    if f.get("price_target_upside") is not None:
        out.append(f"The mean analyst price target of {f['price_target_mean']:.2f} implies {f['price_target_upside']*100:.1f}% versus the last close, with a consensus of {f['consensus']}.")
    if f.get("surprise_pos4") is not None:
        out.append(f"The company beat consensus EPS by more than 2% in {f['surprise_pos4']} of the last 4 quarters.")
    if f.get("beta") is not None:
        out.append(f"Beta versus the S&P 500 is {f['beta']:.2f} with annualised volatility of {f['volatility']*100:.1f}%.")
    return out


def highlights(facts: dict) -> tuple[list[str], str]:
    """Returns (bullets, source) where source is 'claude' or 'template'."""
    _load_env()
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=MODEL, max_tokens=600, system=SYSTEM,
                messages=[{"role": "user", "content": json.dumps(facts, default=float)}])
            bullets = json.loads(msg.content[0].text)
            assert isinstance(bullets, list) and 3 <= len(bullets) <= 5
            if not any(ungrounded_numbers(b, facts) for b in bullets):
                return bullets, "claude"
        except Exception:
            pass
    return template_highlights(facts), "template"
