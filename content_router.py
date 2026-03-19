from google.genai import types
from pathlib import Path
import json
import os
import tempfile
import shutil
import logging
from ocr_utils import retry_gemini_call
from config import GEMINI_API_KEY, GEMINI_MODEL
from gemini_client import get_client

logger = logging.getLogger(__name__)

class ContentRouter:
    def __init__(self, model_name=None):
        self.model_name = model_name or GEMINI_MODEL
        if not GEMINI_API_KEY:
             raise ValueError("GEMINI_API_KEY is not set")

    def classify(self, file_path: Path) -> str:
        """
        ファイルをGemini Flashで分析し、5種類に分類する。
        戻り値: 'Document' | 'Drawing' | 'Mixed' | 'Audio' | 'Video'

        Audio/VideoはMIME/拡張子で即判定（Gemini API不要）。
        PDF/画像はGemini Flashで Drawing / Document / Mixed に分類する。
        """
        file_path = Path(file_path)
        ext = file_path.suffix.lower()

        # 音声・動画はファイル拡張子で即判定（Gemini API不要）
        if ext in (".mp3", ".wav"):
            logger.info(f"Classification: Audio (by extension) for {file_path.name}")
            return "Audio"
        if ext in (".mp4", ".mov"):
            logger.info(f"Classification: Video (by extension) for {file_path.name}")
            return "Video"

        return self._classify_with_ai(file_path)

    @retry_gemini_call()
    def _classify_with_ai(self, file_path: Path) -> str:
        """PDF/画像をGemini Flashで Drawing / Document / Mixed に分類する。"""
        # ファイル存在確認（Google Drive eviction等によるファイル消失を早期検出）
        if not file_path.exists():
            raise FileNotFoundError(f"File not found before classification: {file_path}")

        client = get_client()

        # 日本語ファイル名対策: httpxはHTTPヘッダにASCII以外を送信できないため、
        # 一時的にASCII名のコピーを作成してアップロードする
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
            - Document: テキストが主体のPDF、仕様書、技術基準書、報告書など。
            - Mixed: テキストと図表・写真が混在するカタログ、製品技術資料、施工マニュアルなど。

            出力はJSON形式のみで、キー "type" に "Drawing"、"Document"、または "Mixed" を設定してください。
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
                classification = result.get("type", "Document")
                if classification not in ["Drawing", "Document", "Mixed"]:
                    classification = "Document"
                logger.info(f"AI Classification result for {file_path.name}: {classification}")
                return classification
            except json.JSONDecodeError as e:
                logger.warning(f"JSON Decode Error in classification for {file_path.name}: {e}")
                return "Document"
        finally:
            if temp_dir:
                shutil.rmtree(temp_dir, ignore_errors=True)

