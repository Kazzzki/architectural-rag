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
import uuid
from datetime import datetime, timezone
from typing import Literal, Optional

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
    "assignee", "context_memo",
}


# ---------- Pydantic モデル ----------

class CaptureRequest(BaseModel):
    raw_input: str
    project_name: str
    skip_ai: bool = False


class MemoChatMessage(BaseModel):
    role: str   # "user" | "assistant"
    content: str


class MemoChatRequest(BaseModel):
    query: str
    messages: list[MemoChatMessage] = []
    project_name: Optional[str] = None


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
    status: Optional[Literal['発生中', '対応中', '解決済み']] = None
    priority: Optional[Literal['critical', 'normal', 'minor']] = None
    action_next: Optional[str] = None
    is_collapsed: Optional[int] = None
    pos_x: Optional[float] = None
    pos_y: Optional[float] = None
    project_name: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
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
        text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    if not row:
        logger.warning(f"[IssueMemo] issue_id={issue_id} not found, skipping markdown save")
        return

    issue = _issue_row_to_dict(row)
    edge_rows = db.execute(
        text(f"SELECT * FROM issue_edges WHERE from_id = :id OR to_id = :id"),
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


ISSUE_SELECT_COLS = (
    "id, project_name, title, raw_input, category, priority, status, "
    "description, cause, impact, action_next, is_collapsed, pos_x, pos_y, "
    "template_id, created_at, updated_at, assignee, context_memo"
)
ISSUE_KEYS = [c.strip() for c in ISSUE_SELECT_COLS.split(",")]

EDGE_BASE_KEYS = ["id", "from_id", "to_id", "confirmed", "created_at"]
EDGE_EXT_KEYS = ["id", "from_id", "to_id", "confirmed", "created_at", "label", "relation_type"]


def _issue_row_to_dict(row) -> dict:
    """明示的カラム名ベースの変換。SELECT * ではなく ISSUE_SELECT_COLS を使うこと。"""
    return dict(zip(ISSUE_KEYS[:len(row)], row))


def _edge_row_to_dict(row) -> dict:
    """エッジ行を辞書に変換。カラム数で旧スキーマ(5列)/新スキーマ(7列)を自動判別。"""
    keys = EDGE_EXT_KEYS if len(row) >= 7 else EDGE_BASE_KEYS
    d = dict(zip(keys[:len(row)], row))
    # 旧スキーマの場合、新フィールドにデフォルト値を設定
    d.setdefault("label", None)
    d.setdefault("relation_type", "direct_cause")
    return d


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
        model="gemini-3.1-flash-lite",
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
        text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}
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
        model="gemini-3.1-flash-lite",
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


@router.post("/api/issues/memo-chat")
def memo_chat(req: MemoChatRequest):
    """課題メモをコンテキストにGeminiで自然言語チャット応答を生成する。"""
    from gemini_client import get_client
    from google.genai import types
    from config import GEMINI_MODEL_RAG

    if not req.query.strip():
        raise HTTPException(status_code=400, detail="query が空です")

    # 関連メモを検索（スコア0.3以上のみ採用）
    try:
        indexer = IssueMemoIndexer()
        raw_results = indexer.search(req.query, project_name=req.project_name, top_k=6)
        sources = [r for r in raw_results if r["score"] >= 0.3]
    except Exception as e:
        logger.error(f"[MemoChatSearch] search failed: {e}", exc_info=True)
        sources = []

    # コンテキスト文字列を構築
    if sources:
        context_lines = []
        for i, s in enumerate(sources, 1):
            context_lines.append(
                f"[メモ{i}] タイトル: {s['title']} / カテゴリ: {s['category']} "
                f"/ 優先度: {s['priority']} / ステータス: {s['status']}\n{s['snippet']}"
            )
        context_str = "\n\n".join(context_lines)
    else:
        context_str = "（関連するメモが見つかりませんでした）"

    # 会話履歴を整形（直近6ターンまで）
    history_lines = []
    for msg in req.messages[-6:]:
        role_label = "ユーザー" if msg.role == "user" else "アシスタント"
        history_lines.append(f"{role_label}: {msg.content}")
    history_str = "\n".join(history_lines) if history_lines else ""

    prompt = f"""あなたは建設PM/CMの課題管理アシスタントです。
以下の関連課題メモをもとに、ユーザーの質問に日本語で答えてください。
メモに情報がない場合はその旨を正直に伝えてください。

【関連課題メモ】
{context_str}

{"【これまでの会話】" + chr(10) + history_str + chr(10) if history_str else ""}【ユーザーの質問】
{req.query}"""

    try:
        client = get_client()
        config = types.GenerateContentConfig(
            system_instruction="建設PM/CMの課題管理アシスタント。関連メモを参照しながら、簡潔かつ具体的に日本語で答えよ。",
            temperature=0.3,
        )
        response = client.models.generate_content(
            model=GEMINI_MODEL_RAG,
            contents=prompt,
            config=config,
        )
        answer = response.text.strip()
    except Exception as e:
        logger.error(f"[MemoChatLLM] generate failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"LLM応答エラー: {str(e)}")

    return {"answer": answer, "sources": sources}


@router.get("/api/issues/projects")
def list_projects(db=Depends(get_db)):
    """登録済みプロジェクト名のユニーク一覧"""
    rows = db.execute(
        text("SELECT DISTINCT project_name FROM issues ORDER BY project_name")
    ).fetchall()
    return {"projects": [r[0] for r in rows]}


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
                "title": req.raw_input[:20],
                "raw_input": req.raw_input,
                "created_at": now,
                "updated_at": now,
            })
            db.commit()
            row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
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
            model="gemini-3.1-flash-lite",
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
        row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
        return {"issue": _issue_row_to_dict(row), "edges_created": edges_created}

    except Exception as e:
        logger.error(f"Triage apply failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"処理エラー: {str(e)}")


@router.post("/api/issues/edges/confirm")
def confirm_edge(req: EdgeConfirmRequest, db=Depends(get_db)):
    """因果関係を確認し confirmed=true の場合のみエッジを保存"""
    if not req.confirmed:
        return {"ok": True, "saved": False}

    # self-loop 防止
    if req.from_id == req.to_id:
        raise HTTPException(status_code=400, detail="自己参照エッジは作成できません")

    # 重複エッジ防止
    existing = db.execute(
        text("SELECT id FROM issue_edges WHERE from_id = :from_id AND to_id = :to_id"),
        {"from_id": req.from_id, "to_id": req.to_id},
    ).fetchone()
    if existing:
        return {"ok": True, "saved": False, "edge_id": existing[0], "duplicate": True}

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
    """課題一覧 + 関連エッジ一覧 + プロジェクト名一覧を返す"""
    where_clauses = []
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
        text(f"SELECT {ISSUE_SELECT_COLS} FROM issues {where_sql} ORDER BY created_at ASC"), params
    ).fetchall()
    issues = [_issue_row_to_dict(r) for r in issue_rows]

    # フィルター対象 issue の id セット内のエッジのみ返す（プロジェクト絞り込み済み）
    issue_ids = {iss["id"] for iss in issues}
    if issue_ids:
        edge_rows = db.execute(
            text(f"SELECT * FROM issue_edges WHERE from_id IN (SELECT id FROM issues WHERE project_name = :pn) OR to_id IN (SELECT id FROM issues WHERE project_name = :pn)"),
            {"pn": project_name or ""},
        ).fetchall() if project_name else db.execute(text(f"SELECT * FROM issue_edges")).fetchall()
        edges = [
            _edge_row_to_dict(r)
            for r in edge_rows
            if r[1] in issue_ids and r[2] in issue_ids
        ]
    else:
        edges = []

    proj_rows = db.execute(
        text("SELECT DISTINCT project_name FROM issues ORDER BY project_name")
    ).fetchall()
    projects = [r[0] for r in proj_rows]

    return {"issues": issues, "edges": edges, "projects": projects}


