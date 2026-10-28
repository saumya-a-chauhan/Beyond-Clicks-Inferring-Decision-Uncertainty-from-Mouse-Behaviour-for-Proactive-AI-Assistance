#!/bin/bash
# Beyond Clicks study: start the website on this Mac.
# Double-click this file (first time: right-click > Open). Keep the Terminal window open while the study runs.
cd "$(dirname "$0")"

if [ ! -f ".env" ]; then
  echo "[!] No .env file found. Copy .env.example to .env and fill in the values."
  read -r -p "Press Enter to close."
  exit 1
fi

if [ ! -x ".venv/bin/python" ]; then
  echo "First run: creating the Python environment. This takes a few minutes..."
  python3 -m venv .venv || { echo "[!] Python 3.11+ is needed: https://www.python.org/downloads/"; read -r -p "Press Enter to close."; exit 1; }
  .venv/bin/python -m pip install --upgrade pip
  .venv/bin/pip install -r requirements-analysis.txt || { echo "[!] Package install failed."; read -r -p "Press Enter to close."; exit 1; }
fi

echo
echo " Study website:        http://localhost:8000"
echo " Researcher dashboard: http://localhost:8000/admin   (password: ADMIN_PASSWORD in .env)"
echo " Experimenter guide:   http://localhost:8000/guide"
echo
echo " Keep this window open. Close it to stop the website."
echo
(sleep 2; open "http://localhost:8000") &
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
