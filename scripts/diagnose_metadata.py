import json
import logging
from pathlib import Path
import sys

# Add parent directory to sys.path to import from sibling modules
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from indexer import get_chroma_client, COLLECTION_NAME
from database import get_session, Document

def diagnose():
    client = get_chroma_client()
    collection = client.get_collection(name=COLLECTION_NAME)
    
    print("Fetching all chunks from ChromaDB. This may take a moment...", flush=True)
    results = collection.get()
    
    ids = results.get("ids", [])
    metadatas = results.get("metadatas", [])
    
    total = len(ids)
    missing = []
    
    session = get_session()
    try:
        print("Checking metadata for missing source_pdf_hash...", flush=True)
        for chunk_id, metadata in zip(ids, metadatas):
            rel_path = metadata.get("rel_path", "")
            source_pdf_hash = metadata.get("source_pdf_hash", "")
            
            if not source_pdf_hash:
                filename = Path(rel_path).name
                doc = session.query(Document).filter(Document.file_path == rel_path).first()
                if not doc:
                    doc = session.query(Document).filter(Document.filename == filename).first()
                
                sqlite_hash = doc.source_pdf_hash if doc and doc.source_pdf_hash else ""
                
                missing.append({
                    "chunk_id": chunk_id,
                    "rel_path": rel_path,
                    "sqlite_hash": sqlite_hash
                })
                
        output_file = Path("missing_hash_report.json")
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(missing, f, indent=2, ensure_ascii=False)
            
        print(f"Missing: {len(missing)} / {total}")
        print(f"Report saved to {output_file}")
        
    finally:
        session.close()

if __name__ == "__main__":
    diagnose()
