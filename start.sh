#!/bin/bash
set -e

echo "=== Trading Platform Startup (Paper Mode) ==="
echo "No Docker, PostgreSQL, or Redis required!"
echo ""

echo "1. Setting up backend..."
cd backend
if [ ! -d "venv" ]; then
    python3 -m venv venv
fi
source venv/bin/activate
pip install -r requirements.txt -q

echo "2. Starting backend (port 8000)..."
PYTHONPATH=. uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
BACKEND_PID=$!
cd ..

sleep 2

echo "3. Setting up frontend..."
cd frontend
npm install --silent
echo "4. Starting frontend (port 5173)..."
npm run dev &
FRONTEND_PID=$!
cd ..

echo ""
echo "=== Trading Platform Running ==="
echo "Dashboard: http://localhost:5173"
echo "API Docs:  http://localhost:8000/docs"
echo ""
echo "Quick start:"
echo "  1. Open http://localhost:5173"
echo "  2. Click Deposit and add funds (e.g. \$10,000)"
echo "  3. Go to Bots tab and click 'Start All Bots'"
echo "  4. Watch trades appear in real-time!"
echo ""
echo "Press Ctrl+C to stop"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null" EXIT
wait
