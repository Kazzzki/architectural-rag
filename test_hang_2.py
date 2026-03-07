import sys
print("Starting test_hang_2", flush=True)

def run():
    print("Inside run", flush=True)
    try:
        from retriever import search, get_collection
        print("Imported retriever modules", flush=True)
        
        # Test ChromaDB connection
        coll = get_collection()
        print(f"Chroma Collection connected: {coll.count()} items", flush=True)
        
        res = search("test query", use_rerank=False, use_query_expansion=False, use_hyde=False)
        print("Search completed", flush=True)
        print(f"Results: {len(res.get('documents', []))}", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run()
