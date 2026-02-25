# tests/test_integration.py
# 統合テスト — 全主要エンドポイントの正常動作を検証
#
# 実行方法:
#   cd architectural_rag
#   python3 -m pytest tests/test_integration.py -v
#
# 前提条件:
#   - サーバーが localhost:8000 で起動していること
#   - APP_PASSWORD 環境変数が設定されていること（Basic認証用）
#
# 注意:
#   - 本番データを書き換えない（GET/読み取りテストのみ）
#   - 全テストは独立して動作（順序依存なし）
#   - v3 リトリーバー(クエリ展開+HyDE+リランク)はGemini呼び出しを複数行うため
#     TIMEOUT=30秒に設定

import os
import sys
import pytest
import requests
from requests.auth import HTTPBasicAuth

# Load .env if it exists
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# テスト設定
BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "")
AUTH = HTTPBasicAuth("admin", APP_PASSWORD) if APP_PASSWORD else None
TIMEOUT = 30  # v3ではGemini複数呼び出しが発生するため30秒


def api_get(path: str, **kwargs):
    """GET リクエストヘルパー"""
    return requests.get(f"{BASE_URL}{path}", auth=AUTH, timeout=TIMEOUT, **kwargs)


def api_post(path: str, **kwargs):
    """POST リクエストヘルパー"""
    return requests.post(f"{BASE_URL}{path}", auth=AUTH, timeout=TIMEOUT, **kwargs)


# ========== ヘルスチェック ==========

class TestHealth:
    """システム全体の健全性チェック"""

    def test_health_endpoint_returns_200(self):
        """GET /api/health が 200 を返す"""
        res = api_get("/api/health")
        assert res.status_code == 200, f"Health check failed: {res.status_code} {res.text}"

    def test_health_contains_all_services(self):
        """ヘルスチェックに全サービスのステータスが含まれる"""
        res = api_get("/api/health")
        data = res.json()
        assert "status" in data, "Missing 'status' key"
        assert "services" in data, "Missing 'services' key"
        services = data["services"]
        assert "server" in services, "Missing 'server' in services"
        assert "chromadb" in services, "Missing 'chromadb' in services"
        assert "sqlite" in services, "Missing 'sqlite' in services"
        assert "gemini_api" in services, "Missing 'gemini_api' in services"
        assert "google_drive" in services, "Missing 'google_drive' in services"
        assert "file_storage" in services, "Missing 'file_storage' in services"
        assert "timestamp" in data, "Missing 'timestamp' key"

    def test_server_status_is_ok(self):
        """サーバー自体は常に ok"""
        data = api_get("/api/health").json()
        assert data["services"]["server"] == "ok"


# ========== チャット ==========

class TestChat:
    """チャットエンドポイントの検証"""

    def test_chat_stream_returns_200(self):
        """POST /api/chat/stream が 200 (SSE Stream) を返す"""
        with api_post("/api/chat/stream", json={
            "question": "テスト質問です",
            "category": None,
            "quick_mode": True
        }, stream=True) as res:
            assert res.status_code == 200, f"Chat stream failed: {res.status_code}"
            assert "text/event-stream" in res.headers.get("content-type", "")

    def test_chat_rejects_empty_question(self):
        """空の質問は 400 を返す"""
        res = api_post("/api/chat/stream", json={"question": ""})
        assert res.status_code == 400


# ========== ファイル管理 ==========

class TestFiles:
    """ファイル関連エンドポイントの検証"""

    def test_files_tree_returns_200(self):
        """GET /api/files/tree が 200 を返す"""
        res = api_get("/api/files/tree")
        assert res.status_code == 200
        data = res.json()
        assert "tree" in data or isinstance(data, list) or isinstance(data, dict)

    def test_files_list_returns_200(self):
        """GET /api/files が 200 を返す"""
        res = api_get("/api/files")
        assert res.status_code == 200
        data = res.json()
        assert "files" in data

    def test_stats_returns_200(self):
        """GET /api/stats が 200 を返す"""
        res = api_get("/api/stats")
        assert res.status_code == 200
        data = res.json()
        assert "file_count" in data
        assert "chunk_count" in data


# ========== PDF ==========

class TestPDF:
    """PDFエンドポイントの検証"""

    def test_pdf_list_returns_200(self):
        """GET /api/pdf/list が 200 を返す"""
        res = api_get("/api/pdf/list")
        assert res.status_code == 200
        assert isinstance(res.json(), list)

    def test_pdf_invalid_id_returns_4xx(self):
        """無効なIDで404を返す"""
        res = api_get("/api/pdf/nonexistent_id_12345")
        assert res.status_code in [400, 404]


# ========== Google Drive ==========

class TestDrive:
    """Google Drive 関連の検証"""

    def test_drive_status_returns_200(self):
        """GET /api/drive/status が 200 を返す"""
        res = api_get("/api/drive/status")
        assert res.status_code == 200
        data = res.json()
        assert "authenticated" in data

    def test_drive_folders_requires_auth(self):
        """GET /api/drive/folders は認証状態に依存"""
        res = api_get("/api/drive/folders")
        # 認証済みなら200、未認証なら500で返る
        assert res.status_code in [200, 500]


# ========== タグ ==========

class TestTags:
    """タグエンドポイントの検証"""

    def test_tags_returns_200(self):
        """GET /api/tags が 200 を返す"""
        res = api_get("/api/tags")
        assert res.status_code == 200

    def test_categories_returns_200(self):
        """GET /api/categories が 200 を返す"""
        res = api_get("/api/categories")
        assert res.status_code == 200


# ========== OCR ==========

class TestOCR:
    """OCRステータスの検証"""

    def test_ocr_status_returns_200(self):
        """GET /api/ocr/status が 200 を返す"""
        res = api_get("/api/ocr/status")
        assert res.status_code == 200
        data = res.json()
        assert "processing_count" in data
        assert "jobs" in data


# ========== 設定 ==========

class TestSettings:
    """設定エンドポイントの検証"""

    def test_gemini_key_status(self):
        """GET /api/settings/gemini-key が 200 を返す"""
        res = api_get("/api/settings/gemini-key")
        assert res.status_code == 200
        data = res.json()
        assert "configured" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
