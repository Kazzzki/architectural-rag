import requests
import json
import sys

URL = "http://localhost:8000/api/chat/stream"
AUTH = ('admin', 'antigravity') # wait, should figure out actual pwd

import os
from dotenv import load_dotenv
load_dotenv()

app_pwd = os.environ.get("APP_PASSWORD", "antigravity")
AUTH = ('admin', app_pwd)

queries = [
    "建蔽率の計算方法の原則について教えてください",
    "S造の柱の耐荷重や仕様について注意点を教えてください",
    "配置図など、研修所の計画をする上での主要な動線計画の考え方は？"
]

for i, q in enumerate(queries, 1):
    print(f"\n[{i}] Query: {q}")
    print("-" * 50)
    try:
        response = requests.post(
            URL, 
            json={"question": q, "category": None, "quick_mode": False}, 
            auth=AUTH,
            stream=True
        )
        if response.status_code != 200:
            print(f"Error {response.status_code}: {response.text}")
            continue
            
        full_text = ""
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    data_str = decoded_line[6:]
                    if data_str == '[DONE]':
                        break
                    try:
                        data = json.loads(data_str)
                        if 'text' in data:
                            chunk_text = data['text']
                            full_text += chunk_text
                            print(chunk_text, end='', flush=True)
                    except json.JSONDecodeError:
                        pass
        print("\n" + "=" * 50)
    except Exception as e:
        print(f"Request failed: {e}")
