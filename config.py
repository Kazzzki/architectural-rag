# config.py - 建築意匠ナレッジRAGシステム設定（Webアプリ版）

import os
from pathlib import Path
from dotenv import load_dotenv

# 環境変数をロード
load_dotenv()

# ベースディレクトリ（環境変数またはデフォルト）
BASE_DIR = Path(os.environ.get("RAG_BASE_DIR", "./data"))

# ナレッジDBディレクトリ
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"

# PDFストレージディレクトリ (Phase 1-1)
PDF_STORAGE_DIR = BASE_DIR / "pdfs"

# OCR自動分類設定 (Phase 1-2)
AUTO_CATEGORIZE_UPLOADS_ONLY = os.environ.get("AUTO_CATEGORIZE_UPLOADS_ONLY", "true").lower() == "true"
ENABLE_AUTO_CATEGORIZE = os.environ.get("ENABLE_AUTO_CATEGORIZE", "true").lower() == "true"

# ChromaDB永続化パス
CHROMA_DB_DIR = str(BASE_DIR / "chroma_db")

# SQLiteデータベースパス (SQLAlchemy)
DB_PATH = f"sqlite:///{BASE_DIR / 'antigravity.db'}"

# ファイルインデックスパス (非推奨: DB移行済み。後方互換のため残す)
FILE_INDEX_PATH = str(BASE_DIR / "file_index.json")

# アップロードディレクトリ
UPLOAD_DIR = KNOWLEDGE_BASE_DIR

# 対応ファイル拡張子
SUPPORTED_EXTENSIONS = ['.pdf', '.md', '.txt', '.docx']

# チャンキング設定
CHUNK_SIZE = 1000  # 文字数
CHUNK_OVERLAP = 200  # オーバーラップ文字数

# 検索設定
TOP_K_RESULTS = 8  # 検索で返すチャンク数

# Embedding設定（既存ChromaDBインデックスとの互換性を維持）
EMBEDDING_MODEL = "models/gemini-embedding-001"

# メイン生成エンジン（Gemini 2.5 Flash 安定版）
GEMINI_MODEL = "gemini-3-flash-preview"
MAX_TOKENS = 8192
TEMPERATURE = 0.2  # 技術的正確性を重視

# 高度な解析・図面用（マルチモーダル性能を重視）
VISION_ANALYSIS_MODEL = "gemini-3-flash-preview"

# プレビュー/最新機能（マインドマップ分析等）
PREVIEW_MODEL = "gemini-3-flash-preview"

# ChromaDBコレクション名
COLLECTION_NAME = "architectural_knowledge"

# 除外フォルダ
EXCLUDE_FOLDERS = ["chroma_db", "__pycache__", ".git"]

# CORS設定
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,https://antigravity.rag-architecture.com,https://api.rag-architecture.com").split(",")

# APIキー
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
