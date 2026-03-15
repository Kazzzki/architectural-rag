import os
import json
import logging
import sys
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from drive_sync import get_drive_service, find_folder_by_name, create_folder
from config import GOOGLE_DRIVE_FOLDER_NAME

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

REPORT_FILE = Path(__file__).parent / "drive_audit_report.json"
MOVE_LIST_FILE = Path(__file__).parent / "drive_move_list.json"

def trash_files(service, file_list: List[Dict[str, Any]], reason: str):
    """Move files to trash with user confirmation"""
    if not file_list:
        logger.info(f"削除対象（{reason}）はありません。")
        return 0, 0

    print(f"\n--- 削除対象（{reason}）: {len(file_list)}件 ---")
    for f in file_list[:10]:  # Show first 10
        print(f"  - {f['name']} (ID: {f.get('file_id', 'N/A')}, Path: {f.get('folder_path', 'N/A')})")
    if len(file_list) > 10:
        print(f"  ...他 {len(file_list) - 10}件")

    confirm = input(f"\nこれらの{reason}ファイルをゴミ箱に移動しますか？ (y/N): ").lower()
    if confirm != 'y':
        print("削除をキャンセルしました。")
        return 0, 0

    success_count = 0
    error_count = 0

    for f in file_list:
        file_id = f.get('file_id')
        if not file_id:
            logger.warning(f"File ID missing for {f['name']}")
            error_count += 1
            continue
            
        try:
            service.files().update(fileId=file_id, body={'trashed': True}).execute()
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to trash {f['name']}: {e}")
            error_count += 1

    return success_count, error_count

def trash_duplicate_files(service, file_list: List[Dict[str, Any]]):
    """Move duplicate files to trash with detailed confirmation"""
    if not file_list:
        logger.info("重複PDFの削除対象はありません。")
        return 0, 0

    print(f"\n--- 重複PDF削除対象: {len(file_list)}件 ---")
    for f in file_list[:20]:  # Show more for duplicates
        print(f"  - {f['name']}")
        print(f"    Path:         {f.get('folder_path', 'N/A')}")
        print(f"    Duplicate Of: {f.get('duplicate_of', 'N/A')}")
    if len(file_list) > 20:
        print(f"  ...他 {len(file_list) - 20}件")

    confirm = input(f"\nこれらの重複PDFファイルをゴミ箱に移動しますか？ (y/N): ").lower()
    if confirm != 'y':
        print("削除をキャンセルしました。")
        return 0, 0

    success_count = 0
    error_count = 0

    for f in file_list:
        file_id = f.get('file_id')
        if not file_id:
            logger.warning(f"File ID missing for {f['name']}")
            error_count += 1
            continue
            
        try:
            service.files().update(fileId=file_id, body={'trashed': True}).execute()
            logger.info(f"TRASHED: {f['name']} ({f.get('folder_path')})")
            success_count += 1
        except Exception as e:
            logger.error(f"Failed to trash {f['name']}: {e}")
            error_count += 1

    return success_count, error_count

def move_unclassified_files(service, root_id: str):
    """Move unclassified files based on drive_move_list.json"""
    if not MOVE_LIST_FILE.exists():
        logger.error(f"Error: {MOVE_LIST_FILE.name} が見つかりません。")
        sys.exit(1)

    try:
        with open(MOVE_LIST_FILE, 'r', encoding='utf-8') as f:
            move_list = json.load(f)
    except Exception as e:
        logger.error(f"Failed to load {MOVE_LIST_FILE.name}: {e}")
        sys.exit(1)

    if not move_list:
        logger.info("移動対象のリストが空です。")
        return 0, 0, 0

    move_count = 0
    skip_count = 0
    error_count = 0

    # Cache for destination folder IDs
    dest_folder_cache = {}

    for item in move_list:
        file_id = item.get('file_id')
        name = item.get('name')
        dest_name = item.get('destination_folder')

        if dest_name == 'SKIP':
            logger.info(f"SKIP: {name}")
            skip_count += 1
            continue

        if not file_id or not dest_name:
            logger.warning(f"Invalid entry in move list: {item}")
            error_count += 1
            continue

        try:
            # 1. Get or create destination folder ID
            if dest_name not in dest_folder_cache:
                dest_id = create_folder(service, dest_name, root_id)
                dest_folder_cache[dest_name] = dest_id
            else:
                dest_id = dest_folder_cache[dest_name]

            # 2. Get current parents to remove
            file = service.files().get(fileId=file_id, fields='parents').execute()
            previous_parents = ",".join(file.get('parents', []))

            # 3. Move file
            service.files().update(
                fileId=file_id,
                addParents=dest_id,
                removeParents=previous_parents,
                fields='id, parents'
            ).execute()
            
            logger.info(f"MOVED: {name} -> {dest_name}")
            move_count += 1
        except Exception as e:
            logger.error(f"Failed to move {name}: {e}")
            error_count += 1

    return move_count, skip_count, error_count

def main():
    print("=== Drive クリーンアップ & 整理開始 ===")

    try:
        service = get_drive_service()
    except Exception as e:
        logger.error(f"Drive certification failed: {e}")
        sys.exit(1)

    root_folder_name = GOOGLE_DRIVE_FOLDER_NAME
    root_id = find_folder_by_name(root_folder_name)
    if not root_id:
        logger.error(f"Root folder '{root_folder_name}' not found.")
        sys.exit(1)

    # 1. Load Audit Report for Deletions
    if not REPORT_FILE.exists():
        logger.error(f"Audit report {REPORT_FILE.name} not found. Run drive_audit.py first.")
        # We continue to moving if move_list exists, or should we? 
        # Requirement T-6-C/D implies we should have it.
        report_data = None
    else:
        try:
            with open(REPORT_FILE, 'r', encoding='utf-8') as f:
                report_data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load audit report: {e}")
            report_data = None

    total_deleted = 0
    total_delete_errors = 0

    if report_data:
        files = report_data.get('files', {})
        
        # T-6-B: DELETE_NON_PDF
        del_non_pdf = files.get('DELETE_NON_PDF', [])
        s_del, e_del = trash_files(service, del_non_pdf, "非PDF")
        total_deleted += s_del
        total_delete_errors += e_del

        # T-6-C: DELETE_DUPLICATE
        del_dupe = files.get('DELETE_DUPLICATE', [])
        s_dupe, e_dupe = trash_duplicate_files(service, del_dupe)
        total_deleted += s_dupe
        total_delete_errors += e_dupe

    # 2. T-6-D: MOVE_UNCLASSIFIED
    print("\n--- 未分類ファイルの移動処理 ---")
    move_count, skip_count, move_error_count = move_unclassified_files(service, root_id)

    print("\n=== 実行結果サマリー ===")
    print(f"ゴミ箱に移動成功: {total_deleted}件")
    print(f"削除エラー:      {total_delete_errors}件")
    print(f"フォルダ移動成功: {move_count}件")
    print(f"スキップ:        {skip_count}件")
    print(f"移動エラー:      {move_error_count}件")

if __name__ == "__main__":
    main()
