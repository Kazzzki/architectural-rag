import google.generativeai as genai
from config import GEMINI_API_KEY
import sys

genai.configure(api_key=GEMINI_API_KEY)

models_to_test = ["models/text-embedding-004", "models/embedding-001", "models/gemini-embedding-001"]

for m in models_to_test:
    try:
        res = genai.embed_content(model=m, content="Hello World", task_type="retrieval_document")
        print(f"SUCCESS: {m}")
    except Exception as e:
        print(f"FAILED: {m} - {e}")
