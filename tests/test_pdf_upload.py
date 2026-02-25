import requests
import io

API_BASE = "http://localhost:8000"

def test_flow():
    print("1. Uploading test PDF...")
    pdf_content = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF"
    
    files = {'files': ('test_upload_doc.pdf', pdf_content, 'application/pdf')}
    res = requests.post(f"{API_BASE}/api/files/upload", files=files)
    if res.status_code != 200:
        print("Upload failed:", res.text)
        return
    print("Upload Response:", res.json())
    
    print("\n2. Checking PDF list API...")
    res = requests.get(f"{API_BASE}/api/pdf/list")
    if res.status_code == 200:
        print("List Response:", res.json())
    else:
        print("List failed:", res.text)

if __name__ == "__main__":
    test_flow()
