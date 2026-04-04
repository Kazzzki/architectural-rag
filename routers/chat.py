from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import json
import concurrent.futures
from datetime import datetime, timezone
from retriever import search, build_context, build_context_with_evidence, get_source_files
from generator import generate_answer, generate_answer_stream, generate_answer_direct, generate_answer_stream_direct, verify_groundedness
from database import get_db, ChatSession, ChatMessage
from sqlalchemy.orm import Session
from backend.conversation_scope import ConversationScope

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Chat"])

# 課題キャプチャ用スレッドプール（メイン LLM ストリームと並列実行するため）
_capture_executor = concurrent.futures.ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="issue_capture"
)


def _resolve_model(model: str, question: str, has_rag: bool) -> str:
    """
    model == 'auto' の場合のみ route_model() で自動選択する。
    それ以外は渡されたモデル名をそのまま返す（後方互換）。
    """
    if model != "auto":
        return model
    try:
        from route_model import route_model
        result = route_model(question=question, has_rag_context=has_rag)
        logger.info(f"Auto model selected: {result['model']} ({result['reason']})")
        return result["model"]
    except Exception as e:
        logger.warning(f"Auto model routing failed, falling back to default: {e}")
        from config import GEMINI_MODEL_RAG
        return GEMINI_MODEL_RAG

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
    conversation_scope: Optional[ConversationScope] = None
    # ウェブ検索の使用可否 (False: 検索しない、True: Google Search Grounding有効)
    use_web_search: bool = False
    # v4.1: session_id を body でも受け取れるようにする
    session_id: Optional[str] = None
    # 課題整理モード
    capture_issues: bool = False
    project_name: Optional[str] = None  # 課題グラフのプロジェクト名

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]
    web_sources: Optional[List[dict]] = None
    evidence_trail: Optional[List[dict]] = None
    confidence: Optional[dict] = None

class SessionResponse(BaseModel):
    id: str
    title: Optional[str] = None
    created_at: datetime
    updated_at: datetime

class SessionDetailResponse(SessionResponse):
    messages: List[dict]

class SessionUpdateRequest(BaseModel):
    title: str

ISSUE_KEYWORDS = ["課題", "問題", "遅延", "コスト超過", "品質", "安全", "不具合", "トラブル", "クレーム", "障害", "リスク"]


def _try_capture_issue_from_chat(question: str, project_name: str) -> Optional[dict]:
    """チャットメッセージから課題を検出してキャプチャ。失敗しても例外を出さない。"""
    if not any(kw in question for kw in ISSUE_KEYWORDS):
        return None
    try:
        from database import SessionLocal
        from routers.issues import capture_issue_core
        db = SessionLocal()
        try:
            return capture_issue_core(question, project_name, db)
        finally:
            db.close()
    except Exception as e:
        logger.error(f"チャットからの課題キャプチャ失敗: {e}", exc_info=True)
        return None


def run_memory_pipeline(user_message: str, assistant_response: str, project_id: Optional[str] = None):
    """
    ユーザーの発言とAIの回答から個人知見を抽出し、MemoryV2 (Layer A) および PersonalContext (Layer C) を更新する。
    """
    # 起動条件の判定 (#48)
    if not assistant_response or len(assistant_response.strip()) < 10:
        logger.info("Memory pipeline skipped: Assistant response too short.")
        return

    # 拒絶/定型文の判定
    refusal_patterns = ["申し訳ありません", "分かりかねます", "お答えできません", "データベースにありません"]
    if any(p in assistant_response for p in refusal_patterns):
        logger.info("Memory pipeline skipped: Assistant response contains refusal patterns.")
        return

    logger.info(f"Memory pipeline STARTED: project_id={project_id}")
    try:
        from context_extractor import extract_personal_context
        from context_updater import update_contexts_with_dedup

        # Phase 1: 抽出 (内部で Layer A への ingest も行う)
        candidates = extract_personal_context(user_message, assistant_response)
        
        if not candidates:
            logger.info("Memory pipeline: No personal context detected in this conversation.")
            return

        # Phase 2: 重複解消付き更新 (Layer C)
        update_contexts_with_dedup(candidates, source_question=user_message, project_id=project_id)
        logger.info(f"Memory pipeline COMPLETED: {len(candidates)} candidates processed.")

    except Exception as e:
        # 例外を隔離し、本体のチャットフローを停止させない (#51)
        logger.error(f"Memory pipeline FAILED (non-critical): {e}", exc_info=True)

