from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import json
from datetime import datetime, timezone
from retriever import search, build_context, get_source_files
from generator import generate_answer, generate_answer_stream, generate_answer_direct, generate_answer_stream_direct
from database import get_db, ChatSession, ChatMessage
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])

class ChatRequest(BaseModel):
    question: str
    category: Optional[str] = None
    file_type: Optional[str] = None
    date_range: Optional[str] = None
    tags: Optional[List[str]] = None
    tag_match_mode: Optional[str] = "any"
    history: Optional[List[dict]] = None
    # quick_mode=True : 軽量・高速（クエリ展開・HyDE・リランクをスキップ）
    # quick_mode=False: 高精度（全パイプライン実行）
    # quick_mode=None : エンドポイントごとのデフォルトを使用
    #   - /api/chat        → False（高精度）
    #   - /api/chat/stream → True （TTFB優先）
    quick_mode: Optional[bool] = None
    # v4: モデル選択・コンテキストシート注入
    model: str = "gemini-3-flash-preview"
    context_sheet: Optional[str] = None
    # RAGの使用可否（True: 知識ベース参照、False: LLM直接回答）
    use_rag: bool = True
    project_id: Optional[str] = None
    scope_mode: Optional[str] = "auto"

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]

def run_memory_pipeline(user_message: str, assistant_response: str, project_id: Optional[str] = None):
    """Phase1 → Phase2 を順次実行。全体をtry/exceptで包む。"""
    try:
        from context_extractor import extract_personal_context
        from context_updater import update_contexts_with_dedup

        # Phase 1: 抽出
        candidates = extract_personal_context(user_message, assistant_response)
        if not candidates:
            # logger.debug("No personal context detected in this conversation.")
            return

        # Phase 2: 重複解消付き更新
        update_contexts_with_dedup(candidates, source_question=user_message, project_id=project_id)
        logger.info(f"Memory pipeline completed: {len(candidates)} candidates processed.")

    except Exception as e:
        logger.warning(f"Memory pipeline failed (non-critical): {e}")

def persist_chat_message(session_id: str, user_query: str, assistant_response: str, sources: List[dict], model: str):
    """メッセージをDBに永続化し、セッションの更新日時を更新する"""
    from database import SessionLocal, ChatSession, ChatMessage
    db = SessionLocal()
    try:
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            # セッションがない場合は新規作成（通常は呼ばれないはずだが救済策）
            session = ChatSession(id=session_id)
            db.add(session)
        
        if not session.title:
            session.title = user_query[:30]

        # updated_at は onupdate で自動更新されるが、明示的に変更を入れる
        session.updated_at = datetime.now(timezone.utc)
        
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=user_query,
            sources=json.dumps([], ensure_ascii=False),
            model=model
        )
        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=assistant_response,
            sources=json.dumps(sources, ensure_ascii=False),
            model=model
        )

        db.add(user_msg)
        db.add(assistant_msg)
        db.commit()
        logger.info(f"Chat messages persisted for session {session_id}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to persist chat message: {e}")
    finally:
        db.close()

