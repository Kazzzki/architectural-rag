import time
import shutil
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from pipeline_manager import PipelineManager

# ログ設定
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("antigravity_daemon.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class NewFileHandler(FileSystemEventHandler):
    def __init__(self, pipeline_manager):
        self.pipeline_manager = pipeline_manager

    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = Path(event.src_path)
        filename = filepath.name
        
        # 隠しファイルや一時ファイルは無視
        if filename.startswith('.') or filename.endswith('.tmp'):
            return
            
        # 対象拡張子のみ処理
        if filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            logger.info(f"New file detected: {filename}")
            # ファイル書き込み完了を少し待つ（念のため）
            time.sleep(1)
            try:
                self.pipeline_manager.process_file(filepath)
            except Exception as e:
                logger.error(f"Error processing {filename}: {e}", exc_info=True)

if __name__ == "__main__":
    # 入力ディレクトリ監視
    INPUT_DIR = Path("data/input")
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # パイプラインマネージャ初期化
    pipeline_manager = PipelineManager()
    
    event_handler = NewFileHandler(pipeline_manager)
    observer = Observer()
    observer.schedule(event_handler, str(INPUT_DIR), recursive=False)
    
    logger.info(f"Starting Antigravity Daemon... Monitoring {INPUT_DIR}")
    observer.start()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()
