"""
issue_memo_indexer.py — 課題因果メモ Markdown を ChromaDB へインデックス登録

設計方針:
  1メモ = 1 ChromaDB ドキュメント（チャンク分割しない）
  issue_id が ChromaDB の document ID と 1:1 対応
  検索結果がそのままメモ単位で返る
"""
import logging
import time
from pathlib import Path
from typing import Optional

import chromadb

from config import CHROMA_DB_DIR, ISSUE_MEMO_COLLECTION, ISSUE_MEMOS_DIR
from dense_indexer import _embed_batch_with_retry, get_chroma_client

logger = logging.getLogger(__name__)


class IssueMemoIndexer:
    """課題因果メモ Markdown ファイルを ChromaDB へ登録・削除・再インデックスする。"""

    def __init__(self):
        self.client = get_chroma_client(CHROMA_DB_DIR)
        self.collection = self.client.get_or_create_collection(
            name=ISSUE_MEMO_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def index_file(self, md_path: Path) -> bool:
        """
        1つの Markdown ファイル全文を埋め込み、ChromaDB へ upsert する。
        ファイル名から issue_id を取得（{issue_id}.md）。
        成功時 True、スキップ時 False を返す。
        """
        issue_id = md_path.stem  # ファイル名から .md を除いたもの = issue_id

        try:
            text = md_path.read_text(encoding="utf-8").strip()
        except OSError as e:
            logger.error(f"[IssueMemoIndexer] Failed to read {md_path}: {e}")
            return False

        if not text:
            logger.warning(f"[IssueMemoIndexer] Empty file skipped: {md_path}")
            return False

        # YAML フロントマターからメタデータ抽出
        metadata = _parse_frontmatter(text)
        metadata["issue_id"] = issue_id

        # ChromaDB は None 値を受け付けないので空文字に置換
        clean_meta = {k: (v if v is not None else "") for k, v in metadata.items()}

        # Gemini embedding
        from gemini_client import get_client
        gemini = get_client()
        embeddings = _embed_batch_with_retry(gemini, [text])

        if not embeddings:
            logger.error(f"[IssueMemoIndexer] Embedding failed for issue_id={issue_id}")
            return False

        emb = embeddings[0]
        norm = sum(v * v for v in emb) ** 0.5
        if norm < 1e-6:
            logger.warning(f"[IssueMemoIndexer] Zero vector for issue_id={issue_id}, skipped")
            return False

        self.collection.upsert(
            ids=[issue_id],
            embeddings=[emb],
            documents=[text],
            metadatas=[clean_meta],
        )
        logger.info(f"[IssueMemoIndexer] Indexed issue_id={issue_id} ({md_path.name})")
        return True

    def delete_from_index(self, issue_id: str) -> None:
        """ChromaDB から issue_id のエントリを削除する。"""
        try:
            self.collection.delete(ids=[issue_id])
            logger.info(f"[IssueMemoIndexer] Deleted issue_id={issue_id} from index")
        except Exception as e:
            logger.warning(f"[IssueMemoIndexer] Delete failed for issue_id={issue_id}: {e}")

    def reindex_all(self) -> int:
        """
        ISSUE_MEMOS_DIR 以下の全 .md ファイルを走査して upsert する。
        既存エントリは上書き（upsert）。追加済み件数を返す。
        """
        if not ISSUE_MEMOS_DIR.exists():
            logger.info("[IssueMemoIndexer] ISSUE_MEMOS_DIR does not exist, skipping reindex")
            return 0

        md_files = list(ISSUE_MEMOS_DIR.rglob("*.md"))
        count = 0
        for i, md_path in enumerate(md_files):
            try:
                ok = self.index_file(md_path)
                if ok:
                    count += 1
            except Exception as e:
                logger.error(f"[IssueMemoIndexer] reindex_all error for {md_path}: {e}")
            # レート制限対策: バッチ間スリープ
            if (i + 1) % 10 == 0:
                time.sleep(1.0)

        logger.info(f"[IssueMemoIndexer] reindex_all complete: {count}/{len(md_files)} files indexed")
        return count

    def search(
        self,
        query: str,
        project_name: Optional[str] = None,
        top_k: int = 8,
    ) -> list[dict]:
        """
        自然言語クエリで issue_memos コレクションを検索し、結果リストを返す。

        Returns:
            List of dicts with keys:
              issue_id, title, project_name, category, priority, status,
              score (0–1, 高いほど類似), snippet (先頭200文字)
        """
        from gemini_client import get_client
        from google.genai import types as genai_types

        gemini = get_client()

        # クエリを埋め込む（retrieval_query タスク）
        try:
            res = gemini.models.embed_content(
                model="models/gemini-embedding-001",
                contents=[query],
                config=genai_types.EmbedContentConfig(task_type="retrieval_query"),
            )
            query_embedding = res.embeddings[0].values
        except Exception as e:
            logger.error(f"[IssueMemoIndexer] Query embedding failed: {e}")
            return []

        # ChromaDB クエリ（project_name フィルタ付き）
        where_filter = {"project_name": project_name} if project_name else None
        try:
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(top_k, max(self.collection.count(), 1)),
                where=where_filter,
                include=["documents", "metadatas", "distances"],
            )
        except Exception as e:
            logger.error(f"[IssueMemoIndexer] ChromaDB query failed: {e}")
            return []

        output = []
        ids = results.get("ids", [[]])[0]
        docs = results.get("documents", [[]])[0]
        metas = results.get("metadatas", [[]])[0]
        dists = results.get("distances", [[]])[0]

        for issue_id, doc, meta, dist in zip(ids, docs, metas, dists):
            # cosine distance → similarity score (0–1)
            score = max(0.0, 1.0 - dist)
            # 本文スニペット（フロントマター除去後の先頭200文字）
            snippet = _extract_body_snippet(doc, max_chars=200)
            output.append(
                {
                    "issue_id": issue_id,
                    "title": meta.get("title", ""),
                    "project_name": meta.get("project_name", ""),
                    "category": meta.get("category", ""),
                    "priority": meta.get("priority", ""),
                    "status": meta.get("status", ""),
                    "score": round(score, 4),
                    "snippet": snippet,
                }
            )

        # スコア降順でソート
        output.sort(key=lambda x: x["score"], reverse=True)
        return output


# ------------------------------------------------------------------ #
# Internal helpers
# ------------------------------------------------------------------ #

def _parse_frontmatter(text: str) -> dict:
    """
    YAML フロントマター (--- ... ---) からメタデータを抽出する。
    title, project_name, category, priority, status, updated_at のみ取得。
    """
    meta: dict = {}
    if not text.startswith("---"):
        return meta

    end_idx = text.find("---", 3)
    if end_idx == -1:
        return meta

    fm_block = text[3:end_idx].strip()
    for line in fm_block.splitlines():
        if ":" not in line:
            continue
        key, _, val = line.partition(":")
        key = key.strip()
        val = val.strip()
        # project: フィールドは project_name としてマップ
        if key == "project":
            meta["project_name"] = val
        elif key in {"title", "category", "priority", "status", "updated_at"}:
            meta[key] = val

    return meta


def _extract_body_snippet(text: str, max_chars: int = 200) -> str:
    """フロントマター (--- ... ---) を除いた本文の先頭 max_chars 文字を返す。"""
    if text.startswith("---"):
        end_idx = text.find("---", 3)
        if end_idx != -1:
            text = text[end_idx + 3:].strip()
    return text[:max_chars]