def persist_chat_message(session_id: str, user_query: str, assistant_response: str, sources: List[dict], model: str, web_sources: Optional[List[dict]] = None):
    """
    メッセージをDBに永続化し、セッションの更新日時を更新する。
    トランザクション整合性を保ち、重複保存を防止する。
    """
    if not session_id or not user_query or not assistant_response:
        logger.warning(f"Aborting persistence: Missing session_id or content.")
        return None

    from database import SessionLocal, ChatSession, ChatMessage
    db = SessionLocal()
    try:
        # 1. セッション確保
        session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
        if not session:
            logger.info(f"Creating new session {session_id} in persistence layer.")
            session = ChatSession(id=session_id)
            db.add(session)
        
        if not session.title:
            session.title = user_query[:30]

        # 2. 更新日時の明示的更新 (UTC)
        session.updated_at = datetime.now(timezone.utc)
        
        # 3. 重複保存防止 (#46)
        # セッションの最新メッセージを確認し、全く同じ内容の回答が連続する場合は保存しない
        last_msg = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.desc()).first()
        if last_msg and last_msg.role == "assistant" and last_msg.content == assistant_response:
            logger.info(f"Persistence SKIPPED: Duplicate assistant message detected for session {session_id}.")
            return last_msg.id

        # 4. メッセージ保存 (User -> Assistant の順序固定 #47)
        # Role 正規化 (#44)
        user_msg = ChatMessage(
            session_id=session_id,
            role="user",
            content=user_query,
            sources=json.dumps([], ensure_ascii=False),
            model=model
        )
        db.add(user_msg)
        db.flush() # ID確定のため

        assistant_msg = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=assistant_response,
            sources=json.dumps(sources, ensure_ascii=False),
            web_sources=json.dumps(web_sources or [], ensure_ascii=False),
            model=model
        )
        db.add(assistant_msg)
        
        # 5. 一括コミット (#45)
        db.commit()
        logger.info(f"Chat messages persisted (IDs: user={user_msg.id}, assistant={assistant_msg.id}) for session {session_id}")
        return assistant_msg.id
        
    except Exception as e:
        db.rollback()
        logger.error(f"Persistence FAILED for session {session_id}: {e}", exc_info=True)
        return None
    finally:
        db.close()

