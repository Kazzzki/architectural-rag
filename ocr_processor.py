import os
import time
import traceback
import pypdf
from google.genai import types
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any
from tenacity import RetryError

from config import GEMINI_MODEL_OCR, MAX_TOKENS, PDF_CHUNK_PAGES
from ocr_utils import retry_gemini_call
from gemini_client import get_client

# 互換性のため
GEMINI_MODEL = GEMINI_MODEL_OCR


def _split_pdf(filepath: str, chunk_size: int = PDF_CHUNK_PAGES) -> List[Dict[str, Any]]:
    """PDFを分割して一時ファイルを作成"""
    chunks = []
    reader = pypdf.PdfReader(filepath)
    total_pages = len(reader.pages)
    
    from config import TEMP_CHUNK_DIR
    base_dir = Path(TEMP_CHUNK_DIR)
    os.makedirs(base_dir, exist_ok=True)
    
    filename = Path(filepath).name
    
    if total_pages > chunk_size:
        for i in range(0, total_pages, chunk_size):
            writer = pypdf.PdfWriter()
            end_page = min(i + chunk_size, total_pages)
            for p in range(i, end_page):
                writer.add_page(reader.pages[p])

            chunk_filename = f".chunk_{i}_{filename}"
            chunk_path = base_dir / chunk_filename

            with open(chunk_path, "wb") as f_out:
                writer.write(f_out)

            chunks.append({
                "path": str(chunk_path),
                "mime_type": "application/pdf",
                "label": f"Pages {i+1}-{end_page}",
                "index": i,
                "start_page": i + 1,       # 原本PDF内の開始ページ（1-based）
                "end_page": end_page,       # 原本PDF内の終了ページ（1-based）
                "is_temp": True
            })
    else:
        chunks.append({
            "path": filepath,
            "mime_type": "application/pdf",
            "label": "Full Doc",
            "index": 0,
            "start_page": 1,
            "end_page": total_pages,
            "is_temp": False
        })
        
    return chunks

@retry_gemini_call(max_attempts=5)
def _call_gemini_with_retry(model_name: str, file_path: str, mime_type: str, prompt: str) -> str:
    """Gemini APIを呼び出す（リトライ付き）"""
    client = get_client()

    # Upload
    uploaded_file = client.files.upload(
        file=file_path,
        config=types.UploadFileConfig(mime_type=mime_type)
    )

    wait_count = 0
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(1)
        uploaded_file = client.files.get(name=uploaded_file.name)
        wait_count += 1
        if wait_count > 60:
            raise Exception("File processing timeout")

    if uploaded_file.state.name == "FAILED":
        raise Exception("Google AI File processing failed")

    response = client.models.generate_content(
        model=model_name,
        contents=[prompt, uploaded_file],
        config=types.GenerateContentConfig(
            temperature=0.0,
            max_output_tokens=MAX_TOKENS
        )
    )

    # 空レスポンスガード（コンテンツフィルタ等）
    if not response.candidates or not response.candidates[0].content.parts:
        raise ValueError("Gemini returned empty response (possibly content filtered)")

    # finish_reason チェック: MAX_TOKENS で打ち切られた場合に警告
    finish_reason = response.candidates[0].finish_reason
    if str(finish_reason) in ("FinishReason.MAX_TOKENS", "MAX_TOKENS", "2"):
        import logging as _logging
        _logging.getLogger(__name__).warning(
            f"[OCR TRUNCATED] Gemini hit max_output_tokens ({MAX_TOKENS}) for {file_path}. "
            "Output may be incomplete. Reduce PDF_CHUNK_PAGES in config or .env to fix."
        )

    return response.text


DRAWING_OCR_PROMPT_TEMPLATE = """
あなたは建築設計の専門家です。
この図面を以下の形式で詳細に説明してください：

## 図面種別
（平面図/立面図/断面図/詳細図/設備図 等）

## スケール・方位
（記載がある場合）

## 主要寸法
（全ての寸法値を列挙）

## 材料・仕様
（凡例・材料記号・仕上げ材を全て列挙）

## 注記・特記事項
（図面内の文字情報を全て抽出）

## 図面の概要説明
（設計意図・納まりのポイントを200文字で説明）

PAGE MARKERS: This chunk contains pages {start_page} to {end_page} of the original document.
At the beginning of each page's content, output the marker [[PAGE_N]] on its own line.
"""

