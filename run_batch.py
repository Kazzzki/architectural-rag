import logging
from pathlib import Path
from datetime import datetime
from indexer import get_chroma_client, COLLECTION_NAME, GeminiEmbeddingFunction, _index_single_file_info, _infer_doc_type, _should_exclude
from database import init_db, get_session, Document as DbDocument
from config import SEARCH_MD_DIR

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

def scan_only_pdfs(base_dir: Path):
    """knowledge_base内のPDFのみを抽出 (MD優先ロジックを無視)"""
    files = []
    base_path = Path(base_dir)
    if not base_path.exists():
        return files

    for filepath in base_path.rglob("*.pdf"):
        if filepath.is_dir() or _should_exclude(filepath, base_path):
            continue

        rel_path = filepath.relative_to(base_path)
        parts = rel_path.parts
        category = parts[0] if len(parts) > 1 else "未分類"
        subcategory = parts[1] if len(parts) > 2 else ""
        sub_subcategory = parts[2] if len(parts) > 3 else ""
        doc_type = _infer_doc_type(category, filepath.name)

        files.append({
            "filename":       filepath.name,
            "full_path":      str(filepath),
            "rel_path":       str(rel_path),
            "category":       category,
            "subcategory":    subcategory,
            "sub_subcategory": sub_subcategory,
            "file_type":      "pdf",
            "file_size_kb":   round(filepath.stat().st_size / 1024, 2),
            "modified_at":    datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
            "doc_type":       doc_type,
        })
    return files

def run_batch(limit=5):
    init_db()
    
    files = scan_only_pdfs(SEARCH_MD_DIR)
    client = get_chroma_client()
    embedding_function = GeminiEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )
    
    stats = {"total_files": len(files), "indexed": 0, "skipped": 0, "errors": 0, "chunks": 0}
    
    # SQLite で completed のものをスキップ
    session = get_session()
    try:
        completed_docs = session.query(DbDocument).filter(DbDocument.status == 'completed').all()
        indexed_rels = {doc.file_path for doc in completed_docs}
    finally:
        session.close()

    count = 0
    for file_info in files:
        rel_path = file_info["rel_path"]
        if rel_path in indexed_rels:
            stats["skipped"] += 1
            continue
        
        if count >= limit:
            logging.info(f"Reached batch limit of {limit}. Stopping.")
            break
    
        logging.info(f"OCR Indexing PDF: {file_info['filename']}")
        try:
            _index_single_file_info(file_info, collection, stats)
            
            # Explicitly mark as completed in SQLite
            session = get_session()
            try:
                doc = session.query(DbDocument).filter(DbDocument.file_path == rel_path).first()
                if doc:
                    doc.status = 'completed'
                    session.commit()
            finally:
                session.close()
                
            count += 1
        except Exception as e:
            logging.error(f"Error ({rel_path}): {e}")
            stats["errors"] += 1
            count += 1
    
    logging.info(f"Batch completed: {stats}")

if __name__ == '__main__':
    run_batch()
