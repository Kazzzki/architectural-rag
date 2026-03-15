"""
research_engine/collector.py

SearXNGで検索し、PDF/HTMLをダウンロード・変換・保存する。
エラーは個別にスキップして全体停止しない。
"""
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

import httpx

from .converter import convert_pdf, convert_html

logger = logging.getLogger(__name__)

SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8080")
RESEARCH_VAULT_PATH = os.getenv("RESEARCH_VAULT_PATH", "./research_vault")
MAX_SOURCES = int(os.getenv("RESEARCH_MAX_SOURCES_PER_CATEGORY", "6"))


def _calc_trust_score(url: str, is_pdf: bool) -> float:
    domain = urlparse(url).netloc
    if ".go.jp" in domain:
        score = 0.9
    elif ".ac.jp" in domain:
        score = 0.8
    else:
        score = 0.5
    if is_pdf:
        score = min(1.0, score + 0.1)
    return round(score, 2)


def _is_pdf(url: str, content_type: str) -> bool:
    if url.lower().endswith(".pdf"):
        return True
    if "application/pdf" in content_type.lower():
        return True
    return False


async def collect_sources(
    plan: dict,
    research_id: str,
    progress_callback: Callable[[int, str, int], None],
) -> list[dict]:
    """
    プランに従ってソースを収集・変換する。
    戻り値: 収集したソース情報のリスト（database.add_research_source に渡す形式）
    """
    month_str = datetime.now(timezone.utc).strftime("%Y-%m")
    raw_dir = Path(RESEARCH_VAULT_PATH) / "raw" / month_str / research_id
    md_dir = Path(RESEARCH_VAULT_PATH) / "markdown" / month_str / research_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    md_dir.mkdir(parents=True, exist_ok=True)

    categories = sorted(plan.get("categories", []), key=lambda c: c.get("priority", 99))
    seen_urls: set[str] = set()
    collected: list[dict] = []
    errors: list[str] = []

    total_categories = max(len(categories), 1)

    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        for cat_idx, category in enumerate(categories):
            cat_id = category.get("id", "unknown")
            cat_name = category.get("name", cat_id)
            queries = category.get("queries", [])
            cat_sources = 0

            for query in queries:
                if cat_sources >= MAX_SOURCES:
                    break
                try:
                    search_resp = await client.get(
                        f"{SEARXNG_URL}/search",
                        params={"q": query, "format": "json", "language": "ja-JP"},
                    )
                    search_resp.raise_for_status()
                    results = search_resp.json().get("results", [])
                except Exception as e:
                    msg = f"SearXNG search failed [{query}]: {e}"
                    logger.error(msg)
                    errors.append(msg)
                    raise  # SearXNG接続エラーは上位に伝播

                for result in results:
                    if cat_sources >= MAX_SOURCES:
                        break
                    url = result.get("url", "")
                    if not url or url in seen_urls:
                        continue
                    seen_urls.add(url)

                    # ダウンロード
                    try:
                        dl_resp = await client.get(url)
                        dl_resp.raise_for_status()
                        content_type = dl_resp.headers.get("content-type", "")
                        is_pdf = _is_pdf(url, content_type)
                        raw_content = dl_resp.content
                    except Exception as e:
                        msg = f"Download failed [{url}]: {e}"
                        logger.warning(msg)
                        errors.append(msg)
                        continue

                    # 保存・変換
                    safe_name = f"{len(seen_urls):04d}"
                    ext = ".pdf" if is_pdf else ".html"
                    raw_path = str(raw_dir / f"{safe_name}{ext}")
                    md_path = str(md_dir / f"{safe_name}.md")

                    try:
                        with open(raw_path, "wb") as f:
                            f.write(raw_content)
                    except Exception as e:
                        logger.warning(f"Save raw failed [{url}]: {e}")
                        errors.append(str(e))
                        continue

                    if is_pdf:
                        ok = convert_pdf(raw_path, md_path)
                    else:
                        ok = convert_html(raw_content.decode("utf-8", errors="replace"), md_path, url)

                    if not ok:
                        logger.warning(f"Conversion failed [{url}]")
                        errors.append(f"Conversion failed: {url}")
                        continue

                    trust_score = _calc_trust_score(url, is_pdf)
                    source_info = {
                        "title": result.get("title", ""),
                        "url": url,
                        "source_type": "gov_pdf" if (is_pdf and ".go.jp" in url) else ("paper" if ".ac.jp" in url else ("html" if not is_pdf else "catalog")),
                        "trust_score": trust_score,
                        "category": cat_id,
                        "markdown_path": md_path,
                        "raw_path": raw_path,
                    }
                    collected.append(source_info)
                    cat_sources += 1

                    # 進捗コールバック（収集フェーズ: 25%→65%）
                    progress = 25 + int(40 * (cat_idx / total_categories))
                    detail = f"[{cat_name}] {result.get('title', url)[:40]}"
                    progress_callback(progress, detail, len(collected))

    # errorsを呼び出し元で使えるよう先頭ソースに添付（またはDB更新はrouter側で行う）
    if errors:
        logger.warning(f"collect_sources: {len(errors)} errors for {research_id}")

    return collected
