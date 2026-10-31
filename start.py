#!/usr/bin/env python3
"""One-file launcher for the Equity Report app (macOS, Windows, Linux).

    python start.py            # first run installs everything (a few minutes), then opens the app in the browser
    python start.py --reinstall  # rebuild the environment from scratch
    python start.py --check      # only verify the setup, do not launch

Uses the standard library only, so it runs on any Python 3 and then hands over to Python 3.11+ itself.
"""
from __future__ import annotations

import hashlib
import os
import platform
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
REQ = ROOT / "requirements.txt"
STAMP = VENV / ".eqr_installed"
MIN_PY = (3, 11)
SYSTEM = platform.system()  # Darwin / Windows / Linux

GUIDES = {
    "python": {
        "Darwin": "Install Python 3.12:  brew install python@3.12   (no Homebrew? get it at https://brew.sh)\n"
                  "  or download the installer from https://www.python.org/downloads/",
        "Windows": "Install Python 3.12 from https://www.python.org/downloads/ - tick 'Add python.exe to PATH' in the installer.\n"
                   "  Then open a NEW Command Prompt and run:  py -3.12 start.py",
        "Linux": "Install Python 3.12:  sudo apt install python3.12 python3.12-venv   (Debian/Ubuntu)\n"
                 "  or: sudo dnf install python3.12   (Fedora)",
    },
    "pango": {
        "Darwin": "The PDF engine (WeasyPrint) needs the Pango library:\n  brew install pango\n  (no Homebrew? get it at https://brew.sh)",
        "Windows": "The PDF engine (WeasyPrint) needs the GTK/Pango runtime on Windows:\n"
                   "  1. Install MSYS2 from https://www.msys2.org/\n"
                   "  2. Open the 'MSYS2 MINGW64' terminal and run:  pacman -S mingw-w64-x86_64-pango\n"
                   "  3. Run this launcher again (it finds C:\\msys64\\mingw64\\bin automatically).\n"
                   "  More help: https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#windows",
        "Linux": "The PDF engine (WeasyPrint) needs Pango:\n  sudo apt install libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz-subset0   (Debian/Ubuntu)\n"
                 "  or: sudo dnf install pango   (Fedora)",
    },
    "internet": "Package download failed. Check your internet connection (and any VPN/proxy), then run this launcher again.",
}


def say(msg: str) -> None:
    print(f"\n==> {msg}", flush=True)


def die(title: str, guide: str) -> None:
    print(f"\n{'=' * 70}\nSETUP NEEDED: {title}\n{'=' * 70}\n{guide}\n", flush=True)
    if os.name == "nt" and sys.stdin and sys.stdin.isatty():
        input("Press Enter to close...")
    sys.exit(1)


def venv_python() -> Path:
    return VENV / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def find_python() -> list[str] | None:
    """Command that runs a Python >= 3.11 (the current one, else one found on PATH)."""
    if sys.version_info >= MIN_PY:
        return [sys.executable]
    candidates = [["py", f"-3.{v}"] for v in (13, 12, 11)] if os.name == "nt" else []
    candidates += [[f"python3.{v}"] for v in (13, 12, 11)] + [["python3"], ["python"]]
    for cmd in candidates:
        if shutil.which(cmd[0]) is None:
            continue
        try:
            out = subprocess.run(cmd + ["-c", "import sys;print(sys.version_info[:2] >= (3, 11))"], capture_output=True, text=True, timeout=20)
            if out.stdout.strip() == "True":
                return cmd
        except Exception:
            pass
    return None


def env_for_run() -> dict:
    """Environment that lets WeasyPrint find Pango on each OS."""
    env = dict(os.environ)
    if SYSTEM == "Darwin":
        libs = [p for p in ("/opt/homebrew/lib", "/usr/local/lib") if Path(p).exists()]
        env["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(libs + [env.get("DYLD_FALLBACK_LIBRARY_PATH", "")])
    elif SYSTEM == "Windows":
        for p in (r"C:\msys64\mingw64\bin", r"C:\Program Files\GTK3-Runtime Win64\bin"):
            if Path(p).exists():
                env.setdefault("WEASYPRINT_DLL_DIRECTORIES", p)
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def req_hash() -> str:
    return hashlib.sha256(REQ.read_bytes()).hexdigest()


def venv_ok() -> bool:
    py = venv_python()
    if not py.exists() or not STAMP.exists() or STAMP.read_text().strip() != req_hash():
        return False
    return subprocess.run([str(py), "-c", "import streamlit, yfinance, pandas, matplotlib, jinja2"], capture_output=True).returncode == 0


def ensure_venv(py_cmd: list[str], force: bool) -> None:
    if force and VENV.exists():
        shutil.rmtree(VENV)
    if venv_ok():
        return
    say("Setting up the Python environment (first run only, takes a few minutes)")
    if VENV.exists():
        shutil.rmtree(VENV)  # copied from another machine or half-installed
    r = subprocess.run(py_cmd + ["-m", "venv", str(VENV)])
    if r.returncode != 0:
        die("python venv module is missing", "On Debian/Ubuntu install it with:  sudo apt install python3-venv\n"
            "Otherwise reinstall Python from https://www.python.org/downloads/ and try again.")
    py = str(venv_python())
    subprocess.run([py, "-m", "pip", "install", "--quiet", "--upgrade", "pip"])
    r = subprocess.run([py, "-m", "pip", "install", "-r", str(REQ)])
    if r.returncode != 0:
        die("dependency installation failed", GUIDES["internet"])
    STAMP.write_text(req_hash())


def check_pdf_engine() -> None:
    say("Checking the PDF engine (WeasyPrint)")
    code = "import weasyprint; weasyprint.HTML(string='<p>ok</p>').write_pdf()"
    r = subprocess.run([str(venv_python()), "-c", code], capture_output=True, text=True, env=env_for_run())
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-3:])
        die("PDF library missing", f"{GUIDES['pango'][SYSTEM] if SYSTEM in GUIDES['pango'] else GUIDES['pango']['Linux']}\n\n"
            f"(technical detail: {tail})\nAfter installing, run this launcher again.")


def free_port(start: int = 8501) -> int:
    for port in range(start, start + 20):
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def main() -> None:
    args = set(sys.argv[1:])
    py_cmd = find_python()
    if py_cmd is None:
        die(f"Python {MIN_PY[0]}.{MIN_PY[1]} or newer was not found (you have {sys.version.split()[0]})",
            GUIDES["python"].get(SYSTEM, GUIDES["python"]["Linux"]) + "\n\nThen run:  python start.py")
    if not REQ.exists():
        die("requirements.txt is missing", "Run this file from inside the unzipped equity_report folder.")
    ensure_venv(py_cmd, "--reinstall" in args)
    check_pdf_engine()
    if "--check" in args:
        say("Setup OK")
        return
    port = free_port()
    say(f"Starting the app at http://localhost:{port}  (keep this window open; press Ctrl+C to stop)")
    cmd = [str(venv_python()), "-m", "streamlit", "run", str(ROOT / "app" / "streamlit_app.py"), "--server.port", str(port)]
    try:
        sys.exit(subprocess.call(cmd, cwd=ROOT, env=env_for_run()))
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
