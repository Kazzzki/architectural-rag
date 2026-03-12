import hashlib
import shutil
import os
import time
import uuid
from pathlib import Path

def generate_run_id() -> str:
    """Generate a unique run ID using a short UUID and timestamp."""
    short_id = str(uuid.uuid4())[:8]
    timestamp = int(time.time())
    return f"{timestamp}_{short_id}"

def compute_hash(file_path: str) -> str:
    """Compute SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def ensure_dir(dir_path: str):
    """Ensure a directory exists."""
    os.makedirs(dir_path, exist_ok=True)

def copy_to_working(src_path: str, working_dir: str, run_id: str) -> str:
    """Copy the original file to the working directory with a safe name."""
    ensure_dir(working_dir)
    src = Path(src_path)
    base_name = src.stem
    ext = src.suffix
    dest_name = f"{base_name}__wrk_{run_id}{ext}"
    dest_path = os.path.join(working_dir, dest_name)
    shutil.copy2(src_path, dest_path)
    return dest_path

def make_output_path(src_path: str, output_dir: str, run_id: str) -> str:
    """Generate output path for the finalized file."""
    ensure_dir(output_dir)
    src = Path(src_path)
    base_name = src.stem
    ext = src.suffix
    dest_name = f"{base_name}__out_{run_id}{ext}"
    return os.path.join(output_dir, dest_name)

def make_plan_path(plans_dir: str, src_path: str, run_id: str) -> str:
    """Generate path for saving the plan JSON."""
    ensure_dir(plans_dir)
    src = Path(src_path)
    base_name = src.stem
    dest_name = f"{base_name}__plan_{run_id}.json"
    return os.path.join(plans_dir, dest_name)
    
def get_file_size(file_path: str) -> int:
    return os.path.getsize(file_path)
