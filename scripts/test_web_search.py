
import requests
import json

def test_web_search():
    url = "http://localhost:8000/api/chat/stream"
    payload = {
        "question": "今日の東京の天気は？",
        "use_web_search": True,
        "use_rag": False,
        "model": "gemini-2.0-flash-exp"
    }
    
    print(f"Testing with payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(url, json=payload, stream=True)
        response.raise_for_status()
        
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode('utf-8')
                if decoded_line.startswith('data: '):
                    data = json.loads(decoded_line[6:])
                    if data.get('type') == 'answer':
                        print(data.get('data'), end='', flush=True)
                    elif data.get('type') == 'web_sources':
                        print(f"\n\nWeb Sources: {json.dumps(data.get('data'), indent=2)}")
    except Exception as e:
        print(f"\nError: {e}")

if __name__ == "__main__":
    test_web_search()
