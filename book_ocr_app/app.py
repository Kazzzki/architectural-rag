import os
import time
import shutil
import traceback
import uuid
import threading
import google.generativeai as genai
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image
from functools import wraps
import pypdf
from concurrent.futures import ThreadPoolExecutor, as_completed

# Load API Key
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
APP_PASSWORD = os.getenv("APP_PASSWORD", "memo123") # Default password
SECRET_KEY = os.getenv("SECRET_KEY", "book-ocr-secret-key-2025")

if not API_KEY:
    print("❌ Error: GEMINI_API_KEY is missing in .env")

# Configure AI
genai.configure(api_key=API_KEY)

app = Flask(__name__)
app.secret_key = SECRET_KEY
UPLOAD_FOLDER = 'static/uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# iCloud Save Path
ICLOUD_PATH = os.path.expanduser('~/Library/Mobile Documents/com~apple~CloudDocs/antigravity/scanned_books')
os.makedirs(ICLOUD_PATH, exist_ok=True)

# In-Memory Job Store
# Structure: { job_id: { 'status': 'processing'|'completed'|'failed', 'progress': {'current': 0, 'total': 0}, 'result': {...}, 'created_at': time } }
JOBS = {}

# Helper function
def process_chunk_task(chunk, prompt_template, model_name):
    """Process a single chunk (image/pdf part) with retries"""
    max_retries = 3
    last_error = None
    
    for attempt in range(max_retries):
        try:
            model = genai.GenerativeModel(model_name)
            
            # Upload
            print(f"Uploading chunk: {chunk['label']} (Attempt {attempt+1})")
            uploaded_file = genai.upload_file(chunk['path'], mime_type=chunk['mime_type'])
            
            # Wait
            wait_count = 0
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(1)
                uploaded_file = genai.get_file(uploaded_file.name)
                wait_count += 1
                if wait_count > 60:
                    raise Exception("File processing timeout")
            
            if uploaded_file.state.name == "FAILED":
                raise Exception("Google AI File processing failed for chunk")

            # Generate
            generation_config = genai.types.GenerationConfig(
                max_output_tokens=8192,
                temperature=0.1
            )
            
            print(f"Generating for: {chunk['label']}")
            response = model.generate_content(
                [prompt_template, uploaded_file], 
                generation_config=generation_config
            )
            
            is_truncated = False
            if response.candidates and response.candidates[0].finish_reason.name == "MAX_TOKENS":
                is_truncated = True
            
            # Cleanup chunk if temp
            if chunk.get('is_temp'):
                try:
                    os.remove(chunk['path'])
                except:
                    pass
                    
            return {
                "text": response.text, 
                "truncated": is_truncated, 
                "index": chunk['index'],
                "success": True,
                "page_count": chunk.get('page_count', 0)
            }
            
        except Exception as e:
            print(f"Error in chunk {chunk['label']} (Attempt {attempt+1}): {e}")
            last_error = e
            time.sleep(2 * (attempt + 1)) # Backoff
    
    # Final failure after retries
    traceback.print_exc()
    return {
        "text": f"\n\n> ⚠️ **[Processing Error]** Failed to retrieve content for **{chunk['label']}** after {max_retries} attempts.\n> Error: {str(last_error)}\n\n", 
        "truncated": False, 
        "index": chunk['index'],
        "success": False,
        "page_count": 0
    }

def process_file_preparation(filepath, filename, upload_folder):
    """Prepare file and return list of chunks to process. Sync function."""
    chunks_to_process = []
    total_pages_expected = 1
    
    is_pdf = filename.lower().endswith('.pdf')
    
    if is_pdf:
        try:
            reader = pypdf.PdfReader(filepath)
            total_pages = len(reader.pages)
            total_pages_expected = total_pages
            print(f"PDF Pages: {total_pages}")
            
            CHUNK_SIZE = 2 # Reduced for reliability
            
            if total_pages > CHUNK_SIZE:
                for i in range(0, total_pages, CHUNK_SIZE):
                    writer = pypdf.PdfWriter()
                    end_page = min(i + CHUNK_SIZE, total_pages)
                    for p in range(i, end_page):
                        writer.add_page(reader.pages[p])
                        
                    chunk_filename = f"chunk_{i}_{filename}"
                    chunk_path = os.path.join(upload_folder, chunk_filename)
                    
                    with open(chunk_path, "wb") as f_out:
                        writer.write(f_out)
                        
                    chunks_to_process.append({
                        "path": chunk_path,
                        "mime_type": "application/pdf",
                        "label": f"Pages {i+1}-{end_page}",
                        "index": i,
                        "is_temp": True,
                        "page_count": end_page - i
                    })
            else:
                chunks_to_process.append({
                    "path": filepath, 
                    "mime_type": "application/pdf", 
                    "label": "Full Doc",
                    "index": 0,
                    "is_temp": False,
                    "page_count": total_pages
                })
        except Exception as e:
            print(f"PDF Error: {e}")
            chunks_to_process.append({
                "path": filepath, "mime_type": "application/pdf", "label": "Full Doc (Fallback)", "index": 0, "is_temp": False, "page_count": 0
            })
    else:
        mime_type = 'image/jpeg'
        if filename.lower().endswith('.png'): mime_type = 'image/png'
        if filename.lower().endswith('.webp'): mime_type = 'image/webp'
        chunks_to_process.append({
            "path": filepath, "mime_type": mime_type, "label": "Image", "index": 0, "is_temp": False, "page_count": 1
        })
        
    return chunks_to_process, total_pages_expected

