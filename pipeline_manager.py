from pathlib import Path
import logging
from content_router import ContentRouter
from ingestion_orchestrator import IngestionOrchestrator

logger = logging.getLogger(__name__)

class PipelineManager:
    """
    旧パイプラインマネージャーを IngestionOrchestrator のラッパーとして維持。
    新規実装では IngestionOrchestrator を直接使用することを推奨。
    """
    def __init__(self):
        self.router = ContentRouter()
        self.orchestrator = IngestionOrchestrator()
        
    def process_file(self, file_path: Path, source_pdf_hash: str = "", version_id: str = ""):
        """
        ファイルを分類し、オーケストレーターにジョブを投入する。
        """
        logger.info(f"[PipelineManager] Routing file to Orchestrator: {file_path}")
        
        try:
            # 1. MIME/拡張子による自動分類 (Document/Drawing)
            file_type = self.router.classify(file_path)
            
            # 2. 拡張子チェック
            ext = file_path.suffix.lower()
            is_image = ext in (".png", ".jpg", ".jpeg")
            is_audio = ext in (".mp3", ".wav")
            is_video = ext in (".mp4", ".mov")
            if ext == ".pdf":
                source_kind = "pdf"
            elif is_image:
                source_kind = "image"
            elif is_audio:
                source_kind = "audio"
            elif is_video:
                source_kind = "video"
            else:
                source_kind = "document"

            # 3. doc_type の決定
            doc_type_map = {
                "Drawing": "drawing",
                "Document": "catalog",
                "Mixed": "mixed",
                "Audio": "audio",
                "Video": "video",
            }
            doc_type = doc_type_map.get(file_type, "catalog")
            
            # 4. オーケストレーターにキューイング
            self.orchestrator.enqueue_job(
                version_id=version_id,
                file_path=str(file_path),
                source_pdf_hash=source_pdf_hash,
                source_kind=source_kind,
                doc_type=doc_type
            )
            
        except Exception as e:
            logger.error(f"[PipelineManager] CRITICAL: Failed to route/enqueue file {file_path}: {e}", exc_info=True)
            from metadata_repository import MetadataRepository
            MetadataRepository().fail_processing(str(file_path), f"Routing failure: {str(e)}")

def process_file_pipeline(file_path: str, source_pdf_hash: str = "", version_id: str = ""):
    """
    routers/files.py 等から呼ばれるエントリーポイント。
    """
    manager = PipelineManager()
    manager.process_file(Path(file_path), source_pdf_hash, version_id)

