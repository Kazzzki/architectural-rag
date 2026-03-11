from google import genai
from config import GEMINI_API_KEY
from threading import Lock

_client = None
_client_lock = Lock()


def get_client() -> genai.Client:
    global _client
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY is not set in environment variables or config.")
    with _client_lock:
        if _client is None:
            _client = genai.Client(api_key=GEMINI_API_KEY)
        return _client


def reconfigure(api_key: str):
    """APIキー更新時にクライアントを再生成"""
    global _client
    with _client_lock:
        _client = genai.Client(api_key=api_key)
