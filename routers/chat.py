from fastapi import APIRouter, Request, HTTPException
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

class ChatResponse(BaseModel):
    answer: str
    sources: List[dict]

@router.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest):
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
        answer = generate_answer(request.question, context, source_files, history=request.history)

        logger.info(f"Answer generated ({len(answer)} chars)")

        return ChatResponse(answer=answer, sources=source_files)

    except RuntimeError as e:
        logger.error(f"Gemini API完全失敗: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Chat error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Chat processing failed")

@router.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
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
            # 1. ソース情報を先に送信
            yield f"data: {json.dumps({'type': 'sources', 'data': source_files}, ensure_ascii=False)}\n\n"

            try:
                # 2. 回答をストリーミング
                for chunk in generate_answer_stream(request.question, context, source_files, history=history):
                    yield f"data: {json.dumps({'type': 'answer', 'data': chunk}, ensure_ascii=False)}\n\n"
            except Exception as e:
                logger.error(f"Stream generation exception: {e}", exc_info=True)
                yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"

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
