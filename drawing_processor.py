import fitz  # PyMuPDF
import google.generativeai as genai
import os
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
from config import VISION_ANALYSIS_MODEL, GEMINI_API_KEY

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

def get_gemini_model():
    return genai.GenerativeModel(VISION_ANALYSIS_MODEL)

def process_page_drawing(page_num, img_data):
    """
    図面1ページをVision APIで解析する
    """
    try:
        model = get_gemini_model()
        
        image_part = {
            "mime_type": "image/png",
            "data": img_data
        }
        
        prompt = """
        あなたは建築図面の専門家です。この図面画像を詳細に分析し、以下の情報を抽出してください。
        
        1. **図面の種類**: (例: 1階平面図、立面図、断面詳細図)
        2. **主要な部屋名・スペース**: 図面に記載されている部屋名やエリア名を列挙してください。
        3. **仕上げ情報**: 壁、床、天井などの仕上げ記載があれば抽出してください。
        4. **特記事項**: 寸法、注釈、特記仕様などで重要なもの。
        
        出力フォーマット:
        Markdown形式で出力してください。見出しを適切に使ってください。
        """

        response = model.generate_content([prompt, image_part])
        return {
            "page": page_num,
            "text": response.text,
            "index": page_num - 1
        }
    except Exception as e:
        print(f"Error processing drawing page {page_num}: {e}")
        return {
            "page": page_num,
            "text": f"[Error on Page {page_num}: {e}]",
            "index": page_num - 1
        }

def process_drawing_pdf(pdf_path: str) -> str:
    """
    図面PDF全体を処理し、Markdownテキストを返す
    """
    doc = fitz.open(pdf_path)
    total_pages = doc.page_count
    results = []

    print(f"Processing Drawing: {os.path.basename(pdf_path)} ({total_pages} pages)")

    with ThreadPoolExecutor(max_workers=3) as executor: # 図面解析は重いので並列数控えめ
        futures = []
        for i in range(total_pages):
            page = doc.load_page(i)
            pix = page.get_pixmap(dpi=150) # 図面は詳細が必要なので少し解像度確保
            img_data = pix.tobytes("png")
            futures.append(executor.submit(process_page_drawing, i + 1, img_data))

        for future in tqdm(as_completed(futures), total=total_pages, desc="Analyzing Drawings"):
            results.append(future.result())
    
    doc.close()
    
    # ページ順にソート
    results.sort(key=lambda x: x['index'])
    
    # Markdown結合
    final_markdown = f"# 図面解析結果: {os.path.basename(pdf_path)}\n\n"
    
    # Frontmatter (簡易的な分類タグ)
    final_markdown = "---\n"
    final_markdown += f"filename: {os.path.basename(pdf_path)}\n"
    final_markdown += "type: DRAWING\n"
    final_markdown += "---\n\n" + final_markdown

    for r in results:
        final_markdown += f"\n\n[[PAGE_{r['page']}]]\n"
        final_markdown += f"## Page {r['page']}\n\n"
        final_markdown += r['text']
        final_markdown += "\n\n---\n"

    return final_markdown

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(process_drawing_pdf(sys.argv[1]))
