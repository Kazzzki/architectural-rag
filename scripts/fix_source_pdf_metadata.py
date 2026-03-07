#!/usr/bin/env python3
"""
fix_source_pdf_metadata.py
ChromaDB の architectural_knowledge コレクションで source_pdf が欠損しているチャンクを
rel_path から推論して補完するバッチスクリプト。

使用方法:
  python scripts/fix_source_pdf_metadata.py --dry-run   # 変更プレビュー（デフォルト）
  python scripts/fix_source_pdf_metadata.py             # 実際に更新
"""

import argparse
import logging
import sys
import os
from pathlib import Path

# プロジェクトルートを sys.path に追加
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

PDF_DIR = PROJECT_ROOT / "data" / "pdfs"
BATCH_SIZE = 100


def _find_pdf_for_md(rel_path: str) -> str:
    """
    rel_path が .md の場合、data/pdfs/ 配下でファイル名（拡張子除く）が
    一致する PDF を検索して返す。見つからない場合は空文字を返す。
    """
    stem = Path(rel_path).stem  # 拡張子を除いたファイル名
    if not PDF_DIR.exists():
        return ""
    for pdf_file in PDF_DIR.rglob("*.pdf"):
        if pdf_file.stem == stem:
            # PDF_DIR からの相対パスで返す
            try:
                return str(pdf_file.relative_to(PROJECT_ROOT))
            except ValueError:
                return str(pdf_file)
    return ""


def infer_source_pdf(rel_path: str) -> str:
    """
    rel_path から source_pdf を推論する。
    - .pdf → rel_path をそのまま使用
    - .md  → data/pdfs/ 配下でファイル名マッチ、なければ rel_path
    - その他 → rel_path をそのまま
    """
    if not rel_path:
        return ""
    lower = rel_path.lower()
    if lower.endswith(".pdf"):
        return rel_path
    elif lower.endswith(".md"):
        pdf_path = _find_pdf_for_md(rel_path)
        return pdf_path if pdf_path else rel_path
    else:
        return rel_path


def main():
    parser = argparse.ArgumentParser(
        description="ChromaDB の source_pdf 欠損メタデータを補完する"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="変更のプレビューのみ行い実際には更新しない（デフォルト: True）"
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_false",
        dest="dry_run",
        help="実際にChromaDBに書き込む"
    )
    args = parser.parse_args()
    dry_run = args.dry_run

    if dry_run:
        logger.info("=== DRY-RUN モード（実際の更新は行いません）===")
    else:
        logger.info("=== 実行モード（ChromaDBを更新します）===")

    # ChromaDB コレクション取得
    try:
        from indexer import get_chroma_client, GeminiEmbeddingFunction
        from config import COLLECTION_NAME
    except ImportError as e:
        logger.error(f"モジュールのインポートに失敗しました: {e}")
        sys.exit(1)

    client = get_chroma_client()
    embedding_function = GeminiEmbeddingFunction()
    try:
        collection = client.get_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_function,
        )
    except Exception as e:
        logger.error(f"コレクション取得に失敗しました: {e}")
        sys.exit(1)

    total_count = collection.count()
    logger.info(f"コレクション総チャンク数: {total_count}")

    # A-1-2: 全件取得（メタデータのみ）
    logger.info("全メタデータを取得中...")
    all_data = collection.get(include=["metadatas"])
    ids = all_data["ids"]
    metadatas = all_data["metadatas"]

    # A-1-2: source_pdf 欠損チャンクを検出
    missing = []
    skip_count = 0
    for chunk_id, meta in zip(ids, metadatas):
        meta = meta or {}
        source_pdf = meta.get("source_pdf", "")
        rel_path = meta.get("rel_path", "")

        if not source_pdf:  # None または空文字
            if not rel_path:
                skip_count += 1
                continue
            missing.append((chunk_id, meta, rel_path))

    logger.info(f"source_pdf 欠損チャンク: {len(missing)}件")
    if skip_count > 0:
        logger.info(f"rel_path も欠損のためスキップ: {skip_count}件")

    if not missing:
        logger.info("補完が必要なチャンクはありません。終了します。")
        return

    # A-1-3: 推論ロジックを適用して (chunk_id, new_meta) のペアを生成
    updates = []
    for chunk_id, meta, rel_path in missing:
        inferred = infer_source_pdf(rel_path)
        if inferred:
            new_meta = dict(meta)
            new_meta["source_pdf"] = inferred
            updates.append((chunk_id, new_meta))

    logger.info(f"補完可能なチャンク: {len(updates)}件")

    # A-1-4: dry-run の場合は代表5件を表示して終了
    if dry_run:
        logger.info("\n--- DRY-RUN 変更プレビュー ---")
        preview = updates[:5]
        for i, (chunk_id, new_meta) in enumerate(preview, 1):
            original = next(
                (m for cid, m, _ in missing if cid == chunk_id), {}
            )
            logger.info(
                f"[{i}] ID: {chunk_id[:40]}…\n"
                f"    rel_path:   {new_meta.get('rel_path', '')}\n"
                f"    source_pdf: '' → '{new_meta['source_pdf']}'"
            )
        if len(updates) > 5:
            logger.info(f"... 他 {len(updates) - 5} 件")
        logger.info(f"\n変更予定件数: {len(updates)}件")
        logger.info("実際に更新するには --no-dry-run オプションを指定してください。")
        return

    # A-1-5: 実行モード — 100件バッチで更新
    logger.info(f"ChromaDB メタデータを更新します（{len(updates)}件）...")
    updated_count = 0
    for batch_start in range(0, len(updates), BATCH_SIZE):
        batch = updates[batch_start: batch_start + BATCH_SIZE]
        batch_ids = [item[0] for item in batch]
        batch_metas = [item[1] for item in batch]
        try:
            collection.update(ids=batch_ids, metadatas=batch_metas)
            updated_count += len(batch)
            logger.info(
                f"バッチ更新完了: {batch_start + 1}〜{batch_start + len(batch)}件目"
            )
        except Exception as e:
            logger.error(f"バッチ更新エラー (offset={batch_start}): {e}")

    logger.info(f"更新完了: {updated_count}件")

    # A-1-6: 実行後検証
    logger.info("実行後の欠損チャンク数を再確認中...")
    all_data_after = collection.get(include=["metadatas"])
    after_missing = sum(
        1 for meta in all_data_after["metadatas"]
        if not (meta or {}).get("source_pdf", "")
            and (meta or {}).get("rel_path", "")
    )
    logger.info(f"補完後の欠損件数: {after_missing}件")
    if after_missing == 0:
        logger.info("✅ source_pdf の欠損がすべて解消されました。")
    else:
        logger.warning(f"⚠️ {after_missing}件の欠損が残っています（rel_path からの推論が困難なケース）。")


if __name__ == "__main__":
    main()
