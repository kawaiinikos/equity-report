#!/bin/zsh
# Portable launcher: sets everything up on first run (a few minutes), then just starts the app.
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
export DYLD_FALLBACK_LIBRARY_PATH="/opt/homebrew/lib:/usr/local/lib:$DYLD_FALLBACK_LIBRARY_PATH"

step() { print "\n==> $*"; }
fail() { print "\nERROR: $*\n"; read -k1 "?Press any key to close..."; exit 1 }

# 1. Python >= 3.11
PY=""
for c in python3.13 python3.12 python3.11; do
  if command -v $c >/dev/null 2>&1; then PY=$(command -v $c); break; fi
done
if [ -z "$PY" ]; then
  command -v brew >/dev/null 2>&1 || fail "Python 3.11+ not found and Homebrew is not installed.
Install Homebrew from https://brew.sh (or Python 3.12 from https://www.python.org/downloads/), then double-click this file again."
  step "Installing Python 3.12 via Homebrew"
  brew install python@3.12 || fail "Could not install Python."
  PY=$(command -v python3.12) || fail "Python 3.12 still not found after install."
fi

# 2. Pango (needed by WeasyPrint for PDF rendering)
if command -v brew >/dev/null 2>&1; then
  if ! brew list pango >/dev/null 2>&1; then
    step "Installing pango (PDF rendering library)"
    brew install pango || fail "Could not install pango."
  fi
else
  fail "Homebrew is required for the PDF engine (pango). Install it from https://brew.sh and try again."
fi

# 3. Virtual environment (rebuilt if it was copied from another machine and is broken)
if ! .venv/bin/python -c "import eqr, streamlit, weasyprint, yfinance" >/dev/null 2>&1; then
  step "Setting up Python environment (first run only, takes a few minutes)"
  rm -rf .venv
  "$PY" -m venv .venv || fail "Could not create the virtual environment."
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install -e . lxml requests || fail "Dependency installation failed (is the internet on?)."
  .venv/bin/python -c "import eqr, streamlit, weasyprint, yfinance" || fail "Environment check failed after install."
fi

# 4. Launch (Streamlit opens the browser itself and picks a free port)
step "Starting the app - keep this window open; close it to stop the app"
exec .venv/bin/streamlit run app/streamlit_app.py
