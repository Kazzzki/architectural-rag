import json
import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from indexer import get_chroma_client, COLLECTION_NAME
from gemini_client import get_client
from config import GEMINI_MODEL_RAG
from prompts.research_planner import RESEARCH_PLANNER_SYSTEM_PROMPT, build_research_prompt

logger = logging.getLogger(__name__)

router = APIRouter()

# ====================
# Models
# ====================

class ResearchGenerateRequest(BaseModel):
    node_id: str
    node_label: str
    node_phase: str
    node_category: str
    node_description: str = ""
    node_checklist: List[str] = []
    node_deliverables: List[str] = []
    selected_tools: List[str] = []
    focus: str = ""
    extra_context: Optional[str] = ""

class KnowledgeItem(BaseModel):
    id: str
    title: str
    content: str
    tags: List[str]

class ResearchInjectRequest(BaseModel):
    node_id: str
    node_label: str
    node_phase: str
    node_category: str
    items: List[KnowledgeItem]

# ====================
# Endpoints
# ====================

@router.post("/generate")
def generate_research_plan(request: ResearchGenerateRequest):
    """
    リサーチ指示書 + 知識アイテムをSSEストリーミングで生成
    """
    prompt = build_research_prompt(
        node_id=request.node_id,
        node_label=request.node_label,
        node_phase=request.node_phase,
        node_category=request.node_category,
        node_description=request.node_description,
        node_checklist=request.node_checklist,
        node_deliverables=request.node_deliverables,
        selected_tools=request.selected_tools,
        focus=request.focus,
        extra_context=request.extra_context
    )
    
    def generate_stream():
        try:
            client = get_client()
            if not client:
                raise Exception("Failed to initialize Gemini Client")
            
            # Streaming Generate Content
            response = client.models.generate_content_stream(
                model=GEMINI_MODEL_RAG,
                contents=prompt,
                config={
                    "system_instruction": RESEARCH_PLANNER_SYSTEM_PROMPT,
                    "temperature": 0.4
                }
            )
            
            full_text = ""
            for chunk in response:
                content = chunk.text
                if content:
                    full_text += content
                    yield f"data: {json.dumps({'type': 'chunk', 'data': content}, ensure_ascii=False)}\n\n"
                    
            # 最後にプレーンテキスト全体をパース用データとして送る
            yield f"data: {json.dumps({'type': 'parsed', 'data': full_text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Research generator error: {e}", exc_info=True)
            yield f"event: error\ndata: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
            
    return StreamingResponse(
        generate_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive"
        }
    )

@router.post("/inject")
def inject_research_items(request: ResearchInjectRequest):
    """
    RAGシステム(ChromaDB)のarchitectural_ragコレクションに直接投入
    """
    client = get_chroma_client()
    try:
        collection = client.get_collection(COLLECTION_NAME)
    except Exception as e:
        logger.error(f"ChromaDB retrieve error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Cannot connect to Chroma DB")
        
    ids = []
    documents = []
    metadatas = []
    timestamp = date.today().isoformat()
    
    for item in request.items:
        ids.append(item.id)
        documents.append(item.content)
        
        tags_str = ",".join(item.tags) if item.tags else ""
        
        metadatas.append({
            "source": f"research_planner/{request.node_id}",
            "doc_type": "spec",
            "category": f"process_{request.node_category}",
            "node_id": request.node_id,
            "node_label": request.node_label,
            "node_phase": request.node_phase,
            "tier": "knowledge_item",
            "created_at": timestamp,
            "tags_str": tags_str
        })
        
    if ids:
        try:
            collection.add(
                ids=ids,
                documents=documents,
                metadatas=metadatas
            )
            logger.info(f"Inject success: {len(ids)} items from {request.node_id}")
            return {
                "injected": len(ids),
                "node_id": request.node_id,
                "category": f"process_{request.node_category}"
            }
        except Exception as e:
            logger.error(f"Failed to inject knowledge items: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    else:
        return {"injected": 0, "node_id": request.node_id, "category": f"process_{request.node_category}"}
