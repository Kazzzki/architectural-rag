"""
research_engine/synthesizer.py

収集済みソースを統合してMarkdownレポートを生成する。
Gemini Flash を使用。3ステップ: 統合 → エビデンスチェック → 200字要約
"""
import asyncio
import logging

from config import GEMINI_MODEL_FLASH
from gemini_client import get_client

logger = logging.getLogger(__name__)

_SYSTEM_SYNTHESIS = """\
あなたはPM/CM専門の技術リサーチャーです。
以下のソース情報を統合し、質問に対する技術レポートをMarkdown形式で作成してください。
根拠のある記述のみ行い、ソースに記載のない内容は推測で書かないこと。

出力フォーマット:
# {question}

## エグゼクティブサマリー
（結論を3〜5文）

## 法令・規制
（legal カテゴリのソースから統合）

## 技術基準・設計指針
（technical カテゴリから統合）

## メーカー仕様・製品情報
（manufacturer カテゴリから統合）

## 施工事例・実務上の注意点
（construction_case / construction_pm カテゴリから統合）

## 出典一覧
（各ソースのタイトルとURL）\
"""

_PROMPT_EVIDENCE_CHECK = """\
上記レポートの中で、提供されたソース情報から根拠が確認できない記述に ⚠️ マークを
先頭に付与したレポートを再出力してください。
根拠が確認できる記述はそのまま。指摘がなければ元のレポートをそのまま出力。\
"""

_PROMPT_SUMMARY = """\
上記レポートを200文字以内で要約してください。要約のみ出力。\
"""


def _build_sources_text(sources: list[dict]) -> str:
    lines = []
    for i, s in enumerate(sources, 1):
        lines.append(
            f"[{i}] タイトル: {s.get('title', '')}\n"
            f"    URL: {s.get('url', '')}\n"
            f"    カテゴリ: {s.get('category', '')}\n"
            f"    要約: {s.get('summary', '')}"
        )
    return "\n\n".join(lines)


def _call_gemini_sync(prompt: str) -> str:
    client = get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL_FLASH,
        contents=prompt,
    )
    return response.text or ""


async def _call_gemini(prompt: str) -> str:
    return await asyncio.to_thread(_call_gemini_sync, prompt)


async def synthesize_report(
    question: str,
    sources: list[dict],
    plan: dict,
) -> tuple[str, str]:
    """
    ソース一覧からMarkdownレポートと200字要約を生成する。
    戻り値: (report_markdown全文, summary_200字)
    """
    sources_text = _build_sources_text(sources)
    system = _SYSTEM_SYNTHESIS.format(question=question)
    synthesis_prompt = (
        f"{system}\n\n"
        f"質問: {question}\n\n"
        f"収集したソース情報:\n{sources_text}"
    )

    # 第1回: 統合レポート生成
    report = await _call_gemini(synthesis_prompt)
    logger.info("Synthesizer: initial report generated")

    # 第2回: エビデンスチェック
    try:
        checked_report = await _call_gemini(f"{report}\n\n{_PROMPT_EVIDENCE_CHECK}")
        if checked_report:
            report = checked_report
        logger.info("Synthesizer: evidence check done")
    except Exception as e:
        logger.warning(f"Synthesizer: evidence check failed: {e}")

    # 第3回: 200字要約
    try:
        summary = await _call_gemini(f"{report}\n\n{_PROMPT_SUMMARY}")
    except Exception as e:
        logger.warning(f"Synthesizer: summary generation failed: {e}")
        summary = ""

    return report, summary
