"""Every number in generated text must trace back to the facts dict (rounding-tolerant, % aware)."""
import re

NUM = re.compile(r"(?<![\w.])-?\d[\d,]*\.?\d*")


def _flatten(x, out):
    if isinstance(x, dict):
        for v in x.values():
            _flatten(v, out)
    elif isinstance(x, (list, tuple)):
        for v in x:
            _flatten(v, out)
    elif isinstance(x, (int, float)) and x == x:
        out.append(float(x))
    return out


def ungrounded_numbers(text: str, facts: dict) -> list[str]:
    vals = _flatten(facts, [])
    bad = []
    for m in NUM.findall(text):
        s = m.replace(",", "")
        try:
            x = float(s)
        except ValueError:
            continue
        dec = len(s.split(".")[1]) if "." in s else 0
        tol = 0.5 * 10 ** -dec + 1e-9
        ok = any(abs(abs(f) - abs(x)) <= tol or abs(abs(f * 100) - abs(x)) <= tol or abs(abs(f / 1e9) - abs(x)) <= tol for f in vals)
        if not ok and abs(x) not in (1, 2, 3, 4, 5, 6, 10, 12, 30, 60, 90, 120, 500):  # structural numbers (scale, windows, "S&P 500")
            bad.append(m)
    return bad
