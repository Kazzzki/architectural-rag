import sys
import logging
logging.basicConfig(level=logging.DEBUG)

def run():
    print("Starting test_hang")
    try:
        from retriever import search
        print("Imported search")
        res = search("test query", use_rerank=False, use_query_expansion=False, use_hyde=False)
        print("Search completed")
        print(f"Results: {len(res.get('documents', []))}")
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run()