@router.post("/api/chat", response_model=ChatResponse, response_model_exclude_none=True)
def chat(request: ChatRequest, background_tasks: BackgroundTasks, session_id: Optional[str] = None):
    """質問に対する回答を生成"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    # session_id の正規化: body を優先、query は fallback とする (#20, #23)
    effective_session_id = request.session_id or session_id
    
    # 安全のための初期化 (#18)
    answer = ""
    source_files = []
    web_sources = None
    evidence_trail = []
    
    try:
        if request.use_rag or request.use_web_search:
            # --- RAGあり または ウェブ検索あり ---
            if request.use_rag:
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
                context, evidence_trail = build_context_with_evidence(search_results)
                source_files = get_source_files(search_results)
            else:
                # ウェブ検索のみ（RAGなし）
                logger.info(f"Web search only query: {request.question}")
                context = ""
                source_files = []
                evidence_trail = []

            result = generate_answer(
                request.question, context, source_files,
                history=request.history,
                model=_resolve_model(request.model, request.question, bool(context)),
                context_sheet=request.context_sheet,
                project_id=request.project_id,
                scope_mode=request.scope_mode,
                use_web_search=request.use_web_search,
            )
            if isinstance(result, dict):
                answer = result["answer"]
                web_sources = result.get("web_sources")
            else:
                answer = result
                web_sources = None
        else:
            # --- RAGなし かつ ウェブ検索なし（LLM直接回答） ---
            logger.info(f"Direct query (no RAG, no Web Search): {request.question}")
            source_files = []
            evidence_trail = []
            result = generate_answer_direct(
                request.question,
                history=request.history,
                model=_resolve_model(request.model, request.question, False),
                context_sheet=request.context_sheet,
                use_web_search=request.use_web_search,
            )
            if isinstance(result, dict):
                answer = result["answer"]
                web_sources = result.get("web_sources")
            else:
                answer = result
                web_sources = None

        logger.info(f"Answer generated ({len(answer)} chars)")
        
        # 永続化タスクを BackgroundTasks に移行 (#19, #28)
        if effective_session_id:
            background_tasks.add_task(
                persist_chat_message,
                session_id=effective_session_id,
                user_query=request.question,
                assistant_response=answer,
                sources=source_files,
                model=request.model,
                web_sources=web_sources
            )
        
        # Layer A Memory
        # 空回答時 (#29) は memory pipeline をスキップ
        if answer.strip():
            background_tasks.add_task(
                run_memory_pipeline,
                user_message=request.question,
                assistant_response=answer,
                project_id=request.project_id
            )
        
        return ChatResponse(
            answer=answer,
            sources=source_files,
            web_sources=web_sources,
            evidence_trail=evidence_trail if evidence_trail else None,
        )

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
    
    # session_id の正規化: body を優先、query は fallback とする (#23)
    effective_session_id = request.session_id or session_id
    
    try:
        if request.use_rag or request.use_web_search:
            # --- RAGあり または ウェブ検索あり ---
            if request.use_rag:
                # ストリームでもデフォルト quick_mode=False（精度優先: クエリ展開・HyDE・リランク実行）
                effective_quick = request.quick_mode if request.quick_mode is not None else False
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
                context, evidence_trail = build_context_with_evidence(search_results)
                source_files = get_source_files(search_results)
            else:
                # ウェブ検索のみ（RAGなし）
                logger.info(f"Web search direct stream query: {request.question}")
                context = ""
                source_files = []
                evidence_trail = []
        else:
            # --- RAGなし かつ ウェブ検索なし（LLM直接回答） ---
            logger.info(f"Direct stream query (no RAG, no Web Search): {request.question}")
            context = ""
            source_files = []
            evidence_trail = []

        history = request.history

        def generate(sid):
            # 状態管理の整理 (#30)
            full_answer = ""
            web_sources_collected = []
            done_sent = False
            error_sent = False

            # 初期情報の送出
            yield f"data: {json.dumps({'type': 'sources', 'data': source_files}, ensure_ascii=False)}\n\n"
            # Evidence Trail を初期送出
            if evidence_trail:
                yield f"data: {json.dumps({'type': 'evidence_trail', 'data': evidence_trail}, ensure_ascii=False)}\n\n"

            # 課題キャプチャをメインストリームと並列で開始（ラグ解消）
            capture_future = None
            if (request.capture_issues and request.project_name and
                    any(kw in request.question for kw in ISSUE_KEYWORDS)):
                capture_future = _capture_executor.submit(
                    _try_capture_issue_from_chat,
                    request.question,
                    request.project_name,
                )

            try:
                # generator の呼び出し整理 (#33)
                if request.use_rag or request.use_web_search:
                    stream_gen = generate_answer_stream(
                        request.question, context, source_files,
                        history=history,
                        model=_resolve_model(request.model, request.question, bool(context)),
                        context_sheet=request.context_sheet,
                        project_id=request.project_id,
                        scope_mode=request.scope_mode,
                        use_web_search=request.use_web_search,
                    )
                else:
                    stream_gen = generate_answer_stream_direct(
                        request.question,
                        history=history,
                        model=_resolve_model(request.model, request.question, False),
                        context_sheet=request.context_sheet,
                        use_web_search=request.use_web_search,
                    )
                
                # チャンク送出と累積の責務分離 (#33)
                for part in stream_gen:
                    if part["type"] == "answer":
                        chunk = part["data"]
                        full_answer += chunk
                        yield f"data: {json.dumps({'type': 'answer', 'data': chunk}, ensure_ascii=False)}\n\n"
                    elif part["type"] == "web_sources":
                        web_sources_collected = part["data"]
                        yield f"data: {json.dumps({'type': 'web_sources', 'data': web_sources_collected}, ensure_ascii=False)}\n\n"
                
                # 課題キャプチャ結果を取得（並列実行済みのため待機時間 ≈ 0）
                if capture_future is not None and full_answer.strip():
                    try:
                        capture_result = capture_future.result(timeout=15)
                        if capture_result:
                            yield f"data: {json.dumps({'type': 'issue_capture', 'data': capture_result}, ensure_ascii=False)}\n\n"
                    except concurrent.futures.TimeoutError:
                        logger.warning("Issue capture timed out after 15s, skipping")
                    except Exception as e:
                        logger.error(f"Issue capture future failed: {e}", exc_info=True)

                # 正常終了時の後継タスク登録（副作用の分離） (#31, #35)
                # 空回答時 (#29) は memory pipeline をスキップ
                if full_answer.strip():
                    if sid:
                        background_tasks.add_task(
                            persist_chat_message,
                            session_id=sid,
                            user_query=request.question,
                            assistant_response=full_answer,
                            sources=source_files,
                            model=request.model,
                            web_sources=web_sources_collected
                        )

                    background_tasks.add_task(
                        run_memory_pipeline,
                        user_message=request.question,
                        assistant_response=full_answer,
                        project_id=request.project_id
                    )

                # Groundedness Check（非同期: ストリーム末尾で送信）
                if full_answer.strip() and evidence_trail:
                    try:
                        confidence = verify_groundedness(full_answer, evidence_trail)
                        if confidence:
                            yield f"data: {json.dumps({'type': 'confidence_update', 'data': confidence}, ensure_ascii=False)}\n\n"
                    except Exception as e:
                        logger.warning(f"Groundedness check failed (non-critical): {e}")

            except Exception as e:
                # キャプチャ未完了なら中断
                if capture_future is not None:
                    capture_future.cancel()
                # エラーイベントの多重送信防止・排他制御 (#32, #34, #31)
                if not error_sent and not done_sent:
                    logger.error(f"Stream generation exception: {e}", exc_info=True)
                    yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
                    error_sent = True
            finally:
                # 終端通知の統一と確実な [DONE] 送出 (#24, #32, #36)
                if not done_sent and not error_sent:
                    yield "data: [DONE]\n\n"
                    done_sent = True
        
        return StreamingResponse(
            generate(effective_session_id), 
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
    web_sources: Optional[List[dict]] = None
    model: str

@router.get("/api/chat/sessions", response_model=List[SessionResponse])
def get_sessions(limit: int = 100, db: Session = Depends(get_db)):
    """セッション一覧を取得（更新日時降順）"""
    sessions = db.query(ChatSession).order_by(ChatSession.updated_at.desc()).limit(limit).all()
    return sessions

@router.post("/api/chat/sessions", response_model=SessionResponse)
def create_session(db: Session = Depends(get_db)):
    """新規セッションを作成"""
    new_session = ChatSession()
    db.add(new_session)
    db.commit()
    db.refresh(new_session)
    return new_session

@router.get("/api/chat/sessions/{session_id}", response_model=SessionDetailResponse)
def get_session_detail(session_id: str, db: Session = Depends(get_db)):
    """セッション詳細とメッセージ履歴を取得"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        logger.warning(f"Session not found: {session_id}")
        raise HTTPException(status_code=404, detail="Session not found")
    
    messages = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.created_at.asc()).all()
    
    msg_list = []
    for m in messages:
        msg_list.append({
            "id": m.id,
            "role": m.role,
            "content": m.content,
            "sources": json.loads(m.sources) if m.sources else [],
            "web_sources": json.loads(m.web_sources) if getattr(m, 'web_sources', None) else [],
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

@router.patch("/api/chat/sessions/{session_id}", response_model=SessionResponse)
def update_session(session_id: str, request: SessionUpdateRequest, db: Session = Depends(get_db)):
    """セッション情報の部分更新（現在はタイトルのみ）"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    session.title = request.title
    db.commit()
    db.refresh(session)
    logger.info(f"Session {session_id} title updated to: {request.title}")
    return session

@router.delete("/api/chat/sessions/{session_id}")
def delete_session(session_id: str, db: Session = Depends(get_db)):
    """セッションを削除（メッセージも連鎖削除される）"""
    session = db.query(ChatSession).filter(ChatSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    
    db.delete(session)
    db.commit()
    logger.info(f"Session {session_id} and its messages deleted.")
    return {"status": "success"}

@router.post("/api/chat/sessions/{session_id}/messages")
def save_messages(session_id: str, request: SaveMessagesRequest, db: Session = Depends(get_db)):
    """
    [DEPRECATED] 手動メッセージ保存用。
    現在は chat/stream エンドポイント側で自動保存されるため、基本的には使用しない。
    """
    logger.warning(f"Deprecated endpoint /api/chat/sessions/{session_id}/messages called")
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
        web_sources=json.dumps(request.web_sources or [], ensure_ascii=False),
        model=request.model
    )
    
    db.add(user_msg)
    db.add(assistant_msg)
    db.commit()
    
    return {"status": "success"}

