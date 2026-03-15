"""
research_engine/synthesizer.py

収集済みソースを統合してMarkdownレポートを生成する。
3回のOllama呼び出し: 統合 → エビデンスチェック → 200字要約
"""
import json
import logging
import os

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b-instruct-q4_K_M")

_SYSTEM_SYNTHESIS = """\
あなたはPM/CM専門の技術リサーチャーです。
以下のソース情報を統合し、質問に対する技術レポートをMarkdown形式で作成してください。
根拠のある記述のみ行い、ソースに記載のない内容は推測で書かないこと。

出力フォーマット:
# {question}

## エグゼクティブサマリー
（結論を3〜5文）

## 法令根拠
（legalカテゴリのソースから統合）

## 技術基準・設計指針
（design_guidelineカテゴリから統合）

## 実務上の注意点
（全ソースから実務的観点を抽出）

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


async def _call_ollama(prompt: str, system: str = "", timeout: float = 3600.0) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(f"{OLLAMA_URL}/api/generate", json=payload)
        resp.raise_for_status()
        return resp.json().get("response", "").strip()


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
    synthesis_prompt = (
        f"質問: {question}\n\n"
        f"収集したソース情報:\n{sources_text}"
    )
    system = _SYSTEM_SYNTHESIS.format(question=question)

    # 第1回: 統合レポート生成
    report = await _call_ollama(synthesis_prompt, system=system)
    logger.info("Synthesizer: initial report generated")

    # 第2回: エビデンスチェック
    evidence_prompt = f"{report}\n\n{_PROMPT_EVIDENCE_CHECK}"
    try:
        checked_report = await _call_ollama(evidence_prompt)
        if checked_report:
            report = checked_report
        logger.info("Synthesizer: evidence check done")
    except Exception as e:
        logger.warning(f"Synthesizer: evidence check failed: {e}")

    # 第3回: 200字要約
    summary_prompt = f"{report}\n\n{_PROMPT_SUMMARY}"
    try:
        summary = await _call_ollama(summary_prompt, timeout=1800.0)
    except Exception as e:
        logger.warning(f"Synthesizer: summary generation failed: {e}")
        summary = ""

    return report, summary
