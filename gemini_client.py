"""
Shared Google Gemini API client (google.genai SDK)
全モジュールからインポートして使用する。
APIキーが更新された場合は reconfigure() を呼び出すこと。
"""
from google import genai
from config import GEMINI_API_KEY

_client = genai.Client(api_key=GEMINI_API_KEY)


def get_client() -> genai.Client:
    return _client


def reconfigure(api_key: str):
    """APIキー更新時にクライアントを再生成"""
    global _client
    _client = genai.Client(api_key=api_key)
