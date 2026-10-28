import os
import pickle
import time
from typing import Callable

from .config import CACHE_DIR, CACHE_TTL_HOURS


def cached(key: str, fn: Callable, ttl_hours: float = CACHE_TTL_HOURS):
    """Pickle-backed per-key cache; falls back to stale data if the live call fails."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = CACHE_DIR / f"{key.replace('/', '_').replace('^', '_')}.pkl"
    if os.environ.get("EQR_OFFLINE") == "1":
        if path.exists():
            return pickle.loads(path.read_bytes())
        raise RuntimeError(f"offline mode: {key} not cached")
    fresh = path.exists() and time.time() - path.stat().st_mtime < ttl_hours * 3600
    if fresh:
        return pickle.loads(path.read_bytes())
    value, last = None, None
    for attempt in range(3):
        try:
            value = fn()
            break
        except Exception as e:
            last = e
            if "RateLimit" not in type(e).__name__ and "Too Many" not in str(e):
                break  # only rate limits are worth waiting for
            time.sleep(5 * (attempt + 1) ** 2)
    else:
        value = None
    if value is None and last is not None:
        if path.exists():
            return pickle.loads(path.read_bytes())
        raise last
    path.write_bytes(pickle.dumps(value))
    return value
