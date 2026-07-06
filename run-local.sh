#!/usr/bin/env bash
# One-command local launcher (no Docker needed).
# Starts the FastAPI backend on :8000 and the Vite frontend on :5173,
# then prints the URL to open. Ctrl-C stops both.
#
# Requirements: Python 3.11+ and Node 20+ on your PATH.
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ Backend: creating venv + installing deps (first run only)…"
cd backend
if [ ! -d .venv ]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
. .venv/bin/activate
pip install -q -r requirements.txt
echo "▶ Backend: starting on http://localhost:8000"
uvicorn app.main:app --port 8000 &
BACKEND_PID=$!
deactivate || true
cd ..

echo "▶ Frontend: installing deps (first run only)…"
cd frontend
if [ ! -d node_modules ]; then
  npm install
fi
echo "▶ Frontend: starting on http://localhost:5173"
VITE_API_URL="http://localhost:8000" npm run dev -- --port 5173 &
FRONTEND_PID=$!
cd ..

cleanup() {
  echo; echo "Stopping…"
  kill "$BACKEND_PID" "$FRONTEND_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

sleep 2
echo
echo "=================================================================="
echo "  AI Workflow Copilot is running:"
echo "    Frontend  →  http://localhost:5173   (open this)"
echo "    Backend   →  http://localhost:8000/docs"
echo "  No API keys needed — the scripted provider runs the whole demo."
echo "  Press Ctrl-C to stop both."
echo "=================================================================="
wait
