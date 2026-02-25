import sys
from pathlib import Path
from config import KNOWLEDGE_BASE_DIR
from indexer import index_file

full_path = str(Path(KNOWLEDGE_BASE_DIR) / "03_技術基準/pdf_1771725981_10.md")
print(f"Testing index_file on {full_path}")
print(index_file(full_path))
