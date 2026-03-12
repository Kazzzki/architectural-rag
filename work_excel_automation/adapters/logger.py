import json
import os
from datetime import datetime
from typing import Dict, Any, Optional

class RunLogger:
    def __init__(self, logs_dir: str, run_id: str):
        self.logs_dir = logs_dir
        self.run_id = run_id
        self.events = []
        os.makedirs(logs_dir, exist_ok=True)
        self.log_path = os.path.join(logs_dir, f"{run_id}__run.json")

    def log_operation(self, op: str, sheet: str, status: str, detail: Optional[str] = None):
        event = {
            "timestamp": datetime.now().isoformat(),
            "op": op,
            "sheet": sheet,
            "status": status,
            "detail": detail
        }
        self.events.append(event)
        
    def save(self):
        with open(self.log_path, "w", encoding="utf-8") as f:
            json.dump({"run_id": self.run_id, "events": self.events}, f, indent=2, ensure_ascii=False)
