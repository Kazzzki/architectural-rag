from pathlib import Path
from pipeline_manager import process_file_pipeline

input_dir = Path("data/input")
target_exts = {".pdf", ".png", ".jpg", ".jpeg"}

stalled = [f for f in input_dir.iterdir() if f.suffix.lower() in target_exts]
print(f"放置ファイル数: {len(stalled)}")

for f in stalled:
    print(f"再処理: {f.name}")
    try:
        process_file_pipeline(str(f))
    except Exception as e:
        print(f"  ERROR: {e}")
