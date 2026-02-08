import os
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

from content_router import route_content
from drawing_processor import process_drawing_pdf
import ocr_processor  # 既存のOCRモジュール
from status_manager import OCRStatusManager

def process_file_pipeline(filepath: str, output_path: str = None):
    """
    ファイルの自動分類パイプライン
    1. 図面/文書の判定 (Router)
    2. 専用プロセッサによるMarkdown化
    3. 自動分類と整理 (Finalizer)
    """
    print(f"Pipeline Start: {filepath}")
    status_mgr = OCRStatusManager()
    
    # 出力パスが未指定ならとりあえず同じ場所に .md を作る（後で移動される）
    if output_path is None:
        output_path = str(Path(filepath).with_suffix('.md'))

    try:
        # 1. 判定
        doc_type = route_content(filepath)
        print(f"Document Type: {doc_type} -> {filepath}")
        
        # 2. 分岐処理
        if doc_type == "DRAWING":
            # 図面処理ルート
            # ステータス初期化 (図面処理はページ数ベースで進捗出せればベストだが、一旦簡易的に開始)
            status_mgr.start_processing(filepath, total_pages=1) # 仮

            try:
                markdown_text = process_drawing_pdf(filepath)
                
                # 図面プロセッサはMarkdown文字列を返すので、一旦保存
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(markdown_text)
                
                # 3. 仕上げ (分類・移動・インデックス)
                # Drawingも文書と同じ分類器を通すか、あるいは強制的に 'Drawings' フォルダにするか？
                # ユーザー指示: "解析結果に基づき、ローカルの processed/ フォルダ内で自動仕分け"
                # 既存の classifier にメタデータを渡して処理させるのが統一的。
                # ただし、図面専用のカテゴリロジックが必要なら classifier.py 修正が必要だが、
                # 一旦は既存のルールベースで "図面" キーワード等で分類されることを期待する。
                # あるいは Drawing の場合は classifier にヒントを与える。
                
                # finalize_processing は内部で分類を行う
                ocr_processor.finalize_processing(filepath, output_path, markdown_text, status_mgr)
                
            except Exception as e:
                print(f"Drawing processing failed: {e}")
                traceback.print_exc()
                status_mgr.fail_processing(filepath, str(e))

        else:
            # 文書ルート (既存OCR)
            # OCRプロセッサ内で finalize_processing も呼ばれる
            ocr_processor.process_pdf_background(filepath, output_path)

    except Exception as e:
        print(f"Pipeline Error: {e}")
        traceback.print_exc()
        status_mgr.fail_processing(filepath, str(e))

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        process_file_pipeline(sys.argv[1])
