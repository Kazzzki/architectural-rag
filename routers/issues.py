"""
routers/issues.py — 課題因果グラフ API

エンドポイント:
  POST   /api/issues/capture          課題テキストをAI構造化 + 保存
  POST   /api/issues/capture-photo    写真から課題を抽出してAI構造化 + 保存
  POST   /api/issues/edges/confirm    因果エッジを確定
  GET    /api/issues                  課題・エッジ一覧
  GET    /api/issues/projects         プロジェクト名一覧
  PATCH  /api/issues/{issue_id}       部分更新
  DELETE /api/issues/{issue_id}       物理削除
"""
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import text

from database import get_db

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
    assignee: Optional[str] = None
    context_memo: Optional[str] = None


class MemberCreateRequest(BaseModel):
    project_name: str
    name: str
    role: Optional[str] = None


# ---------- ヘルパー ----------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _issue_row_to_dict(row) -> dict:
    keys = [
        "id", "project_name", "title", "raw_input", "category", "priority",
        "status", "description", "cause", "impact", "action_next",
        "is_collapsed", "pos_x", "pos_y", "template_id", "created_at", "updated_at",
        "assignee", "context_memo",
    ]
    # rowの長さに合わせてキーを切り取る（古いDBとの互換性）
    return dict(zip(keys[:len(row)], row))


def _edge_row_to_dict(row) -> dict:
    keys = ["id", "from_id", "to_id", "confirmed", "created_at"]
    return dict(zip(keys, row))


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
        text("SELECT * FROM issues WHERE id = :id"), {"id": issue_id}
    ).fetchone()
    issue = _issue_row_to_dict(row)

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
    return _issue_row_to_dict(row)


@router.delete("/api/issues/{issue_id}")
def delete_issue(issue_id: str, db=Depends(get_db)):
    """課題と関連エッジを物理削除"""
    db.execute(
        text("DELETE FROM issue_edges WHERE from_id = :id OR to_id = :id"),
        {"id": issue_id},
    )
    db.execute(text("DELETE FROM issues WHERE id = :id"), {"id": issue_id})
    db.commit()
    return {"ok": True}
