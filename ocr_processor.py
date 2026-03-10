import os
import time
import asyncio
import threading
import tempfile
import shutil
import traceback
import uuid
import pypdf
from google.genai import types
from concurrent.futures import ThreadPoolExecutor
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from tenacity import RetryError

from config import GEMINI_MODEL_OCR, MAX_TOKENS, EXECUTOR_WORKERS, API_CONCURRENCY, PDF_CHUNK_PAGES_GENERAL, PDF_CHUNK_PAGES_DRAWING, OCR_TEXT_FASTPATH_MIN_CHARS
from ocr_utils import retry_gemini_call
from gemini_client import get_client
from text_sanitizer import is_text_extraction_usable, detect_garble_reason, normalize_unicode_text

import logging
logger = logging.getLogger(__name__)

# 互換性のため
GEMINI_MODEL = GEMINI_MODEL_OCR

# Phase 2: API同時呼び出し上限（Semaphore）
# max_workersはスレッドプール全体のサイズ。実際のAPI呼び出しはSemaphoreで絞る。
_api_semaphore = threading.Semaphore(API_CONCURRENCY)


# ---------------------------------------------------------------------------
# Phase 1-A: PDF分割ヘルパー
# ---------------------------------------------------------------------------

def _split_pdf(filepath: str, doc_type: str = "general") -> List[Dict[str, Any]]:
    """PDFを分割し、テキスト抽出可能なページはfast path、そうでないものは画像ベースOCR用にチャンク化する。"""
    if doc_type == "drawing":
        chunk_size = PDF_CHUNK_PAGES_DRAWING
    else:
        chunk_size = PDF_CHUNK_PAGES_GENERAL

    chunks = []
    
    # 画像ファイルの場合は_split_pdfをバイパスして1ページのチャンクを作成する
    ext = Path(filepath).suffix.lower()
    if ext in (".png", ".jpg", ".jpeg"):
        from config import TEMP_CHUNK_DIR
        base_dir = Path(TEMP_CHUNK_DIR)
        os.makedirs(base_dir, exist_ok=True)
        
        # shutilを使ってコピーするか、パスをそのまま使う。ここではそのまま使う。
        chunks.append({
            "path": filepath,
            "mime_type": f"image/{ext[1:]}",
            "label": "Full Image",
            "index": 0,
            "start_page": 1,
            "end_page": 1,
            "page_count": 1,
            "is_temp": False,
            "type": "image"
        })
        return chunks

    try:
        reader = pypdf.PdfReader(filepath)
    except Exception as e:
        logger.error(f"Failed to read PDF {filepath}: {e}")
        # 画像として処理できないかフォールバック（ここは一旦エラーで返す）
        raise ValueError(f"Not a valid PDF file: {filepath}") from e

    total_pages = len(reader.pages)

    from config import TEMP_CHUNK_DIR
    base_dir = Path(TEMP_CHUNK_DIR)
    os.makedirs(base_dir, exist_ok=True)
    
    current_pdf_pages = []
    
    # 統計・ログ用
    stats_usable = 0
    stats_fallback = 0
    stats_reasons = {}
    
    def flush_pdf_pages():
        if not current_pdf_pages:
            return
        
        for i in range(0, len(current_pdf_pages), chunk_size):
            chunk_indices = current_pdf_pages[i:i+chunk_size]
            writer = pypdf.PdfWriter()
            for p in chunk_indices:
                writer.add_page(reader.pages[p])
            
            start_p = chunk_indices[0] + 1
            end_p = chunk_indices[-1] + 1
            chunk_filename = f".chunk_{chunk_indices[0]}_{uuid.uuid4().hex[:8]}.pdf"
            chunk_path = base_dir / chunk_filename
            
            with open(chunk_path, "wb") as f_out:
                writer.write(f_out)
                
            chunks.append({
                "path": str(chunk_path),
                "mime_type": "application/pdf",
                "label": f"Pages {start_p}-{end_p}",
                "index": chunk_indices[0],
                "start_page": start_p,
                "end_page": end_p,
                "page_count": len(chunk_indices),
                "is_temp": True,
                "type": "pdf"
            })
        current_pdf_pages.clear()

    for p in range(total_pages):
        page = reader.pages[p]
        text = ""
        try:
            text = page.extract_text()
        except Exception:
            pass
            
        reason = detect_garble_reason(text) if text else "too_short"
        usable = not bool(reason)
            
        if usable:
            stats_usable += 1
            text = normalize_unicode_text(text)
            flush_pdf_pages()
            start_p = p + 1
            end_p = p + 1
            formatted_text = f"[[PAGE_{start_p}]]\n{text.strip()}"
            chunks.append({
                "path": None,
                "mime_type": "text/plain",
                "label": f"Page {start_p} (Text Extraction)",
                "index": p,
                "start_page": start_p,
                "end_page": end_p,
                "page_count": 1,
                "is_temp": False,
                "type": "text",
                "extracted_text": formatted_text
            })
        else:
            stats_fallback += 1
            stats_reasons[reason] = stats_reasons.get(reason, 0) + 1
            logger.info(f"[OCR FastPath] page={p+1}/{total_pages} rejected reason={reason}")
            current_pdf_pages.append(p)
        
        if (p + 1) % 10 == 0:
            logger.info(f"[OCR FastPath] Progress: {p+1}/{total_pages} pages scanned...")
            
    flush_pdf_pages()
    
    logger.info(f"[OCR FastPath] Scan complete. usable_pages={stats_usable} fallback_pages={stats_fallback}. Total chunks: {len(chunks)}")
    
    chunks.sort(key=lambda x: x["index"])
    
    if len(chunks) == 1 and chunks[0].get("type") == "pdf" and chunks[0]["page_count"] == total_pages:
        if chunks[0]["is_temp"]:
            try:
                os.remove(chunks[0]["path"])
            except OSError:
                pass
        chunks[0].update({
            "path": filepath,
            "label": "Full Doc",
            "is_temp": False
        })

    return chunks


