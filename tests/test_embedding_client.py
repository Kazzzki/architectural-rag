"""
tests/test_embedding_client.py - GeminiEmbedding2Client のユニットテスト

実際の Gemini API を呼ばずにモックを使ってテストする。
"""

import asyncio
import math
import time
from unittest.mock import MagicMock, patch

import pytest

from embedding_client import GeminiEmbedding2Client, _l2_normalize, _maybe_normalize


# ---- ヘルパー ----

def make_mock_embedding(values: list[float]):
    """Gemini API のレスポンスを模倣するモックオブジェクトを返す。"""
    emb = MagicMock()
    emb.values = values
    resp = MagicMock()
    resp.embeddings = [emb]
    return resp


def make_mock_batch_embeddings(values_list: list[list[float]]):
    """バッチ埋め込みレスポンスのモック。"""
    embeddings = []
    for v in values_list:
        e = MagicMock()
        e.values = v
        embeddings.append(e)
    resp = MagicMock()
    resp.embeddings = embeddings
    return resp


VEC_3072 = [0.1] * 3072
VEC_768 = [0.5, 0.5, 0.0]  # 3次元で代用（normalization確認用）


# ---- L2正規化テスト ----

def test_l2_normalize_basic():
    vec = [3.0, 4.0]
    result = _l2_normalize(vec)
    assert abs(result[0] - 0.6) < 1e-6
    assert abs(result[1] - 0.8) < 1e-6


def test_l2_normalize_zero_vector():
    vec = [0.0, 0.0, 0.0]
    result = _l2_normalize(vec)
    assert result == [0.0, 0.0, 0.0]


def test_maybe_normalize_3072_no_change():
    """3072次元の場合は正規化しない。"""
    vec = [2.0, 0.0]
    result = _maybe_normalize(vec, 3072)
    assert result == [2.0, 0.0]


def test_maybe_normalize_768_normalizes():
    """768次元 (<3072) の場合は正規化する。"""
    vec = [3.0, 4.0]
    result = _maybe_normalize(vec, 768)
    norm = math.sqrt(sum(v * v for v in result))
    assert abs(norm - 1.0) < 1e-6


# ---- embed_text テスト ----

@pytest.mark.asyncio
async def test_embed_text_success():
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_embedding(VEC_3072)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        result = await client.embed_text("テストテキスト")

    assert len(result) == 3072
    assert result[0] == pytest.approx(0.1)


@pytest.mark.asyncio
async def test_embed_text_with_768_dimensions_normalizes():
    client = GeminiEmbedding2Client()
    raw = [3.0, 4.0, 0.0]
    mock_resp = make_mock_embedding(raw)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        result = await client.embed_text("test", dimensions=768)

    norm = math.sqrt(sum(v * v for v in result))
    assert abs(norm - 1.0) < 1e-6


# ---- embed_image テスト ----

@pytest.mark.asyncio
async def test_embed_image_success():
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_embedding(VEC_3072)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        result = await client.embed_image(b"\x89PNG...", "image/png")

    assert len(result) == 3072


# ---- embed_audio テスト ----

@pytest.mark.asyncio
async def test_embed_audio_success():
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_embedding(VEC_3072)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        result = await client.embed_audio(b"mp3data", "audio/mpeg")

    assert len(result) == 3072


# ---- embed_video テスト ----

@pytest.mark.asyncio
async def test_embed_video_success():
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_embedding(VEC_3072)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        result = await client.embed_video(b"mp4data", "video/mp4")

    assert len(result) == 3072


# ---- embed_interleaved テスト ----

@pytest.mark.asyncio
async def test_embed_interleaved_success():
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_embedding(VEC_3072)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        parts = [
            {"type": "image", "content": b"pngbytes", "mime_type": "image/png"},
            {"type": "text", "content": "1階平面図の説明テキスト"},
        ]
        result = await client.embed_interleaved(parts)

    assert len(result) == 3072


# ---- embed_batch テスト ----

@pytest.mark.asyncio
async def test_embed_batch_success():
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_batch_embeddings([VEC_3072, VEC_3072])

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.return_value = mock_resp
        mock_get_client.return_value = mock_genai

        results = await client.embed_batch(["テキスト1", "テキスト2"])

    assert len(results) == 2
    assert len(results[0]) == 3072


# ---- リトライ動作テスト ----

@pytest.mark.asyncio
async def test_embed_text_retries_on_429(monkeypatch):
    """429エラーが発生した後に成功するケースを確認する。"""
    client = GeminiEmbedding2Client()
    mock_resp = make_mock_embedding(VEC_3072)

    call_count = 0

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise Exception("429 RESOURCE_EXHAUSTED")
        return mock_resp

    # sleep をスキップして高速化
    monkeypatch.setattr("embedding_client.time.sleep", lambda _: None)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.side_effect = side_effect
        mock_get_client.return_value = mock_genai

        result = await client.embed_text("リトライテスト")

    assert call_count == 3
    assert len(result) == 3072


@pytest.mark.asyncio
async def test_embed_text_gives_up_after_max_retries(monkeypatch):
    """最大リトライ回数を超えた場合は例外を送出する。"""
    client = GeminiEmbedding2Client()

    monkeypatch.setattr("embedding_client.time.sleep", lambda _: None)

    with patch("embedding_client.get_client") as mock_get_client:
        mock_genai = MagicMock()
        mock_genai.models.embed_content.side_effect = Exception("Persistent error")
        mock_get_client.return_value = mock_genai

        with pytest.raises(Exception, match="Persistent error"):
            await client.embed_text("失敗テスト")
