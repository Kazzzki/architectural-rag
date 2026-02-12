import os
import time
import traceback
import google.generativeai as genai
import pypdf
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import List, Dict, Any
from tenacity import RetryError

from config import GEMINI_MODEL, GEMINI_API_KEY
from ocr_utils import retry_gemini_call

if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


def _split_pdf(filepath: str, chunk_size: int = 2) -> List[Dict[str, Any]]:
    """PDFを分割して一時ファイルを作成"""
    chunks = []
    reader = pypdf.PdfReader(filepath)
    total_pages = len(reader.pages)
    
    base_dir = Path(filepath).parent
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
                "is_temp": True
            })
    else:
        chunks.append({
            "path": filepath,
            "mime_type": "application/pdf",
            "label": "Full Doc",
            "index": 0,
            "is_temp": False
        })
        
    return chunks

@retry_gemini_call(max_attempts=5)
def _call_gemini_with_retry(model_name: str, file_path: str, mime_type: str, prompt: str) -> str:
    """Gemini APIを呼び出す（リトライ付き）"""
    model = genai.GenerativeModel(model_name)
    
    # Upload
    uploaded_file = genai.upload_file(file_path, mime_type=mime_type)
    
    # Wait for processing
    wait_count = 0
    while uploaded_file.state.name == "PROCESSING":
        time.sleep(1)
        uploaded_file = genai.get_file(uploaded_file.name)
        wait_count += 1
        if wait_count > 60:
            raise Exception("File processing timeout")
    
    if uploaded_file.state.name == "FAILED":
        raise Exception("Google AI File processing failed")

    # Generate
    # Gemini 3.0 Flash向けの生成設定（忠実性重視）
    generation_config = genai.types.GenerationConfig(
        temperature=0.0,
        max_output_tokens=8192  # トークン制限緩和
    )
    response = model.generate_content(
        [prompt, uploaded_file],
        generation_config=generation_config
    )
    
    return response.text


def _process_chunk(chunk: Dict[str, Any], model_name: str) -> Dict[str, Any]:
    """1つのチャンク（PDF断片）をOCR処理"""
    
    prompt = """
    You are a professional digital archivist. Your goal is to digitize this document with 100% fidelity.
    
    STRICT INSTRUCTIONS:
    1. Transcribe the text EXACTLY as it appears in the image/PDF. Do not summarize, correct grammar, or omit anything.
    2. Preserve the structure:
       - Use Markdown headers (#, ##) for titles.
       - Use Markdown lists (-, 1.) for bullet points.
       - Use **bold** for bold text.
       - Use > blockquotes for quoted text.
    3. If there are tables, reconstruct them using Markdown table syntax.
    4. If the text is in Japanese, ensure correct kanji/kana usage.
    5. Output ONLY the markdown content. No introductory text like "Here is the text".
    """
    
    try:
        text = _call_gemini_with_retry(model_name, chunk['path'], chunk['mime_type'], prompt)
        
        # Cleanup temp file
        if chunk.get('is_temp'):
            try:
                os.remove(chunk['path'])
            except:
                pass
                
        return {
            "text": text,
            "index": chunk['index'],
            "success": True
        }
        
    except Exception as e:
        print(f"OCR Failed for chunk {chunk['label']}: {e}")
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
        
        # Frontmatter生成
        frontmatter = classifier.generate_frontmatter(classification_result)
        
        # Markdownファイルを更新 (Frontmatterを先頭に追加)
        full_md_text = frontmatter + markdown_text
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_md_text)
        
        # フォルダ移動 (Phase 1-2: 元のフォルダを考慮)
        from config import ENABLE_AUTO_CATEGORIZE, AUTO_CATEGORIZE_UPLOADS_ONLY, KNOWLEDGE_BASE_DIR
        
        # 元のカテゴリを取得（KNOWLEDGE_BASE_DIRからの相対パス）
        try:
            # resolve()を使って絶対パスで比較
            original_category = Path(filepath).parent.resolve().relative_to(Path(KNOWLEDGE_BASE_DIR).resolve())
            is_uploads = str(original_category) == 'uploads' or str(original_category) == '.'
        except ValueError:
            # KNOWLEDGE_BASE_DIR外の場合は uploads 扱い
            original_category = "uploads"
            is_uploads = True

        category_path = str(original_category)

        if not is_uploads:
            # uploadsフォルダ以外にあるファイルは移動しない（ユーザーが意図して配置した場所を尊重）
            category_path = str(original_category)
        elif not ENABLE_AUTO_CATEGORIZE:
            # 自動分類機能が無効の場合は移動しない
            category_path = "uploads"
        else:
            # uploadsにあり、自動分類有効 -> primary_categoryを使用
            primary_cat = classification_result.get('primary_category')
            if primary_cat and primary_cat != "uploads":
                category_path = primary_cat
            else:
                category_path = "uploads"
        
        target_dir = Path(KNOWLEDGE_BASE_DIR) / category_path
        target_dir.mkdir(parents=True, exist_ok=True)
        
        new_pdf_path = target_dir / Path(filepath).name
        new_md_path = target_dir / Path(output_path).name
        
        # 同名ファイル回避
        if new_pdf_path.exists() and new_pdf_path.resolve() != Path(filepath).resolve():
            timestamp = int(time.time())
            new_pdf_path = target_dir / f"{Path(filepath).stem}_{timestamp}{Path(filepath).suffix}"
            new_md_path = target_dir / f"{Path(output_path).stem}_{timestamp}{Path(output_path).suffix}"
        
        # 移動実行
        if new_pdf_path.resolve() != Path(filepath).resolve():
            shutil.move(filepath, new_pdf_path)
            shutil.move(output_path, new_md_path)
            print(f"自動分類: {category_path} へ移動しました")
            status_mgr.rename_status(filepath, str(new_pdf_path))
            filepath = str(new_pdf_path)
            # output_path (md)も更新が必要だが、呼び出し元では使わない前提あるいは...
            output_path = str(new_md_path)
        else:
            print(f"自動分類: 移動不要 ({category_path})")
        
        # 自動インデックス登録
        try:
            from indexer import index_file
            print(f"インデックス登録開始: {new_md_path}")
            index_file(str(new_md_path))
        except Exception as e:
            print(f"自動インデックス登録エラー: {e}")
            traceback.print_exc()

        status_mgr.complete_processing(filepath)
        return filepath, output_path

    except Exception as e:
        print(f"自動分類・メタデータ付与エラー: {e}")
        traceback.print_exc()
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
        
        with ThreadPoolExecutor(max_workers=2) as executor:
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
                    print(f"Chunk processing error ({chunk['label']}): {e}")
                    results.append({
                        "index": chunk['index'],
                        "text": f"\n> ⚠️ **[System Error]** Processing failed for **{chunk['label']}**.\n> Error: {str(e)}\n",
                        "success": False
                    })
                    processed_count += 1
                    status_mgr.update_progress(filepath, processed_count)
        
        # 3. 結合
        results.sort(key=lambda x: x['index'])
        markdown_text = f"# [OCR Result] {Path(filepath).name}\n\n"
        
        chunk_map = {c['index']: c for c in chunks}
        
        for r in results:
            chunk_info = chunk_map.get(r['index'])
            label = chunk_info['label'] if chunk_info else f"Part {r['index'] + 1}"
            try:
                page_num = int(label.replace('Page ', ''))
            except:
                page_num = r['index'] + 1

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
        print(f"OCRプロセス全体でエラー ({filepath}): {e}")
        traceback.print_exc()
        status_mgr.fail_processing(filepath, str(e))
