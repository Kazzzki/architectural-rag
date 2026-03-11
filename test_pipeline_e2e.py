import os
import shutil
import time
from sqlalchemy.orm import Session
from database import SessionLocal, LegacyDocument
from pipeline_manager import process_file_pipeline
from indexer import get_chroma_client
from config import COLLECTION_NAME
import urllib.request

test_pdf_dest = "data/test_input/test_e2e_input.pdf"

if not os.path.exists("data/test_input"):
    os.makedirs("data/test_input", exist_ok=True)

print("Downloading dummy.pdf for testing...")
urllib.request.urlretrieve("https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf", test_pdf_dest)

client = get_chroma_client()
collection = client.get_or_create_collection(name=COLLECTION_NAME)
db = SessionLocal()

# clean old record
old_doc = db.query(LegacyDocument).filter(LegacyDocument.filename == "test_e2e_input.pdf").first()
if old_doc:
    db.delete(old_doc)
    db.commit()

try:
    print(f"Testing pipeline with {test_pdf_dest} ...")
    process_file_pipeline(test_pdf_dest, "test_e2e_input.pdf", "catalog")
    print("Pipeline execution returned. Waiting 5 seconds just in case...")
    time.sleep(5)
except Exception as e:
    print(f"Pipeline failed: {e}")

results = collection.get(where={"filename": "test_e2e_input.md"})
chunks_found = len(results.get('ids', [])) if results else 0
print(f"Chunks found for test file in ChromaDB: {chunks_found}")
if chunks_found > 0:
    print("✅ ChromaDB にチャンクが登録される")
else:
    print("❌ ChromaDB にチャンクが登録されていない")

import glob
md_files = glob.glob("knowledge_base/*/*.md") + glob.glob("data/input/*.md") + glob.glob("data/knowledge_base/*/*.md") + glob.glob("data/test_input/*.md")
print(f"MD files generated: {[f for f in md_files if 'test_e2e' in f]}")
if any('test_e2e_input' in f and '00_未分類' in f for f in md_files):
    print("✅ knowledge_base/00_未分類/ にMDが生成される")
elif any('test_e2e_input' in f for f in md_files):
    print("⚠️ MDは生成されたが 00_未分類 ではない")
else:
    print("❌ MDが生成されていない")

error_files = glob.glob("data/error/*test_e2e_input.pdf")
if not error_files:
    print("✅ data/error/ にファイルが追加されない")
else:
    print("❌ data/error/ にファイルが追加されている")

status_record = db.query(LegacyDocument).filter(LegacyDocument.filename == "test_e2e_input.pdf").first()
if status_record:
    print(f"DB Status: {status_record.status}")
    if status_record.status == "completed":
        print("✅ status_manager.py complete_processing() 成功")
    else:
        print("❌ status_manager.py complete_processing() 失敗")
else:
    print("❌ DBレコードなし")

try:
    with open("app.log", "r") as f:
        lines = f.readlines()
        recent_lines = "".join(lines[-50:])
        if "OCRエラー" not in recent_lines and "致命的エラー" not in recent_lines:
            print("✅ app.log にOCRエラーが出ない")
        else:
            print("❌ app.log にOCRエラーが出ている可能性がある")
except Exception as e:
    print(f"app.log 読込スキップ: {e}")

db.close()
