# routers/analyze.py
# 複数MDファイル結合・コンテキストシート生成エンドポイント（v2 — ContextSheet テーブル対応）

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from config import KNOWLEDGE_BASE_DIR, GEMINI_MODEL_RAG, MAX_TOKENS, TEMPERATURE
from database import SessionLocal, ContextSheet
from gemini_client import get_client
from google.genai import types

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Analyze"])


# ===== リクエスト / レスポンスモデル =====

class ContextSheetRequest(BaseModel):
    file_paths: Optional[List[str]] = None   # 個別ファイル指定（knowledge_base からの相対パス）
    folder_path: Optional[str] = None        # フォルダ一括指定（配下の全MDを再帰収集）
    role: str                                # pmcm / designer / cost
    model: str = GEMINI_MODEL_RAG
    char_limit: int = Field(default=80000, ge=1000, le=500000)
    title: Optional[str] = None             # ユーザーが付ける任意の名前


class ContextSheetSummary(BaseModel):
    id: int
    title: Optional[str]
    role: str
    model: str
    file_count: int
    truncated: bool
    created_at: str


class ContextSheetDetail(ContextSheetSummary):
    file_paths: List[str]
    char_limit: int
    content: Optional[str]


# ===== MD結合・圧縮ユーティリティ =====

def collect_md_files(
    file_paths: Optional[List[str]],
    folder_path: Optional[str],
) -> List[str]:
    """
    file_paths または folder_path から MD ファイルパス（相対）リストを返す。
    folder_path 指定時はサブフォルダを含めて再帰収集。
    """
    if file_paths:
        return [p for p in file_paths if p.endswith(".md")]

    if folder_path:
        abs_folder = KNOWLEDGE_BASE_DIR / folder_path
        if not abs_folder.is_dir():
            raise HTTPException(
                status_code=404,
                detail=f"フォルダが見つかりません: {folder_path}",
            )
        # 再帰的にすべての .md ファイルを収集（相対パスとして返す）
        return sorted([
            str(p.relative_to(KNOWLEDGE_BASE_DIR))
            for p in abs_folder.rglob("*.md")
        ])

    raise HTTPException(
        status_code=400,
        detail="file_paths または folder_path のいずれかを指定してください。",
    )


def build_combined_md(
    relative_paths: List[str],
    char_limit: int,
) -> tuple[str, bool]:
    """
    複数MDを結合し、上限を超える場合は先頭/中間/末尾をサンプリング。
    Returns: (結合テキスト, 圧縮が発生したか)
    """
    chunks: List[str] = []
    for rel_path in relative_paths:
        abs_path = KNOWLEDGE_BASE_DIR / rel_path
        if abs_path.exists() and abs_path.is_file():
            try:
                text = abs_path.read_text(encoding="utf-8")
                chunks.append(f"\n\n---\n## ファイル: {rel_path}\n\n{text}")
            except Exception as e:
                logger.warning(f"Failed to read {rel_path}: {e}")

    combined = "".join(chunks)
    if not combined:
        raise HTTPException(status_code=404, detail="読み込み可能なMDファイルがありません。")

    truncated = False
    if len(combined) > char_limit:
        truncated = True
        third = char_limit // 3
        mid_start = len(combined) // 2 - third // 2
        combined = (
            combined[:third]
            + f"\n\n...[中略: 文字数上限 {char_limit:,} 文字により省略]...\n\n"
            + combined[mid_start: mid_start + third]
            + f"\n\n...[中略]...\n\n"
            + combined[-third:]
        )

    return combined, truncated


def save_context_sheet(
    role: str,
    model: str,
    file_paths: List[str],
    char_limit: int,
    truncated: bool,
    content: str,
    title: Optional[str],
) -> int:
    """ContextSheet テーブルに保存して id を返す。"""
    session = SessionLocal()
    try:
        sheet = ContextSheet(
            title=title,
            role=role,
            model=model,
            file_paths=json.dumps(file_paths, ensure_ascii=False),
            char_limit=char_limit,
            truncated=truncated,
            content=content,
            created_at=datetime.now(timezone.utc),
        )
        session.add(sheet)
        session.commit()
        session.refresh(sheet)
        logger.info(f"ContextSheet saved: id={sheet.id}, role={role}, files={len(file_paths)}")
        return sheet.id
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to save ContextSheet: {e}", exc_info=True)
        raise
    finally:
        session.close()


# ===== エンドポイント =====

