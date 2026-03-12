
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=API_KEY)
MODEL_NAME = "gemini-3-flash-preview"

print(f"Testing generation with {MODEL_NAME}...")

try:
    response = client.models.generate_content(
        model=MODEL_NAME,
        contents="Draw a cute cat sticker.",
        config=types.GenerateContentConfig(
            response_modalities=['IMAGE', 'TEXT']
        )
    )
    
    print("Response received.")
    image_found = False
    if response.candidates and response.candidates[0].content.parts:
        for part in response.candidates[0].content.parts:
            if part.inline_data:
                print("SUCCESS: Image generated!")
                image_found = True
            if part.text:
                print(f"Text output: {part.text}")
                
    if not image_found:
        print("FAILURE: No image found in response.")

except Exception as e:
    print(f"CRITICAL ERROR: {e}")
