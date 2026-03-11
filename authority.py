# authority.py — 根拠の優先順位 (Authority Hierarchy) 定義
# Phase 4/5: authority hierarchy を持つ証拠の管理とコンフリクト検出

from typing import List, Dict, Any

# Authority Levels (1 = 最高権威)
# 設計文書 section 2.3 の Authority Hierarchy に対応
AUTHORITY_LEVELS = {
    1: "法令・公的基準",                  # 建築基準法・消防法・JIS等
    2: "契約条件・発注条件・承認済み要求",  # 契約書・要求水準書
    3: "承認済みプロジェクト決定事項",       # ProjectDecision (status=active)
    4: "プロジェクト固有文書・議事録・ジャーナル",  # ProjectJournal / 議事録
    5: "組織標準・ガイドブック・業務仕様",   # 社内マニュアル・検索MD
    6: "個人経験・ヒューリスティクス",       # Layer A2 の経験知
}

# 優先順位の境界（これ以上の差があれば明確な優先付け）
HIGH_AUTHORITY_CONFLICT_THRESHOLD = 2


def get_authority_label(level: int) -> str:
    """authority_level の数値から日本語ラベルを返す"""
    return AUTHORITY_LEVELS.get(level, f"不明なレベル({level})")


def detect_high_authority_conflicts(evidence_items: List[Dict[str, Any]]) -> bool:
    """
    証拠リスト内に高権威ソース間の矛盾候補があるかを検出する。
    簡易版: authority_level が 1〜3 かつ conflict_flagged=True のものが2件以上あれば True。

    evidence_items: [{"authority_level": int, "conflict_flagged": bool, "source": str, ...}]
    """
    if not evidence_items:
        return False

    high_authority_conflicts = [
        item for item in evidence_items
        if item.get("conflict_flagged") and item.get("authority_level", 6) <= 3
    ]
    return len(high_authority_conflicts) >= 2


def format_conflict_disclosure(
    what: str,
    which_prioritized: str,
    why: str,
    needs_verification: bool = True,
) -> str:
    """
    設計文書の矛盾開示義務フォーマットを生成する。
    AIが矛盾を発見した際にこの形式で開示する。
    """
    lines = [
        "⚠️ **根拠間の矛盾を検出しました**",
        f"- **何が矛盾しているか**: {what}",
        f"- **優先した根拠**: {which_prioritized}",
        f"- **理由**: {why}",
    ]
    if needs_verification:
        lines.append("- **追加確認が必要**: はい（発注者または担当者への確認を推奨）")
    else:
        lines.append("- **追加確認が必要**: 不要")
    return "\n".join(lines)
