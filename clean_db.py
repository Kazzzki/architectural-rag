# clean_db.py
import sys
import os

from pathlib import Path
import file_store

def clean_missing_files():
    all_files = file_store.list_files()
    deleted = 0
    
    with file_store.get_db() as conn:
        for file_record in all_files:
            current_path = file_record.get("current_path")
            if not current_path or not Path(current_path).exists():
                print(f"File not found on disk, deleting record: {current_path}")
                conn.execute(
                    "DELETE FROM files WHERE id = ?",
                    (file_record["id"],)
                )
                deleted += 1
            
    print(f"Cleaned {deleted} missing files from the database.")

if __name__ == "__main__":
    clean_missing_files()
