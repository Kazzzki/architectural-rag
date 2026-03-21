import uuid
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class ChunkBuilder:
    """
    Phase 3: 3層チャンク（Leaf, Section, Page）を構築する。
    
    - Page Chunk: 1ページ全体のコンテキスト。
    - Section Chunk: Markdownの見出し(#, ##)で区切られた論理セクション。
    - Leaf Chunk: 検索精度のための最小単位（200-400文字程度）。
    """
    def __init__(self, leaf_size: int = 300, leaf_overlap: int = 50):
        self.leaf_size = leaf_size
        self.leaf_overlap = leaf_overlap

    def build(self, md_text: str, ocr_results: List[Dict[str, Any]], source_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        MarkdownテキストとOCR結果からチャンク群を生成する。
        source_metadata: retriever が必要とする情報 (source_pdf_hash, rel_path, category 等)
        """
        source_metadata = source_metadata or {}
        all_chunks = []
        version_id = source_metadata.get("version_id", "unknown") # version_idをsource_metadataから取得

        # 1. Page Chunks
        # ocr_results は [{'text': '...', 'index': 0, 'label': 'Page 1', ...}] の形式
        page_chunks = []
        for res in ocr_results:
            page_text = res.get("text", "").strip()
            if not page_text:
                continue
                
            page_no = res.get("start_page", 0)
            chunk = {
                "id": f"page_{version_id}_{page_no}_{uuid.uuid4().hex[:6]}",
                "version_id": version_id,
                "chunk_type": "page",
                "content": page_text,
                "metadata": {
                    "page_no": page_no,
                    "label": res.get("label", f"Page {page_no}"),
                    **source_metadata
                }
            }
            page_chunks.append(chunk)
            all_chunks.append(chunk)

        # 2. Section Chunks
        # 見出しで分割する。OCR結果には [[PAGE_N]] や ## Page N が含まれている。
        # ここでは単純に "## " または "# " で分割を試みる。
        sections = self._split_by_headers(md_text) # Changed markdown_text to md_text
        section_chunks = []
        for i, sec_text in enumerate(sections):
            if len(sec_text.strip()) < 50: # あまりに短いものはスキップ
                continue
                
            chunk = {
                "id": f"section_{version_id}_{i}_{uuid.uuid4().hex[:6]}",
                "version_id": version_id,
                "chunk_type": "section",
                "content": sec_text.strip(),
                "metadata": {
                    "section_index": i,
                    **source_metadata
                }
            }
            section_chunks.append(chunk)
            all_chunks.append(chunk)

            # 3. Leaf Chunks (Sectionをさらに細分化)
            leaves = self._split_into_leaves(sec_text, self.leaf_size, self.leaf_overlap)
            for j, leaf_text in enumerate(leaves):
                leaf_chunk = {
                    "id": f"leaf_{version_id}_{i}_{j}_{uuid.uuid4().hex[:6]}",
                    "version_id": version_id,
                    "chunk_type": "leaf", # Changed from "type" to "chunk_type" to match existing schema
                    "content": leaf_text.strip(), # Added .strip() to match existing content field
                    "metadata": {
                        "section_id": chunk["id"], # Kept original section_id
                        "leaf_index": j, # Kept original leaf_index
                        **source_metadata
                    }
                }
                all_chunks.append(leaf_chunk)

        logger.info(f"[ChunkBuilder] Generated {len(all_chunks)} chunks (Pages: {len(page_chunks)}, Sections: {len(section_chunks)})")
        return all_chunks

    def _split_by_headers(self, text: str) -> List[str]:
        """Markdownの見出しでテキストを分割（ヘッダーをセクション先頭に保持）。"""
        # lookahead を使って分割点の直前で切る → ヘッダー行が次のセクションの先頭に残る
        pattern = r'(?m)(?=^(?:#{1,3}\s|\[\[PAGE_\d+\]\]))'
        parts = re.split(pattern, text)
        return [p for p in parts if p.strip()]

    def _split_into_leaves(self, text: str, size: int, overlap: int) -> List[str]:
        """テキストを固定サイズの小チャンクに分割。"""
        if not text:
            return []
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunk = text[start:end]
            chunks.append(chunk)
            if end >= len(text):
                break
            start += (size - overlap)
        return chunks
