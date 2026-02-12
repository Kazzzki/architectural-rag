
try:
    print("Importing pipeline_manager...")
    from pipeline_manager import process_file_pipeline
    print("Import successful!")
except Exception as e:
    print(f"Import failed: {e}")
    import traceback
    traceback.print_exc()