@router.post("/api/analyze/context-sheet")
def generate_context_sheet(request: ContextSheetRequest):
    """
    複数MDファイルを結合・分析しSSEストリームでコンテキストシートを返す。
    生成完了後、ContextSheet テーブルに保存する。
    """
    from prompts.context_sheet_roles import get_role_prompt, AVAILABLE_ROLES

    # ロール検証
    if request.role not in AVAILABLE_ROLES:
        raise HTTPException(
            status_code=400,
            detail=f"不明なロール: '{request.role}'. 有効なロール: {list(AVAILABLE_ROLES.keys())}",
        )

    # 対象ファイル収集
    md_paths = collect_md_files(request.file_paths, request.folder_path)
    if not md_paths:
        raise HTTPException(status_code=400, detail="対象MDファイルが存在しません。")

    # MD結合・圧縮
    combined, truncated = build_combined_md(md_paths, request.char_limit)
    file_count = len(md_paths)

    # プロンプト組み立て
    prompt = get_role_prompt(request.role, file_count, combined)
    if prompt is None:
        raise HTTPException(status_code=400, detail="プロンプト生成に失敗しました。")

    def generate():
        full_sheet = ""

        # 圧縮通知を先頭に送信
        if truncated:
            warning = f"⚠️ **文字数上限（{request.char_limit:,}文字）により一部省略されました。** {file_count}件のMDを結合した結果を先頭・中間・末尾からサンプリングして分析しています。\n\n"
            yield f"data: {json.dumps({'type': 'truncation_warning', 'data': warning}, ensure_ascii=False)}\n\n"

        try:
            client = get_client()
            stream_iter = client.models.generate_content_stream(
                model=request.model,
                contents=[types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=prompt)],
                )],
                config=types.GenerateContentConfig(
                    temperature=TEMPERATURE,
                    max_output_tokens=MAX_TOKENS,
                ),
            )
            for chunk in stream_iter:
                if chunk.text:
                    full_sheet += chunk.text
                    yield f"data: {json.dumps({'type': 'answer', 'data': chunk.text}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"Context sheet stream error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            return

        # 生成完了後 → DB 保存
        if full_sheet:
            sheet_id = save_context_sheet(
                role=request.role,
                model=request.model,
                file_paths=md_paths,
                char_limit=request.char_limit,
                truncated=truncated,
                content=full_sheet,
                title=request.title,
            )
            yield f"data: {json.dumps({'type': 'saved', 'id': sheet_id}, ensure_ascii=False)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.get("/api/analyze/context-sheets", response_model=List[ContextSheetSummary])
def list_context_sheets():
    """保存済みコンテキストシートの一覧を返す（本文は含まない）。"""
    session = SessionLocal()
    try:
        sheets = session.query(ContextSheet).order_by(ContextSheet.created_at.desc()).all()
        return [
            ContextSheetSummary(
                id=s.id,
                title=s.title,
                role=s.role,
                model=s.model,
                file_count=len(json.loads(s.file_paths or "[]")),
                truncated=bool(s.truncated),
                created_at=s.created_at.isoformat() if s.created_at else "",
            )
            for s in sheets
        ]
    finally:
        session.close()


@router.get("/api/analyze/context-sheet/{sheet_id}", response_model=ContextSheetDetail)
def get_context_sheet(sheet_id: int):
    """指定IDのコンテキストシート全文を返す。"""
    session = SessionLocal()
    try:
        sheet = session.query(ContextSheet).filter(ContextSheet.id == sheet_id).first()
        if sheet is None:
            raise HTTPException(status_code=404, detail=f"コンテキストシート id={sheet_id} が見つかりません。")
        paths = json.loads(sheet.file_paths or "[]")
        return ContextSheetDetail(
            id=sheet.id,
            title=sheet.title,
            role=sheet.role,
            model=sheet.model,
            file_count=len(paths),
            file_paths=paths,
            char_limit=sheet.char_limit or 80000,
            truncated=bool(sheet.truncated),
            content=sheet.content,
            created_at=sheet.created_at.isoformat() if sheet.created_at else "",
        )
    finally:
        session.close()


@router.delete("/api/analyze/context-sheet/{sheet_id}")
def delete_context_sheet(sheet_id: int):
    """指定IDのコンテキストシートを削除する。"""
    session = SessionLocal()
    try:
        sheet = session.query(ContextSheet).filter(ContextSheet.id == sheet_id).first()
        if sheet is None:
            raise HTTPException(status_code=404, detail=f"コンテキストシート id={sheet_id} が見つかりません。")
        session.delete(sheet)
        session.commit()
        logger.info(f"ContextSheet deleted: id={sheet_id}")
        return {"status": "deleted", "id": sheet_id}
    except HTTPException:
        raise
    except Exception as e:
        session.rollback()
        logger.error(f"Failed to delete ContextSheet: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()
