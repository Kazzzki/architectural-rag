import logging
import threading
from pathlib import Path
from typing import Dict, Any

from ocr_processor import process_pdf_background
from metadata_enricher import MetadataEnricher
# from chunk_builder import build_3tier_chunks
from indexer import index_file

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
        logger.info(f"[Orchestrator] Enqueuing job for version_id={version_id}")
        self.repo.update_ingest_stage_by_version_id(version_id, "processing")
        self.repo.update_ingest_stage(file_path, "processing")
        
        # 非同期スレッドでOCR処理を開始
        threading.Thread(
            target=self._run_ocr_stage,
            args=(version_id, file_path, source_pdf_hash, source_kind, doc_type),
            daemon=True
        ).start()

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
            logger.error(f"[Orchestrator] OCR stage failed: {e}", exc_info=True)
            self.repo.fail_processing(file_path, str(e))

    def dispatch_next_stage(self, version_id: str, current_stage: str, **kwargs):
        """
        各ステージの完了コールバックとして呼ばれる
        """
        logger.info(f"[Orchestrator] Dispatching next stage after '{current_stage}' for {version_id}")
        
        try:
            if current_stage == "ocr_completed":
                # => Next: Metadata Enrichment
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
                self.dispatch_next_stage(
                    version_id, 
                    "enrichment_completed", 
                    filepath=final_pdf_path,
                    final_md_path=final_md_path,
                    output_blocks_path=output_blocks_path
                )
                
            elif current_stage == "enrichment_completed":
                # => Next: Chunking & Indexing (Phase 3)
                filepath = kwargs.get("filepath", "")
                final_md_path = kwargs.get("final_md_path", "")
                output_blocks_path = kwargs.get("output_blocks_path", "")
                
                self.repo.update_ingest_stage_by_version_id(version_id, "indexing")
                self.repo.update_ingest_stage(filepath, "indexing")
                
                try:
                    # 3. チャンク生成 (Hierarchical Chunking)
                    from chunk_builder import ChunkBuilder
                    builder = ChunkBuilder()
                    
                    with open(final_md_path, 'r', encoding='utf-8') as f:
                        markdown_text = f.read()
                    
                    ocr_results = []
                    if output_blocks_path and Path(output_blocks_path).exists():
                        import json
                        with open(output_blocks_path, 'r', encoding='utf-8') as bj:
                            ocr_results = json.load(bj)
                    
                    chunks = builder.build(version_id, markdown_text, ocr_results)
                    
                    # 2. Dense Indexing (ChromaDB)
                    from dense_indexer import DenseIndexer
                    dense = DenseIndexer()
                    dense.upsert_chunks(version_id, chunks)
                    
                    # 3. Lexical Indexing (SQLite FTS5)
                    from lexical_indexer import LexicalIndexer
                    lexical = LexicalIndexer()
                    lexical.upsert_chunks(version_id, chunks)
                    
                    # 4. Completion
                    self.repo.update_ingest_stage(filepath, "completed")
                    self.repo.update_ingest_stage_by_version_id(version_id, "completed")
                    self.repo.mark_as_searchable(filepath)
                    
                    logger.info(f"[Orchestrator] Pipeline finished successfully for {version_id}")
                    
                except Exception as e:
                    logger.error(f"[Orchestrator] Chunking/Indexing failed: {e}", exc_info=True)
                    self.repo.fail_processing(filepath, str(e))
                
        except Exception as e:
            logger.error(f"[Orchestrator] Pipeline failed at dispatch after {current_stage}: {e}", exc_info=True)
            filepath = kwargs.get("filepath")
            if filepath:
                self.repo.fail_processing(filepath, str(e))
