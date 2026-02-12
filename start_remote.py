#!/usr/bin/env python3
"""
リモートアクセス用起動スクリプト
- サーバー起動
- ngrok起動
- URL取得
- メール通知
"""
import os
import sys
import subprocess
import time
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
from datetime import datetime
import requests

# 環境変数読み込み
from dotenv import load_dotenv
load_dotenv()

# 設定
GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")
NOTIFY_EMAIL = os.environ.get("NOTIFY_EMAIL", GMAIL_ADDRESS)
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")

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


def start_ngrok():
    """ngrokを起動してURLを取得"""
    log("Starting ngrok...")
    
    # 既存のngrokを終了
    subprocess.run(["pkill", "-f", "ngrok"], capture_output=True)
    time.sleep(1)
    
    # ngrok起動 (バックグラウンド)
    ngrok_log = open(LOG_DIR / "ngrok.log", "w")
    process = subprocess.Popen(
        ["ngrok", "http", "8000", "--log=stdout"],
        stdout=ngrok_log,
        stderr=subprocess.STDOUT,
    )
    
    # URL取得を待つ
    time.sleep(5)
    
    # ngrok API からURL取得
    try:
        response = requests.get("http://localhost:4040/api/tunnels", timeout=10)
        tunnels = response.json().get("tunnels", [])
        for tunnel in tunnels:
            if tunnel.get("proto") == "https":
                return process, tunnel.get("public_url")
    except Exception as e:
        log(f"Failed to get ngrok URL: {e}")
    
    return process, None


def send_ntfy_notification(ngrok_url: str):
    """URLをntfy.shで通知"""
    topic = os.environ.get("NTFY_TOPIC")
    if not topic:
        log("NTFY_TOPIC not configured. Skipping notification.")
        return False
    
    log(f"Sending notification to ntfy.sh/{topic}...")
    
    try:
        response = requests.post(
            f"https://ntfy.sh/{topic}",
            data=f"🚀 Antigravity Server Started\n🌐 URL: {ngrok_url}\n🔑 Pass: {APP_PASSWORD}".encode("utf-8"),
            headers={
                "Title": "Antigravity RAG Server Rules",
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


def save_url_to_file(ngrok_url: str):
    """URLをファイルに保存（バックアップ）"""
    url_file = SCRIPT_DIR / "current_url.txt"
    with open(url_file, "w") as f:
        f.write(f"URL: {ngrok_url}\n")
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
    
    # ngrok起動
    ngrok_proc, ngrok_url = start_ngrok()
    
    if ngrok_url:
        log(f"✅ ngrok URL: {ngrok_url}")
        save_url_to_file(ngrok_url)
        send_ntfy_notification(ngrok_url)
    else:
        log("❌ Failed to get ngrok URL")
    
    log("All services started. Press Ctrl+C to stop.")
    
    try:
        # プロセスが終了するまで待機
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
        ngrok_proc.terminate()
        log("Goodbye!")


if __name__ == "__main__":
    main()
