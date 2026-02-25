from pathlib import Path
import logging
import shutil
from content_router import ContentRouter
from ocr_processor import process_pdf_background
# from drawing_processor import process_drawing_pipeline # 将来的に実装

logger = logging.getLogger(__name__)

class PipelineManager:
    def __init__(self):
        self.router = ContentRouter()
        from config import BASE_DIR
        self.base_dir = Path(BASE_DIR)
        self.base_dir.mkdir(exist_ok=True)
        
    def process_file(self, file_path: Path):
        """
        ファイルを分類し、適切なパイプラインを実行する。
        """
        logger.info(f"Processing file: {file_path}")
        
        try:
            # 1. 自動分類
            try:
                file_type = self.router.classify(file_path)
                logger.info(f"File classified as: {file_type}")
            except Exception as e:
                raise RuntimeError(f"Classification failed: {e}") from e
            
            # 2. フォルダ移動 (Phase 1-2: 無効化 - OCR Processor側で制御するため)
            # try:
            #     target_dir = self.base_dir / ("02_図面" if file_type == "Drawing" else "01_カタログ")
            #     target_dir.mkdir(parents=True, exist_ok=True)
            #     
            #     new_path = target_dir / file_path.name
            #     shutil.move(str(file_path), str(new_path))
            #     logger.info(f"Moved file to: {new_path}")
            # except Exception as e:
            #      raise RuntimeError(f"File move failed: {e}") from e
            new_path = file_path # 移動しないのでパスはそのまま
            
            # 3. パイプライン実行
            try:
                if file_type in ("Document", "Drawing"):
                    # ドキュメント・図面ともにOCRパイプラインを使用
                    output_path = new_path.with_suffix(".md")
                    logger.info(f"Starting OCR pipeline for {new_path} -> {output_path} (type={file_type})")
                    process_pdf_background(str(new_path), str(output_path))
            except Exception as e:
                # パイプライン実行中のエラー。ファイルはすでに移動済み。
                # 移動先のファイルパスでエラー処理を行う必要があるが、
                # ここでは new_path が有効。
                raise RuntimeError(f"Pipeline execution failed: {e}", new_path) from e
                
        except Exception as e:
            logger.error(f"Pipeline processing failed for {file_path}: {e}", exc_info=True)
            
            from status_manager import OCRStatusManager
            try:
                OCRStatusManager().fail_processing(str(file_path), str(e))
            except Exception as sm_err:
                logger.error(f"Failed to update DB failed status: {sm_err}")
                
            # エラー時は error フォルダへ移動 (隔離)
            from config import ERROR_DIR
            error_dir = Path(ERROR_DIR)
            error_dir.mkdir(parents=True, exist_ok=True)
            
            # 移動元(input)にある場合
            if file_path.exists():
                try:
                    dest = error_dir / file_path.name
                    shutil.move(str(file_path), str(dest))
                    logger.info(f"Moved error file to: {dest}")
                except Exception as move_err:
                    logger.error(f"Failed to move error file {file_path}: {move_err}")
            
            # すでに移動済みでパイプライン処理中にエラーになった場合 (argsにnew_pathが入っている場合を想定)
            elif len(e.args) > 1 and isinstance(e.args[1], Path) and e.args[1].exists():
                failed_path = e.args[1]
                try:
                    dest = error_dir / failed_path.name
                    shutil.move(str(failed_path), str(dest))
                    logger.info(f"Moved processed error file to: {dest}")
                except Exception as move_err:
                    logger.error(f"Failed to move processed error file {failed_path}: {move_err}")

def process_file_pipeline(file_path: str):
    """
    PipelineManagerを使ってファイルを処理するためのラッパー関数
    """
    manager = PipelineManager()
    manager.process_file(Path(file_path))
