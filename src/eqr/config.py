import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]


def _load_env(path: Path = ROOT / ".env") -> None:
    """KEY=value lines from .env (never committed) into os.environ, without overriding real environment variables."""
    import os
    if path.exists():
        for line in path.read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
CACHE_DIR = ROOT / "data" / "cache"
CACHE_TTL_HOURS = 24
MARKET_INDEX = "^GSPC"
DJIA = "^DJI"
