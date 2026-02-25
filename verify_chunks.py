import sys
sys.path.append('.')
from indexer import get_chroma_client, COLLECTION_NAME
client = get_chroma_client()
collection = client.get_collection(name=COLLECTION_NAME)

data = collection.get()
metadatas = data['metadatas']
total = len(metadatas)

missing_hash = sum(1 for m in metadatas if not m.get('source_pdf_hash'))
chunk_pattern = sum(1 for m in metadatas if '.chunk_' in str(m.get('rel_path', '')))

categories = {}
doc_types = {}

for m in metadatas:
    cat = m.get('category', 'unknown')
    categories[cat] = categories.get(cat, 0) + 1
    
    dtype = m.get('doc_type', 'unknown')
    doc_types[dtype] = doc_types.get(dtype, 0) + 1

print(f"Total Chunks: {total}")
print(f"Missing source_pdf_hash: {missing_hash}")
print(f"Contains .chunk_ pattern: {chunk_pattern}")
print("\nCategory Distribution:")
for k, v in categories.items():
    print(f"  {k}: {v}")

print("\nDoc Type Distribution:")
for k, v in doc_types.items():
    print(f"  {k}: {v}")
