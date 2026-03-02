from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import logging
import json
from retriever import search, build_context, get_source_files
from generator import generate_answer, generate_answer_stream

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
    # v3: クエリ展開・HyDE・リランクの有効化（デフォルトTrue）
    # ストリーミングや軽量クライアントでは quick_mode=True を指定するとリランクをスキップ
    quick_mode: Optional[bool] = False
    # v4: モデル選択・コンテキストシート注入
    model: str = "gemini-3-flash-preview"
    context_sheet: Optional[str] = None

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]

def run_memory_pipeline(user_message: str, assistant_response: str):
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
        update_contexts_with_dedup(candidates, source_question=user_message)
        logger.info(f"Memory pipeline completed: {len(candidates)} candidates processed.")

    except Exception as e:
        logger.warning(f"Memory pipeline failed (non-critical): {e}")

@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest, background_tasks: BackgroundTasks):
    """質問に対する回答を生成"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        # v3: quick_mode=True の場合はリランク・拡張・HyDEをスキップ
        use_advanced = not request.quick_mode
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

        # コンテキスト構築
        context = build_context(search_results)

        # ソースファイル取得
        source_files = get_source_files(search_results)

        # 回答生成（会話履歴を渡す）
        answer = generate_answer(
            request.question, context, source_files,
            history=request.history,
            model=request.model,
            context_sheet=request.context_sheet,
        )

        logger.info(f"Answer generated ({len(answer)} chars)")
        
        background_tasks.add_task(
            run_memory_pipeline,
            user_message=request.question,
            assistant_response=answer
        )

        return ChatResponse(answer=answer, sources=source_files)

    except RuntimeError as e:
        logger.error(f"Gemini API完全失敗: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Chat processing failed")

@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest, background_tasks: BackgroundTasks):
    """ストリーミング形式で回答を生成 (Phase 2: SSE対応)"""
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="質問を入力してください")
    
    try:
        # ストリームではデフォルト quick_mode=True（リランク・拡張スキップでTTFB激減）
        use_advanced = not bool(request.quick_mode if request.quick_mode is not None else True)
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
        history = request.history

        def generate():
            full_answer = ""
            # 1. ソース情報を先に送信
            yield f"data: {json.dumps({'type': 'sources', 'data': source_files}, ensure_ascii=False)}\n\n"

            try:
                # 2. 回答をストリーミング
                for chunk in generate_answer_stream(
                    request.question, context, source_files,
                    history=history,
                    model=request.model,
                    context_sheet=request.context_sheet,
                ):
                    full_answer += chunk
                    yield f"data: {json.dumps({'type': 'answer', 'data': chunk}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Stream generation exception: {e}", exc_info=True)
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

            # [DONE]送信前に蓄積タスクを登録
            background_tasks.add_task(
                run_memory_pipeline,
                user_message=request.question,
                assistant_response=full_answer
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
