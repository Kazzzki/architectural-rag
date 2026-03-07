import logging
from typing import List, Dict, Any, Optional
import os

from chromadb import PersistentClient
from config import CHROMA_DB_DIR
from layer_a.memory_models import MemoryItemModel

logger = logging.getLogger(__name__)

# Constants
COLLECTION_ITEMS = "memory_items_v2"
COLLECTION_SUMMARIES = "memory_summaries_v2"

# === 埋め込みモデル・Chroma初期化 ===

# embeddingsは必要なら明示的に指定できるが、
# ここではChromaのデフォルトEmbeddingFunction、
# もしくはGoogleGenerativeAiEmbeddingFunctionを使う構成にする
import chromadb.utils.embedding_functions as embedding_functions
from config import GEMINI_API_KEY, GEMINI_MODEL_EMBEDDING

# Embedding関数初期化
if GEMINI_API_KEY:
    google_ef = embedding_functions.GoogleGenerativeAiEmbeddingFunction(
        api_key=GEMINI_API_KEY,
        task_type="RETRIEVAL_DOCUMENT" # default
    )
    # the model name should match config.GEMINI_MODEL_EMBEDDING, but this defaults to 'models/embedding-001'
else:
    google_ef = embedding_functions.DefaultEmbeddingFunction()

def get_chroma_client() -> PersistentClient:
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    return PersistentClient(path=CHROMA_DB_DIR)

def get_items_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_ITEMS,
        embedding_function=google_ef,
        metadata={"hnsw:space": "cosine"}
    )

def get_summaries_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_SUMMARIES,
        embedding_function=google_ef,
        metadata={"hnsw:space": "cosine"}
    )

# === CRUD / Search ===

def build_embedding_text(item: dict) -> str:
    """埋め込み用のテキストを構築する（canonical_textを中心に周辺情報を結合）"""
    text = item.get("canonical_text", "")
    title = item.get("title")
    tags = item.get("tags_json")
    if title:
        text = f"[{title}]\n{text}"
    if tags:
        # Assuming tags_json is a loaded list or CSV string
        if isinstance(tags, list):
            tags_str = ", ".join(tags)
        else:
            tags_str = str(tags)
        text += f"\nTags: {tags_str}"
    return text

def build_metadata(item: dict) -> dict:
    """Chromaに保存するメタデータ"""
    return {
        "user_id": item.get("user_id", ""),
        "memory_id": item.get("id", ""),
        "memory_type": item.get("memory_type", ""),
        "status": item.get("status", ""),
        "key_norm": item.get("key_norm", "") or "",
        "created_at": str(item.get("created_at")),
        "updated_at": str(item.get("updated_at")),
        "last_used_at": str(item.get("last_used_at")) if item.get("last_used_at") else "",
        "salience": float(item.get("salience", 0.0)),
        "confidence": float(item.get("confidence", 0.0))
    }

def upsert_memory_item(item_data: dict):
    """MemoryItemをChroma(itemsコレクション)にupsertする"""
    collection = get_items_collection()
    text = build_embedding_text(item_data)
    meta = build_metadata(item_data)
    doc_id = item_data["id"]
    
    collection.upsert(
        documents=[text],
        metadatas=[meta],
        ids=[doc_id]
    )

def upsert_memory_summary(item_data: dict):
    """MemoryItemをChroma(summariesコレクション)にupsertする"""
    collection = get_summaries_collection()
    text = build_embedding_text(item_data)
    meta = build_metadata(item_data)
    doc_id = item_data["id"]
    
    collection.upsert(
        documents=[text],
        metadatas=[meta],
        ids=[doc_id]
    )

def search_memory_items(
    query: str,
    user_id: str,
    status: str = "active",
    memory_types: Optional[List[str]] = None,
    limit: int = 15
) -> dict:
    """
    Symbolic filter + Vector Searchでアイテムを取得する
    """
    collection = get_items_collection()
    
    # 必須フィルター (user_id)
    where_filter: Dict[str, Any] = {
        "user_id": user_id
    }
    
    if status:
        # $and の形式で組む
        where_filter = {
            "$and": [
                {"user_id": user_id},
                {"status": status}
            ]
        }
    
    # query実行
    try:
        results = collection.query(
            query_texts=[query],
            n_results=limit,
            where=where_filter,
            include=["metadatas", "documents", "distances"]
        )
    except Exception as e:
        logger.error(f"Error querying memory items chroma: {e}")
        return {"ids": [], "documents": [], "metadatas": [], "distances": []}
    
    return results
