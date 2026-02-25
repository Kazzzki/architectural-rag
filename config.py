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

# ChromaDB保存先
CHROMA_DB_DIR = str(BASE_DIR / "data" / "chroma")

# ファイルインデックス保存先
FILE_INDEX_PATH = str(KNOWLEDGE_BASE_DIR / "99_システム" / "file_index.json")

# SQLiteデータベースパス
DB_PATH = f"sqlite:///{BASE_DIR / 'data' / 'antigravity.db'}"

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

# Gemini API設定
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if not GEMINI_API_KEY:
    import warnings
    warnings.warn(
        "⚠️  GEMINI_API_KEYが未設定です。"
        "チャット・インデックス機能が動作しません。"
        ".env ファイルまたは環境変数に GEMINI_API_KEY を設定してください。",
        stacklevel=2,
    )
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "65536"))
PDF_CHUNK_PAGES = int(os.environ.get("PDF_CHUNK_PAGES", "1"))
TEMPERATURE = 0.2  # 技術的正確性を重視

GEMINI_MODEL_RAG = "gemini-3-flash-preview"  # RAG用
GEMINI_MODEL_OCR = "gemini-3-flash-preview"  # OCR用
GEMINI_MODEL_EMBEDDING = "models/gemini-embedding-001"

# 互換性定数（古いコード用）
GEMINI_MODEL = GEMINI_MODEL_RAG
VISION_ANALYSIS_MODEL = GEMINI_MODEL_OCR
PREVIEW_MODEL = GEMINI_MODEL_RAG
EMBEDDING_MODEL = GEMINI_MODEL_EMBEDDING


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

# CORS設定 (#15: 本番環境では環境変数で制御することを推奨)
_default_cors = (
    "http://localhost:3000,"
    "https://antigravity.rag-architecture.com,"
    "https://api.rag-architecture.com"
)
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", _default_cors).split(",")
