"""
research_engine/collector.py

Gemini Flash + Google Search グラウンディングでソースを収集・分析する。
SearXNG / httpx / marker-pdf / trafilatura は不要。

フロー（カテゴリごと）:
  Gemini が Google を検索 → 関連ページを読解 → 根拠付き分析テキストを生成
  → grounding_chunks から参照URLを抽出 → Markdown として保存
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from google.genai import types

from config import GEMINI_MODEL_FLASH
from gemini_client import get_client

logger = logging.getLogger(__name__)

RESEARCH_VAULT_PATH = os.getenv("RESEARCH_VAULT_PATH", "./research_vault")

_CATEGORY_PROMPT = """\
建築・建設プロジェクトの専門家として、以下の観点で詳しく調査してください。

カテゴリ: {cat_name}
調査ポイント:
{queries_list}

回答には以下を必ず含めてください：
- 具体的な数値基準・閾値
- 法令・規格・告示の条文番号（該当する場合）
- 製品名・型番・認定番号（該当する場合）
- 施工上の注意点・よくあるトラブル

日本語で詳しく回答してください。\
"""


def _calc_trust_score(url: str) -> float:
    domain = urlparse(url).netloc
    if ".go.jp" in domain:
        return 0.95
    elif ".ac.jp" in domain:
        return 0.85
    elif ".or.jp" in domain or ".lg.jp" in domain:
        return 0.80
    else:
        return 0.65  # グラウンディング済みはSearXNG単純検索より信頼性高め


def _call_gemini_grounding_sync(prompt: str):
    """Google Search グラウンディング付き Gemini 呼び出し（同期）。"""
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_FLASH,
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
        ),
    )
    return response


async def _call_gemini_grounding(prompt: str):
    return await asyncio.to_thread(_call_gemini_grounding_sync, prompt)


def _extract_web_sources(response, cat_id: str) -> list[dict]:
    """
    grounding_metadata.grounding_chunks から参照URLを抽出する。
    取得できない場合は空リストを返す。
    """
    sources = []
    try:
        candidate = response.candidates[0]
        if not getattr(candidate, "grounding_metadata", None):
            return sources
        for chunk in candidate.grounding_metadata.grounding_chunks or []:
            web = getattr(chunk, "web", None)
            if web and getattr(web, "uri", None):
                sources.append({
                    "title": getattr(web, "title", None) or web.uri,
                    "url": web.uri,
                    "category": cat_id,
                    "trust_score": _calc_trust_score(web.uri),
                    "source_type": "grounded_web",
                })
    except Exception as e:
        logger.warning(f"grounding source extraction failed: {e}")
    return sources


def _save_markdown(
    md_dir: Path, cat_id: str, cat_name: str, queries: list[str],
    grounded_text: str, web_sources: list[dict],
) -> str:
    """グラウンディング結果を Markdown ファイルとして保存し、パスを返す。"""
    md_path = str(md_dir / f"{cat_id}.md")
    try:
        header_lines = [f"# {cat_name}\n"]
        header_lines.append(f"**調査ポイント**: {' / '.join(queries)}\n")
        if web_sources:
            header_lines.append("\n**参照ソース**:")
            for s in web_sources:
                header_lines.append(f"- [{s['title']}]({s['url']})")
        header_lines.append("\n---\n")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(header_lines) + "\n" + grounded_text)
    except Exception as e:
        logger.warning(f"Failed to save markdown [{cat_id}]: {e}")
        md_path = ""
    return md_path


async def collect_sources(
    plan: dict,
    research_id: str,
    progress_callback: Callable[[int, str, int], None],
) -> list[dict]:
    """
    Gemini Flash + Google Search グラウンディングでカテゴリ別調査を実行する。
    戻り値: ソース情報のリスト（database.add_research_source に渡す形式）
    各ソースには summary フィールドが設定済みのため、呼び出し元での要約不要。
    """
    month_str = datetime.now(timezone.utc).strftime("%Y-%m")
    md_dir = Path(RESEARCH_VAULT_PATH) / "markdown" / month_str / research_id
    md_dir.mkdir(parents=True, exist_ok=True)

    categories = sorted(plan.get("categories", []), key=lambda c: c.get("priority", 99))
    total = max(len(categories), 1)
    all_sources: list[dict] = []

    for cat_idx, category in enumerate(categories):
        cat_id = category.get("id", "unknown")
        cat_name = category.get("name", cat_id)
        queries = category.get("queries", [])
        if not queries:
            continue

        # 進捗通知（開始）
        progress_start = 25 + int(40 * cat_idx / total)
        progress_callback(progress_start, f"[{cat_name}] Google Search で調査中...", len(all_sources))

        prompt = _CATEGORY_PROMPT.format(
            cat_name=cat_name,
            queries_list="\n".join(f"- {q}" for q in queries),
        )

        try:
            response = await _call_gemini_grounding(prompt)
            grounded_text = response.text or ""
        except Exception as e:
            logger.error(f"Gemini grounding failed [{cat_name}]: {e}")
            progress_callback(progress_start, f"[{cat_name}] エラーでスキップ", len(all_sources))
            continue

        web_sources = _extract_web_sources(response, cat_id)
        md_path = _save_markdown(md_dir, cat_id, cat_name, queries, grounded_text, web_sources)
        summary_short = grounded_text[:300].replace("\n", " ")

        if web_sources:
            # 参照された各 Web ソースを個別エントリとして登録
            for src in web_sources:
                all_sources.append({
                    **src,
                    "summary": summary_short,
                    "markdown_path": md_path,
                    "raw_path": "",
                })
        else:
            # グラウンディングチャンクが取れない場合はカテゴリ単位で1件登録
            all_sources.append({
                "title": f"{cat_name} - グラウンディング調査結果",
                "url": "",
                "source_type": "grounded_synthesis",
                "category": cat_id,
                "trust_score": 0.75,
                "summary": summary_short,
                "markdown_path": md_path,
                "raw_path": "",
            })

        # 進捗通知（完了）
        progress_end = 25 + int(40 * (cat_idx + 1) / total)
        progress_callback(
            progress_end,
            f"[{cat_name}] 完了 ({len(web_sources)} ソース参照)",
            len(all_sources),
        )
        logger.info(f"Collector: [{cat_name}] done — {len(web_sources)} grounding sources")

    return all_sources
