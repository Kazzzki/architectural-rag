"""
routers/issues.py — 課題因果グラフ API

エンドポイント:
  POST   /api/issues/capture          課題テキストをAI構造化 + 保存
  POST   /api/issues/capture-photo    写真から課題を抽出してAI構造化 + 保存
  POST   /api/issues/edges/confirm    因果エッジを確定
  GET    /api/issues                  課題・エッジ一覧
  GET    /api/issues/projects         プロジェクト名一覧
  GET    /api/issues/memo-search      課題メモを自然言語で検索（LLM embedding）
  PATCH  /api/issues/{issue_id}       部分更新
  DELETE /api/issues/{issue_id}       物理削除
"""
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from database import get_db
from config import ISSUE_MEMOS_DIR, ISSUE_ATTACHMENTS_DIR
from issue_memo_indexer import IssueMemoIndexer

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Issues"])

UPDATABLE_FIELDS = {
    "status", "priority", "action_next", "is_collapsed",
    "pos_x", "pos_y", "project_name", "title", "description",
    "cause", "impact", "category", "assignee", "context_memo", "deadline",
    "is_task", "completed_at", "due_time", "section_name", "parent_id",
}


# ---------- Pydantic モデル ----------

class CaptureRequest(BaseModel):
    raw_input: str
    project_name: str
    skip_ai: bool = False


class TriageGenerateRequest(BaseModel):
    project_name: str
    template_id: str


class TriageApplyRequest(BaseModel):
    raw_input: str
    project_name: str
    phase_value: Optional[str] = None
    category_value: Optional[str] = None
    related_issue_ids: list = []   # 因果マップ上の既存 issue UUID
    assignee: Optional[str] = None


class EdgeConfirmRequest(BaseModel):
    from_id: str
    to_id: str
    confirmed: bool


class IssueUpdateRequest(BaseModel):
    status: Optional[str] = None
    priority: Optional[str] = None
    action_next: Optional[str] = None
    is_collapsed: Optional[int] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    project_name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    cause: Optional[str] = None
    impact: Optional[str] = None
    category: Optional[str] = None
    assignee: Optional[str] = None
    context_memo: Optional[str] = None


class MemberCreateRequest(BaseModel):
    project_name: str
    name: str
    role: Optional[str] = None


# ---------- ヘルパー ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _render_issue_markdown(issue: dict, edges: list, db) -> str:
    """Issue dict + edges リストから Markdown テキストを生成する。"""
    # 関連課題のタイトルを取得
    causing_titles = []   # この課題の原因（from_id → issue_id）
    caused_titles = []    # この課題が引き起こす課題（issue_id → to_id）

    for edge in edges:
        edge_from = edge[1] if not isinstance(edge, dict) else edge["from_id"]
        edge_to   = edge[2] if not isinstance(edge, dict) else edge["to_id"]
        issue_id  = issue["id"]

        if edge_to == issue_id:
            # edge_from がこの課題の原因
            row = db.execute(
                text("SELECT title FROM issues WHERE id = :id"), {"id": edge_from}
            ).fetchone()
            causing_titles.append((edge_from, row[0] if row else edge_from))
        elif edge_from == issue_id:
            # edge_to がこの課題によって引き起こされる
            row = db.execute(
                text("SELECT title FROM issues WHERE id = :id"), {"id": edge_to}
            ).fetchone()
            caused_titles.append((edge_to, row[0] if row else edge_to))

    causing_lines = "\n".join(f"- [← {t}]({i})" for i, t in causing_titles) or "（なし）"
    caused_lines  = "\n".join(f"- [→ {t}]({i})" for i, t in caused_titles)  or "（なし）"

    lines = [
        "---",
        f"id: {issue.get('id', '')}",
        f"title: {issue.get('title', '')}",
        f"project: {issue.get('project_name', '')}",
        f"category: {issue.get('category', '')}",
        f"priority: {issue.get('priority', '')}",
        f"status: {issue.get('status', '')}",
        f"assignee: {issue.get('assignee') or ''}",
        f"created_at: {issue.get('created_at', '')}",
        f"updated_at: {issue.get('updated_at', '')}",
        "---",
        "",
        f"# {issue.get('title', '')}",
        "",
        "## 原因 (Cause)",
        issue.get("cause") or "（未入力）",
        "",
        "## 影響・リスク (Impact)",
        issue.get("impact") or "（未入力）",
        "",
        "## 説明 (Description)",
        issue.get("description") or "（未入力）",
        "",
        "## 対応策 (Action)",
        issue.get("action_next") or "（未入力）",
        "",
        "## メモ (Context Memo)",
        issue.get("context_memo") or "（未入力）",
        "",
        "## 関連課題 (Related Issues)",
        "### この課題の原因となっている課題（←）",
        causing_lines,
        "",
        "### この課題が引き起こしている課題（→）",
        caused_lines,
    ]
    return "\n".join(lines)


def _save_issue_markdown(issue_id: str, db) -> None:
    """Issue + Edges を読んでMarkdownファイルを書き出し、ChromaDBインデックスも更新する。"""
    row = db.execute(
        text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    if not row:
        logger.warning(f"[IssueMemo] issue_id={issue_id} not found, skipping markdown save")
        return

    issue = _issue_row_to_dict(row)
    edge_rows = db.execute(
        text("SELECT * FROM issue_edges WHERE from_id = :id OR to_id = :id"),
        {"id": issue_id},
    ).fetchall()

    md_content = _render_issue_markdown(issue, edge_rows, db)

    project_dir = ISSUE_MEMOS_DIR / (issue.get("project_name") or "default")
    project_dir.mkdir(parents=True, exist_ok=True)
    md_path = project_dir / f"{issue_id}.md"
    md_path.write_text(md_content, encoding="utf-8")
    logger.info(f"[IssueMemo] Saved markdown: {md_path}")

    try:
        indexer = IssueMemoIndexer()
        indexer.index_file(md_path)
    except Exception as e:
        logger.error(f"[IssueMemo] ChromaDB index failed for {issue_id}: {e}")


def _issue_row_to_dict(row) -> dict:
    keys = [
        "id", "project_name", "title", "raw_input", "category", "priority",
        "status", "description", "cause", "impact", "action_next",
        "is_collapsed", "pos_x", "pos_y", "template_id", "created_at", "updated_at",
        "assignee", "context_memo", "deadline",
        "is_task", "completed_at", "due_time", "section_name", "parent_id",
    ]
    # rowの長さに合わせてキーを切り取る（古いDBとの互換性）
    return dict(zip(keys[:len(row)], row))


def _edge_row_to_dict(row) -> dict:
    keys = ["id", "from_id", "to_id", "confirmed", "created_at"]
    return dict(zip(keys, row))


# --- タグ抽出・FTS5 ヘルパー ---

_TAG_PATTERN = re.compile(r'#([\w\u3040-\u9faf]+)', re.UNICODE)


def _extract_and_save_tags(issue_id: str, memo_text: str, db):
    """メモから #タグ を抽出してissue_tagsに保存"""
    tags = set(_TAG_PATTERN.findall(memo_text or ""))
    now = _now_iso()
    # 既存タグ削除して再挿入
    db.execute(text("DELETE FROM issue_tags WHERE issue_id = :id"), {"id": issue_id})
    for tag in tags:
        db.execute(text(
            "INSERT OR IGNORE INTO issue_tags (id, issue_id, tag_name, created_at) VALUES (:id, :issue_id, :tag, :now)"
        ), {"id": str(uuid.uuid4()), "issue_id": issue_id, "tag": tag, "now": now})
    db.commit()


def _update_fts_index(issue_id: str, title: str, description: str, memo: str, db):
    """FTS5インデックスを更新"""
    try:
        db.execute(text("DELETE FROM issues_fts WHERE issue_id = :id"), {"id": issue_id})
        db.execute(text(
            "INSERT INTO issues_fts (issue_id, title, description, context_memo) VALUES (:id, :title, :desc, :memo)"
        ), {"id": issue_id, "title": title or "", "desc": description or "", "memo": memo or ""})
        db.commit()
    except Exception:
        pass  # FTS5テーブルが未作成の場合はスキップ


def _call_gemini_capture(raw_input: str, existing_issues: list) -> dict:
    """Gemini で課題を構造化し、因果・重複候補を返す"""
    from gemini_client import get_client
    from google.genai import types

    client = get_client()

    context_lines = []
    for iss in existing_issues:
        desc = (iss["description"] or "")[:80]
        context_lines.append(f"- id={iss['id']} title={iss['title']} description={desc}")
    context_str = "\n".join(context_lines) if context_lines else "（既存課題なし）"

    prompt = f"""建設PM/CMの課題を構造化し因果・重複を分析してください。

新規課題: {raw_input}
既存課題: {context_str}

以下JSONのみ返答（各文字列フィールドは30文字以内で簡潔に）:
{{"title":"20字以内","category":"工程","priority":"normal","description":"30字以内","cause":"30字以内か空","impact":"30字以内か空","action_next":"30字以内か空","status":"発生中","causal_candidates":[],"duplicate_candidates":[]}}

- category: 工程/コスト/品質/安全
- priority: critical/normal/minor
- status: 発生中/対応中/解決済み
- causal_candidates要素: {{"issue_id":"uuid","direction":"cause_of_new","confidence":0.85,"reason":"20字以内"}}
  direction: cause_of_new=既存が原因, result_of_new=既存が結果
- duplicate_candidates要素: {{"issue_id":"uuid","similarity":0.90,"reason":"20字以内"}}
- causal_candidatesはconfidence>=0.7のみ, duplicate_candidatesはsimilarity>=0.85のみ
- 候補なければ空配列[]"""

    # gemini-3-flash-preview は max_output_tokens=1024 設定時に誤って90字で打ち切るため省略
    # thinking_level="minimal" は spec 準拠で try/except で適用
    config = types.GenerateContentConfig(
        system_instruction="建設PM/CMの課題を構造化するアシスタント。指定のJSON形式のみで返答せよ。日本語で回答。",
        temperature=0.2,
    )
    try:
        config.thinking_config = types.ThinkingConfig(
            thinking_budget_tokens=None, thinking_level="minimal"
        )
    except Exception:
        pass

    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=prompt,
        config=config,
    )

    raw = response.text.strip()

    # マークダウンフェンスを除去
    import re as _re
    raw = _re.sub(r'^```(?:json)?\s*', '', raw)
    raw = _re.sub(r'\s*```$', '', raw).strip()

    # 先頭の { から末尾の } を切り出す（余計なテキストが前後にある場合の対策）
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end + 1]

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"Gemini JSON parse error: {e}\nraw: {raw[:300]}")
        raise


