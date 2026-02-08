import json
import time
import os
import fcntl
from pathlib import Path
from typing import Dict, Any, Optional
from datetime import datetime

class OCRStatusManager:
    def __init__(self, status_file: str = "ocr_progress.json"):
        from config import KNOWLEDGE_BASE_DIR
        self.status_file_path = Path(KNOWLEDGE_BASE_DIR) / status_file
        self._ensure_file()

    def _ensure_file(self):
        if not self.status_file_path.exists():
            self._save_status({})
            
    def _load_status(self) -> Dict[str, Any]:
        try:
            if not self.status_file_path.exists():
                return {}
            with open(self.status_file_path, 'r', encoding='utf-8') as f:
                fcntl.flock(f, fcntl.LOCK_SH)
                try:
                    return json.load(f)
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
        except Exception:
            return {}

    def _save_status(self, status: Dict[str, Any]):
        try:
            temp_file = self.status_file_path.with_suffix('.tmp')
            with open(temp_file, 'w', encoding='utf-8') as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                try:
                    json.dump(status, f, ensure_ascii=False, indent=2)
                    f.flush()
                    os.fsync(f.fileno())
                finally:
                    fcntl.flock(f, fcntl.LOCK_UN)
            temp_file.replace(self.status_file_path)
        except Exception as e:
            print(f"Error saving status: {e}")

    def start_processing(self, file_path: str, total_pages: int):
        """処理開始を記録"""
        status = self._load_status()
        rel_path = self._get_rel_path(file_path)
        
        status[rel_path] = {
            "status": "processing",
            "total_pages": total_pages,
            "processed_pages": 0,
            "start_time": time.time(),
            "last_updated": time.time(),
            "estimated_remaining": None
        }
        self._save_status(status)

    def update_progress(self, file_path: str, processed_count: int):
        """進捗更新"""
        status = self._load_status()
        rel_path = self._get_rel_path(file_path)
        
        if rel_path in status:
            current = status[rel_path]
            current["processed_pages"] = processed_count
            current["last_updated"] = time.time()
            
            # 残り時間予測
            elapsed = time.time() - current["start_time"]
            if processed_count > 0:
                avg_time_per_page = elapsed / processed_count
                remaining_pages = current["total_pages"] - processed_count
                current["estimated_remaining"] = round(avg_time_per_page * remaining_pages, 1)
            
            self._save_status(status)

    def complete_processing(self, file_path: str):
        """処理完了"""
        status = self._load_status()
        rel_path = self._get_rel_path(file_path)
        
        if rel_path in status:
            current = status[rel_path]
            current["status"] = "completed"
            current["processed_pages"] = current["total_pages"]
            current["end_time"] = time.time()
            current["duration"] = round(current["end_time"] - current["start_time"], 1)
            current["estimated_remaining"] = 0
            self._save_status(status)

    def fail_processing(self, file_path: str, error: str):
        """エラー記録"""
        status = self._load_status()
        rel_path = self._get_rel_path(file_path)
        
        if rel_path in status:
            status[rel_path]["status"] = "failed"
            status[rel_path]["error"] = str(error)
            status[rel_path]["end_time"] = time.time()
            self._save_status(status)

    def remove_status(self, file_path: str):
        """ステータス削除"""
        status = self._load_status()
        rel_path = self._get_rel_path(file_path)
        
        if rel_path in status:
            del status[rel_path]
            self._save_status(status)

    def rename_status(self, old_path: str, new_path: str):
        """ステータスの移動（リネーム）"""
        status = self._load_status()
        old_rel = self._get_rel_path(old_path)
        new_rel = self._get_rel_path(new_path)
        
        if old_rel in status:
            status[new_rel] = status.pop(old_rel)
            self._save_status(status)

    def get_progress(self, file_path: str) -> Optional[Dict[str, Any]]:
        status = self._load_status()
        rel_path = self._get_rel_path(file_path)
        return status.get(rel_path)
        
    def get_all_status(self) -> Dict[str, Any]:
        return self._load_status()

    def _get_rel_path(self, file_path: str) -> str:
        from config import KNOWLEDGE_BASE_DIR
        try:
            return str(Path(file_path).relative_to(KNOWLEDGE_BASE_DIR))
        except ValueError:
            return Path(file_path).name
