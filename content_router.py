from google.genai import types
from pathlib import Path
import json
import os
import tempfile
import shutil
from ocr_utils import retry_gemini_call
from config import GEMINI_API_KEY, GEMINI_MODEL
from gemini_client import get_client

class ContentRouter:
    def __init__(self, model_name=None):
        self.model_name = model_name or GEMINI_MODEL
        if not GEMINI_API_KEY:
             raise ValueError("GEMINI_API_KEY is not set")

    @retry_gemini_call()
    def classify(self, file_path: Path) -> str:
        """
        ファイルをGemini Flashで分析し、'Drawing' または 'Document' に分類する。
        """
        # ファイル存在確認（Google Drive eviction等によるファイル消失を早期検出）
        if not Path(file_path).exists():
            raise FileNotFoundError(f"File not found before classification: {file_path}")

        client = get_client()

        # 日本語ファイル名対策: httpxはHTTPヘッダにASCII以外を送信できないため、
        # 一時的にASCII名のコピーを作成してアップロードする
        file_path = Path(file_path)
        upload_path = file_path
        temp_dir = None

        try:
            # ファイル名がASCII以外の文字を含む場合、一時コピーを作成
            if not file_path.name.isascii():
                temp_dir = tempfile.mkdtemp(prefix="content_router_")
                safe_name = f"upload{file_path.suffix}"
                upload_path = Path(temp_dir) / safe_name
                shutil.copy2(str(file_path), str(upload_path))

            # ファイルアップロード
            uploaded_file = client.files.upload(file=str(upload_path))

            prompt = """
            このファイルの内容を確認し、以下の基準で分類してください。

            - Drawing: 建築図面、CAD図面、詳細図、矩計図、平面図など、図形情報が主体のもの。
            - Document: カタログ、仕様書、技術基準書、報告書、テキストが主体のもの。

            出力はJSON形式のみで、キー "type" に "Drawing" または "Document" を設定してください。
            それ以外の余計なテキストは含めないでください。
            """

            response = client.models.generate_content(
                model=self.model_name,
                contents=[prompt, uploaded_file],
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )

            try:
                result = json.loads(response.text)
                classification = result.get("type", "Document")  # Default to Document
                if classification not in ["Drawing", "Document"]:
                    classification = "Document"
                return classification
            except json.JSONDecodeError:
                # JSONパース失敗時はデフォルトとしてDocument
                return "Document"
        finally:
            # 一時ファイルのクリーンアップ
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

