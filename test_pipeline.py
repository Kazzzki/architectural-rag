import sys
import traceback
from pathlib import Path

try:
    from pipeline_manager import PipelineManager
    import asyncio
    
    pm = PipelineManager()
    dummy_pdf = Path("test_dummy.pdf")
    dummy_pdf.touch()
    
    # Mocking classification to force it to go to process_pdf_background
    pm.router.classify = lambda x: "Document"
    
    pm.process_file(dummy_pdf)
except Exception as e:
    traceback.print_exc()
