#!/usr/bin/env python3
"""
OCR失敗ファイルを一括再処理するスクリプト
使い方: python retry_ocr_failed.py [--dry-run]
"""
import sys
import argparse
import logging
from pathlib import Path

# PYTHONPATHをarchitectural_ragに追加
SCRIPT_DIR = Path(__file__).parent.absolute()
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="実際には実行せず、対象ファイルを表示するのみ")
    args = parser.parse_args()

    # DB等のインポート
    try:
        from database import SessionLocal, Document
        from ocr_processor import process_pdf_background
    except ImportError as e:
        logger.error(f"Failed to import required modules: {e}")
        logger.error("Please run this script from inside the architectural_rag directory or ensure dependencies are installed.")
        sys.exit(1)

    db = SessionLocal()
    try:
        failed_docs = db.query(Document).filter(Document.status == "failed").all()
        logger.info(f"OCR失敗ファイル数: {len(failed_docs)}")

        for doc in failed_docs:
            pdf_path = Path(doc.file_path)
            if not pdf_path.exists():
                logger.warning(f"ファイルが存在しない: {pdf_path}")
                continue

            md_path = pdf_path.parent / (pdf_path.stem + ".md")
            
            logger.info(f"{'[DRY-RUN] ' if args.dry_run else ''}再OCR: {pdf_path.name}")

            if not args.dry_run:
                try:
                    process_pdf_background(str(pdf_path), str(md_path))
                    logger.info(f"  → 完了: {pdf_path.name}")
                except Exception as e:
                    logger.error(f"  → 失敗: {pdf_path.name}: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
