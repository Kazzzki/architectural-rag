# migrate_legacy_files.py
import os
import shutil
from pathlib import Path
from config import KNOWLEDGE_BASE_DIR, REFERENCE_DIR, SEARCH_MD_DIR, ERROR_DIR, TEMP_CHUNK_DIR

def migrate_files():
    print("Starting migration to new directory structure...")
    
    # 基本フォルダ作成
    REFERENCE_DIR.mkdir(parents=True, exist_ok=True)
    SEARCH_MD_DIR.mkdir(parents=True, exist_ok=True)
    ERROR_DIR.mkdir(parents=True, exist_ok=True)
    TEMP_CHUNK_DIR.mkdir(parents=True, exist_ok=True)

    # システムフォルダや新しい構成以外のディレクトリを探索
    base_path = Path(KNOWLEDGE_BASE_DIR)
    
    # 対象とする拡張子
    md_exts = ['.md', '.txt']
    pdf_exts = ['.pdf']
    
    count = 0
    # 旧フォルダ構成などから新しいフォルダへ移動
    for filepath in base_path.rglob("*"):
        if filepath.is_dir():
            continue
            
        # 除外するフォルダパス
        rel_str = str(filepath.relative_to(base_path)).replace('\\', '/')
        if rel_str.startswith('10_参照PDF/') or rel_str.startswith('20_検索MD/') or rel_str.startswith('90_処理用データ/') or rel_str.startswith('99_システム/'):
            continue
            
        if rel_str.startswith('chunks/') or rel_str.startswith('.chunk'):
             dest = TEMP_CHUNK_DIR / filepath.name
             shutil.move(str(filepath), str(dest))
             count += 1
             continue
             
        if rel_str.startswith('error/'):
             dest = ERROR_DIR / filepath.name
             shutil.move(str(filepath), str(dest))
             count += 1
             continue

        category = filepath.parent.name
        if category == "建築意匠ナレッジDB":
            category = "uploads"
            
        ext = filepath.suffix.lower()
        if ext in md_exts:
             target_dir = SEARCH_MD_DIR / category
             target_dir.mkdir(parents=True, exist_ok=True)
             shutil.move(str(filepath), str(target_dir / filepath.name))
             count += 1
        elif ext in pdf_exts:
             target_dir = REFERENCE_DIR / category
             target_dir.mkdir(parents=True, exist_ok=True)
             shutil.move(str(filepath), str(target_dir / filepath.name))
             count += 1

    print(f"Migration finished. {count} files moved to the new structure.")
    print("Consider re-running the index process from the Web UI to update database paths.")

if __name__ == "__main__":
    migrate_files()
