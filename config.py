# config.py - 建築意匠ナレッジRAGシステム設定（Webアプリ版）

import os
from pathlib import Path
from dotenv import load_dotenv

# 環境変数をロード
load_dotenv()

# ローカルベースディレクトリ (Google Driveから完全分離)
BASE_DIR = Path(__file__).parent

# 各種ディレクトリ
KNOWLEDGE_BASE_DIR = BASE_DIR / "knowledge_base"
PDF_STORAGE_DIR    = BASE_DIR / "data" / "pdfs"
PDF_CACHE_DIR      = BASE_DIR / "data" / "cache" / "pdfs"

# Storage Strategy (drive: Google Drive canonical, local: Local filesystem canonical)
PDF_STORAGE_MODE = os.environ.get("PDF_STORAGE_MODE", "drive").lower()
if PDF_STORAGE_MODE not in {"drive", "local"}:
    PDF_STORAGE_MODE = "drive"
PDF_CACHE_MAX_GB = int(os.environ.get("PDF_CACHE_MAX_GB", "2"))

# Google Drive 設定
GOOGLE_DRIVE_FOLDER_NAME = os.environ.get("GOOGLE_DRIVE_FOLDER_NAME", "建築意匠ナレッジDB")
GOOGLE_DRIVE_FOLDER_ID = os.environ.get("GOOGLE_DRIVE_FOLDER_ID") # 指定があればそれを使う
GOOGLE_DRIVE_CREDENTIALS_JSON = os.environ.get("GOOGLE_DRIVE_CREDENTIALS_JSON") # サービスアカウント用

# ChromaDB保存先
CHROMA_DB_DIR = str(BASE_DIR / "data" / "chroma")

# ファイルインデックス保存先
FILE_INDEX_PATH = str(KNOWLEDGE_BASE_DIR / "99_システム" / "file_index.json")

# SQLiteデータベースパス (iCloud同期による I/O Error 回避のためホームディレクトリに配置)
LOCAL_APP_DIR = Path.home() / ".antigravity"
DB_PATH = f"sqlite:///{LOCAL_APP_DIR / 'antigravity.db'}"

# ===== ディレクトリ構成 =====
# 未分類フォルダ名
UNCATEGORIZED_FOLDER = "00_未分類"

# 後方互換エリアス
REFERENCE_DIR = KNOWLEDGE_BASE_DIR
SEARCH_MD_DIR = KNOWLEDGE_BASE_DIR

# 処理用データ・一時ファイル
TEMP_CHUNK_DIR = BASE_DIR / "data" / "temp_chunks"
ERROR_DIR = BASE_DIR / "data" / "error"

# 後方互換のみ
UPLOAD_DIR = KNOWLEDGE_BASE_DIR / UNCATEGORIZED_FOLDER

# Small-to-Bigチャンク。親チャンクのMD保存先
PARENT_CHUNKS_DIR = BASE_DIR / "data" / "parent_chunks"

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
RERANK_THRESHOLD: float = float(os.getenv("RERANK_THRESHOLD", "0.5"))
RERANK_CANDIDATE_COUNT: int = int(os.getenv("RERANK_CANDIDATE_COUNT", "15"))

# Gemini API設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    raise EnvironmentError("GEMINI_API_KEY が未設定です。.env ファイルを確認してください。")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "65536"))
PDF_CHUNK_PAGES = int(os.environ.get("PDF_CHUNK_PAGES", "2"))  # 互換性維持のため残す
PDF_CHUNK_PAGES_GENERAL = int(os.environ.get("PDF_CHUNK_PAGES_GENERAL", "6"))
PDF_CHUNK_PAGES_DRAWING = int(os.environ.get("PDF_CHUNK_PAGES_DRAWING", "2"))
OCR_TEXT_FASTPATH_MIN_CHARS = int(os.environ.get("OCR_TEXT_FASTPATH_MIN_CHARS", "80"))
OCR_GARBLED_MAX_COMBINING_RATIO = float(os.environ.get("OCR_GARBLED_MAX_COMBINING_RATIO", "0.08"))
OCR_MAX_WORKERS = int(os.environ.get("OCR_MAX_WORKERS", "8"))  # 互換性
EXECUTOR_WORKERS = int(os.environ.get("EXECUTOR_WORKERS", "12"))
API_CONCURRENCY = int(os.environ.get("API_CONCURRENCY", "5"))
TEMPERATURE = 0.2  # 技術的正確性を重視

