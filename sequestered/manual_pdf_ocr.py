import os
import sys
import time
import argparse
import google.genai as genai
import pypdf
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration
# If config.py is available, we can try to import it, but for standalone script, we'll redefine constants or load from env
from config import GEMINI_API_KEY, GEMINI_MODEL_OCR as GEMINI_MODEL
from gemini_client import get_client

# v2 SDK Client
client = get_client()

def split_pdf(filepath: str, chunk_size: int = 2):
    """Splits a PDF into chunks of `chunk_size` pages."""
    chunks = []
    reader = pypdf.PdfReader(filepath)
    total_pages = len(reader.pages)
    
    base_dir = Path(filepath).parent
    filename = Path(filepath).stem
    
    print(f"Splitting {filepath} ({total_pages} pages) into chunks of {chunk_size} pages...")
    
    for i in range(0, total_pages, chunk_size):
        writer = pypdf.PdfWriter()
        end_page = min(i + chunk_size, total_pages)
        for p in range(i, end_page):
            writer.add_page(reader.pages[p])
        
        chunk_filename = f".chunk_{i}_{filename}.pdf"
        chunk_path = base_dir / chunk_filename
        
        with open(chunk_path, "wb") as f_out:
            writer.write(f_out)
        
        chunks.append({
            "path": str(chunk_path),
            "mime_type": "application/pdf",
            "label": f"Pages {i+1}-{end_page}",
            "index": i
        })
        
    return chunks

def call_gemini(model_name: str, file_path: str, mime_type: str, prompt: str):
    """Calls Gemini API with the given file and prompt using v2 SDK."""
    from google.genai import types
    
    print(f"Uploading {file_path}...")
    uploaded_file = client.files.upload(path=file_path, config={"mime_type": mime_type})
    
    file_name = uploaded_file.name

    # Wait for processing
    while True:
        f = client.files.get(name=file_name)
        if f.state.name == "ACTIVE":
            break
        if f.state.name == "FAILED":
            raise Exception("Google AI File processing failed")
        time.sleep(1)

    print(f"Generating content for {file_path}...")
    response = client.models.generate_content(
        model=model_name,
        contents=[prompt, uploaded_file]
    )
    return response.text

def process_pdf(filepath: str, output_path: str = None):
    if not output_path:
        output_path = str(Path(filepath).with_suffix('.md'))
        
    chunks = split_pdf(filepath, chunk_size=2)
    
    full_text = f"# OCR Result: {Path(filepath).name}\n\n"
    
    prompt = """
    You are a professional digital archivist. 
    Transcribe the text EXACTLY as it appears in the image/PDF. 
    - Output ONLY the markdown content.
    - Preserve structure (headers, lists).
    - If there are tables, use Markdown tables.
    """

    for chunk in chunks:
        try:
            print(f"Processing chunk: {chunk['label']}")
            text = call_gemini(GEMINI_MODEL, chunk['path'], chunk['mime_type'], prompt)
            
            full_text += f"\n\n## {chunk['label']}\n\n"
            full_text += text
            full_text += "\n\n---\n"
            
        except Exception as e:
            print(f"Error processing {chunk['label']}: {e}")
            full_text += f"\n\n> Error processing {chunk['label']}: {e}\n\n"
        finally:
            # Cleanup temp file
            if os.path.exists(chunk['path']):
                os.remove(chunk['path'])

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(full_text)
        
    print(f"\nDone! Output saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split PDF and OCR with Gemini")
    parser.add_argument("filepath", help="Path to the PDF file")
    parser.add_argument("--model", default=GEMINI_MODEL, help="Gemini model name")
    parser.add_argument("--output", help="Output markdown file path")
    args = parser.parse_args()
    
    if args.model:
        GEMINI_MODEL = args.model
        
    process_pdf(args.filepath, args.output)
