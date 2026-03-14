import os
import sys
import logging
from pathlib import Path

# プロジェクトルートをパスに追加
sys.path.append(str(Path(__file__).parent.parent))

from config import COLLECTION_NAME, PARENT_CHUNKS_DIR
from dense_indexer import get_chroma_client

# ロギング設定
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

import chromadb.errors
import shutil

def reset_chromadb():
    client = get_chroma_client()
    
    try:
        # 1. ChromaDB コレクションの削除
        try:
            collection = client.get_collection(name=COLLECTION_NAME)
            count = collection.count()
            logger.info(f"ChromaDB 削除前チャンク数: {count}")
            
            client.delete_collection(name=COLLECTION_NAME)
            logger.info("ChromaDB コレクション削除完了")
            
        except (ValueError, chromadb.errors.NotFoundError):
            logger.info(f"ChromaDB コレクション '{COLLECTION_NAME}' は存在しません。")

        # 2. parent_chunks の削除
        if PARENT_CHUNKS_DIR.exists():
            logger.info(f"Parent chunks 削除開始: {PARENT_CHUNKS_DIR}")
            file_count = 0
            for item in PARENT_CHUNKS_DIR.glob('*'):
                if item.is_file():
                    item.unlink()
                    file_count += 1
                elif item.is_dir():
                    shutil.rmtree(item)
                    file_count += 1
            logger.info(f"Parent chunks 削除完了 ({file_count} 個のアイテムを削除)")
        else:
            logger.info(f"Parent chunks ディレクトリが存在しません: {PARENT_CHUNKS_DIR}")

    except Exception as e:
        logger.error(f"エラーが発生しました: {e}")
        return

    # 削除後の確認 (ChromaDB)
    try:
        client.get_collection(name=COLLECTION_NAME)
        logger.error("エラー: ChromaDB コレクションがまだ存在します")
    except (ValueError, chromadb.errors.NotFoundError):
        logger.info("ChromaDB コレクション不在を確認")




if __name__ == "__main__":
    reset_chromadb()