def _split_chunk(
    source_path: str,
    original_start_page: int,
    original_index: int,
) -> List[Dict[str, Any]]:
    """
    既存のチャンクPDFをさらに半分に分割して一時ファイルとして返す。
    MAX_TOKENSフォールバック時に使用する。インデックスは元のページ位置ベース。
    """
    from config import TEMP_CHUNK_DIR
    base_dir = Path(TEMP_CHUNK_DIR)
    os.makedirs(base_dir, exist_ok=True)

    reader = pypdf.PdfReader(source_path)
    actual_pages = len(reader.pages)
    half = actual_pages // 2

    split_points = [(0, half), (half, actual_pages)]
    sub_chunks = []

    for idx, (sp, ep) in enumerate(split_points):
        if sp >= ep:
            continue
        writer = pypdf.PdfWriter()
        for p in range(sp, ep):
            writer.add_page(reader.pages[p])

        chunk_filename = f".chunk_{original_index}_{idx}_{uuid.uuid4().hex[:8]}.pdf"
        chunk_path = base_dir / chunk_filename
        with open(chunk_path, "wb") as f_out:
            writer.write(f_out)

        actual_start = original_start_page + sp
        actual_end = original_start_page + ep - 1
        sub_chunks.append({
            "path": str(chunk_path),
            "mime_type": "application/pdf",
            "label": f"Pages {actual_start}-{actual_end}",
            "index": original_index + sp,   # ページ位置をindexに使うことでsort可能
            "start_page": actual_start,
            "end_page": actual_end,
            "page_count": ep - sp,
            "is_temp": True
        })

    return sub_chunks


# ---------------------------------------------------------------------------
# Phase 5: ASCII-safe upload helpers
# ---------------------------------------------------------------------------

def make_chunk_upload_name(version_id: str, chunk_index: int, ext: str) -> str:
    """外部送信用の安全なファイル名 (ASCII) を生成する。"""
    # version_id から、ASCIIの英数字、ハイフン、アンダースコア以外を除去（または置換）
    # isalnum() は日本語文字もTrueになるため、isascii() と組み合わせてチェックする
    safe_id = "".join([c if (c.isascii() and (c.isalnum() or c in "-_")) else "_" for c in version_id])
    if not safe_id or safe_id.strip("_") == "":
        safe_id = "unknown_version"
    
    # ext が . で始まらない場合（かつ空でない場合）は付与
    if ext and not ext.startswith("."):
        ext = "." + ext
        
    return f"ver_{safe_id}_chunk_{chunk_index:04d}{ext}"


