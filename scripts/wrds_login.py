"""One-time WRDS login. Run in Terminal:  python scripts/wrds_login.py

You type your WRDS password (and approve the Duo push) here; the wrds library stores it in ~/.pgpass so the report
can connect later without asking. Nothing is written into this project folder."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))
from eqr import config  # noqa: F401  (loads .env)

import wrds

user = os.environ.get("WRDS_USERNAME") or input("WRDS username: ").strip()
db = wrds.Connection(wrds_username=user)
db.create_pgpass_file()
print("Connected. Libraries visible to you:", ", ".join(sorted(db.list_libraries())[:40]), "...")
print("ibes access:", "ibes" in db.list_libraries())
print(f"Add this line to .env if it is not there yet:  WRDS_USERNAME={user}")
db.close()
