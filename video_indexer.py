"""
video_indexer.py - 動画ファイルの動画ベクトルインデックス登録

動画ファイルを 120 秒セグメントに分割し、Gemini Embedding 2 で直接ベクトル化して
ChromaDB の video_vectors コレクションに登録する。

ffmpeg/ffprobe コマンドを subprocess で呼び出す。
"""

import asyncio
import logging
import os
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional

from config import CHROMA_DB_DIR, VIDEO_VECTORS_COLLECTION
from dense_indexer import get_chroma_client
from embedding_client import GeminiEmbedding2Client

logger = logging.getLogger(__name__)

SEGMENT_DURATION_SEC = 120  # 動画セグメントの長さ（秒）


def _get_duration(file_path: str) -> Optional[float]:
    """ffprobe で動画の長さを取得する。"""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", file_path,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            import json
            info = json.loads(result.stdout)
            dur = info.get("format", {}).get("duration")
            return float(dur) if dur else None
    except FileNotFoundError:
        logger.warning("[VideoIndexer] ffprobe not found; cannot get duration")
    except Exception as e:
        logger.warning(f"[VideoIndexer] Duration check failed: {e}")
    return None


def _split_video(
    file_path: str, segment_sec: int = SEGMENT_DURATION_SEC
) -> list[tuple[float, float, bytes]]:
    """
    動画を segment_sec 秒単位で分割し、(start_sec, end_sec, bytes) のリストを返す。
    ffmpeg を使って MP4 セグメントを一時ファイルに書き出す。
    """
    duration = _get_duration(file_path)
    if duration is None:
        logger.warning(f"[VideoIndexer] Could not determine duration for {file_path}; treating as single segment")
        duration = segment_sec

    segments = []
    start = 0.0

    while start < duration:
        end = min(start + segment_sec, duration)
        with tempfile.NamedTemporaryFile(suffix=".mp4", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", file_path,
                    "-ss", str(start),
                    "-t", str(end - start),
                    "-c", "copy",  # 再エンコードなしでコピー（高速）
                    tmp_path,
                ],
                capture_output=True, timeout=180,
            )
            if result.returncode != 0:
                logger.error(
                    f"[VideoIndexer] ffmpeg failed for segment {start:.0f}-{end:.0f}s: "
                    f"{result.stderr.decode(errors='replace')[:200]}"
                )
            else:
                segment_bytes = Path(tmp_path).read_bytes()
                segments.append((start, end, segment_bytes))
        except Exception as e:
            logger.error(f"[VideoIndexer] Error splitting segment {start:.0f}-{end:.0f}s: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        start = end

    return segments


class VideoIndexer:
    """動画ファイルを 120 秒セグメントに分割してベクトル登録する。"""

    def __init__(self):
        self.client = get_chroma_client(CHROMA_DB_DIR)
        self.collection = self.client.get_or_create_collection(
            name=VIDEO_VECTORS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self.embed_client = GeminiEmbedding2Client()

    async def index_file(
        self,
        file_path: str,
        source_pdf_hash: str,
        version_id: str,
        original_filename: str = "",
    ) -> int:
        """
        動画ファイルをインデックスする。

        Returns:
            登録したベクトル数
        """
        path = Path(file_path)
        orig_name = original_filename or path.name
        start_time = time.time()

        segments = await asyncio.to_thread(_split_video, str(path))
        if not segments:
            logger.warning(f"[VideoIndexer] No segments generated for {orig_name}")
            return 0

        logger.info(f"[VideoIndexer] {orig_name}: {len(segments)} segments to embed")

        ids = []
        embeddings = []
        metadatas = []

        for idx, (start_sec, end_sec, segment_bytes) in enumerate(segments):
            try:
                vec = await self.embed_client.embed_video(segment_bytes, "video/mp4")
            except Exception as e:
                logger.error(
                    f"[VideoIndexer] Failed to embed segment {idx} ({start_sec:.0f}-{end_sec:.0f}s) "
                    f"of {orig_name}: {e}"
                )
                continue

            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)
            embeddings.append(vec)
            metadatas.append({
                "source_id": source_pdf_hash,
                "vector_type": "video",
                "segment_index": idx,
                "start_time_sec": start_sec,
                "end_time_sec": end_sec,
                "original_filename": orig_name,
                "version_id": version_id,
            })

        if ids:
            self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

        elapsed = time.time() - start_time
        logger.info(
            f"[VideoIndexer] Indexed {len(ids)} video vectors for {orig_name} "
            f"(version={version_id}, elapsed={elapsed:.1f}s, dim={len(embeddings[0]) if embeddings else 0})"
        )
        return len(ids)

    def delete_by_version(self, version_id: str):
        self.collection.delete(where={"version_id": version_id})
        logger.info(f"[VideoIndexer] Deleted video vectors for version_id={version_id}")


def index_video_file(
    file_path: str,
    source_pdf_hash: str,
    version_id: str,
    original_filename: str = "",
) -> int:
    """同期エントリーポイント（スレッドから呼び出す用）。"""
    indexer = VideoIndexer()
    return asyncio.run(
        indexer.index_file(file_path, source_pdf_hash, version_id, original_filename)
    )