@router.get("/api/issues/{issue_id}/analysis")
def get_issue_analysis(issue_id: str, db=Depends(get_db)):
    """課題のAI分析ステータスと因果候補を返す。
    キャプチャは同期処理のため、課題が存在すれば常に done を返す。"""
    row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    if row is None:
        return {"ai_status": "pending", "issue": None, "causal_candidates": []}
    issue = _issue_row_to_dict(row)
    # 確定済みエッジから因果候補を構築（この課題が to_id のもの = 原因側候補）
    edge_rows = db.execute(
        text(f"SELECT * FROM issue_edges WHERE to_id = :id AND confirmed = 1"),
        {"id": issue_id},
    ).fetchall()
    causal_candidates = []
    for edge in edge_rows:
        cause_row = db.execute(
            text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": edge[1]}
        ).fetchone()
        if cause_row:
            causal_candidates.append({
                "issue_id": edge[1],
                "direction": "cause_of_new",
                "confidence": 1.0,
                "reason": "確定済みエッジ",
            })
    return {"ai_status": "done", "issue": issue, "causal_candidates": causal_candidates}


@router.get("/api/issues/{issue_id}")
def get_issue(issue_id: str, db=Depends(get_db)):
    """課題を1件取得"""
    row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    return _issue_row_to_dict(row)


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
        text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="課題が見つかりません")

    # Markdown更新 + インデックス更新
    try:
        _save_issue_markdown(issue_id, db)
    except Exception as e:
        logger.error(f"[IssueMemo] Failed to update markdown for {issue_id}: {e}")

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
    # タイムラインメモもカスケード削除
    db.execute(text("DELETE FROM issue_notes WHERE issue_id = :id"), {"id": issue_id})
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


# ---------- 新規エンドポイント (Phase 1) ----------

# --- バッチ更新 ---

class BatchUpdateRequest(BaseModel):
    issue_ids: list[str]
    updates: dict  # {status?, priority?, assignee?}


