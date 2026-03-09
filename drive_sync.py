# drive_sync.py - Google Drive API連携（整理版）

import os
import io
import json
import pickle
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import sys

# Python 3.9互換性パッチ
if sys.version_info < (3, 10):
    try:
        import importlib_metadata
        import importlib.metadata
        importlib.metadata.packages_distributions = importlib_metadata.packages_distributions
    except ImportError:
        pass

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow, Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaFileUpload

from config import (
    KNOWLEDGE_BASE_DIR, 
    SUPPORTED_EXTENSIONS, 
    BASE_DIR,
    GOOGLE_DRIVE_FOLDER_NAME,
    GOOGLE_DRIVE_FOLDER_ID,
    GOOGLE_DRIVE_CREDENTIALS_JSON
)

logger = logging.getLogger(__name__)

# ========== 定数 ==========

SCOPES = ['https://www.googleapis.com/auth/drive']
SECRETS_DIR = BASE_DIR / "data" / "secrets"
SECRETS_DIR.mkdir(parents=True, exist_ok=True)
CREDENTIALS_PATH = SECRETS_DIR / 'credentials.json'
TOKEN_PATH = SECRETS_DIR / 'token.pickle'
# NOTE: REDIRECT_URI は server.py 側で動的に構築して渡す（ハードコード廃止）


# ========== 認証 ==========

from google_auth_oauthlib.flow import Flow

def get_auth_url(redirect_uri: str) -> str:
    """認証用URLを生成（redirect_uri は呼び出し元が動的に構築する）"""
    if not CREDENTIALS_PATH.exists():
        raise FileNotFoundError(
            f"credentials.json が見つかりません。\n"
            f"Google Cloud Console から OAuth 2.0 クライアントIDをダウンロードし、\n"
            f"{CREDENTIALS_PATH} に配置してください。"
        )
    
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri
    )
    auth_url, state = flow.authorization_url(
        prompt='consent', 
        access_type='offline',
        include_granted_scopes='true'
    )
    
    # PKCE の code_verifier と state をファイルに一時保存
    with open(SECRETS_DIR / 'oauth_state.json', 'w') as f:
        json.dump({
            'state': state,
            'code_verifier': flow.code_verifier
        }, f)
        
    return auth_url


def save_credentials_from_code(code: str, redirect_uri: str, state: str = None):
    """認可コードからトークンを取得して保存（redirect_uri は呼び出し元が動的に構築する）"""
    flow = Flow.from_client_secrets_file(
        str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri
    )
    
    state_file = SECRETS_DIR / 'oauth_state.json'
    if state_file.exists():
        with open(state_file, 'r') as f:
            data = json.load(f)
            flow.code_verifier = data.get('code_verifier')
            if not state:
                state = data.get('state')
                
    # fetch_token exchanges the code for tokens and uses the code_verifier
    flow.fetch_token(code=code)
    creds = flow.credentials
    
    with open(TOKEN_PATH, 'wb') as token:
        pickle.dump(creds, token)
        
    if state_file.exists():
        state_file.unlink() # Cleanup
    
    logger.info("Google Drive credentials saved successfully")
    return creds


def get_drive_service():
    """Google Drive APIサービスを取得（Service Account または OAuth認証）"""
    creds = None
    
    # 1. サービスアカウント優先 (GOOGLE_DRIVE_CREDENTIALS_JSON があれば)
    if GOOGLE_DRIVE_CREDENTIALS_JSON and os.path.exists(GOOGLE_DRIVE_CREDENTIALS_JSON):
        try:
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_DRIVE_CREDENTIALS_JSON, scopes=SCOPES
            )
            logger.info("Using Google Drive Service Account credentials")
            return build('drive', 'v3', credentials=creds)
        except Exception as e:
            logger.warning(f"Failed to load service account: {e}")

    # 2. OAuth 2.0 (token.pickle)
    if TOKEN_PATH.exists():
        with open(TOKEN_PATH, 'rb') as token:
            creds = pickle.load(token)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                # リフレッシュ成功したら保存
                with open(TOKEN_PATH, 'wb') as token:
                    pickle.dump(creds, token)
                logger.info("Google Drive token refreshed successfully")
            except Exception as e:
                logger.error(f"Token refresh failed: {e}", exc_info=True)
                # 壊れたトークンを削除して次回の再認証フローを有効にする
                try:
                    TOKEN_PATH.unlink(missing_ok=True)
                    logger.info("Corrupted token.pickle deleted. Re-authentication required.")
                except Exception as del_e:
                    logger.warning(f"Failed to delete token.pickle: {del_e}")
                raise Exception("トークンの更新に失敗しました。再認証が必要です。/api/drive/auth で認証してください。")
        else:
            raise Exception("認証が必要です。/api/drive/auth で認証してください。")
            
    return build('drive', 'v3', credentials=creds)


