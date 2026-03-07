import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from database import SessionLocal, Document

db = SessionLocal()
stuck = db.query(Document).filter(Document.status == "processing").all()
print(f"processingのままのレコード: {len(stuck)}件")
for doc in stuck:
    doc.status = "failed"
    print(f"  → failed に変更: {doc.filename}")
db.commit()
db.close()
print("完了")
