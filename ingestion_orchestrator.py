import logging
import threading
from pathlib import Path
from typing import Dict, Any

from ocr_processor import process_pdf_background
from metadata_enricher import MetadataEnricher
# from chunk_builder import build_3tier_chunks
from indexer import index_file
from visual_indexer import index_visual_file
from audio_indexer import index_audio_file
from video_indexer import index_video_file
from mixed_indexer import index_mixed_file

logger = logging.getLogger(__name__)

class IngestionOrchestrator:
    """
    Phase 3: ファイルの処理パイプラインの進行を管理するオーケストレーター
    """
    def __init__(self):
        from metadata_repository import MetadataRepository
        self.repo = MetadataRepository()
        self.enricher = MetadataEnricher()

    def enqueue_job(self, version_id: str, file_path: str, source_pdf_hash: str, source_kind: str, doc_type: str = "catalog"):
        """
        ファイルアップロード直後に呼び出されるエントリーポイント
        """
        # version_id が渡されていない場合は新規作成を試みる（外部呼び出し用）
        if not version_id:
            res = self.repo.create_document_version(
                filename=Path(file_path).name,
                file_path=file_path,
                source_pdf_hash=source_pdf_hash,
                source_kind=source_kind
            )
            if res.get("skipped"):
                logger.info(f"[Orchestrator] Job already in progress for {file_path}. Skipping enqueue.")
                return
            version_id = res["version_id"]

        logger.info(f"[Orchestrator] Enqueuing job for version_id={version_id}")
        self.repo.update_ingest_stage_by_version_id(version_id, "processing")
        self.repo.update_ingest_stage(file_path, "processing")

        # モダリティに応じたパイプラインへルーティング
        if source_kind == "audio":
            threading.Thread(
                target=self._run_audio_stage,
                args=(version_id, file_path, source_pdf_hash),
                daemon=True,
            ).start()
        elif source_kind == "video":
            threading.Thread(
                target=self._run_video_stage,
                args=(version_id, file_path, source_pdf_hash),
                daemon=True,
            ).start()
        elif doc_type == "drawing":
            threading.Thread(
                target=self._run_visual_stage,
                args=(version_id, file_path, source_pdf_hash),
                daemon=True,
            ).start()
        elif doc_type == "mixed":
            threading.Thread(
                target=self._run_mixed_stage,
                args=(version_id, file_path, source_pdf_hash),
                daemon=True,
            ).start()
        else:
            # 既存テキストパイプライン（Document）
            threading.Thread(
                target=self._run_ocr_stage,
                args=(version_id, file_path, source_pdf_hash, source_kind, doc_type),
                daemon=True,
            ).start()

    def _run_visual_stage(self, version_id: str, file_path: str, source_pdf_hash: str):
        """Drawing ファイルをビジュアルベクトルとしてインデックスする。"""
        try:
            original_filename = Path(file_path).name
            count = index_visual_file(file_path, source_pdf_hash, version_id, original_filename)
            logger.info(f"[Orchestrator] Visual indexing completed: {count} vectors for {version_id}")
            self.repo.update_ingest_stage_by_version_id(version_id, "completed")
            self.repo.update_ingest_stage(file_path, "completed")
            self.repo.mark_as_searchable(file_path)
        except Exception as e:
            logger.error(f"[Orchestrator] Visual stage failed for {file_path}: {e}", exc_info=True)
            self.repo.fail_processing(file_path, f"[Visual Stage Error] {str(e)}")

    def _run_audio_stage(self, version_id: str, file_path: str, source_pdf_hash: str):
        """音声ファイルを音声ベクトルとしてインデックスする。"""
        try:
            original_filename = Path(file_path).name
            count = index_audio_file(file_path, source_pdf_hash, version_id, original_filename)
            logger.info(f"[Orchestrator] Audio indexing completed: {count} vectors for {version_id}")
            self.repo.update_ingest_stage_by_version_id(version_id, "completed")
            self.repo.update_ingest_stage(file_path, "completed")
            self.repo.mark_as_searchable(file_path)
        except Exception as e:
            logger.error(f"[Orchestrator] Audio stage failed for {file_path}: {e}", exc_info=True)
            self.repo.fail_processing(file_path, f"[Audio Stage Error] {str(e)}")

    def _run_video_stage(self, version_id: str, file_path: str, source_pdf_hash: str):
        """動画ファイルを動画ベクトルとしてインデックスする。"""
        try:
            original_filename = Path(file_path).name
            count = index_video_file(file_path, source_pdf_hash, version_id, original_filename)
            logger.info(f"[Orchestrator] Video indexing completed: {count} vectors for {version_id}")
            self.repo.update_ingest_stage_by_version_id(version_id, "completed")
            self.repo.update_ingest_stage(file_path, "completed")
            self.repo.mark_as_searchable(file_path)
        except Exception as e:
            logger.error(f"[Orchestrator] Video stage failed for {file_path}: {e}", exc_info=True)
            self.repo.fail_processing(file_path, f"[Video Stage Error] {str(e)}")

    def _run_mixed_stage(self, version_id: str, file_path: str, source_pdf_hash: str):
        """Mixed PDF をインターリーブベクトルとしてインデックスする。"""
        try:
            original_filename = Path(file_path).name
            count = index_mixed_file(file_path, source_pdf_hash, version_id, original_filename)
            logger.info(f"[Orchestrator] Mixed indexing completed: {count} vectors for {version_id}")
            self.repo.update_ingest_stage_by_version_id(version_id, "completed")
            self.repo.update_ingest_stage(file_path, "completed")
            self.repo.mark_as_searchable(file_path)
        except Exception as e:
            logger.error(f"[Orchestrator] Mixed stage failed for {file_path}: {e}", exc_info=True)
            self.repo.fail_processing(file_path, f"[Mixed Stage Error] {str(e)}")

    def _run_ocr_stage(self, version_id: str, file_path: str, source_pdf_hash: str, source_kind: str, doc_type: str):
        try:
            output_md_path = str(Path(file_path).with_suffix(".md"))
            output_blocks_path = str(Path(file_path).with_suffix(".blocks.json"))
            
            # ocr_processor.py のプロセス呼び出し
            process_pdf_background(
                filepath=file_path,
                output_path=output_md_path,
                doc_type=doc_type,
                source_pdf_hash=source_pdf_hash,
                version_id=version_id,
                blocks_output_path=output_blocks_path # Phase 3: Jsonも保存させる
            )
            
            # ocr_processor は同期ブロックするか、あるいは dispatch_next_stage を呼び出す
        except Exception as e:
            logger.error(f"[Orchestrator] OCR stage failed for {file_path}: {e}", exc_info=True)
            self.repo.fail_processing(file_path, f"[OCR Stage Error] {str(e)}")

    def dispatch_next_stage(self, version_id: str, current_stage: str, **kwargs):
        """
        各ステージの完了コールバックとして呼ばれる

        Bug fix: enrichment_completed に filepath=final_pdf_path を渡していたが、
        LegacyDocument は元の (アップロード直後の) file_path で登録されているため
        update_ingest_stage / fail_processing が DB を更新できなかった。
        original_filepath を全ステージで引き回すことで解決する。
        """
        logger.info(f"[Orchestrator] Dispatching next stage after '{current_stage}' for {version_id}")
        
        try:
            if current_stage == "ocr_completed":
                # => Next: Metadata Enrichment
                # original_filepath: アップロード直後の元パス (LegacyDocument の file_path)
                original_filepath = kwargs.get("original_filepath", kwargs.get("filepath", ""))
                filepath = kwargs.get("filepath", "")
                output_md_path = kwargs.get("output_md_path", "")
                output_blocks_path = kwargs.get("output_blocks_path", "")
                source_pdf_hash = kwargs.get("source_pdf_hash", "")
                
                final_md_path, final_pdf_path = self.enricher.process(
                    version_id=version_id, 
                    markdown_path=output_md_path, 
                    filepath=filepath,
                    source_pdf_hash=source_pdf_hash
                )
                
                # => Next: Indexing
                # Bug fix: filepath を final_pdf_path (移動後パス) ではなく
                # original_filepath (元パス) を渡すことで DB 更新が正常に機能する
                # source_pdf_hash も引き回して chunk のメタデータを正確にする
                self.dispatch_next_stage(
                    version_id, 
                    "enrichment_completed", 
                    original_filepath=original_filepath,
                    filepath=final_pdf_path,
                    final_md_path=final_md_path,
                    output_blocks_path=output_blocks_path,
                    source_pdf_hash=source_pdf_hash,
                )
                
            elif current_stage == "enrichment_completed":
                # => Next: Chunking & Indexing (Phase 3)
                # Bug fix: DB 操作には元のアップロードパス (original_filepath) を使う
                original_filepath = kwargs.get("original_filepath", kwargs.get("filepath", ""))
                final_md_path = kwargs.get("final_md_path", "")
                output_blocks_path = kwargs.get("output_blocks_path", "")
                
                self.repo.update_ingest_stage_by_version_id(version_id, "indexing")
                self.repo.update_ingest_stage(original_filepath, "indexing")
                
                try:
                    # Use unified indexing logic from indexer.py
                    from indexer import process_and_index_file
                    
                    # We need file_info for process_and_index_file
                    file_info = {
                        "filename":        Path(final_md_path).name,
                        "full_path":       final_md_path,
                        "rel_path":        original_filepath, # Use original for mapping
                        "category":        "ingestion", # Will be refined by frontmatter/classifier
                        "file_type":       "md",
                        "source_pdf_hash": kwargs.get("source_pdf_hash", ""),
                        "source_pdf_rel":  original_filepath,
                    }
                    
                    stats = {"indexed": 0, "chunks": 0, "skipped": 0, "errors": 0}
                    process_and_index_file(file_info, stats)
                    
                    # 4. Completion
                    self.repo.update_ingest_stage(original_filepath, "completed")
                    self.repo.update_ingest_stage_by_version_id(version_id, "completed")
                    self.repo.mark_as_searchable(original_filepath)
                    
                    logger.info(f"[Orchestrator] Pipeline finished successfully for {version_id}")
                    
                except Exception as e:
                    logger.error(f"[Orchestrator] Chunking/Indexing failed for {version_id}: {e}", exc_info=True)
                    self.repo.fail_processing(original_filepath, f"[Indexing Stage Error] {str(e)}")
                
        except Exception as e:
            logger.error(f"[Orchestrator] Pipeline failed at dispatch after {current_stage}: {e}", exc_info=True)
            # Bug fix: original_filepath を優先して使う
            err_path = kwargs.get("original_filepath") or kwargs.get("filepath")
            if err_path:
                self.repo.fail_processing(err_path, str(e))