def get_auth_status() -> Dict[str, Any]:
    """認証状態を確認（トークンリフレッシュも試みる）"""
    try:
        if not CREDENTIALS_PATH.exists():
            return {
                'authenticated': False,
                'message': 'credentials.json が見つかりません',
            }
        
        if TOKEN_PATH.exists():
            with open(TOKEN_PATH, 'rb') as token:
                creds = pickle.load(token)
                
                def _calc_expires_hours(c):
                    """残り有効時間（時間）を計算。取得不可の場合はNone。"""
                    try:
                        if c.expiry:
                            from datetime import timezone
                            delta = c.expiry.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
                            return max(0.0, round(delta.total_seconds() / 3600, 1))
                    except Exception:
                        pass
                    return None

                # 有効なトークン
                if creds and creds.valid:
                    return {
                        'authenticated': True,
                        'message': '認証済み',
                        'expires_in_hours': _calc_expires_hours(creds),
                    }
                
                # 期限切れだがリフレッシュ可能
                if creds and creds.expired and creds.refresh_token:
                    try:
                        creds.refresh(Request())
                        with open(TOKEN_PATH, 'wb') as t:
                            pickle.dump(creds, t)
                        return {
                            'authenticated': True,
                            'message': '認証済み（トークン更新済み）',
                            'expires_in_hours': _calc_expires_hours(creds),
                        }
                    except Exception as e:
                        logger.warning(f"Token refresh failed in status check: {e}")
                        # 壊れたトークンを削除して再認証を促す
                        try:
                            TOKEN_PATH.unlink(missing_ok=True)
                            logger.info("Corrupted token.pickle deleted during status check.")
                        except Exception:
                            pass
                        return {
                            'authenticated': False,
                            'message': 'トークンの更新に失敗。再認証が必要です',
                            'expires_in_hours': None,
                        }
        
        return {
            'authenticated': False,
            'message': '認証が必要です',
        }
    except Exception as e:
        return {
            'authenticated': False,
            'message': f'エラー: {str(e)}',
        }


# ========== フォルダ操作 ==========

def create_folder(service, folder_name: str, parent_id: str = None) -> str:
    """Google Driveにフォルダを作成（既存ならIDを返す）"""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
        
    results = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
    }
    if parent_id:
        file_metadata['parents'] = [parent_id]
        
    file = service.files().create(body=file_metadata, fields='id').execute()
    return file.get('id')


def list_drive_folders(service, parent_id: str = 'root') -> List[Dict[str, Any]]:
    """指定フォルダ内のフォルダ一覧を取得"""
    query = f"'{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name, modifiedTime)',
        orderBy='name'
    ).execute()
    
    return results.get('files', [])


def find_folder_by_name(folder_name: str) -> Optional[str]:
    """フォルダ名または config の設定からフォルダIDを取得"""
    if GOOGLE_DRIVE_FOLDER_ID:
        return GOOGLE_DRIVE_FOLDER_ID
    
    service = get_drive_service()
    
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name)'
    ).execute()
    
    files = results.get('files', [])
    if files:
        return files[0]['id']
    return None


# ========== ファイル操作 ==========