# ---------------------------------------------------------------------------
# Phase 3 + 4 + 5: Gemini API呼び出しを3関数に分解
# ---------------------------------------------------------------------------

@retry_gemini_call(max_attempts=3)
def _upload_chunk(
    file_path: str, 
    mime_type: str,
    version_id: str = "unknown",
    chunk_index: int = 0,
    original_filename: Optional[str] = None
):
    """
    Phase 3 + 5: ファイルをGemini File APIにアップロードしてfile_refを返す。
    原本名 (non-ASCII) による UnicodeEncodeError を避けるため、内部IDベースの
    ASCIIファイル名にリネームして一時ファイル経由でアップロードする。
    """
    ext = Path(file_path).suffix
    safe_name = make_chunk_upload_name(version_id, chunk_index, ext)
    orig_name = original_filename or Path(file_path).name

    with _api_semaphore:
        client = get_client()
        with tempfile.TemporaryDirectory(prefix="ag_ocr_upload_") as tmp_dir:
            tmp_path = Path(tmp_dir) / safe_name
            shutil.copy2(file_path, tmp_path)
            
            logger.info(
                f"Uploading chunk to Gemini: {orig_name} -> {safe_name}",
                extra={
                    "version_id": version_id,
                    "chunk_index": chunk_index,
                    "original_filename": orig_name,
                    "outbound_filename": safe_name,
                    "mime_type": mime_type
                }
            )

            try:
                uploaded_file = client.files.upload(
                    file=str(tmp_path),
                    config=types.UploadFileConfig(
                        mime_type=mime_type,
                        display_name=safe_name  # 原本名は渡さない
                    )
                )
                logger.info(f"Successfully uploaded chunk: {safe_name}")
                return uploaded_file
            except Exception as e:
                err_str = str(e).lower()
                # UnicodeEncodeError や不正な形式は retry 不要
                if "ascii" in err_str and "encode" in err_str:
                    logger.error(f"NON-RETRYABLE: UnicodeEncodeError during upload for {orig_name}: {e}")
                    raise # tenorcity 等のラップがあれば non-retryable としてマークするのが理想だが、ここでは例外をそのまま投げる
                elif "unsupported" in err_str or "invalid" in err_str:
                    logger.error(f"NON-RETRYABLE: Input error for {orig_name}: {e}")
                    raise
                
                # それ以外（Timeout, 429, 5xx）は呼び出し側の @retry_gemini_call がリトライする
                logger.warning(f"RETRYABLE (maybe): Upload failed for {safe_name}: {e}")
                raise


def _wait_for_processing(file_ref, timeout: float = 120.0):
    """
    Phase 3 + 4: Geminiファイル処理完了まで待機する。
    Phase 4: 固定1秒ポーリングから指数バックオフ（0.3s→最大3.0s）に変更。
    """
    client = get_client()
    wait = 0.3
    elapsed = 0.0

    while file_ref.state.name == "PROCESSING":
        if elapsed >= timeout:
            raise Exception(f"File processing timeout ({timeout}s): {file_ref.name}")
        time.sleep(wait)
        elapsed += wait
        wait = min(wait * 1.5, 3.0)
        file_ref = client.files.get(name=file_ref.name)

    if file_ref.state.name == "FAILED":
        raise Exception("Google AI File processing failed")

    return file_ref


async def _wait_for_processing_async(file_ref, timeout: float = 120.0):
    """
    Phase 4: 非同期で file_ref が ACTIVE になるまで待機する。
    """
    loop = asyncio.get_running_loop()
    client = get_client()
    wait = 0.3
    elapsed = 0.0

    while file_ref.state.name == "PROCESSING":
        if elapsed >= timeout:
            raise Exception(f"File processing timeout ({timeout}s): {file_ref.name}")
        await asyncio.sleep(wait)
        elapsed += wait
        wait = min(wait * 1.5, 3.0)
        # client.files.get は同期APIなので executor で実行
        file_ref = await loop.run_in_executor(None, lambda name=file_ref.name: client.files.get(name=name))

    if file_ref.state.name == "FAILED":
        raise Exception("Google AI File processing failed")

    return file_ref