def background_ocr_job(job_id, saved_files, model_name, upload_folder):
    """Wait for OCR processing in background"""
    print(f"Starting Job {job_id}")
    JOBS[job_id]['status'] = 'processing'
    
    try:
        all_chunks = []
        file_metadata = []
        
        # 1. Preparation Phase (Split PDFs)
        prompt_template = """
        You are a professional digital archivist. Your goal is to digitize this document with 100% fidelity.
        
        STRICT INSTRUCTIONS:
        1. Transcribe the text EXACTLY as it appears in the image/PDF. Do not summarize, correct grammar, or omit anything.
        2. Preserve the structure:
           - Use Markdown headers (#, ##) for titles.
           - Use Markdown lists (-, 1.) for bullet points.
           - Use **bold** for bold text.
           - Use > blockquotes for quoted text.
        3. If there are tables, reconstruct them using Markdown table syntax.
        4. If the text is in Japanese, ensure correct kanji/kana usage.
        5. Output ONLY the markdown content. No introductory text like "Here is the text".
        """
        
        for fp, fn in saved_files:
            chunks, total_pages = process_file_preparation(fp, fn, upload_folder)
            for c in chunks:
                c['filename'] = fn # Tag chunk with filename
            all_chunks.extend(chunks)
            file_metadata.append({'filename': fn, 'total_pages': total_pages})

        JOBS[job_id]['progress']['total'] = len(all_chunks)
        JOBS[job_id]['progress']['current'] = 0
        
        # 2. Execution Phase (Parallel)
        chunk_results = []
        max_workers = 5
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # key: future, value: chunk
            future_to_chunk = {executor.submit(process_chunk_task, c, prompt_template, model_name): c for c in all_chunks}
            
            for future in as_completed(future_to_chunk):
                try:
                    res = future.result()
                    # Add filename back to result so we can sort later
                    chunk = future_to_chunk[future]
                    res['filename'] = chunk['filename']
                    chunk_results.append(res)
                except Exception as e:
                    print(f"Detailed Thread Error: {e}")
                    traceback.print_exc()
                
                # Update Progress
                JOBS[job_id]['progress']['current'] += 1
        
        # 3. Aggregation Phase
        combined_markdown = ""
        total_truncated = False
        total_chunks = len(chunk_results)
        total_pages_all = sum([f['total_pages'] for f in file_metadata])
        processed_pages_all = sum([r.get('page_count', 0) for r in chunk_results if r.get('success', True)])
        
        # Group result by filename to reconstruct in order
        from itertools import groupby
        
        # sort by filename, then index
        chunk_results.sort(key=lambda x: (x['filename'], x['index']))
        
        for filename, group in groupby(chunk_results, key=lambda x: x['filename']):
            combined_markdown += f"# File: {filename}\n\n"
            file_results = list(group)
            
            combined_markdown += "\n\n".join([r['text'] for r in file_results])
            combined_markdown += "\n\n---\n\n"
            
            if any([r['truncated'] for r in file_results]):
                total_truncated = True

        result_data = {
            "status": "success",
            "markdown": combined_markdown,
            "used_model": model_name,
            "truncated": total_truncated,
            "chunks_processed": total_chunks,
            "files_processed": len(saved_files),
            "total_pages_all": total_pages_all,
            "processed_pages_all": processed_pages_all
        }
        
        JOBS[job_id]['result'] = result_data
        JOBS[job_id]['status'] = 'completed'
        print(f"Job {job_id} Completed")
        
    except Exception as e:
        print(f"Job {job_id} Failed: {e}")
        traceback.print_exc()
        JOBS[job_id]['status'] = 'failed'
        JOBS[job_id]['result'] = {"message": str(e)}

