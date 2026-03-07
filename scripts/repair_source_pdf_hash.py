import json
import hashlib
from pathlib import Path
import sys

# Add parent directory to sys.path to import from sibling modules
parent_dir = str(Path(__file__).parent.parent)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from indexer import get_chroma_client, COLLECTION_NAME
from config import KNOWLEDGE_BASE_DIR

def repair():
    report_file = Path("missing_hash_report.json")
    if not report_file.exists():
        print(f"Report file {report_file} not found. Run diagnose_metadata.py first.")
        return
        
    with open(report_file, "r", encoding="utf-8") as f:
        missing = json.load(f)
        
    total_missing = len(missing)
    if total_missing == 0:
        print("No missing chunks to repair.")
        return
        
    client = get_chroma_client()
    collection = client.get_collection(name=COLLECTION_NAME)
    kb_dir = Path(KNOWLEDGE_BASE_DIR)
    
    repaired_count = 0
    print(f"Starting repair for {total_missing} chunks...")
    
    for idx, item in enumerate(missing, start=1):
        chunk_id = item.get("chunk_id")
        rel_path = item.get("rel_path", "")
        sqlite_hash = item.get("sqlite_hash", "")
        
        if not chunk_id or not rel_path:
            continue
            
        pdf_hash = sqlite_hash
        # Fallback to computing hash of the physical file if sqlite hash is absent
        if not pdf_hash:
            file_path = kb_dir / rel_path
            if file_path.exists():
                try:
                    pdf_hash = hashlib.sha256(file_path.read_bytes()).hexdigest()[:16]
                except Exception as e:
                    print(f"Error hashing {file_path}: {e}")
            else:
                print(f"[{idx}/{total_missing}] Skipping {chunk_id}: File not found ({rel_path}) and no sqlite_hash available.")
                continue
                
        if not pdf_hash:
            print(f"[{idx}/{total_missing}] Skipping {chunk_id}: Could not determine pdf_hash for {rel_path}.")
            continue
            
        # Update Chromadb entry one chunk at a time
        try:
            res = collection.get(ids=[chunk_id])
            if not res or not res.get("ids"):
                print(f"[{idx}/{total_missing}] Skipping {chunk_id}: Not found in ChromaDB.")
                continue
                
            meta = res["metadatas"][0]
            if not meta:
                meta = {}
                
            meta["source_pdf_hash"] = pdf_hash
            meta["source_pdf"] = pdf_hash  # Backwards compatibility alias
            
            collection.update(
                ids=[chunk_id],
                metadatas=[meta]
            )
            repaired_count += 1
            if repaired_count % 100 == 0:
                print(f"Progress: Repaired {repaired_count} chunks so far...")
                
        except Exception as e:
            print(f"[{idx}/{total_missing}] Error updating {chunk_id}: {e}")
            
    print(f"Repaired: {repaired_count} / {total_missing}")

if __name__ == "__main__":
    repair()
