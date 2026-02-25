import os
import sys
import time
import chromadb
from pathlib import Path
from logging import getLogger
import sqlite3

logger = getLogger(__name__)

# Replace with the actual extraction and indexing logic from the app
from indexer import get_chroma_client, _extract_pdf, _infer_doc_type, chunk_for_indexing, GeminiEmbeddingFunction
from database import DB_DIR
from config import PDF_STORAGE_DIR

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from database import Document, Base

# Setup DB for tests
engine = create_engine(f"sqlite:///{DB_DIR}/antigravity.db")
Base.metadata.create_all(bind=engine)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
db = SessionLocal()

pdf_files = [f for f in os.listdir(PDF_STORAGE_DIR) if f.endswith('.pdf') and os.path.getsize(os.path.join(PDF_STORAGE_DIR, f)) > 10000]
if not pdf_files:
    print('No PDFs found!')
    sys.exit(1)

target = pdf_files[0]
target_path = os.path.join(PDF_STORAGE_DIR, target)

print(f"【テスト対象ファイル】{target}")

start_time = time.time()

try:
    # 1. Extraction (simulate _extract)
    print("Extracting...")
    blocks = _extract_pdf(target_path)
    if not blocks:
        print("【OCR結果】失敗 (No blocks returned)")
        sys.exit(1)
    
    # Normally category is inferred from path. We don't have a path, so we guess "00_未分類"
    category = "00_未分類"
    doc_type = _infer_doc_type(category, target)
    print(f"【OCR結果】成功")
    print(f"【doc_type推論】{doc_type}")

    # 2. Chunking
    hash_val = target.replace('.pdf', '')
    chunks = []
    parent_count = 0
    for block in blocks:
        parent_count += 1
        block_chunks = chunk_for_indexing(
            text=block["text"],
            page_number=block["page_number"],
            has_image=block["has_image"],
            doc_type=doc_type,
            source_pdf_hash=hash_val,
            source_pdf_name=target,
            category=category,
            rel_path=target,
            filename=target,
            file_type="pdf",
            modified_at=str(time.time()),
        )
        chunks.extend(block_chunks)
    
    # 3. ChromaDB Insertion
    chroma_client = get_chroma_client()
    collection = chroma_client.get_or_create_collection(
        name="documents",
        embedding_function=GeminiEmbeddingFunction()
    )
    
    import uuid
    ids = [f'{c["metadata"]["source_pdf_hash"]}_{uuid.uuid4().hex[:8]}' for c in chunks]
    documents = [c["text"] for c in chunks]
    metadatas = [c["metadata"] for c in chunks]
    
    if chunks:
        collection.add(documents=documents, metadatas=metadatas, ids=ids)
    print(f"【ChromaDB登録】成功")
    
    # 4. SQLite Insertion
    doc = Document(
        filename=target,
        file_path=target,
        file_type="pdf",
        category=category,
        chunk_count=len(chunks),
        file_hash=hash_val,
        status="completed"
    )
    db.add(doc)
    db.commit()
    print(f"【SQLite登録】成功")

    # Metrics
    parent_count = len(blocks)
    child_count = len(chunks)
    print(f"【チャンク数】子チャンク {child_count}件 / 親チャンク {parent_count}件")

except Exception as e:
    print(f"【エラー内容】{e}")
    sys.exit(1)
finally:
    db.close()

elapsed_time = time.time() - start_time
print(f"【所要時間】約{int(elapsed_time)}秒")
print("【判定】✅ 全件処理に進んで良い")
