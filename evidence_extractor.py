# evidence_extractor.py — Post-Retrieval 構造化数値抽出
#
# 検索後にチャンクからオンデマンドで数値・仕様値を構造化抽出する。
# 事前DB保存は行わない（原本が常にsingle source of truth）。

import json
import logging
import hashlib
from functools import lru_cache
from typing import List, Dict, Any, Optional
from concurrent.futures import ThreadPoolExecutor, TimeoutError

from gemini_client import get_client
from google.genai import types
from utils.retry import sync_retry

logger = logging.getLogger(__name__)

# 抽出タイムアウト（秒）
EXTRACTION_TIMEOUT = 5.0

_EXTRACTION_PROMPT = """以下の検索結果テキストから、ユーザーの質問に関連する数値・仕様値を構造化抽出してください。

質問: {query}

検索結果テキスト:
{chunk_text}

以下のJSON配列を返してください（Markdownコードブロック不要）:
[
  {{
    "item": "項目名（例: コンクリート強度）",
    "value": "値（例: Fc=24）",
    "unit": "単位（例: N/mm²）",
    "scope": "適用範囲（例: 基礎・地中梁）",
    "source_text": "該当する原文テキスト（50文字以内の抜粋）"
  }}
]

抽出するものがない場合は空配列 [] を返してください。
原文テキストに明示的に記載されていない値は抽出しないでください。
"""


def _chunk_hash(text: str) -> str:
    """チャンクテキストのハッシュを生成（キャッシュキー用）"""
    return hashlib.md5(text[:500].encode()).hexdigest()


# LRUキャッシュ: 同一チャンクの再抽出を避ける
_extraction_cache: Dict[str, List[Dict[str, Any]]] = {}
_CACHE_MAX_SIZE = 100


def _get_cached(key: str) -> Optional[List[Dict[str, Any]]]:
    return _extraction_cache.get(key)


def _set_cache(key: str, value: List[Dict[str, Any]]):
    if len(_extraction_cache) >= _CACHE_MAX_SIZE:
        # 古いエントリを1つ削除（簡易LRU）
        oldest_key = next(iter(_extraction_cache))
        del _extraction_cache[oldest_key]
    _extraction_cache[key] = value


@sync_retry(max_retries=1, base_wait=0.5)
def _extract_from_chunk(query: str, chunk_text: str) -> List[Dict[str, Any]]:
    """単一チャンクから構造化データを抽出する"""
    client = get_client()
    from config import GEMINI_MODEL_RAG

    prompt = _EXTRACTION_PROMPT.format(
        query=query,
        chunk_text=chunk_text[:2000],
    )
    response = client.models.generate_content(
        model=GEMINI_MODEL_RAG,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=1024,
        ),
    )
    text = response.text.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        text = text.rsplit("```", 1)[0]
    return json.loads(text)


def extract_structured_values(
    query: str,
    chunks: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """検索結果チャンクから数値・仕様値を構造化抽出する。

    常に原文テキストと出典情報を含む。タイムアウト時は空リストを返す。

    Returns:
        [{item, value, unit, scope, source_text, source_id, page, confidence}]
    """
    if not chunks:
        return []

    results: List[Dict[str, Any]] = []

    def _process_chunk(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        text = chunk.get("context_text") or chunk.get("document", "")
        if not text or len(text) < 20:
            return []

        cache_key = _chunk_hash(text)
        cached = _get_cached(cache_key)
        if cached is not None:
            return cached

        try:
            extracted = _extract_from_chunk(query, text)
        except Exception as e:
            logger.warning(f"Extraction failed for chunk: {e}")
            return []

        _set_cache(cache_key, extracted)
        return extracted

    # タイムアウト付きで並列実行
    try:
        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = []
            for chunk in chunks[:5]:  # 上位5チャンクのみ
                futures.append((executor.submit(_process_chunk, chunk), chunk))

            for future, chunk in futures:
                try:
                    items = future.result(timeout=EXTRACTION_TIMEOUT)
                except TimeoutError:
                    logger.warning("Extraction timed out for chunk")
                    continue
                except Exception as e:
                    logger.warning(f"Extraction error: {e}")
                    continue

                meta = chunk.get("metadata") or {}
                source_id = meta.get("source_id", "")
                page = meta.get("page_no") or meta.get("page_number")
                page_int = None
                if page:
                    try:
                        page_int = int(page)
                    except (ValueError, TypeError):
                        pass

                for item in items:
                    # 確信度: 原文テキストに値が明示的に含まれるかチェック
                    source_text = item.get("source_text", "")
                    value_str = item.get("value", "")
                    text_content = chunk.get("context_text") or chunk.get("document", "")

                    if value_str and value_str in text_content:
                        confidence = "high"
                    elif source_text and source_text in text_content:
                        confidence = "medium"
                    else:
                        confidence = "low"

                    results.append({
                        "item": item.get("item", ""),
                        "value": item.get("value", ""),
                        "unit": item.get("unit", ""),
                        "scope": item.get("scope", ""),
                        "source_text": source_text,
                        "source_id": source_id,
                        "page": page_int,
                        "confidence": confidence,
                        "pdf_path": meta.get("source_pdf", ""),
                        "rel_path": meta.get("rel_path", ""),
                    })
    except Exception as e:
        logger.error(f"extract_structured_values failed: {e}")

    return results
