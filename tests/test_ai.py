import requests
import json
import base64

url = "http://localhost:8000/api/mindmap/ai/action"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Basic " + base64.b64encode(b"user:Antig2026!rag").decode("utf-8")
}
data = {
    "action": "summarize",
    "nodeId": "test",
    "content": "基本設計"
}

try:
    response = requests.post(url, headers=headers, json=data)
    print("Status:", response.status_code)
    print("Body:", response.text)
except Exception as e:
    print("Error:", e)
