import sys; sys.path.insert(0, '.')
import glob
from ocr_processor import _split_pdf, _call_gemini_with_retry
from config import GEMINI_MODEL_OCR
import traceback

pdfs = glob.glob('data/input/*.pdf') + glob.glob('knowledge_base/00_未分類/*.pdf')
if not pdfs:
    print("テスト対象PDFなし。小さなPDFをdata/input/に配置して再実行してください。")
    sys.exit(1)

test_pdf = pdfs[0]
print(f"テスト対象: {test_pdf}")

from content_router import ContentRouter
try:
    router = ContentRouter()
    result = router.classify(test_pdf)
    print(f"分類結果: {result}")
except Exception as e:
    print(f"[FAIL] ContentRouter.classify エラー: {type(e).__name__}: {e}")

try:
    chunks = _split_pdf(test_pdf)
    print(f"チャンク数: {len(chunks)}")
    chunk = chunks[0]
    prompt = "このPDFの最初のページのテキストを抽出してください。"
    text = _call_gemini_with_retry(GEMINI_MODEL_OCR, chunk['path'], chunk['mime_type'], prompt)
    print(f"[OK] OCR成功。文字数: {len(text)}")
    print(f"冒頭100文字: {text[:100]}")
except Exception as e:
    print(f"[FAIL] OCRエラー: {type(e).__name__}: {e}")
    traceback.print_exc()
