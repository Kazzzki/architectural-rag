from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import time
from typing import Optional
from dotenv import load_dotenv
from .persistence import (
    load_graph, update_user_decision,
    add_manual_node, merge_ai_nodes,
    load_chat_history, append_chat_entry,
)
from .watcher import start_watcher
from .llm_agent import LLMAgent
from pydantic import BaseModel

# Load env from .env file in root or backend root
# Assuming the user has a .env check relative to main.py
current_dir = os.path.dirname(os.path.abspath(__file__))
# Try loading from mindmapper root
root_env = os.path.join(current_dir, "../../.env")
if os.path.exists(root_env):
    load_dotenv(root_env)
else:
    # Try backend root
    backend_env = os.path.join(current_dir, "../.env")
    load_dotenv(backend_env)

app = FastAPI()

class DecisionUpdate(BaseModel):
    id: str
    decision: str

class IssueCreate(BaseModel):
    label: str
    category: str = "Issue"
    priority: float = 0.5
    source_file: str = "manual"

class AnalyzeRequest(BaseModel):
    text: str
    source_label: str = "voice_input"

class ChatRequest(BaseModel):
    message: str
    node_id: Optional[str] = None

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

observer = None
_agent = None

@app.on_event("startup")
def startup_event():
    global observer, _agent
    _agent = LLMAgent()
    notes_dir = os.path.join(current_dir, "../../notes")
    print(f"Watching {notes_dir}")
    observer = start_watcher(notes_dir)

@app.on_event("shutdown")
def shutdown_event():
    global observer
    if observer:
        observer.stop()
        observer.join()

@app.get("/api/graph")
def get_graph():
    return load_graph()

@app.post("/api/decision")
def post_decision(update: DecisionUpdate):
    if update_user_decision(update.id, update.decision):
        return {"status": "ok"}
    raise HTTPException(status_code=404, detail="Node not found")


# Bug1 fix: manually add an issue node
@app.post("/api/issue")
def post_issue(req: IssueCreate):
    node = add_manual_node(req.label, req.category, req.priority, req.source_file)
    return node


# Bug3 fix: analyze text with Gemini and merge resulting nodes
@app.post("/api/analyze")
def post_analyze(req: AnalyzeRequest):
    nodes = _agent.analyze_text(req.text, req.source_label)
    if nodes:
        merge_ai_nodes(nodes)
    return {"nodes": nodes, "count": len(nodes)}


# Bug3 fix: chat with Gemini (optionally tied to a node)
@app.post("/api/chat")
def post_chat(req: ChatRequest):
    graph = load_graph()
    response_text = _agent.chat(req.message, req.node_id, graph)
    entry = {
        "ts": time.time(),
        "node_id": req.node_id,
        "node_label": next(
            (n["data"]["label"] for n in graph.get("nodes", []) if n["id"] == req.node_id),
            None,
        ) if req.node_id else None,
        "user_message": req.message,
        "ai_response": response_text,
    }
    append_chat_entry(entry)
    return {"response": response_text, "entry": entry}


# New feature: return full chat history
@app.get("/api/chat_history")
def get_chat_history():
    return load_chat_history()


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