GENERAL_OCR_PROMPT_TEMPLATE = """
    You are a professional digital archivist. Your goal is to digitize this document with 100% fidelity.

    CRITICAL INSTRUCTIONS FOR ACCURACY:
    1. ZERO OMISSIONS: You must transcribe the text EXACTLY as it appears in the image/PDF. Do not summarize, skip, or omit ANY text, no matter how repetitive, dense, or insignificant it seems.
    2. PAGE-BY-PAGE CONFIRMATION: Process every single page in the provided PDF chunk. Do not stop halfway.
    3. Preserve the structure:
       - Use Markdown headers (#, ##) for titles.
       - Use Markdown lists (-, 1.) for bullet points.
       - Use **bold** for bold text.
       - Use > blockquotes for quoted text.
    4. If there are tables, reconstruct them meticulously using Markdown table syntax. Do not skip rows.
    5. If the text is in Japanese, ensure correct kanji/kana usage.
    6. Output ONLY the markdown content. No introductory text like "Here is the text".
    7. PAGE MARKERS: This chunk contains pages {start_page} to {end_page} of the original document.
       At the very beginning of each page's content, output the marker [[PAGE_N]] on its own line,
       where N is the actual page number in the original document (starting from {start_page}).
       For example, before the first page's content output [[PAGE_{start_page}]], before the second page output [[PAGE_{start_page + 1}]], and so on.
    """


def _process_chunk(chunk: Dict[str, Any], model_name: str, doc_type: str = "catalog") -> Dict[str, Any]:
    """1つのチャンク（PDF断片）を OCR 処理（doc_type に応じたプロンプトを使用）"""
    start_page = chunk.get("start_page", 1)
    end_page = chunk.get("end_page", start_page)

    if doc_type == "drawing":
        prompt = DRAWING_OCR_PROMPT_TEMPLATE.format(start_page=start_page, end_page=end_page)
    else:
        prompt = GENERAL_OCR_PROMPT_TEMPLATE.format(
            start_page=start_page, end_page=end_page
        )

    try:
        text = _call_gemini_with_retry(model_name, chunk['path'], chunk['mime_type'], prompt)
        
        # Cleanup temp file
        if chunk.get('is_temp'):
            try:
                os.remove(chunk['path'])
            except OSError:
                pass
                
        return {
            "text": text,
            "index": chunk['index'],
            "success": True
        }
        
    except Exception as e:
        logger.error(f"OCR Failed for chunk {chunk['label']}: {e}", exc_info=True)
        # テンポラリファイルはエラー時も消すべきか？残してデバッグするか？
        # APIエラーでリトライオーバーした場合は、ファイル自体に問題がある可能性もあるので、いったん残すか、削除するか方針次第。
        # ここでは元コードに合わせて削除しない（デバッグ用）
        
        return {
            "text": f"\n> ⚠️ **[OCR Error]** Failed to retrieve content for **{chunk['label']}** after multiple retries.\n> Error: {str(e)}\n",
            "index": chunk['index'],
            "success": False
        }


