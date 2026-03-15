"""
research_engine/embedder.py

リサーチ結果を ChromaDB に格納する。
- 既存の get_chroma_client() シングルトンを使用
- 埋め込みは既存の _embed_batch_with_retry() (Gemini Embedding API) を使用
- 新規 PersistentClient インスタンスの生成は禁止
"""
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_SOURCES_COLLECTION = "research_sources"
_REPORTS_COLLECTION = "research_reports"
_MAX_SOURCE_CHARS = 2000
_CHUNK_SIZE = 1000
_CHUNK_OVERLAP = 200


def _chunk_text(text: str, size: int = _CHUNK_SIZE, overlap: int = _CHUNK_OVERLAP) -> list[str]:
    """テキストをオーバーラップ付きチャンクに分割する"""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        chunks.append(text[start:end])
        if end == len(text):
            break
        start += size - overlap
    return chunks


async def embed_research(
    research_id: str,
    sources: list[dict],
    report_markdown: str,
    question: str,
) -> None:
    """
    ソース一覧とレポートを ChromaDB に格納する。
    失敗時はログに記録するが例外は上位に伝播しない。
    """
    from dense_indexer import get_chroma_client, _embed_batch_with_retry
    from gemini_client import get_client

    try:
        chroma = get_chroma_client()
        gemini = get_client()
        sources_col = chroma.get_or_create_collection(
            _SOURCES_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
        reports_col = chroma.get_or_create_collection(
            _REPORTS_COLLECTION, metadata={"hnsw:space": "cosine"}
        )
    except Exception as e:
        logger.error(f"embed_research: ChromaDB init failed: {e}")
        return

    # ソースの格納
    source_docs, source_ids, source_metas = [], [], []
    for s in sources:
        # Markdownファイルがあればその内容を使用、なければsummaryで代替
        content = s.get("summary", "") or ""
        md_path = s.get("markdown_path", "")
        if md_path:
            try:
                with open(md_path, "r", encoding="utf-8") as f:
                    content = f.read()
            except Exception:
                pass
        content = content[:_MAX_SOURCE_CHARS]
        if not content:
            continue

        doc_id = f"{research_id}_src_{s.get('url', str(len(source_docs)))}"
        source_docs.append(content)
        source_ids.append(doc_id)
        source_metas.append({
            "research_id": research_id,
            "source_type": s.get("source_type", ""),
            "category": s.get("category", ""),
            "trust_score": float(s.get("trust_score", 0.5)),
            "url": s.get("url", ""),
            "title": s.get("title", ""),
        })

    if source_docs:
        try:
            embeddings = _embed_batch_with_retry(gemini, source_docs)
            if embeddings:
                sources_col.upsert(
                    ids=source_ids,
                    documents=source_docs,
                    embeddings=embeddings,
                    metadatas=source_metas,
                )
                logger.info(f"embed_research: {len(source_docs)} sources upserted")
        except Exception as e:
            logger.warning(f"embed_research: sources upsert failed: {e}")

    # レポートのチャンク格納
    if report_markdown:
        chunks = _chunk_text(report_markdown)
        chunk_docs, chunk_ids, chunk_metas = [], [], []
        completed_at = datetime.now(timezone.utc).isoformat()
        for i, chunk in enumerate(chunks):
            chunk_docs.append(chunk)
            chunk_ids.append(f"{research_id}_report_{i}")
            chunk_metas.append({
                "research_id": research_id,
                "question": question[:200],
                "domain": "",
                "completed_at": completed_at,
            })
        try:
            embeddings = _embed_batch_with_retry(gemini, chunk_docs)
            if embeddings:
                reports_col.upsert(
                    ids=chunk_ids,
                    documents=chunk_docs,
                    embeddings=embeddings,
                    metadatas=chunk_metas,
                )
                logger.info(f"embed_research: {len(chunk_docs)} report chunks upserted")
        except Exception as e:
            logger.warning(f"embed_research: report upsert failed: {e}")
