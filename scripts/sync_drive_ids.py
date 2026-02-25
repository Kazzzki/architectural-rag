#!/usr/bin/env python3
"""
scripts/sync_drive_ids.py
ローカル (data/pdfs) に存在する PDF ファイル名から、Google Drive 上の対応するファイルの drive_file_id を検索し、
SQLite の documents テーブルと ChromaDB の該当チャンクのメタデータに反映するスクリプト。
"""

import os
import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
BASE_DIR = Path(__file__).parent.parent
sys.path.append(str(BASE_DIR))

from drive_sync import get_drive_service
from database import get_session, Document as DbDocument
from indexer import get_chroma_client, COLLECTION_NAME

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(message)s")
logger = logging.getLogger(__name__)

def get_file_id_by_name(service, filename: str, folder_id: str = None) -> str:
    """Drive APIを用いてファイル名で検索し、ファイルIDを返す。serviceがNoneの場合はダミー値を返す。"""
    if service is None:
        import time
        import hashlib
        dummy_hash = hashlib.md5(f"{filename}_{time.time()}".encode()).hexdigest()
        return f"dummy_drive_id_{dummy_hash[:12]}"
        
    # 完全に一致するファイル名で検索（ゴミ箱以外）
    query = f"name = '{filename}' and trashed = false"
    if folder_id:
        query += f" and '{folder_id}' in parents"
        
    try:
        results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
        files = results.get('files', [])
        if files:
            return files[0]['id']
    except Exception as e:
        logger.error(f"Error searching for {filename}: {e}")
    return ""

def main():
    logger.info("Starting Drive ID sync...")
    
    try:
        service = get_drive_service()
        use_dummy = False
    except Exception as e:
        logger.warning(f"Failed to connect to Google Drive API: {e}. Falling back to DUMMY IDs.")
        use_dummy = True
        service = None
        
    session = get_session()
    
    try:
        chroma = get_chroma_client()
        collection = chroma.get_collection(name=COLLECTION_NAME)
    except ValueError as e:
        logger.warning(f"ChromaDB collection not found: {e}")
        collection = None

    # SQLiteからすべてのPDFドキュメントを取得
    docs = session.query(DbDocument).filter(DbDocument.file_type == 'pdf').all()
    logger.info(f"Found {len(docs)} PDF documents in SQLite.")
    
    updated_db_count = 0
    updated_chroma_count = 0
    
    for doc in docs:
        if not doc.drive_file_id:
            logger.info(f"Processing: {doc.filename}")
            drive_id = get_file_id_by_name(service, doc.filename)
            
            if drive_id:
                logger.info(f"  -> Found Drive ID: {drive_id}")
                doc.drive_file_id = drive_id
                session.commit()
                updated_db_count += 1
                
                # ChromaDB内の該当ドキュメントチャンクのメタデータを更新
                if collection and doc.source_pdf_hash:
                    results = collection.get(
                        where={"source_pdf_hash": doc.source_pdf_hash}
                    )
                    
                    if results and results['ids']:
                        ids = results['ids']
                        metadatas = results['metadatas']
                        
                        logger.info(f"  -> Updating {len(ids)} chunks in ChromaDB for {doc.filename}...")
                        
                        # それぞれのメタデータ辞書に drive_file_id を追加
                        updated_metadatas = []
                        for m in metadatas:
                            new_m = m.copy()
                            new_m["drive_file_id"] = drive_id
                            updated_metadatas.append(new_m)
                            
                        # 一括アップデート
                        collection.update(
                            ids=ids,
                            metadatas=updated_metadatas
                        )
                        updated_chroma_count += len(ids)
            else:
                logger.warning(f"  -> Drive ID NOT found for {doc.filename}")
                
    session.close()
    
    logger.info("=== Sync Completed ===")
    logger.info(f"Updated SQLite Records: {updated_db_count}")
    logger.info(f"Updated ChromaDB Chunks: {updated_chroma_count}")

if __name__ == "__main__":
    main()
