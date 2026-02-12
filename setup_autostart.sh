#!/bin/bash
# Antigravity RAG - Mac自動起動セットアップスクリプト

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_FILE="$SCRIPT_DIR/com.antigravity.rag.plist"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
TARGET_PLIST="$LAUNCH_AGENTS_DIR/com.antigravity.rag.plist"

echo "🚀 Antigravity RAG 自動起動セットアップ"
echo "========================================"

# LaunchAgents ディレクトリ作成
mkdir -p "$LAUNCH_AGENTS_DIR"

# 既存のサービスを停止
if launchctl list | grep -q "com.antigravity.rag"; then
    echo "📌 既存のサービスを停止中..."
    launchctl unload "$TARGET_PLIST" 2>/dev/null
fi

# plistをコピー
echo "📋 LaunchAgent設定をコピー..."
cp "$PLIST_FILE" "$TARGET_PLIST"

# パーミッション設定
chmod 644 "$TARGET_PLIST"

# サービス登録
echo "🔧 サービスを登録中..."
launchctl load "$TARGET_PLIST"

echo ""
echo "✅ セットアップ完了！"
echo ""
echo "📌 確認方法:"
echo "   launchctl list | grep antigravity"
echo ""
echo "📌 手動起動:"
echo "   launchctl start com.antigravity.rag"
echo ""
echo "📌 停止:"
echo "   launchctl stop com.antigravity.rag"
echo ""
echo "📌 自動起動解除:"
echo "   launchctl unload ~/Library/LaunchAgents/com.antigravity.rag.plist"
echo ""
echo "⚠️ 注意: .env ファイルにGmail設定を行ってください！"