# ---------- 再利用可能なコアロジック ----------

def capture_issue_core(raw_input: str, project_name: str, db) -> dict:
    """課題テキストをAI構造化してDBに保存し、因果・重複候補を返す。
    chat.py からも呼べるよう独立関数として定義。"""
    rows = db.execute(
        text("SELECT id, title, description FROM issues WHERE project_name = :pn"),
        {"pn": project_name},
    ).fetchall()
    existing = [{"id": r[0], "title": r[1], "description": r[2]} for r in rows]

    result = _call_gemini_capture(raw_input, existing)

    now = _now_iso()
    issue_id = str(uuid.uuid4())

    db.execute(
        text("""
            INSERT INTO issues (
                id, project_name, title, raw_input, category, priority, status,
                description, cause, impact, action_next,
                is_collapsed, pos_x, pos_y, template_id, created_at, updated_at
            ) VALUES (
                :id, :project_name, :title, :raw_input, :category, :priority, :status,
                :description, :cause, :impact, :action_next,
                0, 0.0, 0.0, NULL, :created_at, :updated_at
            )
        """),
        {
            "id": issue_id,
            "project_name": project_name,
            "title": (result.get("title") or raw_input)[:20],
            "raw_input": raw_input,
            "category": result.get("category") or "工程",
            "priority": result.get("priority") or "normal",
            "status": result.get("status") or "発生中",
            "description": result.get("description") or "",
            "cause": result.get("cause") or "",
            "impact": result.get("impact") or "",
            "action_next": result.get("action_next") or "",
            "created_at": now,
            "updated_at": now,
        },
    )
    db.commit()

    row = db.execute(
        text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    issue = _issue_row_to_dict(row)

    # Markdown保存 + インデックス更新
    try:
        _save_issue_markdown(issue_id, db)
    except Exception as e:
        logger.error(f"[IssueMemo] Failed to save markdown for {issue_id}: {e}")

    causal_candidates = [
        c for c in result.get("causal_candidates", [])
        if isinstance(c.get("confidence"), (int, float)) and c["confidence"] >= 0.7
    ]
    duplicate_candidates = [
        c for c in result.get("duplicate_candidates", [])
        if isinstance(c.get("similarity"), (int, float)) and c["similarity"] >= 0.85
    ]

    return {
        "issue": issue,
        "causal_candidates": causal_candidates,
        "duplicate_candidates": duplicate_candidates,
    }


def _generate_triage_questions(project_name: str, template_id: str, db) -> dict:
    """マインドマップのノード・フェーズ・カテゴリを Gemini に渡し、
    課題トリアージ用の質問セットを生成して DB に保存する。"""
    from gemini_client import get_client
    from google.genai import types
    import mindmap.template_loader as template_loader

    # テンプレート ID として試みる（raw dict 返却）
    try:
        data = template_loader.load_template(template_id)
    except Exception:
        # プロジェクト ID として試みる → テンプレート ID を取得して再ロード
        import mindmap.project_store as project_store
        proj_data = project_store.get_project_data(template_id)
        if not proj_data:
            raise ValueError(f"template_id='{template_id}' はテンプレートでもプロジェクトでも見つかりません")
        tmpl_id = proj_data["project"]["template_id"]
        data = template_loader.load_template(tmpl_id)

    raw_nodes = data.get("nodes", [])
    raw_phases = data.get("phases", [])
    raw_categories = data.get("categories", [])

    node_summaries = [
        {
            "id": n.get("id", ""),
            "label": n.get("label", ""),
            "phase": n.get("phase", ""),
            "category": n.get("category", ""),
            "key_stakeholders": (n.get("key_stakeholders") or [])[:3],
        }
        for n in raw_nodes[:50]
    ]
    phases = [{"id": p.get("id", ""), "name": p.get("name", "")} for p in raw_phases]
    categories = [{"id": c.get("id", ""), "name": c.get("name", "")} for c in raw_categories]

    prompt = f"""建設プロジェクトのマインドマップから課題トリアージ用の質問セットを生成してください。

フェーズ: {json.dumps(phases, ensure_ascii=False)}
カテゴリ: {json.dumps(categories, ensure_ascii=False)}
ノード（上位50件）: {json.dumps(node_summaries, ensure_ascii=False)}

以下の JSON 形式のみで返答してください:
{{"phase_question":{{"label":"この課題はどの工程フェーズで発生しましたか？","options":[{{"value":"phase_id","label":"フェーズ名","node_ids":["n1","n2"]}}]}},"category_question":{{"label":"この課題はどの専門分野に関係しますか？","options":[{{"value":"cat_id","label":"カテゴリ名","node_ids":["n1"]}}]}},"node_questions":[{{"node_id":"n1","node_label":"ノード名","question":"この課題は〇〇と関連がありますか？","typical_assignee":"担当役割"}}],"assignee_question":{{"label":"この課題の主担当者はどの役割ですか？","options":["役割1","役割2"]}}}}

- node_questions は最重要ノード（フェーズ横断・多くの依存関係を持つ）を優先して最大15件
- typical_assignee は key_stakeholders から推測
- 日本語で回答"""

    client = get_client()
    config = types.GenerateContentConfig(
        system_instruction="建設PM/CMの課題整理アシスタント。指定のJSON形式のみで返答せよ。",
        temperature=0.1,
    )
    response = client.models.generate_content(
        model="gemini-3.1-flash-lite-preview",
        contents=prompt,
        config=config,
    )

    import re as _re
    raw = response.text.strip()
    raw = _re.sub(r'^```(?:json)?\s*', '', raw)
    raw = _re.sub(r'\s*```$', '', raw).strip()
    start = raw.find('{')
    end = raw.rfind('}')
    if start != -1 and end != -1:
        raw = raw[start:end + 1]
    question_data = json.loads(raw)

    now = _now_iso()
    record_id = str(uuid.uuid4())
    db.execute(
        text("DELETE FROM issue_triage_questions WHERE project_name = :pn"),
        {"pn": project_name},
    )
    db.execute(
        text("""
            INSERT INTO issue_triage_questions (id, project_name, question_json, generated_at, template_id)
            VALUES (:id, :pn, :qj, :ga, :tid)
        """),
        {
            "id": record_id,
            "pn": project_name,
            "qj": json.dumps(question_data, ensure_ascii=False),
            "ga": now,
            "tid": template_id,
        },
    )
    db.commit()
    return question_data


# ---------- エンドポイント ----------

@router.get("/api/issues/memo-search")
def memo_search(
    q: str,
    project_name: Optional[str] = None,
    top_k: int = 8,
):
    """
    課題因果メモを自然言語クエリで検索する（Obsidian風 LLM 検索）。

    params:
      q           - 自然言語クエリ（例: "鉄骨納期が遅れている原因"）
      project_name - プロジェクト名でフィルタ（省略時は全プロジェクト）
      top_k        - 返す件数（デフォルト8）

    returns:
      {"results": [{issue_id, title, project_name, category, priority, status, score, snippet}]}
    """
    if not q.strip():
        raise HTTPException(status_code=400, detail="クエリ q が空です")
    top_k = max(1, min(top_k, 20))
    try:
        indexer = IssueMemoIndexer()
        results = indexer.search(q, project_name=project_name, top_k=top_k)
        return {"results": results}
    except Exception as e:
        logger.error(f"[IssueMemo] memo_search failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"検索エラー: {str(e)}")


# ===== 課題チャット（2段階検索パイプライン） =====

CHAT_MAX_ISSUES = 30

# --- Stage 1: 意図分類（ルールベース、LLM不要） ---

_SQL_PATTERNS = {
    "priority_critical": (["重大", "critical", "クリティカル", "優先度の高い", "緊急"], "priority = 'critical'"),
    "priority_minor": (["軽微", "minor", "低優先"], "priority = 'minor'"),
    "status_active": (["発生中", "未解決", "オープン"], "status = '発生中'"),
    "status_wip": (["対応中", "進行中"], "status = '対応中'"),
    "status_resolved": (["解決済み", "完了", "クローズ"], "status = '解決済み'"),
    "cat_process": (["工程"], "category = '工程'"),
    "cat_cost": (["コスト", "予算", "費用"], "category = 'コスト'"),
    "cat_quality": (["品質"], "category = '品質'"),
    "cat_safety": (["安全"], "category = '安全'"),
    "unassigned": (["未割当", "未割り当て", "担当なし", "unassigned"], "assignee IS NULL OR assignee = ''"),
    "overdue": (["期限超過", "期限切れ", "overdue", "遅延"], f"deadline < date('now')"),
}
_SUMMARY_KEYWORDS = ["まとめ", "概要", "summary", "全体", "整理して", "一覧にして", "俯瞰", "サマリー"]


def _classify_chat_intent(message: str) -> tuple:
    """ユーザーメッセージから検索戦略を判定。(strategy, sql_filters)"""
    msg = message.lower()

    # 集約系チェック
    if any(kw in msg for kw in _SUMMARY_KEYWORDS):
        return ("aggregate", [])

    # SQL系チェック
    sql_filters = []
    for key, (keywords, clause) in _SQL_PATTERNS.items():
        if any(kw in msg for kw in keywords):
            sql_filters.append(clause)
    if sql_filters:
        return ("sql", sql_filters)

    # デフォルト: Embedding検索
    return ("semantic", [])


# --- Stage 2: 検索実行 ---

def _retrieve_by_sql(db, project_name, sql_filters, limit=50):
    """構造化フィルタで課題を取得"""
    where_parts = list(sql_filters)
    params = {}
    if project_name:
        where_parts.append("project_name = :project_name")
        params["project_name"] = project_name
    where = " AND ".join(f"({w})" for w in where_parts) if where_parts else "1=1"
    params["limit"] = limit
    rows = db.execute(text(
        f"SELECT * FROM issues WHERE {where} ORDER BY updated_at DESC LIMIT :limit"
    ), params).fetchall()
    total = db.execute(text(
        f"SELECT COUNT(*) FROM issues WHERE {where}"
    ), {k: v for k, v in params.items() if k != "limit"}).scalar()
    return [_issue_row_to_dict(r) for r in rows], total


def _retrieve_by_embedding(db, project_name, query, top_k=15):
    """Embedding検索で関連課題を取得"""
    try:
        indexer = IssueMemoIndexer()
        results = indexer.search(query, project_name=project_name, top_k=top_k)
        if not results:
            return [], 0
        ids = [r["issue_id"] for r in results]
        placeholders = ", ".join(f":id{i}" for i in range(len(ids)))
        params = {f"id{i}": iid for i, iid in enumerate(ids)}
        rows = db.execute(text(
            f"SELECT * FROM issues WHERE id IN ({placeholders})"
        ), params).fetchall()
        return [_issue_row_to_dict(r) for r in rows], len(results)
    except Exception as e:
        logger.warning(f"Embedding search failed, falling back to SQL: {e}")
        return _retrieve_by_sql(db, project_name, [], limit=20)


def _retrieve_by_aggregate(db, project_name):
    """統計情報 + 代表サンプルで集約ビューを構築"""
    params = {}
    where = ""
    if project_name:
        where = "WHERE project_name = :project_name"
        params["project_name"] = project_name

    # 統計
    stats = db.execute(text(
        f"SELECT category, priority, status, COUNT(*) as cnt FROM issues {where} GROUP BY category, priority, status"
    ), params).fetchall()
    total = sum(r[3] for r in stats)
    stats_text = f"全{total}件\n"
    for r in stats:
        stats_text += f"  {r[0]}/{r[1]}/{r[2]}: {r[3]}件\n"

    # 代表サンプル: critical + 各カテゴリから最新数件
    sample_issues = []
    for prio in ["critical", "normal"]:
        p = {**params, "prio": prio}
        rows = db.execute(text(
            f"SELECT * FROM issues {where}{' AND' if where else 'WHERE'} priority = :prio ORDER BY updated_at DESC LIMIT 5"
        ), p).fetchall()
        sample_issues.extend([_issue_row_to_dict(r) for r in rows])

    # 重複除去
    seen = set()
    unique = []
    for d in sample_issues:
        if d["id"] not in seen:
            seen.add(d["id"])
            unique.append(d)

    return unique[:CHAT_MAX_ISSUES], total, stats_text


# --- プロンプト構築 ---

def _compact_issue_line(d: dict) -> str:
    """1課題を1-2行にコンパクト化"""
    parts = [f"[{d.get('priority','normal')}] {d.get('title','')}"]
    meta = []
    if d.get("assignee"): meta.append(f"担当:{d['assignee']}")
    if d.get("deadline"): meta.append(f"期限:{d['deadline']}")
    meta.append(d.get("status", ""))
    parts.append(f"({', '.join(meta)})")
    if d.get("description"): parts.append(f"\n  {d['description'][:80]}")
    if d.get("context_memo"): parts.append(f"\n  メモ: {d['context_memo'][:60]}")
    return " ".join(parts)


class IssueChatRequest(BaseModel):
    message: str
    project_name: Optional[str] = None
    issue_ids: Optional[List[str]] = None


@router.post("/api/issues/chat")
def issue_chat(req: IssueChatRequest, db=Depends(get_db)):
    """2段階検索パイプラインで課題を横断分析するLLMチャット。1000件+対応。"""
    message = (req.message or "")[:500]  # 入力制限
    if not message.strip():
        raise HTTPException(status_code=400, detail="メッセージが空です")

    # 指定IDがある場合は直接取得
    if req.issue_ids:
        placeholders = ", ".join(f":id{i}" for i in range(len(req.issue_ids)))
        params = {f"id{i}": iid for i, iid in enumerate(req.issue_ids)}
        rows = db.execute(text(
            f"SELECT * FROM issues WHERE id IN ({placeholders})"
        ), params).fetchall()
        issues = [_issue_row_to_dict(r) for r in rows]
        total = len(issues)
        strategy = "direct"
        stats_header = ""
    else:
        # 意図分類
        strategy, sql_filters = _classify_chat_intent(message)

        if strategy == "sql":
            issues, total = _retrieve_by_sql(db, req.project_name, sql_filters)
            stats_header = ""
        elif strategy == "aggregate":
            issues, total, stats_header = _retrieve_by_aggregate(db, req.project_name)
        else:
            issues, total = _retrieve_by_embedding(db, req.project_name, message)
            stats_header = ""

    # コンパクトプロンプト構築
    display_issues = issues[:CHAT_MAX_ISSUES]
    context_lines = [_compact_issue_line(d) for d in display_issues]
    context_text = "\n---\n".join(context_lines) if context_lines else "（該当する課題なし）"

    truncation_note = ""
    if total > len(display_issues):
        truncation_note = f"\n（{total}件中{len(display_issues)}件を表示）"

    prompt = (
        f"あなたは建設PM/CM業務の課題整理アシスタントです。\n"
        f"以下の課題データを踏まえて、ユーザーの質問に答えてください。\n\n"
        f"{stats_header}"
        f"## 課題データ ({len(display_issues)}件{truncation_note})\n{context_text}\n\n"
        f"## ユーザーの質問\n{message}\n\n"
        f"簡潔かつ具体的に回答してください。課題の参照時はタイトルを明示してください。"
    )

    try:
        from gemini_client import get_client
        import config
        client = get_client()
        response = client.models.generate_content(
            model=config.GEMINI_MODEL_TRANSCRIPTION,
            contents=prompt,
        )
        return {
            "response": (response.text or "").strip(),
            "issues_count": len(display_issues),
            "total_issues": total,
            "retrieval_strategy": strategy,
        }
    except Exception as e:
        logger.error(f"Issue chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI応答エラー: {str(e)}")


# ===== タグ =====

@router.get("/api/issues/tags")
def list_tags(project_name: Optional[str] = None, db=Depends(get_db)):
    """プロジェクト内のタグ一覧（使用回数付き）"""
    if project_name:
        rows = db.execute(text(
            "SELECT t.tag_name, COUNT(*) as cnt FROM issue_tags t "
            "JOIN issues i ON t.issue_id = i.id WHERE i.project_name = :p "
            "GROUP BY t.tag_name ORDER BY cnt DESC"
        ), {"p": project_name}).fetchall()
    else:
        rows = db.execute(text(
            "SELECT tag_name, COUNT(*) as cnt FROM issue_tags GROUP BY tag_name ORDER BY cnt DESC"
        )).fetchall()
    return {"tags": [{"name": r[0], "count": r[1]} for r in rows]}


@router.get("/api/issues/{issue_id}/tags")
def get_issue_tags(issue_id: str, db=Depends(get_db)):
    """特定課題のタグ一覧"""
    rows = db.execute(text(
        "SELECT tag_name FROM issue_tags WHERE issue_id = :id"
    ), {"id": issue_id}).fetchall()
    return {"tags": [r[0] for r in rows]}


# ===== FTS5キーワード検索 =====

@router.get("/api/issues/search")
def search_issues(
    q: str,
    mode: str = "auto",
    project_name: Optional[str] = None,
    db=Depends(get_db),
):
    """課題検索。mode: fts(キーワード), semantic(意味), auto(両方マージ)"""
    results = []

    if mode in ("fts", "auto"):
        try:
            fts_rows = db.execute(text(
                "SELECT issue_id, snippet(issues_fts, 3, '<b>', '</b>', '...', 30) as snippet "
                "FROM issues_fts WHERE issues_fts MATCH :q LIMIT 20"
            ), {"q": q}).fetchall()
            for r in fts_rows:
                results.append({"issue_id": r[0], "snippet": r[1], "source": "keyword"})
        except Exception as e:
            logger.warning(f"FTS5 search failed: {e}")

    if mode in ("semantic", "auto"):
        try:
            indexer = IssueMemoIndexer()
            sem_results = indexer.search(q, project_name=project_name, top_k=10)
            for r in sem_results:
                if not any(x["issue_id"] == r["issue_id"] for x in results):
                    results.append({**r, "source": "semantic"})
        except Exception as e:
            logger.warning(f"Semantic search failed: {e}")

    # プロジェクトフィルタ
    if project_name and results:
        issue_ids = [r["issue_id"] for r in results]
        placeholders = ", ".join(f":id{i}" for i in range(len(issue_ids)))
        params = {f"id{i}": iid for i, iid in enumerate(issue_ids)}
        params["p"] = project_name
        valid = db.execute(text(
            f"SELECT id FROM issues WHERE id IN ({placeholders}) AND project_name = :p"
        ), params).fetchall()
        valid_ids = {r[0] for r in valid}
        results = [r for r in results if r["issue_id"] in valid_ids]

    return {"results": results, "query": q, "mode": mode}


@router.get("/api/issues/projects")
def list_projects(db=Depends(get_db)):
    """登録済みプロジェクト名のユニーク一覧"""
    rows = db.execute(
        text("SELECT DISTINCT project_name FROM issues ORDER BY project_name")
    ).fetchall()
    return {"projects": [r[0] for r in rows]}


@router.get("/api/issues/projects-summary")
def list_projects_summary(db=Depends(get_db)):
    """プロジェクト名と課題件数のサマリ（軽量版）"""
    rows = db.execute(
        text("SELECT project_name, COUNT(*) as count FROM issues GROUP BY project_name ORDER BY project_name")
    ).fetchall()
    return {"projects": [{"name": r[0], "count": r[1]} for r in rows]}


@router.post("/api/issues/capture")
def capture_issue(req: CaptureRequest, db=Depends(get_db)):
    """課題テキストを DB に保存し、因果・重複候補を返す。skip_ai=True のとき AI 処理をスキップ。"""
    try:
        if req.skip_ai:
            now = _now_iso()
            issue_id = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO issues (
                    id, project_name, title, raw_input, category, priority, status,
                    description, cause, impact, action_next,
                    is_collapsed, pos_x, pos_y, template_id, created_at, updated_at
                ) VALUES (
                    :id, :project_name, :title, :raw_input, '工程', 'normal', '発生中',
                    '', '', '', '', 0, 0.0, 0.0, NULL, :created_at, :updated_at
                )
            """), {
                "id": issue_id,
                "project_name": req.project_name,
                "title": req.raw_input[:60],
                "raw_input": req.raw_input,
                "created_at": now,
                "updated_at": now,
            })
            db.commit()
            row = db.execute(text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
            return {"issue": _issue_row_to_dict(row), "causal_candidates": [], "duplicate_candidates": []}
        return capture_issue_core(req.raw_input, req.project_name, db)
    except Exception as e:
        logger.error(f"Issue capture failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"処理エラー: {str(e)}")


@router.post("/api/issues/capture-photo")
async def capture_issue_from_photo(
    image: UploadFile = File(...),
    project_name: str = Form(...),
    db=Depends(get_db),
):
    """写真（PNG/JPEG）を Gemini Vision で分析し、課題テキストを抽出してDBに保存する。"""
    from gemini_client import get_client
    from google.genai import types as genai_types

    ALLOWED_MIME = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
    mime = image.content_type or "image/jpeg"
    if mime not in ALLOWED_MIME:
        raise HTTPException(status_code=400, detail=f"対応形式: PNG/JPEG/WebP。受信: {mime}")

    try:
        img_bytes = await image.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"画像読み込みエラー: {e}")

    if len(img_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="画像サイズは10MB以内にしてください")

    # Gemini Vision で画像を分析して課題テキストを生成
    try:
        client = get_client()
        image_part = genai_types.Part.from_bytes(data=img_bytes, mime_type=mime)
        vision_prompt = """この建設現場の写真を分析し、写っている課題・問題点を日本語で簡潔に説明してください。

以下の観点で確認してください:
- 安全上の問題（足場、養生、保護具など）
- 品質上の問題（仕上がり、寸法、材料など）
- 工程上の問題（遅延、未完了作業など）
- コスト上の問題（材料の無駄、やり直しなど）

写真に写っている具体的な課題を2〜3文で記述してください。課題が見当たらない場合は「問題なし」と答えてください。"""

        config = genai_types.GenerateContentConfig(
            system_instruction="建設現場の写真から課題を抽出するアシスタント。日本語で簡潔に回答せよ。",
            temperature=0.1,
        )
        vision_response = client.models.generate_content(
            model="gemini-3.1-flash-lite-preview",
            contents=[image_part, vision_prompt],
            config=config,
        )
        extracted_text = vision_response.text.strip()
    except Exception as e:
        logger.error(f"Gemini Vision analysis failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"画像解析エラー: {str(e)}")

    if extracted_text == "問題なし" or not extracted_text:
        raise HTTPException(status_code=422, detail="写真から課題を検出できませんでした")

    # 抽出したテキストで通常の課題キャプチャを実行
    try:
        result = capture_issue_core(extracted_text, project_name, db)
        # 元の画像由来であることを raw_input に付記（任意）
        return {**result, "extracted_text": extracted_text}
    except Exception as e:
        logger.error(f"Issue capture from photo failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"課題登録エラー: {str(e)}")


@router.post("/api/issues/triage-questions/generate")
def generate_triage_questions(req: TriageGenerateRequest, db=Depends(get_db)):
    """マインドマップを Gemini で分析して課題トリアージ質問を事前生成・保存する。
    重い処理なので事前に（プロジェクト設定時などに）呼ぶ想定。"""
    try:
        result = _generate_triage_questions(req.project_name, req.template_id, db)
        return {"status": "ok", "questions": result}
    except Exception as e:
        logger.error(f"Triage question generation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"質問生成エラー: {str(e)}")


@router.get("/api/issues/triage-questions")
def get_triage_questions(project_name: str, raw_input: str = "", db=Depends(get_db)):
    """事前生成済みの構造的質問セットを即座に返す（AI なし）。
    raw_input を渡すとキーワードマッチで既存課題の候補も追加返却する。"""
    row = db.execute(
        text("""
            SELECT question_json, generated_at, template_id
            FROM issue_triage_questions
            WHERE project_name = :pn
            ORDER BY generated_at DESC LIMIT 1
        """),
        {"pn": project_name},
    ).fetchone()
    if not row:
        raise HTTPException(
            status_code=404,
            detail="質問セット未生成。先に POST /api/issues/triage-questions/generate を呼んでください。",
        )

    questions = json.loads(row[0])

    # raw_input が渡されたとき、キーワードマッチで既存課題候補を動的に追加
    related_issues_options = []
    if raw_input.strip():
        import re as _re
        _STOP = frozenset({
            "の","に","は","を","が","で","と","も","な","や","へ","から","まで","です",
            "ます","した","して","します","ある","あり","いる","この","その","こと","もの",
        })
        tokens = _re.split(r"[\s\u3000、。，．,.\-／/\(\)「」【】！？!?]+", raw_input.strip())
        keywords = [t for t in tokens if len(t) >= 2 and t not in _STOP][:8]
        if keywords:
            like_conds = " OR ".join(
                [f"(title LIKE :kw{i} OR description LIKE :kw{i})" for i in range(len(keywords))]
            )
            params: dict = {"pn": project_name}
            for i, kw in enumerate(keywords):
                params[f"kw{i}"] = f"%{kw}%"
            rows = db.execute(
                text(f"""
                    SELECT id, title, category, status, assignee
                    FROM issues
                    WHERE project_name = :pn AND ({like_conds})
                    ORDER BY updated_at DESC LIMIT 10
                """),
                params,
            ).fetchall()
            for r in rows:
                related_issues_options.append({
                    "id": r[0], "title": r[1],
                    "category": r[2], "status": r[3], "assignee": r[4],
                })

    questions["related_issues_question"] = {
        "label": "関連する既存課題を選択してください（複数選択可・スキップ可）",
        "options": related_issues_options,
    }

    return {
        "questions": questions,
        "generated_at": row[1],
        "template_id": row[2],
    }


@router.post("/api/issues/triage-apply")
def triage_apply(req: TriageApplyRequest, db=Depends(get_db)):
    """ユーザーの選択（フェーズ・カテゴリ・関連ノード・担当者）を受け取り
    ノード保存とエッジを一括作成する。"""
    try:
        now = _now_iso()
        issue_id = str(uuid.uuid4())

        db.execute(text("""
            INSERT INTO issues (
                id, project_name, title, raw_input, category, priority, status,
                description, cause, impact, action_next,
                is_collapsed, pos_x, pos_y, template_id, created_at, updated_at, assignee
            ) VALUES (
                :id, :project_name, :title, :raw_input, :category, 'normal', '発生中',
                '', '', '', '', 0, 0.0, 0.0, NULL, :created_at, :updated_at, :assignee
            )
        """), {
            "id": issue_id,
            "project_name": req.project_name,
            "title": req.raw_input[:20],
            "raw_input": req.raw_input,
            "category": req.category_value or "工程",
            "created_at": now,
            "updated_at": now,
            "assignee": req.assignee or "",
        })

        edges_created = []
        for related_id in req.related_issue_ids:
            edge_id = str(uuid.uuid4())
            db.execute(text("""
                INSERT INTO issue_edges (id, from_id, to_id, confirmed, created_at)
                VALUES (:id, :from_id, :to_id, 1, :created_at)
            """), {
                "id": edge_id,
                "from_id": related_id,
                "to_id": issue_id,
                "created_at": now,
            })
            edges_created.append({"from_id": related_id, "to_id": issue_id})

        db.commit()
        row = db.execute(text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
        return {"issue": _issue_row_to_dict(row), "edges_created": edges_created}

    except Exception as e:
        logger.error(f"Triage apply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"処理エラー: {str(e)}")


@router.post("/api/issues/edges/confirm")
def confirm_edge(req: EdgeConfirmRequest, db=Depends(get_db)):
    """因果関係を確認し confirmed=true の場合のみエッジを保存"""
    if not req.confirmed:
        return {"ok": True, "saved": False}

    edge_id = str(uuid.uuid4())
    db.execute(
        text("""
            INSERT INTO issue_edges (id, from_id, to_id, confirmed, created_at)
            VALUES (:id, :from_id, :to_id, 1, :created_at)
        """),
        {"id": edge_id, "from_id": req.from_id, "to_id": req.to_id, "created_at": _now_iso()},
    )
    db.commit()

    # 因果関係が変わったので両issueのMarkdownを更新
    for iid in (req.from_id, req.to_id):
        try:
            _save_issue_markdown(iid, db)
        except Exception as e:
            logger.error(f"[IssueMemo] Failed to update markdown for {iid} after edge confirm: {e}")

    return {"ok": True, "saved": True, "edge_id": edge_id}


@router.get("/api/issues/members")
def list_members(project_name: str, db=Depends(get_db)):
    """プロジェクトメンバー一覧を返す"""
    rows = db.execute(
        text("SELECT id, project_name, name, role, created_at FROM project_members WHERE project_name = :pn ORDER BY name"),
        {"pn": project_name},
    ).fetchall()
    keys = ["id", "project_name", "name", "role", "created_at"]
    return {"members": [dict(zip(keys, r)) for r in rows]}


@router.post("/api/issues/members")
def add_member(req: MemberCreateRequest, db=Depends(get_db)):
    """プロジェクトメンバーを追加する"""
    member_id = str(uuid.uuid4())
    db.execute(
        text("INSERT INTO project_members (id, project_name, name, role, created_at) VALUES (:id, :pn, :name, :role, :created_at)"),
        {"id": member_id, "pn": req.project_name, "name": req.name, "role": req.role, "created_at": _now_iso()},
    )
    db.commit()
    return {"id": member_id, "project_name": req.project_name, "name": req.name, "role": req.role}


@router.delete("/api/issues/members/{member_id}")
def delete_member(member_id: str, db=Depends(get_db)):
    """プロジェクトメンバーを削除する"""
    db.execute(text("DELETE FROM project_members WHERE id = :id"), {"id": member_id})
    db.commit()
    return {"ok": True}


@router.get("/api/issues")
def list_issues(
    project_name: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
    category: Optional[str] = None,
    db=Depends(get_db),
):
    """課題一覧 + 関連エッジ一覧 + プロジェクト名一覧を返す（タスクは除外）"""
    where_clauses = ["(is_task = 0 OR is_task IS NULL)"]
    params: dict = {}

    if project_name:
        where_clauses.append("project_name = :project_name")
        params["project_name"] = project_name
    if status:
        where_clauses.append("status = :status")
        params["status"] = status
    if priority:
        where_clauses.append("priority = :priority")
        params["priority"] = priority
    if category:
        where_clauses.append("category = :category")
        params["category"] = category

    where_sql = ("WHERE " + " AND ".join(where_clauses)) if where_clauses else ""
    issue_rows = db.execute(
        text(f"SELECT * FROM issues {where_sql} ORDER BY created_at ASC"), params
    ).fetchall()
    issues = [_issue_row_to_dict(r) for r in issue_rows]

    # フィルター対象 issue の id セット内のエッジのみ返す
    issue_ids = {iss["id"] for iss in issues}
    if issue_ids:
        edge_rows = db.execute(text("SELECT * FROM issue_edges")).fetchall()
        edges = [
            _edge_row_to_dict(r)
            for r in edge_rows
            if r[1] in issue_ids and r[2] in issue_ids
        ]
    else:
        edges = []

    # 添付ファイル数をまとめて取得
    att_count_rows = db.execute(text(
        "SELECT issue_id, COUNT(*) FROM issue_attachments GROUP BY issue_id"
    )).fetchall()
    att_counts = {r[0]: r[1] for r in att_count_rows}
    for iss in issues:
        iss["attachment_count"] = att_counts.get(iss["id"], 0)

    proj_rows = db.execute(
        text("SELECT DISTINCT project_name FROM issues ORDER BY project_name")
    ).fetchall()
    projects = [r[0] for r in proj_rows]

    return {"issues": issues, "edges": edges, "projects": projects}


@router.patch("/api/issues/{issue_id}")
def update_issue(issue_id: str, req: IssueUpdateRequest, db=Depends(get_db)):
    """課題の部分更新（updated_at を自動更新）"""
    updates: dict = {}
    for field in UPDATABLE_FIELDS:
        val = getattr(req, field, None)
        if val is not None:
            updates[field] = val

    if not updates:
        raise HTTPException(status_code=400, detail="更新フィールドがありません")

    set_clauses = ", ".join([f"{k} = :{k}" for k in updates])
    updates["_id"] = issue_id
    updates["_updated_at"] = _now_iso()

    db.execute(
        text(f"UPDATE issues SET {set_clauses}, updated_at = :_updated_at WHERE id = :_id"),
        updates,
    )
    db.commit()

    row = db.execute(
        text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="課題が見つかりません")

    # Markdown更新 + インデックス更新
    try:
        _save_issue_markdown(issue_id, db)
    except Exception as e:
        logger.error(f"[IssueMemo] Failed to update markdown for {issue_id}: {e}")

    # タグ抽出 (context_memoが更新された場合)
    if "context_memo" in updates:
        try:
            _extract_and_save_tags(issue_id, updates["context_memo"], db)
        except Exception as e:
            logger.error(f"[Tags] Failed to extract tags for {issue_id}: {e}")

    # FTS5インデックス更新
    try:
        d = _issue_row_to_dict(row)
        _update_fts_index(issue_id, d.get("title", ""), d.get("description", ""), d.get("context_memo", ""), db)
    except Exception as e:
        logger.error(f"[FTS] Failed to update FTS for {issue_id}: {e}")

    return _issue_row_to_dict(row)


@router.delete("/api/issues/edges/{edge_id}")
def delete_edge(edge_id: str, db=Depends(get_db)):
    """因果エッジを削除"""
    result = db.execute(
        text("DELETE FROM issue_edges WHERE id = :id"), {"id": edge_id}
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"ok": True}


@router.delete("/api/issues/{issue_id}")
def delete_issue(issue_id: str, db=Depends(get_db)):
    """課題と関連エッジを物理削除"""
    # 削除前に関連issueのIDを取得（エッジ更新のため）
    related_ids: set[str] = set()
    edge_rows = db.execute(
        text("SELECT from_id, to_id FROM issue_edges WHERE from_id = :id OR to_id = :id"),
        {"id": issue_id},
    ).fetchall()
    for r in edge_rows:
        related_ids.update([r[0], r[1]])
    related_ids.discard(issue_id)

    db.execute(
        text("DELETE FROM issue_edges WHERE from_id = :id OR to_id = :id"),
        {"id": issue_id},
    )
    # サブタスクも削除
    db.execute(text("DELETE FROM issues WHERE parent_id = :id"), {"id": issue_id})
    db.execute(text("DELETE FROM issues WHERE id = :id"), {"id": issue_id})
    db.commit()

    # Markdownファイル削除 + インデックス削除
    try:
        indexer = IssueMemoIndexer()
        indexer.delete_from_index(issue_id)
        # プロジェクトディレクトリ以下を走査してファイル削除
        for md_path in ISSUE_MEMOS_DIR.rglob(f"{issue_id}.md"):
            md_path.unlink(missing_ok=True)
            logger.info(f"[IssueMemo] Deleted markdown file: {md_path}")
    except Exception as e:
        logger.error(f"[IssueMemo] Failed to delete markdown for {issue_id}: {e}")

    # 関連issueのMarkdownも更新（因果関係が変わるため）
    for rid in related_ids:
        try:
            _save_issue_markdown(rid, db)
        except Exception as e:
            logger.error(f"[IssueMemo] Failed to update markdown for {rid} after delete: {e}")

    return {"ok": True}


# ===== ノート（課題に紐づくメモ複数件） =====

class NoteCreateRequest(BaseModel):
    content: str
    author: Optional[str] = None


@router.get("/api/issues/{issue_id}/notes")
def list_notes(issue_id: str, db=Depends(get_db)):
    """課題に紐づくノート一覧"""
    rows = db.execute(text(
        "SELECT id, issue_id, author, content, photo_path, created_at "
        "FROM issue_notes WHERE issue_id = :id ORDER BY created_at DESC"
    ), {"id": issue_id}).fetchall()
    return {"notes": [
        {"id": r[0], "issue_id": r[1], "author": r[2], "content": r[3], "photo_path": r[4], "created_at": r[5]}
        for r in rows
    ]}


@router.post("/api/issues/{issue_id}/notes", status_code=201)
def create_note(issue_id: str, req: NoteCreateRequest, db=Depends(get_db)):
    """ノートを追加"""
    note_id = str(uuid.uuid4())
    now = _now_iso()
    db.execute(text(
        "INSERT INTO issue_notes (id, issue_id, author, content, created_at) "
        "VALUES (:id, :issue_id, :author, :content, :now)"
    ), {"id": note_id, "issue_id": issue_id, "author": req.author, "content": req.content, "now": now})
    db.commit()
    return {"id": note_id, "issue_id": issue_id, "author": req.author, "content": req.content, "created_at": now}


@router.delete("/api/issues/notes/{note_id}")
def delete_note(note_id: str, db=Depends(get_db)):
    """ノートを削除"""
    db.execute(text("DELETE FROM issue_notes WHERE id = :id"), {"id": note_id})
    db.commit()
    return {"ok": True}


# ===== 添付ファイル =====

ALLOWED_ATTACHMENT_MIME = {
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "application/pdf",
}


@router.get("/api/issues/{issue_id}/attachments")
def list_attachments(issue_id: str, db=Depends(get_db)):
    """課題に紐づく添付ファイル一覧"""
    rows = db.execute(text(
        "SELECT id, issue_id, attachment_type, file_path, thumbnail_path, caption, created_at "
        "FROM issue_attachments WHERE issue_id = :id ORDER BY created_at DESC"
    ), {"id": issue_id}).fetchall()
    return {"attachments": [
        {
            "id": r[0], "issue_id": r[1], "attachment_type": r[2],
            "file_path": r[3], "thumbnail_path": r[4],
            "caption": r[5], "created_at": r[6],
        }
        for r in rows
    ]}


@router.post("/api/issues/{issue_id}/attachments", status_code=201)
async def create_attachment(
    issue_id: str,
    file: UploadFile = File(...),
    attachment_type: str = Form("photo"),
    caption: str = Form(""),
    db=Depends(get_db),
):
    """課題に写真・図面・レポートを添付"""
    mime = file.content_type or ""
    if mime not in ALLOWED_ATTACHMENT_MIME:
        raise HTTPException(status_code=400, detail=f"対応形式: PNG/JPEG/WebP/PDF。受信: {mime}")

    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ファイルサイズは20MB以内にしてください")

    att_id = str(uuid.uuid4())
    now = _now_iso()

    # Save file to disk
    issue_dir = ISSUE_ATTACHMENTS_DIR / issue_id
    issue_dir.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "bin"
    file_name = f"{att_id}.{ext}"
    file_path = issue_dir / file_name
    file_path.write_bytes(file_bytes)

    # Generate thumbnail for images
    thumbnail_path_str = None
    if mime.startswith("image/"):
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(file_bytes))
            img.thumbnail((200, 200))
            thumb_name = f"{att_id}_thumb.jpg"
            thumb_path = issue_dir / thumb_name
            img.convert("RGB").save(thumb_path, "JPEG", quality=80)
            thumbnail_path_str = str(thumb_path.relative_to(ISSUE_ATTACHMENTS_DIR))
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")

    relative_path = str(file_path.relative_to(ISSUE_ATTACHMENTS_DIR))

    db.execute(text(
        "INSERT INTO issue_attachments (id, issue_id, attachment_type, file_path, thumbnail_path, caption, created_at) "
        "VALUES (:id, :issue_id, :type, :path, :thumb, :caption, :now)"
    ), {
        "id": att_id, "issue_id": issue_id, "type": attachment_type,
        "path": relative_path, "thumb": thumbnail_path_str,
        "caption": caption or None, "now": now,
    })
    db.commit()

    return {
        "id": att_id, "issue_id": issue_id, "attachment_type": attachment_type,
        "file_path": relative_path, "thumbnail_path": thumbnail_path_str,
        "caption": caption or None, "created_at": now,
    }


@router.delete("/api/issues/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, db=Depends(get_db)):
    """添付ファイルを削除"""
    row = db.execute(text(
        "SELECT file_path, thumbnail_path FROM issue_attachments WHERE id = :id"
    ), {"id": attachment_id}).fetchone()
    if row:
        # Delete files from disk
        from pathlib import Path
        for rel_path in [row[0], row[1]]:
            if rel_path:
                full_path = ISSUE_ATTACHMENTS_DIR / rel_path
                if full_path.exists():
                    full_path.unlink()
    db.execute(text("DELETE FROM issue_attachments WHERE id = :id"), {"id": attachment_id})
    db.commit()
    return {"ok": True}


@router.get("/api/issues/attachments/{attachment_id}/file")
def serve_attachment_file(attachment_id: str, db=Depends(get_db)):
    """添付ファイルを配信"""
    from fastapi.responses import FileResponse
    row = db.execute(text(
        "SELECT file_path FROM issue_attachments WHERE id = :id"
    ), {"id": attachment_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="添付ファイルが見つかりません")
    full_path = ISSUE_ATTACHMENTS_DIR / row[0]
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")
    return FileResponse(str(full_path))


@router.get("/api/issues/attachments/{attachment_id}/thumbnail")
def serve_attachment_thumbnail(attachment_id: str, db=Depends(get_db)):
    """サムネイル画像を配信"""
    from fastapi.responses import FileResponse
    row = db.execute(text(
        "SELECT thumbnail_path FROM issue_attachments WHERE id = :id"
    ), {"id": attachment_id}).fetchone()
    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="サムネイルがありません")
    full_path = ISSUE_ATTACHMENTS_DIR / row[0]
    if not full_path.exists():
        raise HTTPException(status_code=404, detail="サムネイルが見つかりません")
    return FileResponse(str(full_path))


# ===== パターンライブラリ =====

def _get_pattern_collection():
    """issue_patterns ChromaDB コレクションを取得（既存RAGとは分離）"""
    from dense_indexer import get_chroma_client
    from config import CHROMA_DB_DIR, ISSUE_PATTERN_COLLECTION
    client = get_chroma_client(CHROMA_DB_DIR)
    return client.get_or_create_collection(
        name=ISSUE_PATTERN_COLLECTION,
        metadata={"hnsw:space": "cosine"},
    )


@router.post("/api/issues/patterns/extract")
def extract_patterns(project_name: str = "", db=Depends(get_db)):
    """解決済み因果チェーン (3+ノード) をパターンとして ChromaDB に保存"""
    from dense_indexer import _embed_batch_with_retry

    where = "WHERE status = '解決済み' AND (is_task = 0 OR is_task IS NULL)"
    params: dict = {}
    if project_name:
        where += " AND project_name = :pn"
        params["pn"] = project_name

    resolved_rows = db.execute(text(
        f"SELECT id, title, description, category, project_name FROM issues {where}"
    ), params).fetchall()
    resolved_ids = {r[0] for r in resolved_rows}
    resolved_map = {r[0]: {"id": r[0], "title": r[1], "description": r[2], "category": r[3], "project_name": r[4]} for r in resolved_rows}

    if not resolved_ids:
        return {"extracted": 0, "message": "解決済み課題がありません"}

    # エッジを取得
    edge_rows = db.execute(text("SELECT from_id, to_id FROM issue_edges WHERE confirmed = 1")).fetchall()

    # 解決済みノードだけでチェーンを探索 (BFS)
    import networkx as nx
    G = nx.DiGraph()
    for r in edge_rows:
        if r[0] in resolved_ids and r[1] in resolved_ids:
            G.add_edge(r[0], r[1])

    # 弱連結コンポーネントで3+ノードのチェーンを抽出
    UG = G.to_undirected()
    chains = [c for c in nx.connected_components(UG) if len(c) >= 3]

    collection = _get_pattern_collection()
    extracted = 0

    for chain_nodes in chains:
        chain_list = list(chain_nodes)
        pattern_id = f"pattern-{'_'.join(sorted(chain_list)[:5])}"

        # パターンのテキスト表現
        titles = [resolved_map[nid]["title"] for nid in chain_list if nid in resolved_map]
        categories = list({resolved_map[nid]["category"] for nid in chain_list if nid in resolved_map})
        descriptions = [resolved_map[nid].get("description") or "" for nid in chain_list if nid in resolved_map]
        pn = next((resolved_map[nid]["project_name"] for nid in chain_list if nid in resolved_map), "")

        pattern_text = f"因果パターン ({'/'.join(categories)}): {' → '.join(titles[:5])}"
        detail_text = " | ".join(f"{t}: {d[:40]}" for t, d in zip(titles, descriptions) if d)

        # Embedding 生成
        try:
            embeddings = _embed_batch_with_retry([pattern_text])
            if not embeddings or not embeddings[0]:
                continue
        except Exception as e:
            logger.warning(f"[PatternExtract] Embedding failed: {e}")
            continue

        collection.upsert(
            ids=[pattern_id],
            embeddings=[embeddings[0]],
            documents=[pattern_text + "\n" + detail_text],
            metadatas=[{
                "project_name": pn,
                "categories": "/".join(categories),
                "node_count": str(len(chain_list)),
                "titles": " → ".join(titles[:5]),
            }],
        )
        extracted += 1

    return {"extracted": extracted, "total_chains": len(chains)}


@router.post("/api/issues/patterns/search")
def search_patterns(
    query: str = "",
    project_name: str = "",
    db=Depends(get_db),
):
    """類似パターンを検索 (similarity > 0.8)"""
    from dense_indexer import _embed_batch_with_retry

    if not query:
        raise HTTPException(status_code=400, detail="queryが必要です")

    try:
        embeddings = _embed_batch_with_retry([query])
        if not embeddings or not embeddings[0]:
            return {"patterns": []}
    except Exception:
        return {"patterns": []}

    collection = _get_pattern_collection()
    try:
        count = collection.count()
    except Exception:
        count = 0

    if count == 0:
        return {"patterns": []}

    results = collection.query(
        query_embeddings=[embeddings[0]],
        n_results=min(5, count),
    )

    patterns = []
    for i, doc_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i] if results.get("distances") else 1.0
        similarity = 1.0 - distance  # cosine distance → similarity
        if similarity < 0.3:
            continue
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        patterns.append({
            "id": doc_id,
            "similarity": round(similarity, 3),
            "titles": meta.get("titles", ""),
            "categories": meta.get("categories", ""),
            "node_count": int(meta.get("node_count", 0)),
            "document": results["documents"][0][i] if results.get("documents") else "",
        })

    return {"patterns": patterns}


# ===== 構造的ギャップ検出 =====

# プロジェクト別キャッシュ: { project_name: { "result": ..., "updated_at": ... } }
_graph_analysis_cache: dict = {}


@router.get("/api/issues/graph-analysis")
def analyze_graph_gaps(project_name: str, db=Depends(get_db)):
    """因果グラフ全体をネットワーク分析し、未接続だが関連すべきクラスターを発見"""
    import networkx as nx

    # キャッシュチェック: issue/edge の最終更新時刻と比較
    latest_row = db.execute(text(
        "SELECT MAX(updated_at) FROM issues WHERE project_name = :pn AND (is_task = 0 OR is_task IS NULL)"
    ), {"pn": project_name}).fetchone()
    latest_ts = latest_row[0] if latest_row and latest_row[0] else ""

    cached = _graph_analysis_cache.get(project_name)
    if cached and cached.get("updated_at") == latest_ts:
        return cached["result"]

    # グラフ構築
    issue_rows = db.execute(text(
        "SELECT id, title, category FROM issues "
        "WHERE project_name = :pn AND (is_task = 0 OR is_task IS NULL)"
    ), {"pn": project_name}).fetchall()

    if len(issue_rows) < 2:
        result = {"gaps": [], "stats": {"nodes": len(issue_rows), "edges": 0, "components": len(issue_rows)}}
        _graph_analysis_cache[project_name] = {"result": result, "updated_at": latest_ts}
        return result

    issue_map = {r[0]: {"id": r[0], "title": r[1], "category": r[2]} for r in issue_rows}
    issue_ids = set(issue_map.keys())

    edge_rows = db.execute(text(
        "SELECT from_id, to_id FROM issue_edges WHERE confirmed = 1"
    )).fetchall()
    valid_edges = [(r[0], r[1]) for r in edge_rows if r[0] in issue_ids and r[1] in issue_ids]

    G = nx.DiGraph()
    G.add_nodes_from(issue_ids)
    G.add_edges_from(valid_edges)

    # 連結成分を検出 (無向グラフとして)
    UG = G.to_undirected()
    components = list(nx.connected_components(UG))

    gaps = []
    if len(components) >= 2:
        # 各コンポーネントペアについてギャップ候補を生成
        for i in range(min(len(components), 5)):
            for j in range(i + 1, min(len(components), 5)):
                comp_a = list(components[i])[:5]
                comp_b = list(components[j])[:5]

                # カテゴリの重複があるクラスターは関連の可能性が高い
                cats_a = {issue_map[nid]["category"] for nid in comp_a if nid in issue_map}
                cats_b = {issue_map[nid]["category"] for nid in comp_b if nid in issue_map}
                shared_cats = cats_a & cats_b

                if shared_cats:
                    titles_a = [issue_map[nid]["title"] for nid in comp_a[:3] if nid in issue_map]
                    titles_b = [issue_map[nid]["title"] for nid in comp_b[:3] if nid in issue_map]
                    gaps.append({
                        "cluster_a": comp_a,
                        "cluster_b": comp_b,
                        "shared_categories": list(shared_cats),
                        "suggestion": f"「{'、'.join(titles_a[:2])}」と「{'、'.join(titles_b[:2])}」は{'/'.join(shared_cats)}カテゴリが共通。因果関係の確認を推奨。",
                    })

    # betweenness centrality (重要ノードの検出)
    key_nodes = []
    if len(G.nodes) >= 3 and len(valid_edges) >= 2:
        try:
            k = min(len(G.nodes), 100)
            bc = nx.betweenness_centrality(G, k=k)
            top_nodes = sorted(bc.items(), key=lambda x: x[1], reverse=True)[:5]
            key_nodes = [
                {"id": nid, "title": issue_map.get(nid, {}).get("title", ""), "centrality": round(score, 3)}
                for nid, score in top_nodes if score > 0
            ]
        except Exception:
            pass

    result = {
        "gaps": gaps[:10],
        "key_nodes": key_nodes,
        "stats": {
            "nodes": len(G.nodes),
            "edges": len(valid_edges),
            "components": len(components),
        },
    }
    _graph_analysis_cache[project_name] = {"result": result, "updated_at": latest_ts}
    return result


# ===== AI原因サジェスト =====

@router.post("/api/issues/{issue_id}/suggest-causes")
async def suggest_causes(issue_id: str, db=Depends(get_db)):
    """Gemini APIで課題の原因候補を提案する"""
    import asyncio
    from gemini_client import get_client
    from google.genai import types as genai_types

    # 対象課題を取得
    row = db.execute(text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="課題が見つかりません")
    issue = _issue_row_to_dict(row)

    # 同プロジェクトの既存課題を取得（コンテキスト用）
    existing_rows = db.execute(text(
        "SELECT id, title, description, category FROM issues "
        "WHERE project_name = :pn AND id != :id AND (is_task = 0 OR is_task IS NULL) "
        "ORDER BY created_at DESC LIMIT 30"
    ), {"pn": issue["project_name"], "id": issue_id}).fetchall()
    existing_context = "\n".join(
        f"- {r[1]} ({r[3]}): {(r[2] or '')[:60]}" for r in existing_rows
    ) or "（他に課題なし）"

    # 既存の因果エッジを取得
    edge_rows = db.execute(text(
        "SELECT from_id, to_id FROM issue_edges WHERE from_id = :id OR to_id = :id"
    ), {"id": issue_id}).fetchall()
    connected_ids = {r[0] for r in edge_rows} | {r[1] for r in edge_rows}
    connected_ids.discard(issue_id)

    prompt = f"""建設現場の課題について、考えられる原因を分析してください。

対象課題:
  タイトル: {issue['title']}
  カテゴリ: {issue['category']}
  説明: {issue.get('description') or '（なし）'}
  原因（既知）: {issue.get('cause') or '（未特定）'}
  影響: {issue.get('impact') or '（未特定）'}

同プロジェクトの他の課題:
{existing_context}

以下の形式でJSON配列のみ返答してください（3件以内）:
[{{"title":"原因の簡潔な名称（15字以内）","description":"具体的な説明（30字以内）","confidence":0.85,"reason":"なぜこれが原因と考えられるか（20字以内）"}}]

- confidence: 0.0〜1.0（確信度）
- 建設現場の実務経験に基づいた具体的な原因を提案
- 既に接続済みの課題ID: {list(connected_ids)} は除外
- 候補がない場合は空配列[]"""

    try:
        client = get_client()
        config = genai_types.GenerateContentConfig(
            system_instruction="建設現場の課題分析アシスタント。原因の候補を具体的に提案する。JSON配列のみ返答。",
            temperature=0.3,
        )

        async def _call_gemini():
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[prompt],
                config=config,
            )
            return response.text.strip()

        raw_text = await asyncio.wait_for(_call_gemini(), timeout=10.0)

        # JSONパース（```json ... ``` ラッパー対応）
        cleaned = raw_text
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()

        suggestions = json.loads(cleaned)
        if not isinstance(suggestions, list):
            suggestions = []

        # confidence < 0.3 をフィルタ
        suggestions = [s for s in suggestions if s.get("confidence", 0) >= 0.3]

        return {"suggestions": suggestions, "ai_status": "done"}

    except asyncio.TimeoutError:
        logger.warning(f"[SuggestCauses] Gemini timeout for issue {issue_id}")
        return {"suggestions": [], "ai_status": "error", "error": "AI分析がタイムアウトしました"}
    except json.JSONDecodeError as e:
        logger.warning(f"[SuggestCauses] JSON parse error: {e}")
        return {"suggestions": [], "ai_status": "error", "error": "AI応答の解析に失敗しました"}
    except Exception as e:
        logger.error(f"[SuggestCauses] Gemini error for issue {issue_id}: {e}")
        return {"suggestions": [], "ai_status": "error", "error": "AI分析が一時的に利用できません"}


# ===== タスク管理 =====

_DATE_PATTERNS = [
    (re.compile(r'明日'), 1),
    (re.compile(r'明後日'), 2),
    (re.compile(r'今日'), 0),
    (re.compile(r'来週'), 7),
]
_PRIORITY_PATTERN = re.compile(r'[pP]([1-3])|[!！]{2,}')
_TIME_PATTERN = re.compile(r'(\d{1,2})[:\uff1a](\d{2})')


def _parse_quick_add(raw: str) -> dict:
    """テキストから日付・優先度・時刻をルールベースで抽出"""
    result: dict = {"title": raw}
    text = raw

    # 優先度
    m = _PRIORITY_PATTERN.search(text)
    if m:
        if m.group(1):
            result["priority"] = {"1": "critical", "2": "normal", "3": "minor"}.get(m.group(1), "normal")
        else:
            result["priority"] = "critical"
        text = text[:m.start()] + text[m.end():]

    # 日付
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    for pattern, delta in _DATE_PATTERNS:
        if pattern.search(text):
            result["deadline"] = (today + timedelta(days=delta)).isoformat()
            text = pattern.sub("", text)
            break

    # 時刻
    m = _TIME_PATTERN.search(text)
    if m:
        result["due_time"] = f"{int(m.group(1)):02d}:{m.group(2)}"
        text = text[:m.start()] + text[m.end():]

    result["title"] = text.strip() or raw
    return result


class QuickAddRequest(BaseModel):
    text: str
    project_name: Optional[str] = None


@router.post("/api/tasks/quick-add")
def task_quick_add(req: QuickAddRequest, db=Depends(get_db)):
    """クイック追加: テキストからタスクを作成"""
    parsed = _parse_quick_add(req.text)
    now = _now_iso()
    issue_id = str(uuid.uuid4())

    db.execute(text("""
        INSERT INTO issues (
            id, project_name, title, raw_input, category, priority, status,
            is_task, deadline, due_time,
            is_collapsed, pos_x, pos_y, created_at, updated_at
        ) VALUES (
            :id, :project_name, :title, :raw_input, '工程', :priority, '発生中',
            1, :deadline, :due_time,
            0, 0.0, 0.0, :now, :now
        )
    """), {
        "id": issue_id,
        "project_name": req.project_name or "",
        "title": parsed["title"][:60],
        "raw_input": req.text,
        "priority": parsed.get("priority", "normal"),
        "deadline": parsed.get("deadline"),
        "due_time": parsed.get("due_time"),
        "now": now,
    })
    db.commit()

    row = db.execute(text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    return {"task": _issue_row_to_dict(row), "parsed": parsed}


@router.get("/api/tasks/today")
def tasks_today(project_name: Optional[str] = None, db=Depends(get_db)):
    """今日のタスク + 期限超過"""
    today = datetime.now(timezone.utc).date().isoformat()
    params: dict = {"today": today}
    project_filter = ""
    if project_name:
        project_filter = "AND project_name = :pn"
        params["pn"] = project_name

    overdue = db.execute(text(f"""
        SELECT * FROM issues WHERE is_task = 1 AND status != '解決済み'
        AND deadline IS NOT NULL AND deadline < :today AND parent_id IS NULL {project_filter}
        ORDER BY deadline ASC
    """), params).fetchall()

    today_tasks = db.execute(text(f"""
        SELECT * FROM issues WHERE is_task = 1 AND status != '解決済み'
        AND deadline = :today AND parent_id IS NULL {project_filter}
        ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'normal' THEN 1 WHEN 'minor' THEN 2 ELSE 3 END, due_time ASC
    """), params).fetchall()

    no_date = db.execute(text(f"""
        SELECT * FROM issues WHERE is_task = 1 AND status != '解決済み'
        AND deadline IS NULL AND parent_id IS NULL {project_filter}
        ORDER BY created_at DESC LIMIT 10
    """), params).fetchall()

    return {
        "overdue": [_issue_row_to_dict(r) for r in overdue],
        "today": [_issue_row_to_dict(r) for r in today_tasks],
        "no_date": [_issue_row_to_dict(r) for r in no_date],
    }


@router.get("/api/tasks/upcoming")
def tasks_upcoming(days: int = 7, project_name: Optional[str] = None, db=Depends(get_db)):
    """今後N日のタスク"""
    from datetime import timedelta
    today = datetime.now(timezone.utc).date()
    end = (today + timedelta(days=days)).isoformat()
    params: dict = {"today": today.isoformat(), "end": end}
    pf = ""
    if project_name:
        pf = "AND project_name = :pn"
        params["pn"] = project_name

    rows = db.execute(text(f"""
        SELECT * FROM issues WHERE is_task = 1 AND status != '解決済み'
        AND deadline > :today AND deadline <= :end AND parent_id IS NULL {pf}
        ORDER BY deadline ASC, CASE priority WHEN 'critical' THEN 0 WHEN 'normal' THEN 1 WHEN 'minor' THEN 2 ELSE 3 END
    """), params).fetchall()

    return {"tasks": [_issue_row_to_dict(r) for r in rows]}


@router.get("/api/tasks/inbox")
def tasks_inbox(db=Depends(get_db)):
    """プロジェクト未割当のタスク"""
    rows = db.execute(text("""
        SELECT * FROM issues WHERE is_task = 1 AND status != '解決済み'
        AND (project_name IS NULL OR project_name = '') AND parent_id IS NULL
        ORDER BY created_at DESC
    """)).fetchall()
    return {"tasks": [_issue_row_to_dict(r) for r in rows]}


@router.patch("/api/tasks/{task_id}/done")
def task_done(task_id: str, db=Depends(get_db)):
    """タスク完了"""
    now = _now_iso()
    db.execute(text(
        "UPDATE issues SET status = '解決済み', completed_at = :now, updated_at = :now WHERE id = :id AND is_task = 1"
    ), {"id": task_id, "now": now})
    db.commit()
    return {"ok": True}


@router.patch("/api/tasks/{task_id}/snooze")
def task_snooze(task_id: str, days: int = 1, db=Depends(get_db)):
    """タスク延期"""
    from datetime import timedelta
    new_date = (datetime.now(timezone.utc).date() + timedelta(days=days)).isoformat()
    db.execute(text(
        "UPDATE issues SET deadline = :d, updated_at = :now WHERE id = :id AND is_task = 1"
    ), {"id": task_id, "d": new_date, "now": _now_iso()})
    db.commit()
    return {"ok": True, "new_deadline": new_date}


@router.get("/api/tasks/done")
def tasks_done(days: int = 7, project_name: Optional[str] = None, db=Depends(get_db)):
    """完了タスク一覧"""
    from datetime import timedelta
    since = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()
    params: dict = {"since": since}
    pf = ""
    if project_name:
        pf = "AND project_name = :pn"
        params["pn"] = project_name

    rows = db.execute(text(f"""
        SELECT * FROM issues WHERE is_task = 1 AND status = '解決済み'
        AND completed_at >= :since AND parent_id IS NULL {pf}
        ORDER BY completed_at DESC
    """), params).fetchall()

    return {"tasks": [_issue_row_to_dict(r) for r in rows]}


@router.patch("/api/tasks/{task_id}/reopen")
def task_reopen(task_id: str, db=Depends(get_db)):
    """完了タスクを元に戻す"""
    db.execute(text(
        "UPDATE issues SET status = '発生中', completed_at = NULL, updated_at = :now WHERE id = :id AND is_task = 1"
    ), {"id": task_id, "now": _now_iso()})
    db.commit()
    return {"ok": True}


# ===== サブタスク =====

@router.get("/api/tasks/{task_id}/subtasks")
def get_subtasks(task_id: str, db=Depends(get_db)):
    """親タスクのサブタスク一覧"""
    rows = db.execute(text("""
        SELECT * FROM issues WHERE parent_id = :pid AND is_task = 1
        ORDER BY CASE priority WHEN 'critical' THEN 0 WHEN 'normal' THEN 1 WHEN 'minor' THEN 2 ELSE 3 END,
                 created_at ASC
    """), {"pid": task_id}).fetchall()
    return {"subtasks": [_issue_row_to_dict(r) for r in rows]}


class SubtaskCreateRequest(BaseModel):
    text: str


@router.post("/api/tasks/{task_id}/subtasks")
def create_subtask(task_id: str, req: SubtaskCreateRequest, db=Depends(get_db)):
    """サブタスク作成（親タスクのproject_nameを継承）"""
    # 親タスク存在確認 + 孫タスク防止
    parent = db.execute(
        text("SELECT * FROM issues WHERE id = :id AND is_task = 1"), {"id": task_id}
    ).fetchone()
    if not parent:
        raise HTTPException(status_code=404, detail="Parent task not found")
    parent_dict = _issue_row_to_dict(parent)
    if parent_dict.get("parent_id"):
        raise HTTPException(status_code=400, detail="Nested subtasks not allowed")

    parsed = _parse_quick_add(req.text)
    now = _now_iso()
    sub_id = str(uuid.uuid4())

    db.execute(text("""
        INSERT INTO issues (
            id, project_name, title, raw_input, category, priority, status,
            is_task, deadline, due_time, parent_id,
            is_collapsed, pos_x, pos_y, created_at, updated_at
        ) VALUES (
            :id, :project_name, :title, :raw_input, '工程', :priority, '発生中',
            1, :deadline, :due_time, :parent_id,
            0, 0.0, 0.0, :now, :now
        )
    """), {
        "id": sub_id,
        "project_name": parent_dict.get("project_name", ""),
        "title": parsed["title"][:60],
        "raw_input": req.text,
        "priority": parsed.get("priority", "normal"),
        "deadline": parsed.get("deadline"),
        "due_time": parsed.get("due_time"),
        "parent_id": task_id,
        "now": now,
    })
    db.commit()

    row = db.execute(text("SELECT * FROM issues WHERE id = :id"), {"id": sub_id}).fetchone()
    return {"subtask": _issue_row_to_dict(row), "parsed": parsed}


@router.get("/api/tasks/{task_id}/subtask-counts")
def subtask_counts(task_id: str, db=Depends(get_db)):
    """サブタスクの総数と完了数"""
    row = db.execute(text("""
        SELECT
            COUNT(*) as total,
            SUM(CASE WHEN status = '解決済み' THEN 1 ELSE 0 END) as done
        FROM issues WHERE parent_id = :pid AND is_task = 1
    """), {"pid": task_id}).fetchone()
    return {"subtask_count": row[0], "subtask_done_count": row[1]}


@router.post("/api/tasks/subtask-counts-batch")
def subtask_counts_batch(body: dict, db=Depends(get_db)):
    """複数タスクのサブタスクカウントを一括取得"""
    task_ids = body.get("task_ids", [])
    if not task_ids:
        return {"counts": {}}
    placeholders = ",".join(f"'{tid}'" for tid in task_ids if isinstance(tid, str) and len(tid) < 40)
    if not placeholders:
        return {"counts": {}}
    rows = db.execute(text(f"""
        SELECT parent_id,
            COUNT(*) as total,
            SUM(CASE WHEN status = '解決済み' THEN 1 ELSE 0 END) as done
        FROM issues WHERE parent_id IN ({placeholders}) AND is_task = 1
        GROUP BY parent_id
    """)).fetchall()
    counts = {r[0]: {"total": r[1], "done": r[2]} for r in rows}
    return {"counts": counts}
