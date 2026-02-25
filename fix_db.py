from database import SessionLocal, Document
from datetime import datetime

db = SessionLocal()
docs = db.query(Document).filter(Document.status == 'processing').all()
for doc in docs:
    print(f"Fixing {doc.filename}...")
    doc.status = 'failed'
    doc.error_message = 'Process terminated unexpectedly.'
    doc.updated_at = datetime.now()
db.commit()
db.close()
print("Done.")
