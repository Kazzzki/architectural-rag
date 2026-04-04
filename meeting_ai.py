"""
meeting_ai.py — 会議 AI ロジック (エンティティ抽出、自動タグ、クロスRAG)

routers/meetings.py の CRUD から分離した Gemini 呼び出し専用モジュール。
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text

import config
from gemini_client import get_client

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ===== 自動エンティティリンク抽出 =====

MEETING_TAG_CATEGORIES = [
    "設計変更", "コスト", "工程", "安全", "品質",
    "法規", "近隣", "発注者指示", "VE", "クレーム",
]


def extract_entity_links(session_id: int, db) -> List[Dict[str, Any]]:
    """文字起こし + ライブメモからエンティティ（イシュー・過去会議）を自動検出"""
    # 1. 対象セッション情報取得
    session = db.execute(
        text("SELECT * FROM meeting_sessions WHERE id = :id"),
        {"id": session_id}
    ).fetchone()
    if not session:
        return []

    session_dict = dict(session._mapping)
    project_name = session_dict.get("project_name")

    # 2. 全文取得（チャンク + ライブメモ）
    chunks = db.execute(text("""
        SELECT transcript FROM meeting_chunks
        WHERE session_id = :sid ORDER BY chunk_index ASC
    """), {"sid": session_id}).fetchall()
    chunk_text = "\n".join(r[0] for r in chunks if r[0])

    notes = db.execute(text("""
        SELECT content FROM meeting_live_notes
        WHERE session_id = :sid ORDER BY timestamp_sec ASC
    """), {"sid": session_id}).fetchall()
    note_text = "\n".join(r[0] for r in notes if r[0])

    full_text = f"{chunk_text}\n\n--- ライブメモ ---\n{note_text}".strip()
    if not full_text or len(full_text) < 10:
        return []

    # 3. 既存イシュー一覧を取得
    if project_name:
        issues = db.execute(text("""
            SELECT id, title, category, status FROM issues
            WHERE project_name = :pn
            ORDER BY created_at DESC LIMIT 50
        """), {"pn": project_name}).fetchall()
    else:
        issues = db.execute(text("""
            SELECT id, title, category, status FROM issues
            ORDER BY created_at DESC LIMIT 30
        """)).fetchall()

    issues_context = "\n".join(
        f"- [{dict(r._mapping)['id']}] {dict(r._mapping)['title']} ({dict(r._mapping).get('category', '')})"
        for r in issues
    )

    # 4. 既存会議一覧を取得（自分以外）
    meetings = db.execute(text("""
        SELECT id, title, created_at, series_name FROM meeting_sessions
        WHERE id != :sid
        ORDER BY created_at DESC LIMIT 30
    """), {"sid": session_id}).fetchall()

    meetings_context = "\n".join(
        f"- [会議#{dict(r._mapping)['id']}] {dict(r._mapping)['title']} ({dict(r._mapping).get('created_at', '')[:10]})"
        for r in meetings
    )

    # 5. Gemini でエンティティ抽出
    prompt = f"""以下の会議テキストから、既存のイシューや過去の会議への言及を検出してください。

## 会議テキスト
{full_text[:8000]}

## 既存イシュー一覧
{issues_context or "(なし)"}

## 過去の会議一覧
{meetings_context or "(なし)"}

