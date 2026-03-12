import os
import shutil
import hashlib
import time
import uuid

def generate_run_id() -> str:
    timestamp = int(time.time())
    short_uuid = str(uuid.uuid4())[:8]
    return f"run_{timestamp}_{short_uuid}"

def compute_file_hash(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            hasher.update(chunk)
    return f"sha256:{hasher.hexdigest()}"

def intake_file(inbox_filepath: str, working_dir: str = "working") -> tuple[str, str, dict]:
    """
    Intakes a file from inbox, generates a run_id, copies to working dir securely,
    and returns run_id, working_filepath, and file_info dict for Manifest.
    """
    if not os.path.exists(inbox_filepath):
        raise FileNotFoundError(f"Input file not found: {inbox_filepath}")
        
    run_id = generate_run_id()
    
    filename = os.path.basename(inbox_filepath)
    name, ext = os.path.splitext(filename)
    
    working_filename = f"{name}__{run_id}{ext}"
    working_filepath = os.path.join(working_dir, working_filename)
    
    # Safe copy
    shutil.copy2(inbox_filepath, working_filepath)
    
    size_bytes = os.path.getsize(inbox_filepath)
    file_hash = compute_file_hash(inbox_filepath)
    
    file_info = {
        "filename": filename,
        "extension": ext,
        "size_bytes": size_bytes,
        "hash": file_hash
    }
    
    return run_id, working_filepath, file_info