GEMINI_MODEL_RAG = "gemini-3-flash-preview"  # RAG用
GEMINI_MODEL_OCR = "gemini-3-flash-preview"  # OCR用
GEMINI_MODEL_EMBEDDING = "models/gemini-embedding-001"

# 互換性定数（古いコード用）
GEMINI_MODEL = GEMINI_MODEL_RAG
VISION_ANALYSIS_MODEL = GEMINI_MODEL_OCR
PREVIEW_MODEL = GEMINI_MODEL_RAG
EMBEDDING_MODEL = GEMINI_MODEL_EMBEDDING

# 利用可能なモデル（フロントエンドのセレクターに使用）
AVAILABLE_MODELS: dict[str, str] = {
    "gemini-3-flash-preview":  "Gemini 3 Flash（高速・標準）",
    "gemini-3.1-pro-preview":  "Gemini 3.1 Pro（高精度・低速）",
    "gemini-2.0-flash":        "Gemini 2.0 Flash（安定板）",
}

# ===== Layer A Memory v2 Feature Flags =====
MEMORY_V2_ENABLED = os.environ.get("MEMORY_V2_ENABLED", "true").lower() == "true"
MEMORY_V2_WRITE_ENABLED = os.environ.get("MEMORY_V2_WRITE_ENABLED", "true").lower() == "true"
MEMORY_V2_READ_ENABLED = os.environ.get("MEMORY_V2_READ_ENABLED", "true").lower() == "true"
MEMORY_MAX_INJECTION_TOKENS = int(os.environ.get("MEMORY_MAX_INJECTION_TOKENS", "900"))
MEMORY_RAW_TRANSCRIPT_TTL_DAYS = int(os.environ.get("MEMORY_RAW_TRANSCRIPT_TTL_DAYS", "30"))
MEMORY_STATE_DEFAULT_TTL_DAYS = int(os.environ.get("MEMORY_STATE_DEFAULT_TTL_DAYS", "30"))
MEMORY_DAILY_RETENTION_DAYS = int(os.environ.get("MEMORY_DAILY_RETENTION_DAYS", "14"))
MEMORY_WEEKLY_RETENTION_WEEKS = int(os.environ.get("MEMORY_WEEKLY_RETENTION_WEEKS", "12"))
MEMORY_MONTHLY_RETENTION_MONTHS = int(os.environ.get("MEMORY_MONTHLY_RETENTION_MONTHS", "24"))



# ChromaDBコレクション名
COLLECTION_NAME = "architectural_knowledge"

# 除外フォルダ（インデックス対象外）
EXCLUDE_FOLDERS = [
    "chroma_db", "__pycache__", ".git", "99_システム",
    "90_処理用データ",   # OCR一時チャンクファイル
    "20_検索MD",            # 旧アーキテクチャのMD池（重複インデックス原因）
    "10_参照PDF",           # 旧アーキテクチャのPDF池（重複インデックス原因）
]

# 除外ファイルパターン（ファイル名に含む文字列）
EXCLUDE_PATTERNS = [".chunk_"]  # OCR一時チャンクファイル

# CORS設定 (#15: ALLOW_LOCALHOSTによるローカルホスト許可)
_default_cors_list = [
    "https://antigravity.rag-architecture.com",
    "https://api.rag-architecture.com"
]
if os.environ.get("ALLOW_LOCALHOST", "false").lower() == "true":
    _default_cors_list.append("http://localhost:3000")

_default_cors = ",".join(_default_cors_list)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", _default_cors).split(",")