def finalize_processing(filepath: str, output_path: str, markdown_text: str, status_mgr=None):
    """
    生成されたMarkdownテキストを元に、分類・Frontmatter付与・フォルダ移動・インデックス登録を行う
    """
    try:
        from classifier import DocumentClassifier
        # import here to avoid circular dependency if possible
        from config import KNOWLEDGE_BASE_DIR
        import shutil
        from pathlib import Path
        import traceback
        import time

        if status_mgr is None:
             from status_manager import OCRStatusManager
             status_mgr = OCRStatusManager()

        # 分類実行
        classifier = DocumentClassifier()
        meta_input = {'title': Path(filepath).stem}
        classification_result = classifier.classify(markdown_text[:5000], meta_input)
        
        import hashlib
        # ハッシュIDを生成
        with open(filepath, 'rb') as f:
            pdf_hash = hashlib.sha256(f.read()).hexdigest()

        # Google Driveへのアップロード実行とID取得
        drive_file_id = ""
        try:
            from drive_sync import upload_single_file_to_drive
            logger.info("Uploading PDF to Google Drive...")
            # 連携用に元のファイル名でアップロードする
            uploaded_id = upload_single_file_to_drive(filepath)
            if uploaded_id:
                drive_file_id = uploaded_id
                logger.info(f"Successfully uploaded {filepath} to Drive: {drive_file_id}")
        except Exception as e:
            logger.error(f"Failed to upload {filepath} to Google Drive: {e}")

        # Frontmatter生成
        extra_meta = {
            "source_pdf": pdf_hash,
            "pdf_filename": Path(filepath).name,
            "drive_file_id": drive_file_id
        }
        frontmatter = classifier.generate_frontmatter(classification_result, extra_meta)
        
        # Markdownファイルを更新 (Frontmatterを先頭に追加)
        full_md_text = frontmatter + markdown_text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_md_text)
        
        # フォルダ移動 (PDF と MD を同一カテゴリフォルダに配置)
        from config import ENABLE_AUTO_CATEGORIZE, AUTO_CATEGORIZE_UPLOADS_ONLY, KNOWLEDGE_BASE_DIR, UNCATEGORIZED_FOLDER, PDF_STORAGE_DIR

        # 元のカテゴリを取得（KNOWLEDGE_BASE_DIRからの相対パス）
        try:
            # resolve()を使って絶対パスで比較
            original_category = Path(filepath).parent.resolve().relative_to(Path(KNOWLEDGE_BASE_DIR).resolve())
            # "00_未分類"・"uploads"・ルート直下（"."）はすべて未分類扱い
            is_uploads = str(original_category) in ('uploads', '.', UNCATEGORIZED_FOLDER)
        except ValueError:
            # KNOWLEDGE_BASE_DIR外（例: data/input/）の場合は未分類扱い
            original_category = UNCATEGORIZED_FOLDER
            is_uploads = True

        category_path = str(original_category)

        if not is_uploads:
            # カテゴリフォルダに意図的に置かれたファイルは移動しない
            category_path = str(original_category)
        elif not ENABLE_AUTO_CATEGORIZE:
            # 自動分類無効の場合は未分類フォルダへ
            category_path = UNCATEGORIZED_FOLDER
        else:
            # 自動分類有効 → primary_categoryを使用
            primary_cat = classification_result.get('primary_category')
            if primary_cat and primary_cat not in ("uploads", UNCATEGORIZED_FOLDER):
                category_path = primary_cat
            else:
                category_path = UNCATEGORIZED_FOLDER

        # PDFはハッシュ名でPDF_STORAGE_DIRに格納し、MDはカテゴリフォルダへ配置
        target_pdf_dir = Path(PDF_STORAGE_DIR)
        target_md_dir = Path(KNOWLEDGE_BASE_DIR) / category_path
        
        target_pdf_dir.mkdir(parents=True, exist_ok=True)
        target_md_dir.mkdir(parents=True, exist_ok=True)
        
        new_pdf_path = target_pdf_dir / f"{pdf_hash}{Path(filepath).suffix}"
        new_md_path = target_md_dir / Path(output_path).name

        # 移動実行（同名ファイルは上書き。タイムスタンプ付加はしない）
        pdf_moved = False
        md_moved = False
        
        if new_pdf_path.resolve() != Path(filepath).resolve():
            # 移動先に既存ファイルがある場合は先に削除して上書き
            if new_pdf_path.exists():
                new_pdf_path.unlink()
            shutil.move(filepath, new_pdf_path)
            pdf_moved = True
            
        if new_md_path.resolve() != Path(output_path).resolve():
            if new_md_path.exists():
                new_md_path.unlink()
            shutil.move(output_path, new_md_path)
            md_moved = True
            
        if pdf_moved or md_moved:
            print(f"自動分類: PDFは {PDF_STORAGE_DIR}、MDは {category_path} へ移動しました")
            if pdf_moved:
                status_mgr.rename_status(filepath, str(new_pdf_path))
                # file_store の current_path を新しいパスに更新
                try:
                    import file_store as fs
                    file_rec = fs.get_file_by_path(filepath)
                    if file_rec:
                        fs.update_path(file_rec["id"], str(new_pdf_path))
                except Exception as _e:
                    logger.warning(f"file_store パス更新エラー ({filepath}): {_e}")
                filepath = str(new_pdf_path)
            if md_moved:
                output_path = str(new_md_path)
        else:
            print(f"自動分類: 移動不要 ({category_path})")
        
        # 自動インデックス登録
        try:
            from indexer import index_file
            print(f"インデックス登録開始: {new_md_path}")
            index_file(str(new_md_path))
        except Exception as e:
            logger.error(f"自動インデックス登録エラー ({new_md_path}): {e}", exc_info=True)

        status_mgr.complete_processing(filepath)
        return filepath, output_path

    except Exception as e:
        logger.error(f"自動分類・メタデータ付与エラー ({filepath}): {e}", exc_info=True)
        status_mgr.complete_processing(filepath)
        return filepath, output_path