@router.patch("/api/issues/batch")
def batch_update(req: BatchUpdateRequest, db=Depends(get_db)):
    """複数課題を一括更新（トランザクション: 全成功 or 全失敗）"""
    if len(req.issue_ids) > 100:
        raise HTTPException(status_code=400, detail="一括更新は100件以内にしてください")
    if not req.issue_ids or not req.updates:
        raise HTTPException(status_code=400, detail="issue_ids と updates は必須です")

    allowed = {"status", "priority", "assignee"}
    valid_status = {'発生中', '対応中', '解決済み'}
    valid_priority = {'critical', 'normal', 'minor'}
    updates = {k: v for k, v in req.updates.items() if k in allowed and v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="有効な更新フィールドがありません")
    if "status" in updates and updates["status"] not in valid_status:
        raise HTTPException(status_code=400, detail=f"不正なstatus: {updates['status']}")
    if "priority" in updates and updates["priority"] not in valid_priority:
        raise HTTPException(status_code=400, detail=f"不正なpriority: {updates['priority']}")

    # 全IDが同一プロジェクトに属するか確認
    placeholders = ",".join(f":id{i}" for i in range(len(req.issue_ids)))
    rows = db.execute(
        text(f"SELECT DISTINCT project_name FROM issues WHERE id IN ({placeholders})"),
        {f"id{i}": uid for i, uid in enumerate(req.issue_ids)},
    ).fetchall()
    if len(rows) > 1:
        raise HTTPException(status_code=400, detail="異なるプロジェクトの課題を一括更新できません")

    set_clauses = ", ".join([f"{k} = :{k}" for k in updates])
    now = _now_iso()
    try:
        for uid in req.issue_ids:
            params = {**updates, "_id": uid, "_updated_at": now}
            db.execute(
                text(f"UPDATE issues SET {set_clauses}, updated_at = :_updated_at WHERE id = :_id"),
                params,
            )
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"一括更新に失敗: {str(e)}")

    updated = []
    for uid in req.issue_ids:
        row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": uid}).fetchone()
        if row:
            updated.append(_issue_row_to_dict(row))
    return {"updated": updated}


# --- エッジ更新 ---

class EdgeUpdateRequest(BaseModel):
    label: Optional[str] = None
    relation_type: Optional[Literal['direct_cause', 'indirect_cause', 'correlation', 'countermeasure']] = None


@router.patch("/api/issues/edges/{edge_id}")
def update_edge(edge_id: str, req: EdgeUpdateRequest, db=Depends(get_db)):
    """エッジのラベル・関係種別を更新"""
    updates = {}
    if req.label is not None:
        updates["label"] = req.label
    if req.relation_type is not None:
        updates["relation_type"] = req.relation_type
    if not updates:
        raise HTTPException(status_code=400, detail="更新フィールドがありません")

    set_clauses = ", ".join([f"{k} = :{k}" for k in updates])
    updates["_id"] = edge_id
    result = db.execute(text(f"UPDATE issue_edges SET {set_clauses} WHERE id = :_id"), updates)
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Edge not found")
    return {"ok": True}


# --- タイムラインメモ CRUD ---

class NoteCreateRequest(BaseModel):
    content: str
    author: Optional[str] = None


class NoteUpdateRequest(BaseModel):
    content: str


NOTE_SELECT_COLS = "id, issue_id, author, content, photo_path, created_at"
NOTE_KEYS = [c.strip() for c in NOTE_SELECT_COLS.split(",")]


def _note_row_to_dict(row) -> dict:
    return dict(zip(NOTE_KEYS[:len(row)], row))


@router.get("/api/issues/{issue_id}/notes")
def list_notes(issue_id: str, db=Depends(get_db)):
    """課題のタイムラインメモ一覧"""
    rows = db.execute(
        text(f"SELECT {NOTE_SELECT_COLS} FROM issue_notes WHERE issue_id = :id ORDER BY created_at ASC"),
        {"id": issue_id},
    ).fetchall()
    return {"notes": [_note_row_to_dict(r) for r in rows]}


