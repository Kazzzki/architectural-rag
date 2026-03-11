
import logging
import json
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

from database import SessionLocal, PersonalContext
from dense_indexer import _get_chroma_client, _embed_batch_with_retry
from gemini_client import get_client
from config import PERSONAL_CONTEXT_COLLECTION, EMBEDDING_MODEL
from google.genai import types

logger = logging.getLogger(__name__)

class PersonalContextManager:
    def __init__(self):
        self.chroma_client = _get_chroma_client()
        self.collection = self.chroma_client.get_or_create_collection(
            name=PERSONAL_CONTEXT_COLLECTION,
            metadata={"hnsw:space": "cosine"}
        )

    def search_similar(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        """ChromaDBを使用して類似コンテキストを検索"""
        try:
            gemini = get_client()
            # retrieval_query タスクタイプを使用
            res = gemini.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=[query],
                config=types.EmbedContentConfig(task_type="retrieval_query")
            )
            query_embedding = res.embeddings[0].values

            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=limit
            )

            contexts = []
            if results and results["ids"] and results["ids"][0]:
                for i in range(len(results["ids"][0])):
                    contexts.append({
                        "id": results["metadatas"][0][i]["id"],
                        "type": results["metadatas"][0][i].get("type", "unknown"),
                        "content": results["documents"][0][i],
                        # 距離 (cosine distance) をスコアに変換
                        "score": 1.0 - (results["distances"][0][i] if "distances" in results else 0.5)
                    })
            return contexts
        except Exception as e:
            logger.error(f"Failed to search similar personal contexts: {e}")
            return []

    def index_context(self, context_id: int):
        """特定のコンテキストを ChromaDB にインデックス"""
        session = SessionLocal()
        try:
            ctx = session.query(PersonalContext).filter(PersonalContext.id == context_id).first()
            if not ctx:
                return
            
            # 検索対象外の場合は削除
            if not ctx.is_active or ctx.status != "approved":
                self.delete_from_index(context_id)
                return

            gemini = get_client()
            embeddings = _embed_batch_with_retry(gemini, [ctx.content])
            if embeddings:
                self.collection.upsert(
                    ids=[str(ctx.id)],
                    embeddings=embeddings,
                    documents=[ctx.content],
                    metadatas=[{"type": ctx.type, "id": ctx.id}]
                )
                logger.info(f"Indexed personal context {ctx.id} to ChromaDB")
        finally:
            session.close()

    def delete_from_index(self, context_id: int):
        """ChromaDB から削除"""
        try:
            self.collection.delete(ids=[str(context_id)])
        except Exception:
            pass

    def sync_all(self):
        """全ての approved なコンテキストを同期"""
        session = SessionLocal()
        try:
            contexts = session.query(PersonalContext).filter(
                PersonalContext.is_active == True,
                PersonalContext.status == "approved"
            ).all()
            
            if not contexts:
                return
            
            logger.info(f"Syncing {len(contexts)} approved personal contexts to ChromaDB...")
            
            ids = [str(c.id) for c in contexts]
            documents = [c.content for c in contexts]
            metadatas = [{"type": c.type, "id": c.id} for c in contexts]
            
            gemini = get_client()
            # バッチサイズ 100 制限に注意 (_embed_batch_with_retry が内部で管理)
            embeddings = _embed_batch_with_retry(gemini, documents)
            
            if embeddings:
                self.collection.upsert(
                    ids=ids,
                    embeddings=embeddings,
                    documents=documents,
                    metadatas=metadatas
                )
                logger.info(f"Synced {len(ids)} personal contexts to ChromaDB successfully.")
        finally:
            session.close()

if __name__ == "__main__":
    # 初期化時に全件同期
    logging.basicConfig(level=logging.INFO)
    mgr = PersonalContextManager()
    mgr.sync_all()