@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, background_tasks: BackgroundTasks, session_id: Optional[str] = None):
    """質問に対する回答を生成"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        if request.use_rag:
            # --- RAGあり（従来の動作） ---
            # v3: デフォルトは高精度モード（quick_mode=None → False 扱い）
            use_advanced = not (request.quick_mode if request.quick_mode is not None else False)
            search_results = search(
                request.question,
                filter_category=request.category,
                filter_file_type=request.file_type,
                filter_date_range=request.date_range,
                filter_tags=request.tags,
                tag_match_mode=request.tag_match_mode or "any",
                use_query_expansion=use_advanced,
                use_hyde=use_advanced,
                use_rerank=use_advanced,
            )
            logger.info(f"Query: {request.question}, Results: {len(search_results.get('documents', []))}")
            context = build_context(search_results)
            source_files = get_source_files(search_results)
            answer = generate_answer(
                request.question, context, source_files,
                history=request.history,
                model=request.model,
                context_sheet=request.context_sheet,
                project_id=request.project_id,
                scope_mode=request.scope_mode,
            )
        else:
            # --- RAGなし（LLM直接回答） ---
            logger.info(f"Direct query (no RAG): {request.question}")
            source_files = []
            answer = generate_answer_direct(
                request.question,
                history=request.history,
                model=request.model,
                context_sheet=request.context_sheet,
            )

        logger.info(f"Answer generated ({len(answer)} chars)")
        
        # 永続化タスク
        if session_id:
            background_tasks.add_task(
                persist_chat_message,
                session_id=session_id,
                user_query=request.question,
                assistant_response=answer,
                sources=source_files,
                model=request.model
            )

        background_tasks.add_task(
            run_memory_pipeline,
            user_message=request.question,
            assistant_response=answer,
            project_id=request.project_id
        )

        return ChatResponse(answer=answer, sources=source_files)

    except RuntimeError as e:
        logger.error(f"Gemini API完全失敗: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Chat processing failed")

@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest, background_tasks: BackgroundTasks, session_id: Optional[str] = None):
    """ストリーミング形式で回答を生成 (Phase 2: SSE対応)"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        if request.use_rag:
            # --- RAGあり（従来の動作） ---
            # ストリームではデフォルト quick_mode=True（リランク・拡張スキップでTTFB激減）
            effective_quick = request.quick_mode if request.quick_mode is not None else True
            use_advanced = not effective_quick
            search_results = search(
                request.question,
                filter_category=request.category,
                filter_file_type=request.file_type,
                filter_date_range=request.date_range,
                filter_tags=request.tags,
                tag_match_mode=request.tag_match_mode or "any",
                use_query_expansion=use_advanced,
                use_hyde=use_advanced,
                use_rerank=use_advanced,
            )
            context = build_context(search_results)
            source_files = get_source_files(search_results)
        else:
            # --- RAGなし（LLM直接回答） ---
            logger.info(f"Direct stream query (no RAG): {request.question}")
            context = ""
            source_files = []

        history = request.history

        def generate():
            full_answer = ""
            yield f"data: {json.dumps({'type': 'sources', 'data': source_files}, ensure_ascii=False)}\n\n"

            try:
                if request.use_rag:
                    stream_gen = generate_answer_stream(
                        request.question, context, source_files,
                        history=history,
                        model=request.model,
                        context_sheet=request.context_sheet,
                        project_id=request.project_id,
                        scope_mode=request.scope_mode,
                    )
                else:
                    stream_gen = generate_answer_stream_direct(
                        request.question,
                        history=history,
                        model=request.model,
                        context_sheet=request.context_sheet,
                    )
                
                # 2. 回答をストリーミング
                for chunk in stream_gen:
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'answer', 'data': chunk}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Stream generation exception: {e}", exc_info=True)
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                return

            # [DONE]送信前に蓄積タスクを登録 (正常終了時のみ)
            if full_answer.strip():
                # 永続化
                if session_id:
                    background_tasks.add_task(
                        persist_chat_message,
                        session_id=session_id,
                        user_query=request.question,
                        assistant_response=full_answer,
                        sources=source_files,
                        model=request.model
                    )

                background_tasks.add_task(
                    run_memory_pipeline,
                    user_message=request.question,
                    assistant_response=full_answer,
                    project_id=request.project_id
                )

                # 3. 完了シグナル
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            generate(), 
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
            }
        )
        
    except Exception as e:
        logger.error(f"Stream routing error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Stream initialization failed")


# --- Chat History Endpoints ---

class SaveMessagesRequest(BaseModel):
    user: str
    assistant: str
    sources: List[dict]
    model: str

@router.get("/api/chat/sessions")
def get_sessions(limit: int = 100, db: Session = Depends(get_db)):
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit).all()
    return [{"id": s.id, "title": s.title, "created_at": s.created_at, "updated_at": s.updated_at} for s in sessions]

@router.post("/api/chat/sessions")
def create_session(db: Session = Depends(get_db)):
    new_session = ChatSession()
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return {"id": new_session.id}

@router.get("/api/chat/sessions/{session_id}")
def get_session_detail(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    
    msg_list = []
    for m in messages:
        msg_list.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else [],
            "model": m.model,
            "created_at": m.created_at
        })
        
    return {
        "id": session.id,
        "title": session.title,
        "created_at": session.created_at,
        "updated_at": session.updated_at,
        "messages": msg_list
    }

@router.delete("/api/chat/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    db.delete(session)
    db.commit()
    return {"status": "success"}

@router.post("/api/chat/sessions/{session_id}/messages")
def save_messages(session_id: str, request: SaveMessagesRequest, db: Session = Depends(get_db)):
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    if not session.title:
        session.title = request.user[:30]

    session.updated_at = datetime.now(timezone.utc)
    
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=request.user,
        sources=json.dumps([]),
        model=request.model
    )
    assistant_msg = ChatMessage(
        session_id=session_id,
        role="assistant",
        content=request.assistant,
        sources=json.dumps(request.sources, ensure_ascii=False),
        model=request.model
    )
    
    db.add(user_msg)
    db.add(assistant_msg)
    db.commit()
    
    return {"status": "success"}

