import json
import logging
import asyncio
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from indexer import get_chroma_client, COLLECTION_NAME
from gemini_client import get_client
from config import GEMINI_MODEL_RAG

from prompts.commander_prompt import COMMANDER_SYSTEM_PROMPT, build_commander_prompt
from prompts.aggregator_prompt import AGGREGATOR_SYSTEM_PROMPT, build_aggregator_prompt

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
    リサーチ指示書 + 知識アイテムをSSEストリーミングで生成 (3-stage AI Orchestrator)
    """
    
    async def generate_stream():
        try:
            client = get_client()
            if not client:
                raise Exception("Failed to initialize Gemini Client")
            
            # --- Phase 1: Commander AI (Gap Analysis) ---
            yield f"data: {json.dumps({'type': 'phase_start', 'phase': 1, 'message': '司令塔AIがギャップを分析中...'}, ensure_ascii=False)}\n\n"
            
            commander_prompt = build_commander_prompt(
                node_id=request.node_id,
                node_label=request.node_label,
                node_phase=request.node_phase,
                node_category=request.node_category,
                node_description=request.node_description,
                node_checklist=request.node_checklist,
                node_deliverables=request.node_deliverables,
                focus=request.focus,
                extra_context=request.extra_context
            )
            
            logger.info(f"[{request.node_id}] Phase 1: Calling Commander AI")
            commander_resp = await client.aio.models.generate_content(
                model=GEMINI_MODEL_RAG,
                contents=commander_prompt,
                config={
                    "system_instruction": COMMANDER_SYSTEM_PROMPT,
                    "temperature": 0.2,
                    "response_mime_type": "application/json"
                }
            )
            
            try:
                gaps_data = json.loads(commander_resp.text)
                gaps = gaps_data.get("gaps", [])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse commander response: {commander_resp.text}")
                raise Exception("Commander AI did not return valid JSON")
                
            # Limit to 5 gaps to prevent excessive API calls
            gaps = gaps[:5]
            
            yield f"data: {json.dumps({'type': 'commander_done', 'data': {'gaps': gaps}}, ensure_ascii=False)}\n\n"
            
            # --- Phase 2: Search AI (Parallel Gemini Calls) ---
            yield f"data: {json.dumps({'type': 'phase_start', 'phase': 2, 'message': f'Geminiが調査中 ({len(gaps)}件並列)...'}, ensure_ascii=False)}\n\n"
            
            search_results = []
            
            if gaps:
                semaphore = asyncio.Semaphore(3) # Max 3 concurrent requests
                
                async def _run_single_search(gap: dict):
                    async with semaphore:
                        node_context = {
                            "label": request.node_label,
                            "desc": request.node_description
                        }
                        
                        prompt = f"""あなたは建築・設計・プロジェクト管理の専門知識を持つリサーチャーです。

【調査対象ノード】
ノード名: {node_context['label']}
概要: {node_context['desc']}

【調査すべきギャップ】
タイトル: {gap['title']}
背景: {gap['description']}

【検索クエリ】
{gap.get('search_query', '')}

上記のギャップを解消するために必要な知識・情報・基準・法令・実務的注意点を、
建築プロジェクトのPM/CMが実務で使える形で調査・整理してください。

出力形式:
- 調査結果サマリー（200字程度）
- 重要なポイント（3〜5件の箇条書き）
- 参照すべき情報源・基準・法令名（存在する場合）"""
                        
                        logger.info(f"[{request.node_id}] Phase 2: Searching gap - {gap['id']}")
                        try:
                            resp = await client.aio.models.generate_content(
                                model=GEMINI_MODEL_RAG,
                                contents=prompt,
                                config={
                                    "temperature": 0.3
                                }
                            )
                            result_text = resp.text
                        except Exception as e:
                            logger.error(f"Search failed for gap {gap['id']}: {e}")
                            result_text = f"調査エラー: {e}"
                        
                        return {
                            "gap_id": gap["id"],
                            "gap_title": gap["title"],
                            "findings": result_text
                        }
                
                # Execute in parallel
                tasks = [_run_single_search(gap) for gap in gaps]
                
                for coro in asyncio.as_completed(tasks):
                    res: dict = await coro
                    search_results.append(res)
                    yield f"data: {json.dumps({'type': 'search_done', 'data': {'gap_id': res['gap_id'], 'title': res['gap_title'], 'findings': res['findings']}}, ensure_ascii=False)}\n\n"
            
            # --- Phase 3: Aggregator AI (Streaming Output) ---
            yield f"data: {json.dumps({'type': 'phase_start', 'phase': 3, 'message': '取りまとめAIが指示書を生成中...'}, ensure_ascii=False)}\n\n"
            
            node_context = {
                "label": request.node_label,
                "desc": request.node_description
            }
            
            aggregator_prompt = build_aggregator_prompt(
                node_context=node_context,
                search_results=search_results,
                selected_tools=request.selected_tools
            )
            
            logger.info(f"[{request.node_id}] Phase 3: Calling Aggregator AI")
            aggregator_resp = await client.aio.models.generate_content_stream(
                model=GEMINI_MODEL_RAG,
                contents=aggregator_prompt,
                config={
                    "system_instruction": AGGREGATOR_SYSTEM_PROMPT,
                    "temperature": 0.4
                }
            )
            
            full_text = ""
            async for chunk in aggregator_resp:
                content = chunk.text
                if content:
                    full_text += str(content)
                    yield f"data: {json.dumps({'type': 'chunk', 'data': content}, ensure_ascii=False)}\n\n"
                    
            # 最後にプレーンテキスト全体をパース用データとして送る
            yield f"data: {json.dumps({'type': 'parsed', 'data': full_text}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            
        except Exception as e:
            logger.error(f"Research generator error: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            
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
