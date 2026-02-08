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

# ChromaDB永続化パス
CHROMA_DB_DIR = str(BASE_DIR / "chroma_db")

# ファイルインデックスパス
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

# Embedding設定
EMBEDDING_MODEL = "models/text-embedding-004"  # Gemini Embedding

# LLM設定（Gemini 3.0 Flash）
GEMINI_MODEL = "gemini-3.0-flash"
MAX_TOKENS = 8192  # Gemini 3.0 Flashの最大出力トークン
TEMPERATURE = 0.2  # 技術的正確性を重視

# ChromaDBコレクション名
COLLECTION_NAME = "architectural_knowledge"

# 除外フォルダ
EXCLUDE_FOLDERS = ["chroma_db", "__pycache__", ".git"]

# CORS設定
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")

# APIキー
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