def list_drive_files(
    service,
    folder_id: str,
    extensions: List[str] = None
) -> List[Dict[str, Any]]:
    """指定フォルダ内のファイル一覧を取得（再帰的）"""
    if extensions is None:
        extensions = SUPPORTED_EXTENSIONS
    
    all_files = []
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(
        q=query,
        spaces='drive',
        fields='files(id, name, mimeType, modifiedTime, size, webViewLink)',
        pageSize=1000
    ).execute()
    
    for file in results.get('files', []):
        if file['mimeType'] == 'application/vnd.google-apps.folder':
            sub_files = list_drive_files(service, file['id'], extensions)
            for sf in sub_files:
                sf['folder_path'] = f"{file['name']}/{sf.get('folder_path', '')}"
            all_files.extend(sub_files)
        else:
            ext = Path(file['name']).suffix.lower()
            if ext in extensions:
                file['folder_path'] = ''
                all_files.append(file)
    
    return all_files


def download_file(service, file_id: str, file_name: str) -> bytes:
    """Google Driveからファイルをダウンロード"""
    request = service.files().get_media(fileId=file_id)
    file_buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(file_buffer, request)
    
    done = False
    while not done:
        status, done = downloader.next_chunk()
    
    return file_buffer.getvalue()


# ========== 同期 ==========

def upload_recursive(service, local_path: Path, parent_id: str = None, stats: Dict = None):
    """ディレクトリを再帰的にアップロード"""
    if stats is None:
        stats = {'created': 0, 'updated': 0, 'errors': 0}

    if local_path.is_file():
        query = f"name = '{local_path.name}' and trashed = false"
        if parent_id:
            query += f" and '{parent_id}' in parents"
            
        try:
            # fetch id and modifiedTime
            results = service.files().list(q=query, fields='files(id, modifiedTime)').execute()
            files = results.get('files', [])
            
            # stats needs 'skipped' key initialization
            if 'skipped' not in stats:
                stats['skipped'] = 0
            
            file_metadata = {'name': local_path.name}
            if parent_id:
                file_metadata['parents'] = [parent_id]
                
            media = MediaFileUpload(str(local_path), resumable=True)
            
            if files:
                drive_file = files[0]
                local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime)
                try:
                    drive_mtime = datetime.fromisoformat(
                        drive_file['modifiedTime'].replace('Z', '+00:00')
                    ).replace(tzinfo=None)
                    
                    if local_mtime <= drive_mtime:
                        logger.info(f"  スキップ(変更なし): {local_path.name}")
                        stats['skipped'] += 1
                        return
                except (KeyError, ValueError):
                    pass # modifiedTime parsing failed, proceed with update
                
                logger.info(f"  更新: {local_path.name}")
                result = service.files().update(
                    fileId=drive_file['id'],
                    media_body=media
                ).execute()
                stats['updated'] += 1
                # file_store統合: Drive IDを記録
                _update_file_store_drive_id(local_path, files[0]['id'])
            else:
                logger.info(f"  アップロード: {local_path.name}")
                result = service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
                stats['created'] += 1
                _update_file_store_drive_id(local_path, result.get('id'))
        except Exception as e:
            logger.error(f"Upload error ({local_path.name}): {e}", exc_info=True)
            stats['errors'] += 1
            
    elif local_path.is_dir():
        if local_path.name.startswith('.') or local_path.name == '__pycache__':
            return
            
        try:
            folder_id = create_folder(service, local_path.name, parent_id)
            for child in local_path.iterdir():
                upload_recursive(service, child, folder_id, stats)
        except Exception as e:
            logger.error(f"Folder process error ({local_path.name}): {e}", exc_info=True)
            stats['errors'] += 1