@retry_gemini_call(max_attempts=3)
def _generate_content(file_ref, model_name: str, prompt: str):
    """
    Phase 3: アップロード済みfile_refを使ってgenerate_contentを実行する。
    Semaphoreでレートリミット制御（Phase 2）。戻り値はresponseオブジェクト。
    """
    with _api_semaphore:
        client = get_client()
        response = client.models.generate_content(
            model=model_name,
            contents=[prompt, file_ref],
            config=types.GenerateContentConfig(
                temperature=0.0,
                max_output_tokens=MAX_TOKENS
            )
        )

    # 空レスポンスガード（コンテンツフィルタ等）
    if not response.candidates or not response.candidates[0].content.parts:
        raise ValueError("Gemini returned empty response (possibly content filtered)")

    return response


# ---------------------------------------------------------------------------
# プロンプトテンプレート
# ---------------------------------------------------------------------------

DRAWING_OCR_PROMPT_TEMPLATE = """
あなたは建築設計の専門家です。
この図面を以下の形式で正確にテキスト化・抽出してください。不確かな推論はなるべく避け、図面に記載されている文字・数値を忠実に抽出してください：

## 図面種別
（記載がある場合）

## スケール・方位
（記載がある場合）

## 寸法・注記・仕様
（図面内の文字情報、寸法値、材料、特記事項を忠実に全て抽出・列挙）

PAGE MARKERS: This chunk contains pages {start_page} to {end_page} of the original document.
At the very beginning of each page's content, output the marker [[PAGE_N]] on its own line,
where N is the actual page number in the original document (starting from {start_page}).
For example, before the first page's content output [[PAGE_{start_page}]], and increment the number for subsequent pages.
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
       For example, before the first page's content output [[PAGE_{start_page}]], and increment the number for each subsequent page.
    """


# ---------------------------------------------------------------------------
# Phase 1-B: MAX_TOKENSフォールバック付きOCR
# ---------------------------------------------------------------------------

def _build_prompt(chunk: Dict[str, Any], doc_type: str) -> str:
    """チャンク情報からプロンプトを生成する。"""
    start_page = chunk.get("start_page", 1)
    end_page = chunk.get("end_page", start_page)
    if doc_type == "drawing":
        return DRAWING_OCR_PROMPT_TEMPLATE.format(start_page=start_page, end_page=end_page)
    return GENERAL_OCR_PROMPT_TEMPLATE.format(start_page=start_page, end_page=end_page)


