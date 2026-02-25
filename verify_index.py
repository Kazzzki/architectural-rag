from indexer import get_chroma_client, COLLECTION_NAME
from collections import Counter

client = get_chroma_client()
collection = client.get_collection(COLLECTION_NAME)

data = collection.get()
metadatas = data.get('metadatas', [])

total_chunks = len(metadatas)
print(f"Total chunks: {total_chunks}")

missing_hash = sum(1 for m in metadatas if not m.get('source_pdf_hash'))
print(f"Chunks missing source_pdf_hash: {missing_hash}")

chunk_pattern = sum(1 for m in metadatas if '.chunk_' in str(m.get('rel_path', '')))
print(f"Chunks with .chunk_ pattern: {chunk_pattern}")

category_counts = Counter(m.get('category', 'unknown') for m in metadatas)
doc_type_counts = Counter(m.get('doc_type', 'unknown') for m in metadatas)

print("\nCategory Distribution:")
for k, v in category_counts.items():
    print(f"  {k}: {v}")

print("\nDoc Type Distribution:")
for k, v in doc_type_counts.items():
    print(f"  {k}: {v}")