def upload_rag_pdf_to_drive(local_path: str, source_pdf_hash: str, target_folder_name: str = GOOGLE_DRIVE_FOLDER_NAME, subfolder_name: str = "pdfs") -> Optional[str]:
    """
    RAGパイプライン用の、ハッシュ値をキーとしたべき等なアップロード。
    Driveの 'appProperties' に source_pdf_hash を記録し、重複アップロードを防止する。
    """
    service = get_drive_service()
    try:
        local_p = Path(local_path)
        if not local_p.exists() or not local_p.is_file():
            logger.error(f"Upload source not found: {local_path}")
            return None

        root_id = create_folder(service, target_folder_name)
        folder_id = create_folder(service, subfolder_name, root_id) if subfolder_name else root_id
            
        # 1. すでに同じハッシュのファイルがあるか appProperties で検索
        # ※ appProperties はインデックスされるため高速
        query = f"appProperties has {{ key='source_pdf_hash' and value='{source_pdf_hash}' }} and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields='files(id, name)').execute()
        files = results.get('files', [])
        
        media = MediaFileUpload(str(local_p), resumable=True)
        
        if files:
            drive_file_id = files[0]['id']
            logger.info(f"Drive RAG upload: Found existing file for hash {source_pdf_hash[:8]} (ID: {drive_file_id}). Skipping/Updating metadata.")
            # 名前が違う場合は更新しておく（管理用）
            if files[0]['name'] != local_p.name:
                service.files().update(fileId=drive_file_id, body={'name': local_p.name}).execute()
            return drive_file_id
        else:
            # 2. 新規アップロード
            logger.info(f"Drive RAG upload: Creating new file for hash {source_pdf_hash[:8]} ({local_p.name})")
            file_metadata = {
                'name': local_p.name, 
                'parents': [folder_id],
                'appProperties': {
                    'source_pdf_hash': source_pdf_hash
                }
            }
            result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            return result.get('id')
            
    except Exception as e:
        logger.error(f"RAG upload error (hash={source_pdf_hash}): {e}", exc_info=True)
        return None


def upload_single_file_to_drive(local_path: str, target_folder_name: str = GOOGLE_DRIVE_FOLDER_NAME, subfolder_name: str = "pdfs") -> Optional[str]:
    """1つのファイルを指定したDriveフォルダにアップロードまたは更新し、ファイルIDを返す"""
    service = get_drive_service()
    try:
        root_id = create_folder(service, target_folder_name)
        if subfolder_name:
            folder_id = create_folder(service, subfolder_name, root_id)
        else:
            folder_id = root_id
            
        local_p = Path(local_path)
        if not local_p.exists() or not local_p.is_file():
            return None
            
        query = f"name = '{local_p.name}' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields='files(id)').execute()
        files = results.get('files', [])
        
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(str(local_p), resumable=True)
        
        if files:
            logger.info(f"Drive single upload: Updating {local_p.name}")
            result = service.files().update(
                fileId=files[0]['id'],
                media_body=media
            ).execute()
            return files[0]['id']
        else:
            logger.info(f"Drive single upload: Creating {local_p.name}")
            file_metadata = {'name': local_p.name, 'parents': [folder_id]}
            result = service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id'
            ).execute()
            return result.get('id')
    except Exception as e:
        logger.error(f"Single upload error ({local_path}): {e}", exc_info=True)
        return None



def _update_file_store_drive_id(local_path: Path, drive_id: str):
    """file_storeにDrive IDを記録（可能な場合）"""
    try:
        import file_store
        import hashlib
        # ファイルのチェックサムでfile_store内を検索
        with open(local_path, 'rb') as f:
            content = f.read()
        checksum = hashlib.sha256(content).hexdigest()
        file_info = file_store.get_file_by_checksum(checksum)
        if file_info:
            file_store.update_drive_sync(file_info['id'], drive_id)
            logger.info(f"Drive sync recorded for {file_info['id']}")
    except Exception as e:
        # file_storeが無くても動く
        logger.debug(f"file_store integration skipped: {e}")


def sync_upload_to_drive(target_folder_name: str = GOOGLE_DRIVE_FOLDER_NAME):
    """ローカルのナレッジベースをGoogle Driveに同期（アップロード）"""
    service = get_drive_service()
    logger.info(f"同期（アップロード）開始: {target_folder_name}")
    
    stats = {'created': 0, 'updated': 0, 'errors': 0}
    
    try:
        root_id = create_folder(service, target_folder_name)
        base_dir = Path(KNOWLEDGE_BASE_DIR)
        if not base_dir.exists():
            return {"status": "error", "message": "Local directory not found"}
            
        for child in base_dir.iterdir():
            upload_recursive(service, child, root_id, stats)
            
        logger.info(f"同期完了: {stats}")
        return {"status": "success", "folder": target_folder_name, "stats": stats}
        
    except Exception as e:
        logger.error(f"sync_upload_to_drive failed: {e}", exc_info=True)
        return {"status": "error", "message": str(e), "stats": stats}