def process_pdf_background(filepath: str, output_path: str):
    """
    指定されたPDFをOCR処理してMarkdownに変換し、保存する（バックグラウンド実行用）
    """
    print(f"OCR開始: {filepath} -> {output_path}")
    from status_manager import OCRStatusManager
    status_mgr = OCRStatusManager()
    
    try:
        # 1. PDF分割
        chunks = _split_pdf(filepath)
        total_chunks = len(chunks)
        
        # ステータス初期化
        status_mgr.start_processing(filepath, total_chunks)
        
        # 2. 並列処理でOCR
        results = []
        processed_count = 0
        
        with ThreadPoolExecutor(max_workers=4) as executor:
            future_to_chunk = {
                executor.submit(_process_chunk, chunk, GEMINI_MODEL): chunk 
                for chunk in chunks
            }
            
            for future in as_completed(future_to_chunk):
                chunk = future_to_chunk[future]
                try:
                    res = future.result()
                    results.append(res)
                    processed_count += 1
                    status_mgr.update_progress(filepath, processed_count)
                except Exception as e:
                    logger.error(f"Chunk processing error ({chunk['label']}): {e}", exc_info=True)
                    results.append({
                        "index": chunk['index'],
                        "text": f"\n> ⚠️ **[System Error]** Processing failed for **{chunk['label']}**.\n> Error: {str(e)}\n",
                        "success": False
                    })
                    processed_count += 1
                    status_mgr.update_progress(filepath, processed_count)
        
        # 3. 結合
        results.sort(key=lambda x: x['index'])
        markdown_text = f"# {Path(filepath).stem}\n\n"
        
        chunk_map = {c['index']: c for c in chunks}

        for r in results:
            chunk_info = chunk_map.get(r['index'])
            label = chunk_info['label'] if chunk_info else f"Part {r['index'] + 1}"
            # start_page フィールドから正確な開始ページを取得（フォールバック: index+1）
            page_num = chunk_info['start_page'] if chunk_info else r['index'] + 1

            # Geminiが per-page [[PAGE_X]] を出力するが、フォールバックとしてチャンク先頭マーカーも付与
            markdown_text += f"\n\n[[PAGE_{page_num}]]\n"
            markdown_text += f"## {label}\n\n"
            markdown_text += r['text']
            markdown_text += "\n\n---\n"
        
        # 4. 保存 (一旦)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown_text)
            
        print(f"OCR完了・保存: {output_path}")
        
        # 5. 仕上げ処理 (分類・移動・インデックス)
        finalize_processing(filepath, output_path, markdown_text, status_mgr)
        
    except Exception as e:
        logger.error(f"OCRプロセス全体でエラー ({filepath}): {e}", exc_info=True)
        status_mgr.fail_processing(filepath, str(e))
