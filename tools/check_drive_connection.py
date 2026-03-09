import os
import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))

from drive_sync import get_drive_service, get_auth_status, find_folder_by_name
from config import GOOGLE_DRIVE_FOLDER_NAME

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_drive():
    print("=== Google Drive Connection Diagnostic ===")
    
    # 1. 認証状態の確認
    try:
        status = get_auth_status()
        print(f"Auth Status: {status.get('message', 'Unknown')}")
        if not status.get('authenticated'):
            print("ERROR: Not authenticated. Please run the OAuth flow via /api/drive/auth.")
            # サービスアカウントのチェック
            from config import GOOGLE_DRIVE_CREDENTIALS_JSON
            if GOOGLE_DRIVE_CREDENTIALS_JSON:
                print(f"Service Account Path: {GOOGLE_DRIVE_CREDENTIALS_JSON}")
                if os.path.exists(GOOGLE_DRIVE_CREDENTIALS_JSON):
                    print("Service Account JSON exists, attempting connection...")
                else:
                    print("Service Account JSON NOT FOUND at specified path.")
            return
    except Exception as e:
        print(f"ERROR during auth check: {e}")
        return

    # 2. サービス取得テスト
    try:
        service = get_drive_service()
        print("Drive Service: Initialized successfully.")
    except Exception as e:
        print(f"ERROR: Failed to initialize Drive service: {e}")
        return

    # 3. フォルダ検索テスト
    try:
        folder_name = GOOGLE_DRIVE_FOLDER_NAME
        print(f"Target Folder: {folder_name}")
        folder_id = find_folder_by_name(folder_name)
        if folder_id:
            print(f"Folder ID: {folder_id} (Found)")
        else:
            print(f"Folder ID: NOT FOUND. It will be created during the first upload.")
    except Exception as e:
        print(f"ERROR during folder lookup: {e}")

    print("=== Diagnostic Complete ===")

if __name__ == "__main__":
    check_drive()
