import os
import sys
import time
import chromadb
import sqlite3
from pathlib import Path
from indexer import build_index, save_metadata
from config import PDF_STORAGE_DIR

pdf_files = [f for f in os.listdir(PDF_STORAGE_DIR) if f.endswith('.pdf')]
if not pdf_files:
    print('No PDFs found!')
    sys.exit(1)

target = pdf_files[0]
target_path = os.path.join(PDF_STORAGE_DIR, target)

print(f"【テスト対象ファイル】{target}")

start_time = time.time()

# Mock the directory logic by just pointing to the single file or forcing rebuild_index
# Wait, build_index takes a directory. Let's just create a temp dir, put a symlink, and index that.
temp_dir = Path("temp_index_dir")
temp_dir.mkdir(exist_ok=True)
category_dir = temp_dir / "01_テスト"
category_dir.mkdir(exist_ok=True)

# indexer natively uses KNOWLEDGE_BASE_DIR. We can manipulate config or just use the DB directly.
# Wait, in the user's instructions it says: "from indexer import index_single_file"
# Let me check if index_single_file exists or if 'process_pdf_background' is better.