@router.post("/api/issues/{issue_id}/notes")
def create_note(issue_id: str, req: NoteCreateRequest, db=Depends(get_db)):
    """タイムラインメモを作成"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content は必須です")
    note_id = str(uuid.uuid4())
    now = _now_iso()
    db.execute(
        text("INSERT INTO issue_notes (id, issue_id, author, content, created_at) VALUES (:id, :issue_id, :author, :content, :created_at)"),
        {"id": note_id, "issue_id": issue_id, "author": req.author, "content": req.content.strip(), "created_at": now},
    )
    db.commit()
    row = db.execute(text(f"SELECT {NOTE_SELECT_COLS} FROM issue_notes WHERE id = :id"), {"id": note_id}).fetchone()
    return _note_row_to_dict(row)


@router.patch("/api/issues/notes/{note_id}")
def update_note(note_id: str, req: NoteUpdateRequest, db=Depends(get_db)):
    """タイムラインメモを編集"""
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content は必須です")
    result = db.execute(
        text("UPDATE issue_notes SET content = :content WHERE id = :id"),
        {"id": note_id, "content": req.content.strip()},
    )
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    row = db.execute(text(f"SELECT {NOTE_SELECT_COLS} FROM issue_notes WHERE id = :id"), {"id": note_id}).fetchone()
    return _note_row_to_dict(row)


@router.delete("/api/issues/notes/{note_id}")
def delete_note(note_id: str, db=Depends(get_db)):
    """タイムラインメモを削除"""
    result = db.execute(text("DELETE FROM issue_notes WHERE id = :id"), {"id": note_id})
    db.commit()
    if result.rowcount == 0:
        raise HTTPException(status_code=404, detail="Note not found")
    return {"ok": True}


# --- 関連メモ検索 ---

@router.get("/api/issues/{issue_id}/related-memos")
def related_memos(issue_id: str, top_k: int = 5, db=Depends(get_db)):
    """ChromaDB類似検索で関連メモを返す"""
    row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue = _issue_row_to_dict(row)
    query = f"{issue['title']} {issue.get('description') or ''} {issue.get('context_memo') or ''}"
    try:
        indexer = IssueMemoIndexer()
        results = indexer.search(query, project_name=issue["project_name"], top_k=top_k)
        results = [r for r in results if r.get("issue_id") != issue_id]
        return {"results": results}
    except Exception as e:
        logger.error(f"[RelatedMemos] search failed: {e}", exc_info=True)
        return {"results": []}


# --- AI深掘り調査 ---

class AIInvestigateRequest(BaseModel):
    type: Literal['rca', 'impact', 'countermeasure']


def _traverse_causal_chain(issue_id: str, db, max_depth: int = 3, max_nodes: int = 100) -> list[dict]:
    """BFSで因果チェーンを走査し、関連課題を返す（fan-out制限付き）"""
    visited = set()
    queue = [(issue_id, 0)]
    result = []
    while queue and len(result) < max_nodes:
        current_id, depth = queue.pop(0)
        if current_id in visited or depth > max_depth:
            continue
        visited.add(current_id)
        row = db.execute(
            text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": current_id}
        ).fetchone()
        if row:
            result.append(_issue_row_to_dict(row))
        if depth < max_depth:
            edges = db.execute(
                text("SELECT from_id, to_id FROM issue_edges WHERE from_id = :id OR to_id = :id"),
                {"id": current_id},
            ).fetchall()
            for e in edges:
                neighbor = e[1] if e[0] == current_id else e[0]
                if neighbor not in visited:
                    queue.append((neighbor, depth + 1))
    return result


@router.post("/api/issues/{issue_id}/ai-investigate")
def ai_investigate(issue_id: str, req: AIInvestigateRequest, db=Depends(get_db)):
    """ノード単位のAI深掘り調査（RCA/影響分析/対策提案）"""
    import concurrent.futures
    from gemini_client import get_client
    from google.genai import types

    row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Issue not found")
    target = _issue_row_to_dict(row)

    chain = _traverse_causal_chain(issue_id, db)
    chain_str = "\n".join(
        f"- {iss['title']}（{iss['category']}/{iss['priority']}/{iss['status']}）: {(iss.get('description') or '')[:80]}"
        for iss in chain
    )

    prompts = {
        "rca": f"以下の課題の根本原因を「なぜなぜ分析」で特定してください。\n\n対象課題: {target['title']}\n説明: {target.get('description') or '未入力'}\n推定原因: {target.get('cause') or '未入力'}\n\n因果チェーン上の関連課題:\n{chain_str}\n\n5つの「なぜ」を使い、根本原因を特定し、具体的な対策を提案してください。日本語で200字以内。",
        "impact": f"以下の課題が解決されない場合の波及影響を分析してください。\n\n対象課題: {target['title']}\n説明: {target.get('description') or '未入力'}\n影響: {target.get('impact') or '未入力'}\n\n因果チェーン上の関連課題:\n{chain_str}\n\n下流への波及影響を具体的に列挙してください。日本語で200字以内。",
        "countermeasure": f"以下の課題に対する具体的な対策を提案してください。\n\n対象課題: {target['title']}\n説明: {target.get('description') or '未入力'}\n原因: {target.get('cause') or '未入力'}\n\n因果チェーン上の関連課題:\n{chain_str}\n\n即効性のある対策と根本対策をそれぞれ提案してください。日本語で200字以内。",
    }

    try:
        client = get_client()
        config = types.GenerateContentConfig(
            system_instruction="建設PM/CMの課題分析アシスタント。簡潔かつ具体的に日本語で回答せよ。",
            temperature=0.3,
        )

        def call_gemini():
            return client.models.generate_content(
                model="gemini-3.1-flash-lite", contents=prompts[req.type], config=config,
            )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(call_gemini)
            response = future.result(timeout=30)

        return {
            "type": req.type,
            "result": response.text.strip(),
            "related_issue_ids": [iss["id"] for iss in chain if iss["id"] != issue_id],
        }
    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="AI分析がタイムアウトしました（30秒）。後でお試しください。")
    except Exception as e:
        logger.error(f"[AIInvestigate] failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI分析エラー: {str(e)}")


# --- AI因果推定 ---

class AIInferCausationRequest(BaseModel):
    issue_ids: list[str]


@router.post("/api/issues/ai-infer-causation")
def ai_infer_causation(req: AIInferCausationRequest, db=Depends(get_db)):
    """選択したノード間の隠れた因果関係をAIで推定"""
    import concurrent.futures
    from gemini_client import get_client
    from google.genai import types

    if len(req.issue_ids) < 2 or len(req.issue_ids) > 8:
        raise HTTPException(status_code=400, detail="2〜8件の課題IDを指定してください")

    issues = []
    for uid in req.issue_ids:
        row = db.execute(text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE id = :id"), {"id": uid}).fetchone()
        if row:
            issues.append(_issue_row_to_dict(row))

    if len(issues) < 2:
        raise HTTPException(status_code=400, detail="有効な課題が2件未満です")

    existing_edges = []
    for i, a in enumerate(issues):
        for b in issues[i+1:]:
            edge = db.execute(
                text("SELECT id FROM issue_edges WHERE (from_id = :a AND to_id = :b) OR (from_id = :b AND to_id = :a)"),
                {"a": a["id"], "b": b["id"]},
            ).fetchone()
            if edge:
                existing_edges.append(f"{a['title']} ↔ {b['title']}")

    issues_str = "\n".join(
        f"- ID:{iss['id'][:8]} タイトル:{iss['title']} カテゴリ:{iss['category']} 説明:{(iss.get('description') or '')[:60]}"
        for iss in issues
    )
    existing_str = "\n".join(existing_edges) if existing_edges else "（なし）"

    prompt = f"""以下の建設課題間に隠れた因果関係はありますか？

