import sys
import time

print("Starting test_advanced_search", flush=True)

def run():
    try:
        from retriever import search, get_collection
        print("Imported retriever modules", flush=True)
        
        start_time = time.time()
        print("Testing search WITH advanced features...", flush=True)
        res = search("鉄骨工場の断熱材", use_rerank=True, use_query_expansion=True, use_hyde=True)
        print(f"Search completed in {time.time() - start_time:.2f}s", flush=True)
        print(f"Results: {len(res.get('documents', []))}", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run()
