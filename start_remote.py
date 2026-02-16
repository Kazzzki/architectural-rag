#!/usr/bin/env python3
"""
リモートアクセス用起動スクリプト
- サーバー起動
- Cloudflare Tunnel起動 (固定URL)
- 通知
"""
import os
import sys
import subprocess
import time
import json
from pathlib import Path
from datetime import datetime
import requests

# 環境変数読み込み
from dotenv import load_dotenv
load_dotenv()

# 設定
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
TUNNEL_NAME = os.environ.get("CF_TUNNEL_NAME", "antigravity")
TUNNEL_HOSTNAME = os.environ.get("CF_TUNNEL_HOSTNAME", "")  # e.g. antigravity.your-domain.com

SCRIPT_DIR = Path(__file__).parent.absolute()
LOG_DIR = SCRIPT_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)


def log(message: str):
    """ログ出力"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {message}")
    with open(LOG_DIR / "startup.log", "a") as f:
        f.write(f"[{timestamp}] {message}\n")


def start_server():
    """FastAPIサーバーを起動"""
    log("Starting FastAPI server...")
    server_log = open(LOG_DIR / "server.log", "w")
    process = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=SCRIPT_DIR,
        stdout=server_log,
        stderr=subprocess.STDOUT,
    )
    time.sleep(3)  # サーバー起動待ち
    return process


def start_daemon():
    """自動分類デーモンを起動"""
    log("Starting classification daemon...")
    daemon_log = open(LOG_DIR / "daemon.log", "w")
    process = subprocess.Popen(
        [sys.executable, "antigravity_daemon.py"],
        cwd=SCRIPT_DIR,
        stdout=daemon_log,
        stderr=subprocess.STDOUT,
    )
    return process


def start_tunnel():
    """Cloudflare Tunnelを起動"""
    log("Starting Cloudflare Tunnel...")

    # cloudflaredの存在確認
    cloudflared_path = "cloudflared"
    home_bin = Path.home() / "bin" / "cloudflared"
    if home_bin.exists():
        cloudflared_path = str(home_bin)
    else:
        result = subprocess.run(["which", "cloudflared"], capture_output=True)
        if result.returncode != 0:
            log("❌ cloudflared not found. Install with: brew install cloudflared")
            log("   Falling back to ngrok...")
            return start_ngrok_fallback()

    # Cloudflare Tunnel起動
    tunnel_log = open(LOG_DIR / "tunnel.log", "w")
    process = subprocess.Popen(
        [cloudflared_path, "tunnel", "run", TUNNEL_NAME],
        stdout=tunnel_log,
        stderr=subprocess.STDOUT,
    )

    time.sleep(3)

    # トンネルURLを返す
    if TUNNEL_HOSTNAME:
        url = f"https://{TUNNEL_HOSTNAME}"
        log(f"✅ Cloudflare Tunnel URL: {url}")
        return process, url
    else:
        log("⚠️ CF_TUNNEL_HOSTNAME not set. Tunnel started but URL unknown.")
        log("   Set CF_TUNNEL_HOSTNAME in .env to get the URL.")
        return process, None


def start_ngrok_fallback():
    """ngrokフォールバック（cloudflaredが未インストールの場合）"""
    log("Starting ngrok (fallback)...")

    subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
    time.sleep(1)

    ngrok_log = open(LOG_DIR / "ngrok.log", "w")
    process = subprocess.Popen(
        ["ngrok", "http", "8000", "--log=stdout"],
        stdout=ngrok_log,
        stderr=subprocess.STDOUT,
    )

    time.sleep(5)

    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=10)
        tunnels = response.json().get("tunnels", [])
        for tunnel in tunnels:
            if tunnel.get("proto") == "https":
                return process, tunnel.get("public_url")
    except Exception as e:
        log(f"Failed to get ngrok URL: {e}")

    return process, None


def send_ntfy_notification(tunnel_url: str):
    """URLをntfy.shで通知"""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log("NTFY_TOPIC not configured. Skipping notification.")
        return False

    log(f"Sending notification to ntfy.sh/{topic}...")

    try:
        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=f"🚀 Antigravity Server Started\n🌐 URL: {tunnel_url}\n🔑 Pass: {APP_PASSWORD}".encode("utf-8"),
            headers={
                "Title": "Antigravity RAG Server Online",
                "Priority": "high",
                "Tags": "rocket,server"
            },
            timeout=10
        )
        if response.status_code == 200:
            log("ntfy.sh notification sent successfully!")
            return True
        else:
            log(f"Failed to send ntfy.sh notification: {response.status_code} {response.text}")
            return False
    except Exception as e:
        log(f"Failed to send ntfy.sh notification: {e}")
        return False


def save_url_to_file(tunnel_url: str):
    """URLをファイルに保存（バックアップ）"""
    url_file = SCRIPT_DIR / "current_url.txt"
    with open(url_file, "w") as f:
        f.write(f"URL: {tunnel_url}\n")
        f.write(f"Password: {APP_PASSWORD}\n")
        f.write(f"Started: {datetime.now().isoformat()}\n")
    log(f"URL saved to {url_file}")


def main():
    log("=" * 50)
    log("Starting Antigravity Remote Access")
    log("=" * 50)

    # サーバー起動
    server_proc = start_server()
    daemon_proc = start_daemon()

    # Cloudflare Tunnel起動
    tunnel_proc, tunnel_url = start_tunnel()

    if tunnel_url:
        log(f"✅ Remote URL: {tunnel_url}")
        save_url_to_file(tunnel_url)
        send_ntfy_notification(tunnel_url)
    else:
        log("⚠️ Tunnel started but URL not confirmed")

    log("All services started. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(60)
            # ヘルスチェック
            try:
                response = requests.get("http://localhost:8000/api/health", timeout=5)
                if response.status_code != 200:
                    log("⚠️ Server health check failed")
            except:
                log("⚠️ Server not responding")

    except KeyboardInterrupt:
        log("Shutting down...")
        server_proc.terminate()
        daemon_proc.terminate()
        tunnel_proc.terminate()
        log("Goodbye!")


if __name__ == "__main__":
    main()
