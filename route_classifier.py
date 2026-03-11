# route_classifier.py — Flash による質問の軽量分類
# Phase 4: 設計文書に基づく classifier + rule + escalation ルーティングの Step 1

import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)

CLASSIFIER_PROMPT = """以下の質問を分類してください。JSONのみ返してください。

分類項目:
- task_type: fact | summarize | analyze | recommend | draft | review
- stakes: low | medium | high
- evidence_need: low | medium | high
- ambiguity: low | high
- conflict_risk: low | high
- needs_raw_journal: true | false

判断基準:
- recommend: どうすべきか、方針、進言、採否判断
- review: 文案レビュー、説明方針レビュー、妥当性レビュー
- draft: 文書作成、議事録、報告書の草案
- analyze: 比較分析、要因分析、リスク評価
- summarize: 要約、整理、一覧化
- fact: 事実確認、仕様確認、数値照合
- high stakes: 契約、増額、工期、品質、安全、対外説明
- evidence_need high: 技術資料/契約/過去決定の参照が重要
- conflict_risk high: 関係者対立、根拠競合、過去決定との矛盾
- needs_raw_journal: 過去のやり取りの原文を見ないと判断が不確かになる場合

質問: {question}
"""

_DEFAULT_CLASSIFICATION = {
    "task_type": "analyze",
    "stakes": "medium",
    "evidence_need": "medium",
    "ambiguity": "low",
    "conflict_risk": "low",
    "needs_raw_journal": False,
}


def classify_request(question: str, timeout_seconds: float = 5.0) -> dict:
    """
    Flash モデルで質問を軽量分類する。
    失敗またはタイムアウト時はデフォルト値を返す（フォールバック安全）。

    Returns:
        dict with keys: task_type, stakes, evidence_need, ambiguity, conflict_risk, needs_raw_journal
    """
    if not question or not question.strip():
        return _DEFAULT_CLASSIFICATION.copy()

    try:
        from gemini_client import get_client
        from config import GEMINI_MODEL_FLASH
        from google.genai import types

        client = get_client()
        prompt = CLASSIFIER_PROMPT.format(question=question[:500])  # 長い質問は先頭500文字に制限

        response = client.models.generate_content(
            model=GEMINI_MODEL_FLASH,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
                max_output_tokens=256,
            )
        )

        raw = response.text.strip()
        result = json.loads(raw)

        # 必須フィールドのバリデーション
        validated = {}
        validated["task_type"] = result.get("task_type", "analyze")
        if validated["task_type"] not in ("fact", "summarize", "analyze", "recommend", "draft", "review"):
            validated["task_type"] = "analyze"

        validated["stakes"] = result.get("stakes", "medium")
        if validated["stakes"] not in ("low", "medium", "high"):
            validated["stakes"] = "medium"

        validated["evidence_need"] = result.get("evidence_need", "medium")
        if validated["evidence_need"] not in ("low", "medium", "high"):
            validated["evidence_need"] = "medium"

        validated["ambiguity"] = result.get("ambiguity", "low")
        if validated["ambiguity"] not in ("low", "high"):
            validated["ambiguity"] = "low"

        validated["conflict_risk"] = result.get("conflict_risk", "low")
        if validated["conflict_risk"] not in ("low", "high"):
            validated["conflict_risk"] = "low"

        validated["needs_raw_journal"] = bool(result.get("needs_raw_journal", False))

        logger.debug(f"Classified question: task_type={validated['task_type']}, stakes={validated['stakes']}")
        return validated

    except Exception as e:
        logger.warning(f"classify_request failed (fallback to default): {e}")
        return _DEFAULT_CLASSIFICATION.copy()
