"""
embedding_client.py - Gemini Embedding 2 マルチモーダル埋め込みクライアント

Gemini Embedding 2 (gemini-embedding-2-preview) を使い、テキスト・画像・音声・
動画・インターリーブの各モダリティに対応した埋め込みを非同期で取得する。

特徴:
- asyncio.Semaphore で同時実行数を制限 (デフォルト 5)
- 429 / タイムアウトに対して指数バックオフでリトライ (最大 4 回)
- output_dimensionality 対応 (デフォルト 3072)
- dimensions < 3072 の場合は L2 正規化を自動適用
- gemini_client.get_client() のシングルトンを再利用
"""

import asyncio
import logging
import math
import time
from typing import Any

from google.genai import types

from config import EMBEDDING_MODEL_V2, EMBED_SEMAPHORE_LIMIT
from gemini_client import get_client

logger = logging.getLogger(__name__)

_EMBED_MAX_RETRIES = 4
_EMBED_BASE_WAIT = 2.0  # 指数バックオフ基準秒数 (2^(attempt+1))

# モジュールレベルのセマフォ (同一プロセス内で共有)
_semaphore = asyncio.Semaphore(EMBED_SEMAPHORE_LIMIT)


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    if norm < 1e-10:
        return vec
    return [v / norm for v in vec]


def _maybe_normalize(vec: list[float], dimensions: int) -> list[float]:
    """3072 次元未満の場合のみ L2 正規化を適用する。"""
    if dimensions < 3072:
        return _l2_normalize(vec)
    return vec


def _embed_sync(contents: Any, task_type: str, dimensions: int) -> list[float]:
    """同期 Gemini API 呼び出し (asyncio.to_thread でラップして使う)。"""
    client = get_client()
    config = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=dimensions,
    )
    for attempt in range(_EMBED_MAX_RETRIES):
        try:
            res = client.models.embed_content(
                model=EMBEDDING_MODEL_V2,
                contents=contents,
                config=config,
            )
            vec = res.embeddings[0].values
            return _maybe_normalize(list(vec), dimensions)
        except Exception as e:
            wait = _EMBED_BASE_WAIT ** (attempt + 1)
            if attempt < _EMBED_MAX_RETRIES - 1:
                logger.warning(
                    f"[EmbeddingClient] embed_content failed "
                    f"(attempt {attempt + 1}/{_EMBED_MAX_RETRIES}): {e} — retrying in {wait:.1f}s"
                )
                time.sleep(wait)
            else:
                logger.error(
                    f"[EmbeddingClient] embed_content gave up after {_EMBED_MAX_RETRIES} attempts: {e}"
                )
                raise


def _embed_batch_sync(
    contents_list: list[Any], task_type: str, dimensions: int
) -> list[list[float]]:
    """複数コンテンツをバッチで埋め込む同期版。"""
    client = get_client()
    config = types.EmbedContentConfig(
        task_type=task_type,
        output_dimensionality=dimensions,
    )
    for attempt in range(_EMBED_MAX_RETRIES):
        try:
            res = client.models.embed_content(
                model=EMBEDDING_MODEL_V2,
                contents=contents_list,
                config=config,
            )
            return [_maybe_normalize(list(e.values), dimensions) for e in res.embeddings]
        except Exception as e:
            wait = _EMBED_BASE_WAIT ** (attempt + 1)
            if attempt < _EMBED_MAX_RETRIES - 1:
                logger.warning(
                    f"[EmbeddingClient] batch embed_content failed "
                    f"(attempt {attempt + 1}/{_EMBED_MAX_RETRIES}): {e} — retrying in {wait:.1f}s"
                )
                time.sleep(wait)
            else:
                logger.error(
                    f"[EmbeddingClient] batch embed_content gave up after {_EMBED_MAX_RETRIES} attempts: {e}"
                )
                raise


