#!/bin/zsh
# Antigravity startup wrapper — sourced by launchd
# This script sets up the correct PATH/conda env and starts all services.

# Load user shell environment
source ~/.zshrc 2>/dev/null || true
source ~/.zshprofile 2>/dev/null || true

# Work dir
SCRIPT_DIR="/Users/kaz/Library/Mobile Documents/com~apple~CloudDocs/antigravity/architectural_rag"
cd "$SCRIPT_DIR"

# Activate venv if available
if [ -d "$SCRIPT_DIR/.venv" ]; then
    source "$SCRIPT_DIR/.venv/bin/activate"
elif command -v conda &> /dev/null; then
    conda activate antigravity 2>/dev/null || true
fi



# Kill any stale processes
pkill -f server.py 2>/dev/null || true
pkill -f antigravity_daemon.py 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -9 -f cloudflared 2>/dev/null || true
sleep 2

# Start everything
exec python3 "$SCRIPT_DIR/start_remote.py"
