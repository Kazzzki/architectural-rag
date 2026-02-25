import requests
import json

url = "http://localhost:8000/api/chat/stream"
payload = json.dumps({
  "question": "test",
  "quick_mode": True
})
headers = {
  'Content-Type': 'application/json'
}

response = requests.request("POST", url, headers=headers, data=payload, auth=('admin', 'antigravity'), stream=True)

print(response.status_code)
for line in response.iter_lines():
    print(line.decode('utf-8'))