class GeminiEmbedding2Client:
    """
    Gemini Embedding 2 の非同期クライアント。

    すべての embed_* メソッドは async で、セマフォにより同時実行数を制限する。
    """

    async def embed_text(
        self,
        text: str,
        task_type: str = "RETRIEVAL_DOCUMENT",
        dimensions: int = 3072,
    ) -> list[float]:
        """テキストを埋め込みベクトルに変換する。"""
        contents = types.Content(
            parts=[types.Part.from_text(text=text)]
        )
        async with _semaphore:
            result = await asyncio.to_thread(_embed_sync, contents, task_type, dimensions)
        logger.debug(f"[EmbeddingClient] embed_text: dim={len(result)}, task={task_type}")
        return result

    async def embed_image(
        self,
        image_bytes: bytes,
        mime_type: str,
        dimensions: int = 3072,
    ) -> list[float]:
        """画像バイナリを直接埋め込みベクトルに変換する。"""
        contents = types.Content(
            parts=[types.Part.from_bytes(data=image_bytes, mime_type=mime_type)]
        )
        async with _semaphore:
            result = await asyncio.to_thread(
                _embed_sync, contents, "RETRIEVAL_DOCUMENT", dimensions
            )
        logger.debug(f"[EmbeddingClient] embed_image: dim={len(result)}, mime={mime_type}")
        return result

    async def embed_audio(
        self,
        audio_bytes: bytes,
        mime_type: str,
        dimensions: int = 3072,
    ) -> list[float]:
        """音声バイナリを直接埋め込みベクトルに変換する。"""
        contents = types.Content(
            parts=[types.Part.from_bytes(data=audio_bytes, mime_type=mime_type)]
        )
        async with _semaphore:
            result = await asyncio.to_thread(
                _embed_sync, contents, "RETRIEVAL_DOCUMENT", dimensions
            )
        logger.debug(f"[EmbeddingClient] embed_audio: dim={len(result)}, mime={mime_type}")
        return result

    async def embed_video(
        self,
        video_bytes: bytes,
        mime_type: str,
        dimensions: int = 3072,
    ) -> list[float]:
        """動画バイナリを直接埋め込みベクトルに変換する。"""
        contents = types.Content(
            parts=[types.Part.from_bytes(data=video_bytes, mime_type=mime_type)]
        )
        async with _semaphore:
            result = await asyncio.to_thread(
                _embed_sync, contents, "RETRIEVAL_DOCUMENT", dimensions
            )
        logger.debug(f"[EmbeddingClient] embed_video: dim={len(result)}, mime={mime_type}")
        return result

    async def embed_interleaved(
        self,
        parts: list[dict],
        dimensions: int = 3072,
    ) -> list[float]:
        """
        テキストと画像を組み合わせたインターリーブ埋め込み。

        parts の各要素は以下のいずれかの形式:
            {"type": "text",  "content": str}
            {"type": "image", "content": bytes, "mime_type": str}
        """
        content_parts = []
        for p in parts:
            if p["type"] == "text":
                content_parts.append(types.Part.from_text(text=p["content"]))
            elif p["type"] == "image":
                content_parts.append(
                    types.Part.from_bytes(data=p["content"], mime_type=p["mime_type"])
                )
        contents = types.Content(parts=content_parts)
        async with _semaphore:
            result = await asyncio.to_thread(
                _embed_sync, contents, "RETRIEVAL_DOCUMENT", dimensions
            )
        logger.debug(f"[EmbeddingClient] embed_interleaved: dim={len(result)}, parts={len(parts)}")
        return result

    async def embed_batch(
        self,
        contents: list[Any],
        dimensions: int = 3072,
    ) -> list[list[float]]:
        """
        複数コンテンツを一括で埋め込む。

        contents の各要素は types.Content または str (テキスト)。
        str の場合は自動的に types.Content に変換する。
        """
        converted = []
        for c in contents:
            if isinstance(c, str):
                converted.append(
                    types.Content(parts=[types.Part.from_text(text=c)])
                )
            else:
                converted.append(c)

        async with _semaphore:
            results = await asyncio.to_thread(
                _embed_batch_sync, converted, "RETRIEVAL_DOCUMENT", dimensions
            )
        logger.debug(
            f"[EmbeddingClient] embed_batch: count={len(results)}, dim={len(results[0]) if results else 0}"
        )
        return results
