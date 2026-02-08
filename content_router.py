import google.generativeai as genai
from pathlib import Path
import json
import os
from ocr_utils import retry_gemini_call

class ContentRouter:
    def __init__(self, model_name="gemini-1.5-flash"):
        self.model_name = model_name
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
             raise ValueError("GEMINI_API_KEY is not set")
        genai.configure(api_key=self.api_key)

    @retry_gemini_call()
    def classify(self, file_path: Path) -> str:
        """
        ファイルをGemini Flashで分析し、'Drawing' または 'Document' に分類する。
        """
        model = genai.GenerativeModel(self.model_name)
        
        # ファイルアップロード
        uploaded_file = genai.upload_file(file_path)
        
        prompt = """
        このファイルの内容を確認し、以下の基準で分類してください。
        
        - Drawing: 建築図面、CAD図面、詳細図、矩計図、平面図など、図形情報が主体のもの。
        - Document: カタログ、仕様書、技術基準書、報告書、テキストが主体のもの。
        
        出力はJSON形式のみで、キー "type" に "Drawing" または "Document" を設定してください。
        それ以外の余計なテキストは含めないでください。
        """
        
        response = model.generate_content(
            [prompt, uploaded_file],
            generation_config={"response_mime_type": "application/json"}
        )
        
        try:
            result = json.loads(response.text)
            classification = result.get("type", "Document") # Default to Document
            if classification not in ["Drawing", "Document"]:
                classification = "Document"
            return classification
        except json.JSONDecodeError:
            # JSONパース失敗時はデフォルトとしてDocument
            return "Document"