課題一覧:
{issues_str}

既存の因果関係:
{existing_str}

以下のJSON配列のみ返答してください（最大5件）。因果関係がなければ空配列[]。
[{{"from_id":"ID先頭8文字","to_id":"ID先頭8文字","confidence":0.8,"reason":"20字以内","suggested_label":"理由ラベル"}}]
"""

    try:
        client = get_client()
        config = types.GenerateContentConfig(
            system_instruction="建設PM/CMの因果分析アシスタント。指定のJSON形式のみで返答せよ。",
            temperature=0.2,
        )

        def call_gemini():
            return client.models.generate_content(
                model="gemini-3.1-flash-lite", contents=prompt, config=config,
            )

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(call_gemini)
            response = future.result(timeout=30)

        import re as _re
        raw = response.text.strip()
        raw = _re.sub(r'^```(?:json)?\s*', '', raw)
        raw = _re.sub(r'\s*```$', '', raw).strip()
        start = raw.find('[')
        end = raw.rfind(']')
        if start != -1 and end != -1:
            raw = raw[start:end + 1]

        inferred = json.loads(raw) if raw.startswith('[') else []
        id_map = {iss["id"][:8]: iss["id"] for iss in issues}
        resolved = []
        for edge in inferred[:5]:
            from_full = id_map.get(edge.get("from_id", ""))
            to_full = id_map.get(edge.get("to_id", ""))
            if from_full and to_full and from_full != to_full:
                resolved.append({
                    "from_id": from_full, "to_id": to_full,
                    "confidence": edge.get("confidence", 0.5),
                    "reason": edge.get("reason", ""),
                    "suggested_label": edge.get("suggested_label", ""),
                })
        return {"inferred_edges": resolved}
    except concurrent.futures.TimeoutError:
        raise HTTPException(status_code=504, detail="AI分析がタイムアウトしました")
    except Exception as e:
        logger.error(f"[AIInferCausation] failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"AI推定エラー: {str(e)}")


# --- グラフ健全性チェック ---

@router.post("/api/issues/{project_name}/health-check")
def health_check(project_name: str, db=Depends(get_db)):
    """グラフの健全性チェック: 孤立ノード、ループ、未解決critical"""
    import concurrent.futures
    from gemini_client import get_client
    from google.genai import types

    issue_rows = db.execute(
        text(f"SELECT {ISSUE_SELECT_COLS} FROM issues WHERE project_name = :pn ORDER BY created_at ASC"),
        {"pn": project_name},
    ).fetchall()
    issues = [_issue_row_to_dict(r) for r in issue_rows]
    issue_ids = {iss["id"] for iss in issues}

    edge_rows = db.execute(text(f"SELECT * FROM issue_edges")).fetchall()
    edges = [_edge_row_to_dict(r) for r in edge_rows if r[1] in issue_ids and r[2] in issue_ids]

    # 1. 孤立ノード
    connected_ids = set()
    for e in edges:
        connected_ids.add(e["from_id"])
        connected_ids.add(e["to_id"])
    orphans = [iss for iss in issues if iss["id"] not in connected_ids]

    # 2. ループ検出（DFS）
    adjacency: dict[str, list[str]] = {iss["id"]: [] for iss in issues}
    for e in edges:
        adjacency.setdefault(e["from_id"], []).append(e["to_id"])

    loops: list[list[str]] = []
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in adjacency}
    path: list[str] = []
    id_to_title = {iss["id"]: iss["title"] for iss in issues}

    def _dfs(node):
        color[node] = GRAY
        path.append(node)
        for neighbor in adjacency.get(node, []):
            if color.get(neighbor) == GRAY:
                cycle_start = path.index(neighbor)
                loops.append([id_to_title.get(n, n) for n in path[cycle_start:]])
            elif color.get(neighbor) == WHITE:
                _dfs(neighbor)
        path.pop()
        color[node] = BLACK

    for node in adjacency:
        if color[node] == WHITE:
            _dfs(node)

    # 3. 未解決critical
    unresolved = [iss for iss in issues if iss["priority"] == "critical" and iss["status"] != "解決済み"]

    # 4. AIサジェスト（上位50ノードのみ）
    ai_suggestions = []
    if len(issues) >= 3:
        top_issues = issues[:50]
        issues_str = "\n".join(f"- {iss['title']}（{iss['category']}/{iss['status']}）" for iss in top_issues)
        edges_str = "\n".join(
            f"- {id_to_title.get(e['from_id'], '?')} → {id_to_title.get(e['to_id'], '?')}" for e in edges[:30]
        ) or "（なし）"
        prompt = f"以下の建設プロジェクトの課題グラフで見落とされている因果関係を最大5件、JSON配列で返してください。\n\n課題:\n{issues_str}\n\n既存因果:\n{edges_str}\n\n[{{\"from_title\":\"A\",\"to_title\":\"B\",\"reason\":\"理由\"}}] なければ[]"
        try:
            client = get_client()
            config = types.GenerateContentConfig(
                system_instruction="建設PM/CMの因果分析アシスタント。JSON形式のみで返答。", temperature=0.2,
            )
            def call_gemini():
                return client.models.generate_content(model="gemini-3.1-flash-lite", contents=prompt, config=config)
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(call_gemini)
                response = future.result(timeout=30)
            import re as _re
            raw = response.text.strip()
            raw = _re.sub(r'^```(?:json)?\s*', '', raw)
            raw = _re.sub(r'\s*```$', '', raw).strip()
            s, e2 = raw.find('['), raw.rfind(']')
            if s != -1 and e2 != -1:
                raw = raw[s:e2+1]
            ai_suggestions = (json.loads(raw) if raw.startswith('[') else [])[:5]
        except Exception as e:
            logger.error(f"[HealthCheck] AI suggestions failed: {e}")

    return {
        "orphans": orphans, "loops": loops, "unresolved_criticals": unresolved,
        "ai_suggestions": ai_suggestions,
        "summary": {
            "total_issues": len(issues), "total_edges": len(edges),
            "orphan_count": len(orphans), "loop_count": len(loops),
            "critical_unresolved_count": len(unresolved),
        },
    }


# ===== Phase 1: 添付ファイル =====

ALLOWED_ATTACHMENT_MIME = {
    "image/png", "image/jpeg", "image/jpg", "image/webp",
    "application/pdf",
}


@router.get("/api/issues/{issue_id}/attachments")
def list_attachments(issue_id: str, db=Depends(get_db)):
    rows = db.execute(text(
        "SELECT id, issue_id, attachment_type, file_path, thumbnail_path, caption, created_at "
        "FROM issue_attachments WHERE issue_id = :id ORDER BY created_at DESC"
    ), {"id": issue_id}).fetchall()
    return {"attachments": [
        {"id": r[0], "issue_id": r[1], "attachment_type": r[2], "file_path": r[3],
         "thumbnail_path": r[4], "caption": r[5], "created_at": r[6]}
        for r in rows
    ]}


@router.post("/api/issues/{issue_id}/attachments", status_code=201)
async def create_attachment(
    issue_id: str, file: UploadFile = File(...),
    attachment_type: str = Form("photo"), caption: str = Form(""),
    db=Depends(get_db),
):
    mime = file.content_type or ""
    if mime not in ALLOWED_ATTACHMENT_MIME:
        raise HTTPException(status_code=400, detail=f"対応形式: PNG/JPEG/WebP/PDF。受信: {mime}")
    file_bytes = await file.read()
    if len(file_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ファイルサイズは20MB以内")
    att_id = str(uuid.uuid4())
    now = _now_iso()
    issue_dir = ISSUE_ATTACHMENTS_DIR / issue_id
    issue_dir.mkdir(parents=True, exist_ok=True)
    ext = file.filename.rsplit(".", 1)[-1] if file.filename and "." in file.filename else "bin"
    file_path = issue_dir / f"{att_id}.{ext}"
    file_path.write_bytes(file_bytes)
    thumbnail_path_str = None
    if mime.startswith("image/"):
        try:
            from PIL import Image
            import io
            img = Image.open(io.BytesIO(file_bytes))
            img.thumbnail((200, 200))
            thumb_path = issue_dir / f"{att_id}_thumb.jpg"
            img.convert("RGB").save(thumb_path, "JPEG", quality=80)
            thumbnail_path_str = str(thumb_path.relative_to(ISSUE_ATTACHMENTS_DIR))
        except Exception as e:
            logger.warning(f"Thumbnail generation failed: {e}")
    relative_path = str(file_path.relative_to(ISSUE_ATTACHMENTS_DIR))
    db.execute(text(
        "INSERT INTO issue_attachments (id, issue_id, attachment_type, file_path, thumbnail_path, caption, created_at) "
        "VALUES (:id, :issue_id, :type, :path, :thumb, :caption, :now)"
    ), {"id": att_id, "issue_id": issue_id, "type": attachment_type,
        "path": relative_path, "thumb": thumbnail_path_str, "caption": caption or None, "now": now})
    db.commit()
    return {"id": att_id, "issue_id": issue_id, "attachment_type": attachment_type,
            "file_path": relative_path, "thumbnail_path": thumbnail_path_str,
            "caption": caption or None, "created_at": now}


@router.delete("/api/issues/attachments/{attachment_id}")
def delete_attachment(attachment_id: str, db=Depends(get_db)):
    row = db.execute(text("SELECT file_path, thumbnail_path FROM issue_attachments WHERE id = :id"),
                     {"id": attachment_id}).fetchone()
    if row:
        from pathlib import Path
        for rel_path in [row[0], row[1]]:
            if rel_path:
                full = ISSUE_ATTACHMENTS_DIR / rel_path
                if full.exists(): full.unlink()
    db.execute(text("DELETE FROM issue_attachments WHERE id = :id"), {"id": attachment_id})
    db.commit()
    return {"ok": True}


@router.get("/api/issues/attachments/{attachment_id}/file")
def serve_attachment_file(attachment_id: str, db=Depends(get_db)):
    from fastapi.responses import FileResponse
    row = db.execute(text("SELECT file_path FROM issue_attachments WHERE id = :id"),
                     {"id": attachment_id}).fetchone()
    if not row: raise HTTPException(status_code=404)
    full = ISSUE_ATTACHMENTS_DIR / row[0]
    if not full.exists(): raise HTTPException(status_code=404)
    return FileResponse(str(full))


@router.get("/api/issues/attachments/{attachment_id}/thumbnail")
def serve_attachment_thumbnail(attachment_id: str, db=Depends(get_db)):
    from fastapi.responses import FileResponse
    row = db.execute(text("SELECT thumbnail_path FROM issue_attachments WHERE id = :id"),
                     {"id": attachment_id}).fetchone()
    if not row or not row[0]: raise HTTPException(status_code=404)
    full = ISSUE_ATTACHMENTS_DIR / row[0]
    if not full.exists(): raise HTTPException(status_code=404)
    return FileResponse(str(full))


# ===== Phase 2: AI原因サジェスト =====

@router.post("/api/issues/{issue_id}/suggest-causes")
async def suggest_causes(issue_id: str, db=Depends(get_db)):
    import asyncio
    from gemini_client import get_client
    from google.genai import types as genai_types

    row = db.execute(text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}).fetchone()
    if not row: raise HTTPException(status_code=404)
    issue = _issue_row_to_dict(row)

    existing_rows = db.execute(text(
        "SELECT id, title, description, category FROM issues "
        "WHERE project_name = :pn AND id != :id AND (is_task = 0 OR is_task IS NULL) LIMIT 30"
    ), {"pn": issue["project_name"], "id": issue_id}).fetchall()
    existing_context = "\n".join(f"- {r[1]} ({r[3]}): {(r[2] or '')[:60]}" for r in existing_rows) or "（他に課題なし）"

    edge_rows = db.execute(text(
        "SELECT from_id, to_id FROM issue_edges WHERE from_id = :id OR to_id = :id"
    ), {"id": issue_id}).fetchall()
    connected_ids = {r[0] for r in edge_rows} | {r[1] for r in edge_rows}
    connected_ids.discard(issue_id)

    prompt = f"""建設現場の課題について、考えられる原因を分析してください。

