import traceback
import sys

try:
    from server import app
    print("FastAPI app loaded successfully.")
    
    from fastapi.testclient import TestClient
    client = TestClient(app)
    
    # Test health endpoint
    print("Requesting /api/health...")
    res = client.get("/api/health")
    print(f"Health Status: {res.status_code}")
    print(f"Health JSON: {res.json()}")

except Exception as e:
    print("Test failed:")
    traceback.print_exc()