## 指示
- テキスト中で言及されているイシューや会議を特定してください
- RFI番号、イシューID、会議名への言及を探してください
- JSON配列で返してください。各要素: {{"entity_type": "issue"|"meeting", "entity_id": "ID", "mention_text": "言及テキスト", "confidence": 0.0-1.0}}
- 確信度0.6以上のもののみ返してください
- 結果がない場合は空配列 [] を返してください
- JSON配列のみ返してください。説明不要です。"""

    try:
        client = get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL_RAG,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        # JSON抽出（コードブロック対応）
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0]
        entities = json.loads(raw)
        if not isinstance(entities, list):
            entities = []
    except Exception as e:
        logger.error(f"Entity extraction error: {e}", exc_info=True)
        return []

    # 6. DB保存
    now = _now_iso()
    saved = []
    for ent in entities:
        if not isinstance(ent, dict):
            continue
        entity_type = ent.get("entity_type", "")
        entity_id = str(ent.get("entity_id", ""))
        if not entity_type or not entity_id:
            continue

        try:
            result = db.execute(text("""
                INSERT INTO meeting_entity_links
                    (session_id, entity_type, entity_id, mention_text, confidence, created_at)
                VALUES (:sid, :et, :eid, :mt, :conf, :ca)
            """), {
                "sid": session_id,
                "et": entity_type,
                "eid": entity_id,
                "mt": ent.get("mention_text", ""),
                "conf": min(1.0, max(0.0, float(ent.get("confidence", 0.8)))),
                "ca": now,
            })
            saved.append({
                "id": result.lastrowid,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "mention_text": ent.get("mention_text", ""),
                "confidence": ent.get("confidence", 0.8),
            })
        except Exception as e:
            logger.warning(f"Failed to save entity link: {e}")

    if saved:
        db.commit()
    return saved


# ===== 自動タグ付与 =====

def auto_tag_meeting(session_id: int, db) -> List[Dict[str, Any]]:
    """文字起こしからタグを自動付与（最大5つ）"""
    # 全文取得
    chunks = db.execute(text("""
        SELECT transcript FROM meeting_chunks
        WHERE session_id = :sid ORDER BY chunk_index ASC
    """), {"sid": session_id}).fetchall()
    full_text = "\n".join(r[0] for r in chunks if r[0])

    notes = db.execute(text("""
        SELECT content FROM meeting_live_notes
        WHERE session_id = :sid ORDER BY timestamp_sec ASC
    """), {"sid": session_id}).fetchall()
    full_text += "\n" + "\n".join(r[0] for r in notes if r[0])

    if not full_text.strip() or len(full_text.strip()) < 10:
        return []

    categories_str = "、".join(MEETING_TAG_CATEGORIES)
    prompt = f"""以下の会議テキストに該当するカテゴリタグを最大5つ選んでください。

カテゴリ: {categories_str}

会議テキスト:
{full_text[:6000]}

JSON配列で返してください。例: ["工程", "コスト", "安全"]
該当なしの場合は空配列 [] を返してください。JSON配列のみ返してください。"""

    try:
        client = get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL_RAG,
            contents=prompt,
        )
        raw = (response.text or "").strip()
        if raw.startswith("```"):
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
            raw = raw.rsplit("```", 1)[0]
        tags = json.loads(raw)
        if not isinstance(tags, list):
            tags = []
    except Exception as e:
        logger.error(f"Auto-tag error: {e}", exc_info=True)
        return []

    # DB保存（重複無視）
    now = _now_iso()
    saved = []
    for tag_name in tags[:5]:
        if not isinstance(tag_name, str) or tag_name not in MEETING_TAG_CATEGORIES:
            continue
        try:
            db.execute(text("""
                INSERT OR IGNORE INTO meeting_tags (session_id, tag_name, source, created_at)
                VALUES (:sid, :tn, 'ai', :ca)
            """), {"sid": session_id, "tn": tag_name, "ca": now})
            saved.append({"tag_name": tag_name, "source": "ai"})
        except Exception as e:
            logger.warning(f"Failed to save tag: {e}")

    if saved:
        db.commit()
    return saved


def add_manual_tag(session_id: int, tag_name: str, db) -> Optional[Dict[str, Any]]:
    """手動タグ追加（#tag をライブメモからパース時に使用）"""
    now = _now_iso()
    try:
        db.execute(text("""
            INSERT OR IGNORE INTO meeting_tags (session_id, tag_name, source, created_at)
            VALUES (:sid, :tn, 'manual', :ca)
        """), {"sid": session_id, "tn": tag_name, "ca": now})
        db.commit()
        return {"tag_name": tag_name, "source": "manual"}
    except Exception as e:
        logger.warning(f"Failed to add manual tag: {e}")
        return None


def get_meeting_tags(session_id: int, db) -> List[Dict[str, Any]]:
    """セッションのタグ一覧"""
    rows = db.execute(text("""
        SELECT * FROM meeting_tags WHERE session_id = :sid ORDER BY tag_name
    """), {"sid": session_id}).fetchall()
    return [dict(r._mapping) for r in rows]


def get_entity_links(session_id: int, db) -> List[Dict[str, Any]]:
    """セッションのエンティティリンク一覧"""
    rows = db.execute(text("""
        SELECT * FROM meeting_entity_links WHERE session_id = :sid ORDER BY confidence DESC
    """), {"sid": session_id}).fetchall()
    return [dict(r._mapping) for r in rows]
