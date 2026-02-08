import fitz  # PyMuPDF
import google.generativeai as genai
import os
import json
from typing import Literal

# Configure Gemini API
# 実際のAPIキーは環境変数から読み込むことを想定
if "GOOGLE_API_KEY" not in os.environ:
    # 開発用フォールバック（本番では削除推奨）
    pass

def get_gemini_model():
    # Gemini 3.0 Flash がまだ利用できない場合は 2.0 Flash または 1.5 Flash を使用
    # ここでは利用可能性が高い gemini-2.0-flash-exp を指定し、失敗したら gemini-1.5-flash にフォールバックするロジックを入れるか、
    # ユーザー指示通り一旦モデル名を指定する。
    return genai.GenerativeModel('gemini-2.0-flash-exp') 

def route_content(pdf_path: str) -> Literal["DRAWING", "DOCUMENT"]:
    """
    PDFの1ページ目を画像化し、Geminiで図面か文書かを判定する。
    """
    try:
        doc = fitz.open(pdf_path)
        if doc.page_count < 1:
            return "DOCUMENT" # 空のPDFなどは文書扱い（あるいはエラー）

        page = doc.load_page(0)
        pix = page.get_pixmap()
        img_data = pix.tobytes("png") # 画像データ(bytes)を取得
        
        doc.close()

        # 画像オブジェクトの作成 (Gemini API用)
        # genai.GenerativeModel.generate_content は bytes を直接受け取れない場合があるため、
        # PIL Imageにするか、適切なBlob形式にする必要がある。
        # ここでは単純化のため、一時ファイルを作らずにメモリ上で処理したいが、
        # genaiの仕様に合わせて辞書形式で渡す。
        
        image_part = {
            "mime_type": "image/png",
            "data": img_data
        }

        model = get_gemini_model()
        prompt = """
        以下の画像を分析し、このドキュメントが「建築図面 (Architecture Drawing)」か「一般的な文書 (Text Document)」かを判定してください。
        
        判定基準:
        - DRAWING: 平面図、立面図、断面図、矩計図、詳細図など、線画と寸法が主体のアウトプット。
        - DOCUMENT: 仕様書、契約書、計算書、報告書、カタログ、法規チェックリストなど、テキストが主体のもの。表が含まれていても、全体がテキストベースならDOCUMENTとする。
        
        回答は以下のJSON形式のみで出力してください。Markdownのコードブロックは不要です。
        { "type": "DRAWING" } または { "type": "DOCUMENT" }
        """

        response = model.generate_content([prompt, image_part])
        
        text = response.text.strip()
        # JSONパース（Markdownコードブロック除去）
        if text.startswith("```json"):
            text = text[7:-3].strip()
        elif text.startswith("```"):
            text = text[3:-3].strip()
            
        result = json.loads(text)
        return result.get("type", "DOCUMENT")

    except Exception as e:
        print(f"Content routing failed for {pdf_path}: {e}")
        # エラー時は安全側に倒して DOCUMENT とする（OCRで無理やり読む）
        return "DOCUMENT"

if __name__ == "__main__":
    # テスト用
    import sys
    if len(sys.argv) > 1:
        print(route_content(sys.argv[1]))
