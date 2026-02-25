
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    print("Error: GEMINI_API_KEY not found")
    exit(1)

client = genai.Client(api_key=api_key)

try:
    print("Listing available models...")
    for m in client.models.list():
        if hasattr(m, 'supported_generation_methods') and 'generateContent' in (m.supported_generation_methods or []):
            print(f"- {m.name}")
        elif hasattr(m, 'name'):
            print(f"- {m.name}")
except Exception as e:
    print(f"Error listing models: {e}")