# Login Wrapper
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == APP_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        else:
            return render_template('login.html', error='パスワードが違います')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html')

@app.route('/ocr', methods=['POST'])
@login_required
def ocr_image():
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No files uploaded"}), 400
    
    files = request.files.getlist('image')
    if not files or files[0].filename == '':
        return jsonify({"status": "error", "message": "No selected file"}), 400

    model_name_input = request.form.get('model_name', 'gemini-3-flash')
    model_map = {
        'gemini-3-flash': 'gemini-3-flash-preview', 
        'gemini-3-pro': 'gemini-3-pro-preview', 
        'gemini-2.5-flash': 'gemini-2.5-flash', 
        'gemini-2.0-flash-exp': 'gemini-2.0-flash-exp'
    }
    model_name = model_map.get(model_name_input, model_name_input)
    
    # Save files synchronously
    saved_files = []
    for file in files:
        if file.filename:
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            saved_files.append((filepath, filename))
    
    # Create Job
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        'status': 'queued',
        'progress': {'current': 0, 'total': 0},
        'created_at': time.time(),
        'result': None
    }
    
    # Start Background Thread
    thread = threading.Thread(target=background_ocr_job, args=(job_id, saved_files, model_name, app.config['UPLOAD_FOLDER']))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        "status": "success",
        "job_id": job_id,
        "message": "Job started"
    })

@app.route('/job/<job_id>', methods=['GET'])
@login_required
def get_job_status(job_id):
    job = JOBS.get(job_id)
    if not job:
        return jsonify({"status": "error", "message": "Job not found"}), 404
        
    return jsonify({
        "status": job['status'],
        "progress": job['progress'],
        "result": job['result']
    })

@app.route('/api/save', methods=['POST'])
@login_required
def save_markdown():
    data = request.json
    text = data.get('text')
    path = data.get('path')

    if not text or not path:
        return jsonify({"status": "error", "message": "Missing text or path"}), 400

    try:
        if path.startswith('/'):
            target_path = path
        else:
            target_path = os.path.join(ICLOUD_PATH, path)
            
        if not target_path.endswith('.md'):
            target_path += '.md'

        os.makedirs(os.path.dirname(target_path), exist_ok=True)

        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(text)

        return jsonify({"status": "success", "path": target_path})

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/count_tokens', methods=['POST'])
@login_required
def count_tokens():
    if 'image' not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    
    files = request.files.getlist('image')
    model_name_input = request.form.get('model_name', 'gemini-2.0-flash-exp')
    
    model_map = {
        'gemini-3-flash': 'gemini-3-flash-preview', 
        'gemini-3-pro': 'gemini-3-pro-preview', 
        'gemini-2.5-flash': 'gemini-2.5-flash', 
        'gemini-2.0-flash-exp': 'gemini-2.0-flash-exp'
    }
    model_name = model_map.get(model_name_input, model_name_input)
    
    total_tokens = 0
    total_cost = 0.0
    
    try:
        pricing = {
            'gemini-1.5-flash': 0.075,
            'gemini-1.5-flash-8b': 0.0375,
            'gemini-1.5-pro': 3.50, # Assuming < 128k context
            'gemini-2.0-flash-exp': 0, # Experimental is free
            'gemini-experimental': 0, # Preview likely free
            'gemini-exp-1206': 0,
            'gemini-3-flash': 0.075, # Assume
            'gemini-3-pro': 3.50, # Assume
            'gemini-3-flash-preview': 0.075,
            'gemini-3-pro-preview': 3.50
        }
        price_per_1m = pricing.get(model_name, 0)

        model = genai.GenerativeModel(model_name)

        # Basic logic: process all files for count
        for file in files:
            if file.filename == '': continue
            
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], 'temp_count_' + filename)
            file.save(filepath)
            
            mime_type = 'application/pdf' if filename.lower().endswith('.pdf') else 'image/jpeg'
            
            uploaded_file = genai.upload_file(filepath, mime_type=mime_type)
            
            # Simple wait loop
            import time
            while uploaded_file.state.name == "PROCESSING":
                time.sleep(0.5)
                uploaded_file = genai.get_file(uploaded_file.name)
            
            count_res = model.count_tokens(uploaded_file)
            tokens = count_res.total_tokens
            total_tokens += tokens
            
            try:
                os.remove(filepath)
            except:
                pass
        
        cost = (total_tokens / 1_000_000) * price_per_1m
        
        return jsonify({
            "status": "success",
            "tokens": total_tokens,
            "cost": cost,
            "currency": "USD",
            "model": model_name
        })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5002)