def backup_to_drive(target_folder_name: str = "Architectural_RAG_Backup"):
    """互換性のためのエイリアス"""
    return sync_upload_to_drive(target_folder_name)


def sync_drive_folder(
    folder_id: str,
    folder_name: str = None
) -> Dict[str, int]:
    """Google Driveフォルダをローカルに同期"""
    service = get_drive_service()
    
    stats = {
        'total': 0,
        'downloaded': 0,
        'skipped': 0,
        'errors': 0,
    }
    
    if folder_name is None:
        folder_info = service.files().get(fileId=folder_id, fields='name').execute()
        folder_name = folder_info['name']
    
    logger.info(f"Google Drive フォルダを同期中: {folder_name}")
    
    files = list_drive_files(service, folder_id)
    stats['total'] = len(files)
    
    for file in files:
        try:
            folder_path = file.get('folder_path', '').strip('/')
            if folder_path:
                local_dir = Path(KNOWLEDGE_BASE_DIR) / folder_path
            else:
                local_dir = Path(KNOWLEDGE_BASE_DIR)
            
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / file['name']
            
            if local_path.exists():
                local_mtime = datetime.fromtimestamp(local_path.stat().st_mtime)
                drive_mtime = datetime.fromisoformat(
                    file['modifiedTime'].replace('Z', '+00:00')
                ).replace(tzinfo=None)
                
                if local_mtime >= drive_mtime:
                    stats['skipped'] += 1
                    continue
            
            logger.info(f"  ダウンロード: {file['name']}")
            content = download_file(service, file['id'], file['name'])
            
            with open(local_path, 'wb') as f:
                f.write(content)
            
            stats['downloaded'] += 1
            
        except Exception as e:
            logger.error(f"  エラー ({file['name']}): {e}", exc_info=True)
            stats['errors'] += 1
    
    logger.info(f"同期完了: {stats['downloaded']}ダウンロード, {stats['skipped']}スキップ, {stats['errors']}エラー")
    return stats


def upload_mirror_to_drive(local_dir: str, drive_folder_id: str):
    """Local -> Drive のミラーリングアップロード"""
    service = get_drive_service()
    local_path = Path(local_dir)
    
    if not local_path.exists():
        return {"success": False, "error": f"Local directory {local_dir} does not exist"}

    results = service.files().list(
        q=f"'{drive_folder_id}' in parents and trashed = false",
        fields="nextPageToken, files(id, name)").execute()
    drive_files = {f['name']: f['id'] for f in results.get('files', [])}
    
    uploaded_count = 0
    errors = []

    for file_path in local_path.rglob('*'):
        if file_path.is_file() and file_path.name not in ['.DS_Store', 'Thumbs.db']:
            if file_path.name not in drive_files:
                try:
                    file_metadata = {'name': file_path.name, 'parents': [drive_folder_id]}
                    media = MediaFileUpload(str(file_path), resumable=True)
                    result = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
                    uploaded_count += 1
                    _update_file_store_drive_id(file_path, result.get('id'))
                    logger.info(f"Uploaded: {file_path.name}")
                except Exception as e:
                    errors.append(f"{file_path.name}: {str(e)}")
                    logger.error(f"Failed to upload {file_path.name}: {e}", exc_info=True)
                
    return {
        "success": True,
        "uploaded_count": uploaded_count,
        "errors": errors,
        "message": f"Uploaded {uploaded_count} files."
    }


if __name__ == "__main__":
    status = get_auth_status()
    print(f"認証状態: {status}")
    
    if status['authenticated']:
        folder_id = find_folder_by_name("建築意匠ナレッジDB")
        if folder_id:
            sync_drive_folder(folder_id)
        else:
            print("フォルダが見つかりません")
