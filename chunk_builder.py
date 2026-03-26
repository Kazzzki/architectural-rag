import uuid
import re
import hashlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# 句点・感嘆符・疑問符・全角スペース区切り（日本語文末判定）
_SENTENCE_END_RE = re.compile(r'(?<=[。！？\n])')

# ヘッダー行パターン（lookahead で分割するのでヘッダー行が各チャンクの先頭に残る）
_HEADER_SPLIT_RE = re.compile(r'(?m)(?=^(?:#{1,3}\s+|\[\[PAGE_\d+\]\]))', )

# [[PAGE_N]] マーカーからページ番号を抽出する正規表現
_PAGE_MARKER_RE = re.compile(r'\[\[PAGE_(\d+)\]\]')


class ChunkBuilder:
    """
    Phase 3: 3層チャンク（Leaf, Section, Page）を構築する。

    - Page Chunk: 1ページ全体のコンテキスト。
    - Section Chunk: Markdownの見出し(#, ##)で区切られた論理セクション。
    - Leaf Chunk: 検索精度のための最小単位（日本語向け 500 文字程度）。
    """
    def __init__(self, leaf_size: int = 600, leaf_overlap: int = 120):
        # 日本語向け推奨: 500〜800文字, overlap 100〜150文字
        self.leaf_size = leaf_size
        self.leaf_overlap = leaf_overlap

    def build(self, md_text: str, ocr_results: List[Dict[str, Any]], source_metadata: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        MarkdownテキストとOCR結果からチャンク群を生成する。
        source_metadata: retriever が必要とする情報 (source_pdf_hash, rel_path, category 等)
        """
        source_metadata = source_metadata or {}
        all_chunks = []
        version_id = source_metadata.get("version_id", "unknown")
        source_file = source_metadata.get("rel_path") or source_metadata.get("filename", "")

        # 1. Page Chunks
        page_chunks = []
        for res in ocr_results:
            page_text = res.get("text", "").strip()
            if not page_text:
                continue

            page_no = res.get("start_page", 0)
            # 決定論的ID: UUIDなし（同一version_id・同一ページは常に同じIDになり重複防止）
            chunk_id = f"page_{version_id}_{page_no}"
            chunk = {
                "id": chunk_id,
                "version_id": version_id,
                "chunk_type": "page",
                "content": page_text,
                "metadata": {
                    "page_number": page_no,
                    "section_title": "",
                    "source_file": source_file,
                    "label": res.get("label", f"Page {page_no}"),
                    **source_metadata
                }
            }
            page_chunks.append(chunk)
            all_chunks.append(chunk)

        # 2. Section Chunks
        # lookahead split でヘッダー行を各セクションの先頭に保持する
        raw_sections = self._split_by_headers(md_text)

        # [[PAGE_N]] だけのセクションをマージし、ページ番号を後続セクションに引き継ぐ
        sections = self._merge_page_marker_sections(raw_sections)

        section_chunks = []
        for i, (sec_text, sec_page) in enumerate(sections):
            stripped = sec_text.strip()
            if len(stripped) < 50:
                continue

            # セクションタイトルを1行目から抽出
            section_title = self._extract_title(stripped.splitlines()[0])

            # セクション内に追加の [[PAGE_N]] マーカーがあればそこからもページ番号を抽出
            section_page = self._extract_page_number(stripped) or sec_page

            # セクションコンテンツから [[PAGE_N]] マーカーを除去（メタデータに移行済み）
            clean_content = _PAGE_MARKER_RE.sub('', stripped).strip()

            # 決定論的ID
            chunk_id = f"section_{version_id}_{i}"
            chunk = {
                "id": chunk_id,
                "version_id": version_id,
                "chunk_type": "section",
                "content": clean_content,
                "metadata": {
                    "section_index": i,
                    "section_title": section_title,
                    "page_number": section_page,
                    "source_file": source_file,
                    **source_metadata
                }
            }
            section_chunks.append(chunk)
            all_chunks.append(chunk)

            # 3. Leaf Chunks (Sectionをさらに細分化)
            # セクション内の [[PAGE_N]] マーカー位置をスキャンし、各リーフにページ番号を割り当て
            page_markers = self._scan_page_markers(stripped)
            leaves = self._split_into_leaves(stripped, self.leaf_size, self.leaf_overlap)
            char_offset = 0
            for j, leaf_text in enumerate(leaves):
                leaf_stripped = leaf_text.strip()
                # 50文字未満の極短チャンクはスキップ
                if len(leaf_stripped) < 50:
                    continue

                # リーフの開始位置に基づいてページ番号を決定
                leaf_start = stripped.find(leaf_stripped, char_offset)
                if leaf_start < 0:
                    leaf_start = char_offset
                leaf_page = self._resolve_page_at(leaf_start, page_markers, section_page)
                char_offset = leaf_start + 1

                # リーフコンテンツから [[PAGE_N]] マーカーを除去
                clean_leaf = _PAGE_MARKER_RE.sub('', leaf_stripped).strip()
                if len(clean_leaf) < 50:
                    continue

                # 決定論的ID
                leaf_id = f"leaf_{version_id}_{i}_{j}"
                leaf_chunk = {
                    "id": leaf_id,
                    "version_id": version_id,
                    "chunk_type": "leaf",
                    "content": clean_leaf,
                    "metadata": {
                        "section_id": chunk_id,
                        "section_title": section_title,
                        "leaf_index": j,
                        "page_number": leaf_page,
                        "source_file": source_file,
                        **source_metadata
                    }
                }
                all_chunks.append(leaf_chunk)

        logger.info(f"[ChunkBuilder] Generated {len(all_chunks)} chunks (Pages: {len(page_chunks)}, Sections: {len(section_chunks)})")
        return all_chunks

    @staticmethod
    def _merge_page_marker_sections(raw_sections: List[str]) -> List[Tuple[str, Optional[int]]]:
        """
        [[PAGE_N]] だけのセクションを消費し、ページ番号を後続セクションに引き継ぐ。
        戻り値: [(セクションテキスト, ページ番号), ...]
        """
        merged: List[Tuple[str, Optional[int]]] = []
        pending_page: Optional[int] = None

        for sec in raw_sections:
            stripped = sec.strip()
            if not stripped:
                continue
            # [[PAGE_N]] だけのセクションかチェック
            m = _PAGE_MARKER_RE.fullmatch(stripped)
            if m:
                pending_page = int(m.group(1))
                continue
            # 通常のセクション: pending_page があればそれを引き継ぐ
            merged.append((sec, pending_page))
            # pending_page はリセットしない（次のPAGEマーカーまで維持）

        return merged

    @staticmethod
    def _extract_page_number(text: str) -> Optional[int]:
        """テキスト内の最初の [[PAGE_N]] マーカーからページ番号を抽出する。"""
        m = _PAGE_MARKER_RE.search(text)
        return int(m.group(1)) if m else None

    @staticmethod
    def _scan_page_markers(text: str) -> List[Tuple[int, int]]:
        """テキスト内の全 [[PAGE_N]] マーカーの (文字位置, ページ番号) リストを返す。"""
        return [(m.start(), int(m.group(1))) for m in _PAGE_MARKER_RE.finditer(text)]

    @staticmethod
    def _resolve_page_at(char_pos: int, page_markers: List[Tuple[int, int]], fallback: Optional[int]) -> Optional[int]:
        """文字位置に基づき、直近の [[PAGE_N]] マーカーのページ番号を返す。"""
        resolved = fallback
        for marker_pos, page_num in page_markers:
            if marker_pos <= char_pos:
                resolved = page_num
            else:
                break
        return resolved

    def _split_by_headers(self, text: str) -> List[str]:
        """
        Markdownの見出しでテキストを分割。
        lookahead split によりヘッダー行は次チャンクの先頭に残る。
        """
        parts = _HEADER_SPLIT_RE.split(text)
        return [p for p in parts if p.strip()]

    def _extract_title(self, header_line: str) -> str:
        """ヘッダー行からタイトル文字列を抽出する。"""
        # ## タイトル → タイトル
        title = re.sub(r'^#{1,3}\s*', '', header_line.strip())
        # [[PAGE_N]] マーカーを除去
        title = re.sub(r'^\[\[PAGE_\d+\]\]\s*', '', title)
        return title.strip()

    def _split_into_leaves(self, text: str, size: int, overlap: int) -> List[str]:
        """
        テキストを日本語文末（句点・感嘆符・疑問符・改行）境界を優先して分割。
        境界が見つからない場合は固定サイズでフォールバック。
        """
        if not text:
            return []
        chunks = []
        start = 0
        text_len = len(text)
        while start < text_len:
            end = min(start + size, text_len)
            if end < text_len:
                # [start, end] の範囲内で最後の文末境界を探す
                segment = text[start:end]
                last_boundary = -1
                for m in _SENTENCE_END_RE.finditer(segment):
                    last_boundary = m.start()
                if last_boundary > 0:
                    end = start + last_boundary
            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= text_len:
                break
            start = end - overlap
            # 無限ループ防止: 進んでいなければ強制前進
            if start <= (end - size):
                start = end
        return chunks
