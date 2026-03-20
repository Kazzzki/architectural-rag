#!/bin/bash
# 全サービスをデーモンとして起動（macOS対応）
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "Stopping old processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:3000 | xargs kill -9 2>/dev/null
pkill -f "cloudflared tunnel" 2>/dev/null
sleep 1

mkdir -p logs

# 各プロセスを独立シェルで起動（親プロセスから切り離す）
echo "Starting backend..."
/bin/bash -c "PYTHONDONTWRITEBYTECODE=1 PYTHONPATH='$DIR' exec '$DIR/.venv/bin/python3' -B '$DIR/server.py' >> '$DIR/logs/server.log' 2>&1" &
disown
sleep 1

echo "Starting frontend..."
/bin/bash -c "cd '$DIR/frontend' && exec /opt/homebrew/bin/npm run dev >> '$DIR/logs/frontend.log' 2>&1" &
disown
sleep 1

echo "Starting tunnel..."
/bin/bash -c "exec /opt/homebrew/bin/cloudflared tunnel run antigravity >> '$DIR/logs/tunnel.log' 2>&1" &
disown

echo ""
echo "All services starting in background."
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "URL: https://antigravity.rag-architecture.com"
echo ""
echo "Wait ~30s for embedding indexing to complete."
echo "Check: curl http://localhost:8000/api/health"
