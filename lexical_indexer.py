import re
import sqlite3
import logging
import json
from typing import List, Dict, Any
from database import DB_PATH

logger = logging.getLogger(__name__)

class LexicalIndexer:
    """
    Phase 3: SQLite FTS5 を用いた全文検索インデックスを管理する。
    """
    def __init__(self):
        # DB_PATH は sqlite:///path/to/db の形式
        self.db_file = DB_PATH.replace("sqlite:///", "")
        self._init_fts()

    def _init_fts(self):
        """FTS5 仮想テーブルの初期化"""
        with sqlite3.connect(self.db_file) as conn:
            # 外部コンテンツテーブルあるいは単独仮想テーブル
            # ここではシンプルに仮想テーブルを作成
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS v_chunks_fts USING fts5(
                    content,
                    version_id UNINDEXED,
                    chunk_id UNINDEXED,
                    metadata_json UNINDEXED,
                    tokenize='unicode61'
                )
            """)
            conn.commit()

    def upsert_chunks(self, version_id: str, chunks: List[Dict[str, Any]]):
        """チャンクを FTS インデックスに登録。"""
        if not chunks:
            return

        leaf_chunks = [c for c in chunks if c["chunk_type"] == "leaf"]
        if not leaf_chunks:
            return

        with sqlite3.connect(self.db_file) as conn:
            # 既存のバージョンデータを削除 (べき等性の確保)
            conn.execute("DELETE FROM v_chunks_fts WHERE version_id = ?", (version_id,))
            
            # 挿入
            data = [
                (c["content"], version_id, c["id"], json.dumps(c.get("metadata", {}))) 
                for c in leaf_chunks
            ]
            conn.executemany(
                "INSERT INTO v_chunks_fts (content, version_id, chunk_id, metadata_json) VALUES (?, ?, ?, ?)",
                data
            )
            conn.commit()
            
        logger.info(f"[LexicalIndexer] Indexed {len(leaf_chunks)} leaf chunks for {version_id}")

    def delete_by_version(self, version_id: str):
        """特定のバージョンのインデックスを削除。"""
        with sqlite3.connect(self.db_file) as conn:
            conn.execute("DELETE FROM v_chunks_fts WHERE version_id = ?", (version_id,))
            conn.commit()

    def _sanitize_fts_query(self, query: str) -> str:
        """FTS5 で問題となる特殊文字を除去する。
        FTS5 は " ^ * - ( ) などを演算子として解釈するため、
        そのままクエリに渡すと OperationalError になる。
        """
        sanitized = re.sub(r'["\'\-\*\^\(\)\\]', ' ', query)
        return ' '.join(sanitized.split())

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """全文検索を実行。クエリサニタイズと例外ハンドリング付き。"""
        sanitized = self._sanitize_fts_query(query)
        if not sanitized:
            return []
        try:
            with sqlite3.connect(self.db_file) as conn:
                conn.row_factory = sqlite3.Row
                # FTS5のBM25スコアでソート
                cursor = conn.execute("""
                    SELECT chunk_id, version_id, content, metadata_json, bm25(v_chunks_fts) as score
                    FROM v_chunks_fts
                    WHERE v_chunks_fts MATCH ?
                    ORDER BY score
                    LIMIT ?
                """, (sanitized, limit))

                results = []
                for row in cursor:
                    results.append({
                        "chunk_id": row["chunk_id"],
                        "version_id": row["version_id"],
                        "content": row["content"],
                        "metadata": json.loads(row["metadata_json"]),
                        "score": row["score"]
                    })
                return results
        except Exception as e:
            logger.warning(f"[LexicalIndexer] FTS search failed for query '{query}': {e}")
            return []
