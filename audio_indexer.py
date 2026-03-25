"""
audio_indexer.py - 音声ファイルの音声ベクトルインデックス登録

音声ファイルを 60 秒チャンクに分割し、Gemini Embedding 2 で直接ベクトル化して
ChromaDB の audio_vectors コレクションに登録する。

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

from config import CHROMA_DB_DIR, AUDIO_VECTORS_COLLECTION
from dense_indexer import get_chroma_client
from embedding_client import GeminiEmbedding2Client

logger = logging.getLogger(__name__)

CHUNK_DURATION_SEC = 60  # 音声チャンクの長さ（秒）

_AUDIO_MIME_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
}


def _get_duration(file_path: str) -> Optional[float]:
    """ffprobe で音声の長さを取得する。"""
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
        logger.warning("[AudioIndexer] ffprobe not found; cannot get duration")
    except Exception as e:
        logger.warning(f"[AudioIndexer] Duration check failed: {e}")
    return None


def _split_audio(file_path: str, ext: str, chunk_sec: int = CHUNK_DURATION_SEC) -> list[tuple[float, float, bytes]]:
    """
    音声を chunk_sec 秒単位で分割し、(start_sec, end_sec, bytes) のリストを返す。
    ffmpeg を使って WAV/MP3 チャンクを一時ファイルに書き出す。
    """
    duration = _get_duration(file_path)
    if duration is None:
        logger.warning(f"[AudioIndexer] Could not determine duration for {file_path}; treating as single chunk")
        duration = chunk_sec  # フォールバック: 1チャンクとして処理

    chunks = []
    start = 0.0
    output_ext = ".wav"  # WAV で出力（可逆）
    output_mime = "audio/wav"

    while start < duration:
        end = min(start + chunk_sec, duration)
        with tempfile.NamedTemporaryFile(suffix=output_ext, delete=False) as tmp:
            tmp_path = tmp.name

        try:
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", file_path,
                    "-ss", str(start),
                    "-t", str(end - start),
                    "-ar", "16000",  # 16kHz サンプリング
                    "-ac", "1",      # モノラル
                    tmp_path,
                ],
                capture_output=True, timeout=120,
            )
            if result.returncode != 0:
                logger.error(
                    f"[AudioIndexer] ffmpeg failed for chunk {start:.0f}-{end:.0f}s: "
                    f"{result.stderr.decode(errors='replace')[:200]}"
                )
            else:
                chunk_bytes = Path(tmp_path).read_bytes()
                chunks.append((start, end, chunk_bytes))
        except Exception as e:
            logger.error(f"[AudioIndexer] Error splitting chunk {start:.0f}-{end:.0f}s: {e}")
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

        start = end

    return chunks


class AudioIndexer:
    """音声ファイルを 60 秒チャンクに分割してベクトル登録する。"""

    def __init__(self):
        self.client = get_chroma_client(CHROMA_DB_DIR)
        self.collection = self.client.get_or_create_collection(
            name=AUDIO_VECTORS_COLLECTION,
            metadata={"hnsw:space": "cosine"},
        )
        self.embed_client = GeminiEmbedding2Client()

    async def index_file(
        self,
        file_path: str,
        source_pdf_hash: str,
        version_id: str,
        original_filename: str = "",
        project_id: str = "",
    ) -> int:
        """
        音声ファイルをインデックスする。

        Returns:
            登録したベクトル数
        """
        path = Path(file_path)
        ext = path.suffix.lower()
        orig_name = original_filename or path.name
        start_time = time.time()

        chunks = await asyncio.to_thread(_split_audio, str(path), ext)
        if not chunks:
            logger.warning(f"[AudioIndexer] No chunks generated for {orig_name}")
            return 0

        logger.info(f"[AudioIndexer] {orig_name}: {len(chunks)} chunks to embed")

        ids = []
        embeddings = []
        metadatas = []

        for idx, (start_sec, end_sec, chunk_bytes) in enumerate(chunks):
            try:
                vec = await self.embed_client.embed_audio(chunk_bytes, "audio/wav")
            except Exception as e:
                logger.error(
                    f"[AudioIndexer] Failed to embed chunk {idx} ({start_sec:.0f}-{end_sec:.0f}s) "
                    f"of {orig_name}: {e}"
                )
                continue

            chunk_id = str(uuid.uuid4())
            ids.append(chunk_id)
            embeddings.append(vec)
            metadatas.append({
                "source_id": source_pdf_hash,
                "vector_type": "audio",
                "chunk_index": idx,
                "start_time_sec": start_sec,
                "end_time_sec": end_sec,
                "original_filename": orig_name,
                "version_id": version_id,
                "project_id": project_id or "",
            })

        if ids:
            self.collection.upsert(ids=ids, embeddings=embeddings, metadatas=metadatas)

        elapsed = time.time() - start_time
        logger.info(
            f"[AudioIndexer] Indexed {len(ids)} audio vectors for {orig_name} "
            f"(version={version_id}, elapsed={elapsed:.1f}s, dim={len(embeddings[0]) if embeddings else 0})"
        )
        return len(ids)

    def delete_by_version(self, version_id: str):
        self.collection.delete(where={"version_id": version_id})
        logger.info(f"[AudioIndexer] Deleted audio vectors for version_id={version_id}")


def index_audio_file(
    file_path: str,
    source_pdf_hash: str,
    version_id: str,
    original_filename: str = "",
    project_id: str = "",
) -> int:
    """同期エントリーポイント（スレッドから呼び出す用）。"""
    indexer = AudioIndexer()
    return asyncio.run(
        indexer.index_file(file_path, source_pdf_hash, version_id, original_filename, project_id)
    )
