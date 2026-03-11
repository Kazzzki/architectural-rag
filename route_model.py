# route_model.py — classifier + rule + escalation によるモデルルーティング
# Phase 4: 設計文書 section 5.4 に基づく実装

import logging
from typing import Optional

logger = logging.getLogger(__name__)


def route_model(
    question: str,
    project_state: Optional[dict] = None,
    has_rag_context: bool = False,
) -> dict:
    """
    質問の性質に応じて最適なモデルを選択する。

    Args:
        question: ユーザーの質問文
        project_state: {"open_issues": list, "relevant_decisions": list, "evidence_items": list}
        has_rag_context: RAG検索結果が存在するか

    Returns:
        {
            "model": "gemini-...",
            "reason": "選択理由の説明（日本語）",
            "cls": {...}  # classifierの分類結果
        }
    """
    from config import GEMINI_MODEL_FLASH, GEMINI_MODEL_FLASH_THINKING, GEMINI_MODEL_PRO
    from route_classifier import classify_request
    from authority import detect_high_authority_conflicts

    if project_state is None:
        project_state = {}

    # Step 1: 軽量分類
    cls = classify_request(question)

    has_open_issues = bool(project_state.get("open_issues"))
    has_conflict = detect_high_authority_conflicts(
        project_state.get("evidence_items", [])
    )

    # Step 2: ルールベース選択
    selected = _apply_base_rules(cls, GEMINI_MODEL_FLASH, GEMINI_MODEL_FLASH_THINKING, GEMINI_MODEL_PRO)
    reason = _describe_rule(cls, selected, GEMINI_MODEL_FLASH, GEMINI_MODEL_FLASH_THINKING, GEMINI_MODEL_PRO)

    # Step 3: 昇格判定
    escalated, escalation_reason = _check_escalation(
        selected=selected,
        cls=cls,
        has_open_issues=has_open_issues,
        has_conflict=has_conflict,
        has_rag_context=has_rag_context,
        flash=GEMINI_MODEL_FLASH,
        thinking=GEMINI_MODEL_FLASH_THINKING,
        pro=GEMINI_MODEL_PRO,
    )

    if escalated != selected:
        reason = f"{reason}（昇格: {escalation_reason}）"
        selected = escalated

    logger.info(f"route_model: selected={selected}, task_type={cls['task_type']}, stakes={cls['stakes']}")

    return {
        "model": selected,
        "reason": reason,
        "cls": cls,
    }


def _apply_base_rules(cls: dict, flash: str, thinking: str, pro: str) -> str:
    """Step 2: ルールベース選択"""
    task_type = cls["task_type"]
    stakes = cls["stakes"]
    evidence_need = cls["evidence_need"]

    if task_type in ("recommend", "review"):
        if stakes == "high":
            return pro
        if evidence_need == "high":
            return pro
        return thinking

    if task_type in ("analyze", "summarize", "draft"):
        if evidence_need in ("medium", "high"):
            return thinking
        return flash

    # fact
    if stakes == "low":
        return flash
    return thinking


def _check_escalation(
    selected: str, cls: dict,
    has_open_issues: bool, has_conflict: bool, has_rag_context: bool,
    flash: str, thinking: str, pro: str,
) -> tuple[str, str]:
    """
    Step 3: 昇格判定
    以下の条件で 1段階上位モデルへ昇格する。
    """
    def escalate_one(current: str) -> str:
        if current == flash:
            return thinking
        return pro  # thinking → pro

    reasons = []

    if has_conflict and selected != pro:
        selected = escalate_one(selected)
        reasons.append("高authorityソース間の矛盾あり")

    if cls.get("conflict_risk") == "high" and selected != pro:
        selected = escalate_one(selected)
        reasons.append("矛盾リスク高")

    if has_open_issues and cls["task_type"] in ("recommend", "review") and selected != pro:
        selected = pro
        reasons.append("未解決issueが多い状態での判断依頼")

    if cls.get("needs_raw_journal") and selected == flash:
        selected = thinking
        reasons.append("ジャーナル参照が必要な質問")

    return selected, "、".join(reasons) if reasons else ""


def _describe_rule(cls: dict, selected: str, flash: str, thinking: str, pro: str) -> str:
    labels = {flash: "Flash（高速）", thinking: "Flash Thinking（分析）", pro: "Pro（高精度）"}
    task = cls["task_type"]
    stakes = cls["stakes"]
    evidence = cls["evidence_need"]
    return f"{labels.get(selected, selected)} — task={task}, stakes={stakes}, evidence_need={evidence}"
