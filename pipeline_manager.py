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
        self.base_dir = Path("data")
        self.base_dir.mkdir(exist_ok=True)
        
    def process_file(self, file_path: Path):
        """
        ファイルを分類し、適切なパイプラインを実行する。
        """
        logger.info(f"Processing file: {file_path}")
        
        try:
            # 1. 自動分類
            file_type = self.router.classify(file_path)
            logger.info(f"File classified as: {file_type}")
            
            # 2. フォルダ移動
            target_dir = self.base_dir / ("02_図面" if file_type == "Drawing" else "01_カタログ")
            target_dir.mkdir(parents=True, exist_ok=True)
            
            new_path = target_dir / file_path.name
            shutil.move(str(file_path), str(new_path))
            logger.info(f"Moved file to: {new_path}")
            
            # 3. パイプライン実行
            if file_type == "Document":
                # ドキュメントパイプライン (OCR)
                # 出力パスを作成 (.pdf -> .md)
                output_path = new_path.with_suffix(".md")
                logger.info(f"Starting OCR pipeline for {new_path} -> {output_path}")
                process_pdf_background(str(new_path), str(output_path))
                
            elif file_type == "Drawing":
                # 図面パイプライン (未実装のためログ出力のみ)
                logger.info(f"Drawing pipeline pending for {new_path}")
                # process_drawing_pipeline(str(new_path))
                
        except Exception as e:
            logger.error(f"Pipeline processing failed for {file_path}: {e}", exc_info=True)
            # エラー時は error フォルダへ移動
            error_dir = self.base_dir / "error"
            error_dir.mkdir(exist_ok=True)
            if file_path.exists():
                 shutil.move(str(file_path), str(error_dir / file_path.name))

def process_file_pipeline(file_path: str):
    """
    PipelineManagerを使ってファイルを処理するためのラッパー関数
    """
    manager = PipelineManager()
    manager.process_file(Path(file_path))
