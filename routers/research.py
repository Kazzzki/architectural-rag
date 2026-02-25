# routers/research.py

import json
import logging
from datetime import datetime
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
# Pipeline Nodes Specs
# ====================

PIPELINE_NODES = [
    {
        "id": "ingestion",
        "label": "Ingestion",
        "description": "PDFのOCR処理・メタデータ抽出・チャンキング (Small-to-Big)",
        "components": ["ocr_processor.py", "indexer.py"],
        "domains": ["PDF構造解析", "PyMuPDFテキスト抽出", "マークダウン変換", "ドキュメントカテゴリ推論"],
        "default_doc_type": "catalog",
        "default_tools": ["Gemini Deep Research", "Perplexity Pro"],
    },
    {
        "id": "retrieval",
        "label": "Retrieval",
        "description": "クエリ展開・HyDE・並列ベクトル検索・LLMリランキング",
        "components": ["retriever.py"],
        "domains": ["Query Expansion建築特化チューニング", "HyDE仮想文書生成", "Cross-Encoder Reranking"],
        "default_doc_type": "spec",
        "default_tools": ["Claude web_fetch", "arXiv Explorer"],
    },
    {
        "id": "generation",
        "label": "Generation",
        "description": "コンテキスト結合・回答生成・ソース参照マッピング",
        "components": ["generator.py"],
        "domains": ["System Prompt最適化", "ソース引用アイコン付与", "会話履歴コンテキスト補完"],
        "default_doc_type": "law",
        "default_tools": ["Gemini Code Assist"],
    },
    {
        "id": "routing",
        "label": "Routing / API",
        "description": "FastAPIルーター・SSEストリーミング・依存関係注入",
        "components": ["server.py", "routers/*.py"],
        "domains": ["FastAPI Pydantic", "SSE Server-Sent Events", "Middleware/CORS"],
        "default_doc_type": "spec",
        "default_tools": ["Github Issues/Discussions"],
    },
    {
        "id": "data_layer",
        "label": "Data Layer",
        "description": "ChromaDBベクトルDB・SQLite状態管理",
        "components": ["database.py", "file_store.py", "drive_sync.py"],
        "domains": ["ChromaDB Metadata Filtering", "SQLite SQLAlchemy", "Google Drive API Auth"],
        "default_doc_type": "drawing",
        "default_tools": ["Gemini Deep Research"],
    }
]

# ====================
# Models
# ====================

class ResearchGenerateRequest(BaseModel):
    node_id: str
    node_label: str
    node_desc: str
    node_components: List[str]
    node_domains: List[str]
    search_category: str
    doc_type: str
    selected_tools: List[str]
    focus: str
    extra_context: Optional[str] = ""

class KnowledgeItem(BaseModel):
    id: str
    title: str
    content: str
    tags: List[str]
    search_category: str
    doc_type: str

class ResearchInjectRequest(BaseModel):
    node_id: str
    node_label: str
    items: List[KnowledgeItem]

# ====================
# Endpoints
# ====================

@router.get("/nodes")
def get_research_nodes():
    return PIPELINE_NODES

@router.post("/generate")
def generate_research_plan(request: ResearchGenerateRequest):
    """
    リサーチ指示書 + 知識アイテムをSSEストリーミングで生成
    """
    prompt = build_research_prompt(
        node_id=request.node_id,
        node_label=request.node_label,
        node_desc=request.node_desc,
        node_components=request.node_components,
        node_domains=request.node_domains,
        search_category=request.search_category,
        doc_type=request.doc_type,
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
            # フロント側で独自パースする実装なので生テキストを渡す
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
    timestamp = datetime.utcnow().isoformat()
    
    preview_titles = []
    
    for item in request.items:
        ids.append(item.id)
        documents.append(item.content)
        
        tags_str = ",".join(item.tags) if item.tags else ""
        
        metadatas.append({
            "source": f"research_planner/{request.node_id}",
            "doc_type": item.doc_type,
            "category": item.search_category,
            "node_id": request.node_id,
            "tier": "knowledge_item",
            "created_at": timestamp,
            "source_pdf_name": f"{request.node_label}_Research.md",
            "source_pdf_hash": f"ki_hash_{request.node_id}_{item.id[-8:]}",
            "filename": f"{request.node_label}_Research.md",
            "rel_path": f"{request.node_label}_Research.md",
            "tags_str": tags_str,
            "page_no": 1,
            "chunk_index": 0,
            "parent_chunk_id": "",
            "has_image": False,
            "drive_file_id": ""
        })
        
        preview_titles.append(f"{item.title}: {item.content[:60]}...")
        
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
                "category": request.items[0].search_category if request.items else "",
                "preview": preview_titles
            }
        except Exception as e:
            logger.error(f"Failed to inject knowledge items: {e}", exc_info=True)
            raise HTTPException(status_code=500, detail=str(e))
    else:
        return {"injected": 0, "preview": []}
