from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
from dotenv import load_dotenv
from .persistence import load_graph, update_user_decision
from .watcher import start_watcher
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

observer = None

@app.on_event("startup")
def startup_event():
    global observer
    # backend/app -> ../../notes
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

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
