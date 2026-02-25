#!/bin/bash
# scripts/startup_check.sh — システム起動チェック
# 使用方法: cd architectural_rag && bash scripts/startup_check.sh

set -e

echo "=== システム起動チェック ==="
echo ""

# 1. 環境変数チェック
echo "【環境変数】"
required_vars=("GEMINI_API_KEY" "APP_PASSWORD")
optional_vars=("CF_TUNNEL_NAME" "CF_TUNNEL_HOSTNAME" "RAG_BASE_DIR")

for var in "${required_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "  ❌ $var が未設定 (必須)"
  else
    echo "  ✅ $var OK"
  fi
done

for var in "${optional_vars[@]}"; do
  if [ -z "${!var}" ]; then
    echo "  ⚠️  $var 未設定 (任意)"
  else
    echo "  ✅ $var OK"
  fi
done

echo ""

# 2. 必須ファイルの存在チェック  
echo "【必須ファイル】"
required_files=(".env" "config.py" "server.py")
secret_files=("data/secrets/credentials.json" "data/secrets/token.pickle")

for f in "${required_files[@]}"; do
  if [ -f "$f" ]; then
    echo "  ✅ $f"
  else
    echo "  ❌ $f が存在しない"
  fi
done

for f in "${secret_files[@]}"; do
  if [ -f "$f" ]; then
    echo "  ✅ $f"
  else
    echo "  ⚠️  $f が存在しない (Google Drive連携に必要)"
  fi
done

echo ""

# 3. データディレクトリチェック
echo "【データディレクトリ】"
data_dirs=("data" "data/chroma_db" "data/pdfs" "data/secrets")
for d in "${data_dirs[@]}"; do
  if [ -d "$d" ]; then
    echo "  ✅ $d/"
  else
    echo "  ❌ $d/ が存在しない"
  fi
done

echo ""

# 4 プロセスチェック
echo "【プロセス】"
if pgrep -f "uvicorn" > /dev/null 2>&1; then
  echo "  ✅ uvicorn (FastAPI server) 起動中"
else
  echo "  ❌ uvicorn が起動していない"
fi

if pgrep -f "antigravity_daemon" > /dev/null 2>&1; then
  echo "  ✅ antigravity_daemon 起動中"
else
  echo "  ⚠️  antigravity_daemon が起動していない"
fi

echo ""

# 5. サービスヘルスチェック
echo "【サービス状態】"
HEALTH_URL="http://localhost:8000/api/health"

if [ -n "$APP_PASSWORD" ]; then
  AUTH_HEADER="-u admin:$APP_PASSWORD"
else
  AUTH_HEADER=""
fi

HEALTH_RESPONSE=$(curl -s $AUTH_HEADER "$HEALTH_URL" 2>/dev/null)
if [ $? -eq 0 ] && [ -n "$HEALTH_RESPONSE" ]; then
  echo "$HEALTH_RESPONSE" | python3 -m json.tool 2>/dev/null || echo "  ⚠️  レスポンスのパースに失敗: $HEALTH_RESPONSE"
else
  echo "  ❌ サーバーに接続できません ($HEALTH_URL)"
fi

echo ""
echo "=== チェック完了 ==="
