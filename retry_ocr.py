from ocr_processor import process_pdf_background
from config import KNOWLEDGE_BASE_DIR
from pathlib import Path
import os
import sys

# Python 3.9互換性パッチ
if sys.version_info < (3, 10):
    import importlib_metadata
    import importlib.metadata
    importlib.metadata.packages_distributions = importlib_metadata.packages_distributions

# パス解決
sys.path.append(os.getcwd())

filename = "基本設計段階チェックリスト（設計者／CMr）S造研修所.pdf"
pdf_path = Path(KNOWLEDGE_BASE_DIR) / "uploads" / filename
md_path = pdf_path.with_suffix(".md")

if not pdf_path.exists():
    print(f"File not found: {pdf_path}")
    sys.exit(1)

print(f"Retrying OCR for: {filename}")
process_pdf_background(str(pdf_path), str(md_path))
