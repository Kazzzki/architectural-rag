# config.py - 建築意匠ナレッジRAGシステム設定（Webアプリ版）

import os
from pathlib import Path
from dotenv import load_dotenv

# 環境変数をロード
load_dotenv()

# Google Driveマウントポイント
GOOGLE_DRIVE_ROOT = os.getenv(
    "GOOGLE_DRIVE_ROOT",
    str(Path.home() / "Google Drive" / "My Drive")
)

# ナレッジベースフォルダ（Google Drive上）
KNOWLEDGE_BASE_DIR = Path(os.path.join(GOOGLE_DRIVE_ROOT, "建築意匠ナレッジDB"))

# ChromaDB保存先（Google Drive上）
CHROMA_DB_DIR = str(KNOWLEDGE_BASE_DIR / "99_システム" / "chroma_db")

# ファイルインデックス保存先
FILE_INDEX_PATH = str(KNOWLEDGE_BASE_DIR / "99_システム" / "file_index.json")

# SQLiteデータベースパス (SQLAlchemy) - ローカルに保持 (ロック回避のため)
# 既存のローカルデータを維持するか、移行するかはユーザー判断だが、システムデータはローカルが安全
BASE_DIR = Path(os.environ.get("RAG_BASE_DIR", "./data"))
DB_PATH = f"sqlite:///{BASE_DIR / 'antigravity.db'}"

# アップロードディレクトリ (Google Driveへ)
UPLOAD_DIR = KNOWLEDGE_BASE_DIR

# PDFストレージディレクトリ (Phase 1-1) - Google Driveへ統合
PDF_STORAGE_DIR = KNOWLEDGE_BASE_DIR / "02_図面"

# OCR自動分類設定
AUTO_CATEGORIZE_UPLOADS_ONLY = os.environ.get("AUTO_CATEGORIZE_UPLOADS_ONLY", "true").lower() == "true"
ENABLE_AUTO_CATEGORIZE = os.environ.get("ENABLE_AUTO_CATEGORIZE", "true").lower() == "true"

# 対応ファイル拡張子
SUPPORTED_EXTENSIONS = ['.pdf', '.md', '.txt', '.docx']

# チャンキング設定
CHUNK_SIZE = 1000  # 文字数
CHUNK_OVERLAP = 200  # オーバーラップ文字数

# 検索設定
TOP_K_RESULTS = 8  # 検索で返すチャンク数

# Gemini API設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
MAX_TOKENS = 8192
TEMPERATURE = 0.2  # 技術的正確性を重視

GEMINI_MODEL_RAG = "gemini-3-flash-preview"  # RAG用
GEMINI_MODEL_OCR = "gemini-3-flash-preview"  # OCR用
GEMINI_MODEL_EMBEDDING = "models/text-embedding-004"

# 互換性定数（古いコード用）
GEMINI_MODEL = GEMINI_MODEL_RAG
VISION_ANALYSIS_MODEL = GEMINI_MODEL_OCR
PREVIEW_MODEL = GEMINI_MODEL_RAG
EMBEDDING_MODEL = GEMINI_MODEL_EMBEDDING

# Google Drive API設定
DRIVE_SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
CREDENTIALS_FILE = str(KNOWLEDGE_BASE_DIR / "99_システム" / "credentials.json")
TOKEN_FILE = str(KNOWLEDGE_BASE_DIR / "99_システム" / "token.json")

# ChromaDBコレクション名
COLLECTION_NAME = "architectural_knowledge"

# 除外フォルダ
EXCLUDE_FOLDERS = ["chroma_db", "__pycache__", ".git", "99_システム"]

# CORS設定
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000,https://antigravity.rag-architecture.com,https://api.rag-architecture.com").split(",")
