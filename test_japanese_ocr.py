import sys
import logging
import traceback
sys.path.insert(0, '.')
from pipeline_manager import process_file_pipeline

logging.basicConfig(level=logging.INFO)

def test():
    try:
        process_file_pipeline('data/input/書籍 2026年3月3日 (1).pdf')
        print('SUCCESS')
    except Exception as e:
        print("FAILED WITH ERROR:")
        traceback.print_exc()

if __name__ == "__main__":
    test()
