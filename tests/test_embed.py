"""
embedding モデルの疎通確認スクリプト（新SDK版）
"""
from google import genai
from config import GEMINI_API_KEY, EMBEDDING_MODEL

client = genai.Client(api_key=GEMINI_API_KEY)

models_to_test = [EMBEDDING_MODEL, "models/text-embedding-004"]

for m in models_to_test:
    try:
        res = client.models.embed_content(model=m, contents="Hello World")
        print(f"SUCCESS: {m}")
    except Exception as e:
        print(f"FAILED: {m} - {e}")
