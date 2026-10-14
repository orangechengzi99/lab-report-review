#!/usr/bin/env bash
# ============================================================
#  Lab Report Review - One-click launcher (macOS / Linux)
#  Usage:  ./start.sh   (or double-click if your file manager allows)
#  Stop:   Ctrl+C in this terminal (stops both services)
# ============================================================

set -euo pipefail

cd "$(dirname "$0")"

echo
echo "============================================"
echo "  Lab Report Review - starting"
echo "============================================"
echo

# --- Check backend venv ---
if [ ! -x "backend/.venv/bin/python" ]; then
    echo "[ERROR] Backend venv not found: backend/.venv/bin/python"
    echo
    echo "Run this once to set it up:"
    echo "    cd backend"
    echo "    python3 -m venv .venv"
    echo "    .venv/bin/pip install -r requirements.txt"
    echo
    exit 1
fi

# --- Check frontend deps ---
if [ ! -d "frontend/node_modules" ]; then
    echo "[ERROR] Frontend deps not installed: frontend/node_modules"
    echo
    echo "Run this once to set it up:"
    echo "    cd frontend"
    echo "    npm ci"
    echo
    exit 1
fi

BACKEND_PID=""
FRONTEND_PID=""

cleanup() {
    echo
    echo "Shutting down ..."
    [ -n "$BACKEND_PID" ]  && kill "$BACKEND_PID"  2>/dev/null || true
    [ -n "$FRONTEND_PID" ] && kill "$FRONTEND_PID" 2>/dev/null || true
    wait 2>/dev/null || true
    echo "Stopped."
}
trap cleanup EXIT INT TERM

echo "[1/3] Starting backend on port 8000 ..."
(
    cd backend
    exec .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
) &
BACKEND_PID=$!

sleep 4

echo "[2/3] Starting frontend on port 5173 ..."
(
    cd frontend
    exec npm run dev -- --host 127.0.0.1 --port 5173 --strictPort
) &
FRONTEND_PID=$!

sleep 6

echo "[3/3] Opening browser ..."
UI_URL="http://127.0.0.1:5173"
if command -v open >/dev/null 2>&1; then
    open "$UI_URL"                     # macOS
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$UI_URL"                 # Linux
else
    echo "     Open this in your browser: $UI_URL"
fi

echo
echo "============================================"
echo "  Started"
echo "--------------------------------------------"
echo "  UI:  http://127.0.0.1:5173"
echo "  API: http://127.0.0.1:8000/docs"
echo
echo "  Press Ctrl+C here to stop both services."
echo "============================================"
echo

wait