対象課題: {issue['title']} ({issue['category']})
説明: {issue.get('description') or '（なし）'}
原因（既知）: {issue.get('cause') or '（未特定）'}

同プロジェクトの他の課題:
{existing_context}

JSON配列のみ返答（3件以内）:
[{{"title":"原因名（15字以内）","description":"説明（30字以内）","confidence":0.85,"reason":"理由（20字以内）"}}]
"""
    try:
        client = get_client()
        config = genai_types.GenerateContentConfig(
            system_instruction="建設現場の課題分析アシスタント。JSON配列のみ返答。", temperature=0.3)

        async def _call():
            return client.models.generate_content(
                model="gemini-2.5-flash", contents=[prompt], config=config).text.strip()

        raw = await asyncio.wait_for(_call(), timeout=10.0)
        cleaned = raw
        if cleaned.startswith("```"): cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"): cleaned = cleaned.rsplit("```", 1)[0]
        suggestions = json.loads(cleaned.strip())
        if not isinstance(suggestions, list): suggestions = []
        suggestions = [s for s in suggestions if s.get("confidence", 0) >= 0.3]
        return {"suggestions": suggestions, "ai_status": "done"}
    except asyncio.TimeoutError:
        return {"suggestions": [], "ai_status": "error", "error": "AI分析がタイムアウトしました"}
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"[SuggestCauses] error: {e}")
        return {"suggestions": [], "ai_status": "error", "error": "AI分析が一時的に利用できません"}


# ===== Phase 3: 構造的ギャップ検出 =====

_graph_analysis_cache: dict = {}

@router.get("/api/issues/graph-analysis")
def analyze_graph_gaps(project_name: str, db=Depends(get_db)):
    import networkx as nx

    latest_row = db.execute(text(
        "SELECT MAX(updated_at) FROM issues WHERE project_name = :pn AND (is_task = 0 OR is_task IS NULL)"
    ), {"pn": project_name}).fetchone()
    latest_ts = latest_row[0] if latest_row and latest_row[0] else ""
    cached = _graph_analysis_cache.get(project_name)
    if cached and cached.get("updated_at") == latest_ts:
        return cached["result"]

    issue_rows = db.execute(text(
        "SELECT id, title, category FROM issues WHERE project_name = :pn AND (is_task = 0 OR is_task IS NULL)"
    ), {"pn": project_name}).fetchall()
    if len(issue_rows) < 2:
        result = {"gaps": [], "stats": {"nodes": len(issue_rows), "edges": 0, "components": len(issue_rows)}}
        _graph_analysis_cache[project_name] = {"result": result, "updated_at": latest_ts}
        return result

    issue_map = {r[0]: {"id": r[0], "title": r[1], "category": r[2]} for r in issue_rows}
    issue_ids = set(issue_map.keys())
    edge_rows = db.execute(text("SELECT from_id, to_id FROM issue_edges WHERE confirmed = 1")).fetchall()
    valid_edges = [(r[0], r[1]) for r in edge_rows if r[0] in issue_ids and r[1] in issue_ids]

    G = nx.DiGraph()
    G.add_nodes_from(issue_ids)
    G.add_edges_from(valid_edges)
    UG = G.to_undirected()
    components = list(nx.connected_components(UG))

    gaps = []
    if len(components) >= 2:
        for i in range(min(len(components), 5)):
            for j in range(i + 1, min(len(components), 5)):
                comp_a, comp_b = list(components[i])[:5], list(components[j])[:5]
                cats_a = {issue_map[n]["category"] for n in comp_a if n in issue_map}
                cats_b = {issue_map[n]["category"] for n in comp_b if n in issue_map}
                shared = cats_a & cats_b
                if shared:
                    ta = [issue_map[n]["title"] for n in comp_a[:3] if n in issue_map]
                    tb = [issue_map[n]["title"] for n in comp_b[:3] if n in issue_map]
                    gaps.append({"cluster_a": comp_a, "cluster_b": comp_b, "shared_categories": list(shared),
                                 "suggestion": f"「{'、'.join(ta[:2])}」と「{'、'.join(tb[:2])}」は{'/'.join(shared)}カテゴリが共通。"})

    key_nodes = []
    if len(G.nodes) >= 3 and len(valid_edges) >= 2:
        try:
            bc = nx.betweenness_centrality(G, k=min(len(G.nodes), 100))
            key_nodes = [{"id": n, "title": issue_map.get(n, {}).get("title", ""), "centrality": round(s, 3)}
                         for n, s in sorted(bc.items(), key=lambda x: x[1], reverse=True)[:5] if s > 0]
        except Exception:
            pass

    result = {"gaps": gaps[:10], "key_nodes": key_nodes,
              "stats": {"nodes": len(G.nodes), "edges": len(valid_edges), "components": len(components)}}
    _graph_analysis_cache[project_name] = {"result": result, "updated_at": latest_ts}
    return result


# ===== Phase 4: パターンライブラリ =====

def _get_pattern_collection():
    from dense_indexer import get_chroma_client
    from config import CHROMA_DB_DIR, ISSUE_PATTERN_COLLECTION
    client = get_chroma_client(CHROMA_DB_DIR)
    return client.get_or_create_collection(name=ISSUE_PATTERN_COLLECTION, metadata={"hnsw:space": "cosine"})


@router.post("/api/issues/patterns/extract")
def extract_patterns(project_name: str = "", db=Depends(get_db)):
    from dense_indexer import _embed_batch_with_retry
    import networkx as nx

    where = "WHERE status = '解決済み' AND (is_task = 0 OR is_task IS NULL)"
    params: dict = {}
    if project_name:
        where += " AND project_name = :pn"
        params["pn"] = project_name

    rows = db.execute(text(f"SELECT id, title, description, category, project_name FROM issues {where}"), params).fetchall()
    resolved_ids = {r[0] for r in rows}
    resolved_map = {r[0]: {"id": r[0], "title": r[1], "description": r[2], "category": r[3], "project_name": r[4]} for r in rows}
    if not resolved_ids:
        return {"extracted": 0}

    edge_rows = db.execute(text("SELECT from_id, to_id FROM issue_edges WHERE confirmed = 1")).fetchall()
    G = nx.DiGraph()
    for r in edge_rows:
        if r[0] in resolved_ids and r[1] in resolved_ids:
            G.add_edge(r[0], r[1])
    chains = [c for c in nx.connected_components(G.to_undirected()) if len(c) >= 3]

    collection = _get_pattern_collection()
    extracted = 0
    for chain in chains:
        chain_list = list(chain)
        pattern_id = f"pattern-{'_'.join(sorted(chain_list)[:5])}"
        titles = [resolved_map[n]["title"] for n in chain_list if n in resolved_map]
        categories = list({resolved_map[n]["category"] for n in chain_list if n in resolved_map})
        pattern_text = f"因果パターン ({'/'.join(categories)}): {' → '.join(titles[:5])}"
        try:
            embeddings = _embed_batch_with_retry([pattern_text])
            if not embeddings or not embeddings[0]: continue
        except Exception:
            continue
        pn = next((resolved_map[n]["project_name"] for n in chain_list if n in resolved_map), "")
        collection.upsert(ids=[pattern_id], embeddings=[embeddings[0]], documents=[pattern_text],
                          metadatas=[{"project_name": pn, "categories": "/".join(categories),
                                      "node_count": str(len(chain_list)), "titles": " → ".join(titles[:5])}])
        extracted += 1
    return {"extracted": extracted, "total_chains": len(chains)}


@router.post("/api/issues/patterns/search")
def search_patterns(query: str = "", db=Depends(get_db)):
    from dense_indexer import _embed_batch_with_retry
    if not query: raise HTTPException(status_code=400, detail="queryが必要")
    try:
        embeddings = _embed_batch_with_retry([query])
        if not embeddings or not embeddings[0]: return {"patterns": []}
    except Exception:
        return {"patterns": []}
    collection = _get_pattern_collection()
    try:
        count = collection.count()
    except Exception:
        count = 0
    if count == 0: return {"patterns": []}
    results = collection.query(query_embeddings=[embeddings[0]], n_results=min(5, count))
    patterns = []
    for i, doc_id in enumerate(results["ids"][0]):
        distance = results["distances"][0][i] if results.get("distances") else 1.0
        similarity = 1.0 - distance
        if similarity < 0.3: continue
        meta = results["metadatas"][0][i] if results.get("metadatas") else {}
        patterns.append({"id": doc_id, "similarity": round(similarity, 3), "titles": meta.get("titles", ""),
                          "categories": meta.get("categories", ""), "node_count": int(meta.get("node_count", 0))})
    return {"patterns": patterns}
