import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache"
CACHE_TTL_HOURS = 24
MARKET_INDEX = "^GSPC"
DJIA = "^DJI"
