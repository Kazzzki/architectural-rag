import os
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any, Optional

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from drive_sync import get_drive_service, find_folder_by_name
from config import GOOGLE_DRIVE_FOLDER_NAME

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

REPORT_FILE = Path(__file__).parent / "drive_audit_report.json"

# Special Folders
DELETE_FOLDERS = ["20_検索MD", "90_処理用データ", "99_システム"]
LEGACY_PDF_FOLDER = "10_参照PDF"
UNCLASSIFIED_FOLDERS = ["uploads", ""]  # "" means root

# New System Folders (examples from requirements plus others that look like categories)
# Actually, anything NOT in DELETE_FOLDERS, LEGACY_PDF_FOLDER, UNCLASSIFIED_FOLDERS and is a category folder
# We'll detect them dynamically: any folder that isn't one of the above.

def list_all_files_recursive(service, folder_id: str, current_path: str = "") -> List[Dict[str, Any]]:
    """Recursive scan of all files in Drive folder"""
    all_files = []
    page_token = None
    
    query = f"'{folder_id}' in parents and trashed = false"
    
    while True:
        results = service.files().list(
            q=query,
            spaces='drive',
            fields='nextPageToken, files(id, name, mimeType, modifiedTime, size)',
            pageSize=1000,
            pageToken=page_token
        ).execute()
        
        items = results.get('files', [])
        for item in items:
            item['folder_path'] = current_path
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                # Recurse into subfolder
                subfolder_path = f"{current_path}/{item['name']}".strip("/")
                all_files.extend(list_all_files_recursive(service, item['id'], subfolder_path))
            else:
                # It's a file
                all_files.append(item)
        
        page_token = results.get('nextPageToken')
        if not page_token:
            break
            
    return all_files

def classify_files(files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Classify files according to requirements"""
    
    # Pre-index for duplicate check (name -> list of paths)
    pdf_map = {} # name -> [folder_path]
    for f in files:
        if f['name'].lower().endswith('.pdf'):
            name = f['name']
            if name not in pdf_map:
                pdf_map[name] = []
            pdf_map[name].append(f['folder_path'])

    results = {
        "DELETE_NON_PDF": [],
        "DELETE_DUPLICATE": [],
        "MOVE_UNCLASSIFIED": [],
        "KEEP": []
    }
    
    for f in files:
        name = f['name']
        folder_path = f['folder_path']
        ext = Path(name).suffix.lower()
        size = int(f.get('size', 0))
        file_id = f['id']
        
        # 1. DELETE_NON_PDF check
        # Non-PDF or system folders
        in_delete_folder = any(folder_path.startswith(df) for df in DELETE_FOLDERS)
        is_non_pdf_ext = ext in ['.md', '.json', '.txt', '.pickle', '.py']
        if is_non_pdf_ext or in_delete_folder:
            results["DELETE_NON_PDF"].append({
                "file_id": file_id,
                "name": name,
                "folder_path": folder_path,
                "size": size
            })
            continue
            
        # From here, we only care about PDFs that aren't in DELETE_FOLDERS
        if ext == '.pdf':
            # 2. DELETE_DUPLICATE check
            # PDF in 10_参照PDF/ and same name exists in "new system" folders
            if folder_path.startswith(LEGACY_PDF_FOLDER):
                # Look for duplicates in other folders (not root, not uploads, not legacy)
                duplicates = [p for p in pdf_map.get(name, []) 
                             if p != folder_path 
                             and not p.startswith(LEGACY_PDF_FOLDER)
                             and p not in UNCLASSIFIED_FOLDERS]
                
                if duplicates:
                    results["DELETE_DUPLICATE"].append({
                        "file_id": file_id,
                        "name": name,
                        "folder_path": folder_path,
                        "size": size,
                        "duplicate_of": duplicates[0] # Just report the first one found
                    })
                    continue
            
            # 3. MOVE_UNCLASSIFIED check
            # PDF in uploads/ or root
            if folder_path in UNCLASSIFIED_FOLDERS:
                results["MOVE_UNCLASSIFIED"].append({
                    "file_id": file_id,
                    "name": name,
                    "folder_path": folder_path,
                    "size": size
                })
                continue
                
            # 4. KEEP
            # Valid PDFs in category folders
            results["KEEP"].append({
                "file_id": file_id,
                "name": name,
                "folder_path": folder_path,
                "size": size
            })
            
    return results

def main():
    print("=== Drive棚卸しレポート開始 ===")
    
    try:
        service = get_drive_service()
    except Exception as e:
        logger.error(f"Drive certification failed: {e}")
        sys.exit(1)
        
    root_folder_name = GOOGLE_DRIVE_FOLDER_NAME # "建築意匠ナレッジDB"
    root_id = find_folder_by_name(root_folder_name)
    
    if not root_id:
        logger.error(f"Root folder '{root_folder_name}' not found.")
        sys.exit(1)
        
    print(f"スキャン対象: {root_folder_name} (ID: {root_id})")
    
    files = list_all_files_recursive(service, root_id)
    print(f"取得ファイル数: {len(files)}件")
    
    classified = classify_files(files)
    
    # Prepare summary
    summary = {
        "total": len(files),
        "DELETE_NON_PDF": len(classified["DELETE_NON_PDF"]),
        "DELETE_DUPLICATE": len(classified["DELETE_DUPLICATE"]),
        "MOVE_UNCLASSIFIED": len(classified["MOVE_UNCLASSIFIED"]),
        "KEEP": len(classified["KEEP"])
    }
    
    report_data = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summary,
        "files": classified
    }
    
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        json.dump(report_data, f, ensure_ascii=False, indent=2)
        
    # Helper to format size in MB
    def to_mb(byte_list):
        total_bytes = sum(f['size'] for f in byte_list)
        return total_bytes / (1024 * 1024)

    print("\n=== Drive棚卸しレポート ===")
    print(f"合計ファイル数:        {summary['total']}件")
    print(f"削除対象（非PDF）:      {summary['DELETE_NON_PDF']}件  {to_mb(classified['DELETE_NON_PDF']):.1f} MB")
    print(f"削除対象（重複PDF）:    {summary['DELETE_DUPLICATE']}件  {to_mb(classified['DELETE_DUPLICATE']):.1f} MB")
    print(f"移動対象（未分類PDF）:  {summary['MOVE_UNCLASSIFIED']}件  {to_mb(classified['MOVE_UNCLASSIFIED']):.1f} MB")
    print(f"保持:                 {summary['KEEP']}件")
    print(f"レポート出力先: {REPORT_FILE}")

if __name__ == "__main__":
    main()
