"""
routers/transcribe.py — Gemini 音声文字起こし API

POST /api/transcribe   multipart/form-data で音声ファイルを受け取り
                       Gemini 3-flash-preview で日本語テキストに変換して返す
"""
import logging

from fastapi import APIRouter, File, HTTPException, UploadFile
from google.genai import types

from gemini_client import get_client

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Transcribe"])


@router.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """音声ファイルを Gemini で文字起こし"""
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="音声データが空です")

    # ブラウザの MediaRecorder は audio/webm を送ってくる
    mime_type = file.content_type or "audio/webm"

    try:
        client = get_client()
        response = client.models.generate_content(
            model="gemini-3-flash-preview",
            contents=[
                types.Part(inline_data=types.Blob(mime_type=mime_type, data=audio_bytes)),
                types.Part(
                    text=(
                        "この音声を日本語でそのまま文字起こしてください。"
                        "句読点をつけて自然な日本語にしてください。"
                        "余計な説明・補足・翻訳は不要です。文字起こし結果のテキストのみ返してください。"
                    )
                ),
            ],
        )
        text = (response.text or "").strip()
        return {"text": text}
    except Exception as e:
        logger.error(f"Gemini transcribe error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"文字起こしエラー: {str(e)}")
