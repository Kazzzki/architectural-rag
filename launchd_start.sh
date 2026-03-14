#!/bin/zsh
# Antigravity startup wrapper — sourced by launchd

# Set explicit PATH for homebrew and basic system binaries
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

# Work dir - Absolute path to the repository
SCRIPT_DIR="/Users/kaz/Library/Mobile Documents/com~apple~CloudDocs/antigravity/architectural_rag"
cd "$SCRIPT_DIR"

# Explicit path to the venv python
PYTHON_EXEC="$SCRIPT_DIR/.venv/bin/python3"

# Kill any stale processes to ensure a clean start
pkill -f server.py 2>/dev/null || true
pkill -f antigravity_daemon.py 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true
pkill -9 -f cloudflared 2>/dev/null || true
sleep 2

# Start the remote management script which launches all components
exec "$PYTHON_EXEC" "$SCRIPT_DIR/start_remote.py"
