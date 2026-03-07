import sys
print("Starting test_hang_3", flush=True)

def run():
    try:
        from generator import generate_answer_stream
        print("Imported generator modules", flush=True)
        
        chunks = generate_answer_stream("test query", "test context", [], history=[])
        print("Got generator, starting iteration", flush=True)
        for chunk in chunks:
            print(f"Chunk: {chunk}", flush=True)
            
        print("Stream completed", flush=True)
    except Exception as e:
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run()