def _ocr_with_adaptive_fallback(
    chunk: Dict[str, Any],
    file_ref,
    doc_type: str,
    version_id: str = "unknown",
    original_filename: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Phase 1-B: アップロード済みfile_refでOCRを実行する。
    MAX_TOKENS超過を検知した場合はチャンクを半分に再分割してリトライ（再帰）。
    1ページでMAX_TOKENSに達した場合は警告ログを出して結果をそのまま返す。
    戻り値: 結果dictのリスト（再分割時は複数要素。通常時は1要素）。
    """
    prompt = _build_prompt(chunk, doc_type)

    try:
        response = _generate_content(file_ref, GEMINI_MODEL, prompt)
    except Exception as e:
        logger.error(f"OCR Failed for chunk {chunk['label']}: {e}", exc_info=True)
        return [{
            "text": f"\n> ⚠️ **[OCR Error]** Failed to retrieve content for **{chunk['label']}** after multiple retries.\n> Error: {str(e)}\n",
            "index": chunk["index"],
            "label": chunk["label"],
            "start_page": chunk.get("start_page", chunk["index"] + 1),
            "success": False,
        }]

    finish_reason = response.candidates[0].finish_reason
    is_max_tokens = str(finish_reason) in ("FinishReason.MAX_TOKENS", "MAX_TOKENS", "2")

    if is_max_tokens:
        page_count = chunk.get("page_count", chunk.get("end_page", 1) - chunk.get("start_page", 1) + 1)
        half = page_count // 2

        if half < 1:
            logger.error(
                f"1ページでMAX_TOKENS到達: {chunk['label']} — 結果が不完全な可能性あり"
            )
            return [{
                "text": normalize_unicode_text(response.text),
                "index": chunk["index"],
                "label": chunk["label"],
                "start_page": chunk.get("start_page", chunk["index"] + 1),
                "success": True,
                "truncated": True,
            }]

        logger.warning(
            f"MAX_TOKENS到達: {chunk['label']} ({page_count}ページ) → 半分に再分割してリトライ"
        )
        sub_chunks = _split_chunk(chunk["path"], chunk.get("start_page", 1), chunk["index"])

        results = []
        for sc in sub_chunks:
            try:
                sc_file_ref = _upload_chunk(
                    sc["path"], 
                    sc["mime_type"], 
                    version_id=version_id, 
                    chunk_index=sc["index"],
                    original_filename=original_filename
                )
                sc_file_ref = _wait_for_processing(sc_file_ref)
                sub_results = _ocr_with_adaptive_fallback(
                    sc, 
                    sc_file_ref, 
                    doc_type, 
                    version_id=version_id,
                    original_filename=original_filename
                )
                results.extend(sub_results)
            except Exception as e:
                logger.error(f"Sub-chunk OCR failed for {sc['label']}: {e}", exc_info=True)
                results.append({
                    "text": f"\n> ⚠️ **[OCR Error]** Failed for **{sc['label']}**.\n> Error: {str(e)}\n",
                    "index": sc["index"],
                    "label": sc["label"],
                    "start_page": sc.get("start_page", sc["index"] + 1),
                    "success": False,
                })
            finally:
                if sc.get("is_temp"):
                    try:
                        os.remove(sc["path"])
                    except OSError:
                        pass
        return results

    # 正常終了（finish_reason チェック: 警告ログ）
    return [{
        "text": normalize_unicode_text(response.text),
        "index": chunk["index"],
        "label": chunk["label"],
        "start_page": chunk.get("start_page", chunk["index"] + 1),
        "success": True,
    }]


def _process_chunk(chunk: Dict[str, Any], model_name: str, doc_type: str = "catalog") -> Dict[str, Any]:
    """
    後方互換ラッパー。内部的には_ocr_with_adaptive_fallbackを使用する。
    単一のチャンクを処理し、最初の結果のみを返す（旧インターフェース互換）。
    """
    try:
        file_ref = _upload_chunk(
            chunk["path"], 
            chunk["mime_type"],
            version_id="legacy",
            chunk_index=chunk["index"]
        )
        file_ref = _wait_for_processing(file_ref)
        results = _ocr_with_adaptive_fallback(
            chunk, 
            file_ref, 
            doc_type,
            version_id="legacy"
        )
        return results[0] if results else {
            "text": "", "index": chunk["index"], "success": False
        }
    except Exception as e:
        logger.error(f"OCR Failed for chunk {chunk['label']}: {e}", exc_info=True)
        return {
            "text": f"\n> ⚠️ **[OCR Error]** Failed for **{chunk['label']}**.\n> Error: {str(e)}\n",
            "index": chunk["index"],
            "success": False,
        }
    finally:
        if chunk.get("is_temp"):
            try:
                os.remove(chunk["path"])
            except OSError:
                pass


# ---------------------------------------------------------------------------
# Phase 3: asyncio パイプライン処理
# ---------------------------------------------------------------------------

async def _process_all_chunks_pipelined(
    chunks: List[Dict[str, Any]],
    doc_type: str,
    executor: ThreadPoolExecutor,
    repo,
    filepath: str,
    version_id: str = "unknown",
) -> List[Dict[str, Any]]:
    """
    Phase 3: 真のストリーミングパイプライン(streaming pipeline)。
    各チャンクを個別の非同期タスクとして upload -> wait -> OCR を直列化し、
    完了したものからページ単位で進捗を更新する。
    """
    loop = asyncio.get_running_loop()
    
    progress = {"pages": 0}
    lock = asyncio.Lock()
    
    async def process_single_chunk(chunk: Dict[str, Any]) -> List[Dict[str, Any]]:
        
        if chunk.get("type") == "text":
            result = [{
                "text": chunk["extracted_text"],
                "index": chunk["index"],
                "label": chunk["label"],
                "start_page": chunk.get("start_page", chunk["index"] + 1),
                "success": True,
            }]
        else:
            try:
                orig_filename = Path(filepath).name
                file_ref = await loop.run_in_executor(
                    executor, 
                    _upload_chunk, 
                    chunk["path"], 
                    chunk["mime_type"],
                    version_id,
                    chunk["index"],
                    orig_filename
                )
                file_ref = await _wait_for_processing_async(file_ref)
                
                result = await loop.run_in_executor(
                    executor, 
                    _ocr_with_adaptive_fallback, 
                    chunk, 
                    file_ref, 
                    doc_type,
                    version_id,
                    orig_filename
                )
            except Exception as e:
                logger.error(f"Processing failed for chunk {chunk['label']}: {e}", exc_info=True)
                result = [{
                    "text": f"\n> ⚠️ **[System Error]** Processing failed for **{chunk['label']}**.\n> Error: {str(e)}\n",
                    "index": chunk["index"],
                    "label": chunk["label"],
                    "start_page": chunk.get("start_page", chunk["index"] + 1),
                    "success": False,
                }]
            finally:
                if chunk.get("is_temp"):
                    try:
                        os.remove(chunk["path"])
                    except OSError:
                        pass
                        
        async with lock:
            progress["pages"] += chunk.get("page_count", 1)
            repo.update_processed_pages(filepath, progress["pages"])
            
        return result

    logger.info(f"[Pipeline] Starting streaming processing for {len(chunks)} chunks...")
    tasks = [asyncio.create_task(process_single_chunk(c)) for c in chunks]
    
    ocr_results = []
    # 完了したものから回収（順序は後でソートする）
    for done_task in asyncio.as_completed(tasks):
        result = await done_task
        ocr_results.append(result)

    # フラット化
    flat_results: List[Dict[str, Any]] = []
    for sublist in ocr_results:
        flat_results.extend(sublist)

    return flat_results


# ---------------------------------------------------------------------------
# 既存の仕上げ処理（変更なし）
# ---------------------------------------------------------------------------

def finalize_processing(
    filepath: str, 
    output_path: str, 
    markdown_text: str, 
    source_pdf_hash: str = "",
    version_id: str = ""
):
    """
    生成されたMarkdownテキストを元に、分類・Frontmatter付与・フォルダ移動・インデックス登録を行う
    """
    try:
        from metadata_repository import MetadataRepository
        repo = MetadataRepository()
        from classifier import DocumentClassifier
        # import here to avoid circular dependency if possible
        from config import KNOWLEDGE_BASE_DIR
        import shutil
        from pathlib import Path
        import traceback
        import time


        # 分類実行
        classifier = DocumentClassifier()
        meta_input = {'title': Path(filepath).stem}
        classification_result = classifier.classify(markdown_text[:5000], meta_input)
        
        import hashlib
        # ハッシュIDがない場合は生成 (互換性のため残す)
        if not source_pdf_hash:
            with open(filepath, 'rb') as f:
                source_pdf_hash = hashlib.sha256(f.read()).hexdigest()

        # Google Driveへのアップロードは別ジョブに分離 (ここでは実行しない)
        drive_file_id = ""

        # Frontmatter生成
        extra_meta = {
            "source_pdf": source_pdf_hash,
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
        
        new_pdf_path = target_pdf_dir / f"{source_pdf_hash}{Path(filepath).suffix}"
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
            logger.info(f"自動分類: PDFは {PDF_STORAGE_DIR}、MDは {category_path} へ移動しました")
            if pdf_moved:
                # status_mgr は廃止し、repo を使用
                repo.update_ingest_stage(filepath, "completed") # 暫定
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
            logger.info(f"自動分類: 移動不要 ({category_path})")
        
        # 自動インデックス登録
        try:
            from indexer import index_file
            logger.info(f"インデックス登録開始: {new_md_path}")
            index_file(str(new_md_path))
        except Exception as e:
            logger.error(f"自動インデックス登録エラー ({new_md_path}): {e}", exc_info=True)

        if version_id:
            repo.update_ingest_stage(filepath, "indexing_completed")
            repo.mark_as_searchable(filepath)
        
        return filepath, output_path

    except Exception as e:
        logger.error(f"自動分類・メタデータ付与エラー ({filepath}): {e}", exc_info=True)
        return filepath, output_path


# ---------------------------------------------------------------------------
# メインエントリーポイント
# ---------------------------------------------------------------------------
def process_pdf_background(
    filepath: str, 
    output_path: str, 
    doc_type: str = "catalog", 
    source_pdf_hash: str = "",
    version_id: str = "",
    blocks_output_path: str = ""
):
    """
    指定されたPDFをOCR処理してMarkdownに変換し、保存する（バックグラウンド実行用）。
    doc_type: 'catalog' | 'drawing' | 'spec' | 'law' — プロンプト選択に使用

    Phase 3: asyncioパイプラインで全チャンクの並列アップロード＋OCRを実行する。
    """
    logger.info(f"OCR開始: {filepath} -> {output_path} (doc_type={doc_type}, hash={source_pdf_hash}, version={version_id})")
    from metadata_repository import MetadataRepository
    repo = MetadataRepository()

    try:
        # 1. PDF分割（Phase 1 + 2: text extraction fast path + chunking）
        chunks = _split_pdf(filepath, doc_type)
        
        total_pages = sum(c.get("page_count", 1) for c in chunks)
        fast_path_pages = sum(c.get("page_count", 1) for c in chunks if c.get("type") == "text")
        logger.info(f"[OCR Fast Path] {fast_path_pages} text pages extracted without API / Sent {total_pages - fast_path_pages} pages to OCR.")

        # ステータス初期化 (総ページ数ベース)
        repo.update_ingest_stage(filepath, "processing", total_pages=total_pages)

        # 2. asyncioパイプラインで並列OCR（Phase 2: max_workers=EXECUTOR_WORKERS）
        with ThreadPoolExecutor(max_workers=EXECUTOR_WORKERS) as executor:
            try:
                results = asyncio.run(
                    asyncio.wait_for(
                    _process_all_chunks_pipelined(
                        chunks, doc_type, executor, repo, filepath, version_id
                    ),
                    timeout=1800  # 全体上限30分
                    )
                )
            except asyncio.TimeoutError:
                logger.error(f"OCR全体タイムアウト（1800秒）: {filepath}")
                repo.fail_processing(filepath, "OCR overall timeout: exceeded 1800 seconds")
                return

        # 3. 結合（index順にソートして全結果をMarkdown化）
        results.sort(key=lambda x: x["index"])
        markdown_text = f"# {Path(filepath).stem}\n\n"

        for r in results:
            label = r.get("label", f"Part {r['index'] + 1}")
            
            # [[PAGE_N]] はプロンプト出力・抽出テキスト自体に含むため重複追加しない
            markdown_text += f"## {label}\n\n"
            markdown_text += r.get("text", "")
            markdown_text += "\n\n---\n"
            
        markdown_text = normalize_unicode_text(markdown_text)

        # 4. 保存（一旦）
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(markdown_text)
            
        if blocks_output_path:
            import json
            with open(blocks_output_path, "w", encoding="utf-8") as bf:
                json.dump(results, bf, ensure_ascii=False, indent=2)

        logger.info(f"OCR完了・保存: {output_path}")

        # 5. 次のステージへディスパッチ (Phase 3)
        repo.update_ingest_stage(filepath, "ocr_completed")
        
        from ingestion_orchestrator import IngestionOrchestrator
        orchestrator = IngestionOrchestrator()
        
        logger.info(f"Dispatching to Metadata Enrichment stage...")
        threading.Thread(
            target=orchestrator.dispatch_next_stage,
            args=(version_id, "ocr_completed"),
            kwargs={
                "original_filepath": filepath,  # Bug fix: 元のアップロードパスをoriginal_filepathとして明示的に渡す
                "filepath": filepath,
                "output_md_path": output_path,
                "output_blocks_path": blocks_output_path,
                "source_pdf_hash": source_pdf_hash
            },
            daemon=True
        ).start()

    except Exception as e:
        logger.error(f"OCRプロセス全体でエラー ({filepath}): {e}", exc_info=True)
        repo.fail_processing(filepath, str(e))
    finally:
        # 最終クリーンアップ (成功・失敗に関わらず一時ファイルを削除)
        if 'chunks' in locals():
            for c in chunks:
                if c.get("is_temp") and c.get("path") and os.path.exists(c["path"]):
                    try:
                        os.remove(c["path"])
                    except OSError:
                        pass
