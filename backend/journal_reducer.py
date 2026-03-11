# backend/journal_reducer.py — ジャーナルから現在状態を導出
# Phase 3: project_journal をソースとして state_summary / relevant_decisions / open_issues_digest を生成

import logging
from typing import Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_state_summary(project_id: str, user_id: str = "default") -> str:
    """
    project_journals から state_summary を生成して返す。
    ジャーナルが空の場合は空文字列を返す（安全フォールバック）。
    """
    try:
        from database import SessionLocal, ProjectJournal
        from sqlalchemy import desc
        from config import GEMINI_MODEL_FLASH_THINKING

        db = SessionLocal()
        try:
            journals = (
                db.query(ProjectJournal)
                .filter(ProjectJournal.project_id == project_id)
                .order_by(desc(ProjectJournal.occurred_at))
                .limit(20)
                .all()
            )
            if not journals:
                return ""

            journal_text = "\n".join([
                f"[{j.occurred_at.strftime('%Y-%m-%d')} / {j.event_type}] {j.content}"
                for j in journals
            ])

            # Flash Thinking で状態要約を生成
            from gemini_client import get_client
            from google.genai import types

            client = get_client()
            prompt = f"""以下のプロジェクトジャーナルから、現在の「プロジェクト状態要約」を300文字程度で生成してください。
「何が決まったか」「何が未解決か」「現在の主要タスク」を簡潔にまとめてください。

【ジャーナル（最新20件）】
{journal_text}

【出力形式】
300文字以内の箇条書きまたは短い段落。ヘッダー不要。
"""
            response = client.models.generate_content(
                model=GEMINI_MODEL_FLASH_THINKING,
                contents=prompt,
                config=types.GenerateContentConfig(temperature=0.1, max_output_tokens=500)
            )
            return response.text.strip()

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"get_state_summary failed for project={project_id}: {e}")
        return ""


def get_relevant_decisions(project_id: str, query: str, limit: int = 5) -> list:
    """
    project_decisions から query に関連する active 決定事項を返す。
    テーブルが空の場合は [] を返す（安全フォールバック）。
    """
    try:
        from database import SessionLocal, ProjectDecision
        from sqlalchemy import desc

        db = SessionLocal()
        try:
            decisions = (
                db.query(ProjectDecision)
                .filter(
                    ProjectDecision.project_id == project_id,
                    ProjectDecision.status == "active",
                )
                .order_by(desc(ProjectDecision.decided_at))
                .limit(limit * 3)
                .all()
            )
            if not decisions:
                return []

            # キーワード簡易フィルター（決定事項が多い場合）
            query_words = _extract_words(query)
            if query_words and len(decisions) > limit:
                scored = []
                for d in decisions:
                    score = sum(1 for w in query_words if w in (d.title or "") or w in (d.detail or ""))
                    scored.append((score, d))
                scored.sort(key=lambda x: -x[0])
                decisions = [d for _, d in scored[:limit]]
            else:
                decisions = decisions[:limit]

            return [
                {
                    "id": d.id,
                    "title": d.title,
                    "detail": d.detail or "",
                    "authority_level": d.authority_level,
                    "decided_at": d.decided_at.isoformat() if d.decided_at else None,
                }
                for d in decisions
            ]
        finally:
            db.close()

    except Exception as e:
        logger.warning(f"get_relevant_decisions failed for project={project_id}: {e}")
        return []


def get_open_issues_digest(project_id: str) -> str:
    """
    project_issues の open / in_progress 課題を250文字以内のダイジェストとして返す。
    テーブルが空の場合は空文字列を返す（安全フォールバック）。
    """
    try:
        from database import SessionLocal, ProjectIssue
        from sqlalchemy import asc

        db = SessionLocal()
        try:
            PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2}

            issues = (
                db.query(ProjectIssue)
                .filter(
                    ProjectIssue.project_id == project_id,
                    ProjectIssue.status.in_(["open", "in_progress"]),
                )
                .limit(20)
                .all()
            )
            if not issues:
                return ""

            # 優先度順にソート
            issues.sort(key=lambda i: PRIORITY_ORDER.get(i.priority, 9))

            lines = []
            for issue in issues[:8]:
                prio_label = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(issue.priority, "")
                lines.append(f"{prio_label} {issue.title} [{issue.status}]")

            return "\n".join(lines)

        finally:
            db.close()

    except Exception as e:
        logger.warning(f"get_open_issues_digest failed for project={project_id}: {e}")
        return ""


def format_decisions_block(decisions: list) -> str:
    """決定事項リストを user_prompt 注入用ブロックに整形する"""
    if not decisions:
        return ""
    lines = []
    for d in decisions:
        auth = d.get("authority_level", 3)
        lines.append(f"- [L{auth}] {d['title']}: {d.get('detail', '')[:100]}")
    return "【関連決定事項】\n" + "\n".join(lines)


def _extract_words(text: str) -> list:
    """簡易単語抽出（漢字・カタカナ・英数字 2文字以上）"""
    import re
    return re.findall(r'[一-龠ぁ-んァ-ヶa-zA-Z0-9]{2,}', text)
