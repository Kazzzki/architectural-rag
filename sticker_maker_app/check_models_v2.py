
import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)

print("Listing models...")
try:
    # Simpler listing that just prints names
    for m in client.models.list(config={"page_size": 100}):
        print(f"Model: {m.name}")
        # print(f" - Display name: {m.display_name}")
except Exception as e:
    print(f"Error: {e}")
