import os
import threading
import uuid
import time
from flask import Flask, render_template, request, jsonify, send_from_directory, send_file
from archiver import Archiver
from dotenv import load_dotenv

# Load Env
load_dotenv()

app = Flask(__name__)
app.config['DOWNLOAD_FOLDER'] = os.path.abspath('downloads')
app.secret_key = os.getenv("SECRET_KEY", "smart-archive-secret")
PASSWORD = os.getenv("APP_PASSWORD", "book123") # Default password same as Book OCR

# Global State for simplicity (Single user assumption)
job_state = {
    "status": "idle", # idle, processing, completed, error
    "job_id": None,
    "total": 0,
    "processed": 0,
    "logs": [],
    "results": [],
    "failures": []
}

def job_callback(event, url=None, filename=None, error=None):
    """Callback from Archiver to update job state"""
    timestamp = time.strftime("%H:%M:%S")
    
    if event == "processing":
        job_state["logs"].append(f"[{timestamp}] 🚀 Processing: {url}")
        
    elif event == "analyzing":
        job_state["logs"].append(f"[{timestamp}] 🧠 Generic Title AI: Analyzing content...")
        
    elif event == "completed":
        job_state["processed"] += 1
        job_state["logs"].append(f"[{timestamp}] ✅ Saved: {filename}")
        job_state["results"].append({"url": url, "filename": filename})
        
    elif event == "failed":
        job_state["processed"] += 1 # Count as processed even if failed
        job_state["logs"].append(f"[{timestamp}] ❌ Failed: {error}")
        job_state["failures"].append({"url": url, "error": error})

def run_archive_job(urls):
    """Background Task"""
    global job_state
    
    # Initialize
    job_state["status"] = "processing"
    job_state["logs"] = []
    job_state["results"] = []
    job_state["failures"] = []
    job_state["total"] = len(urls)
    job_state["processed"] = 0
    job_state["job_id"] = str(uuid.uuid4())
    
    try:
        archiver = Archiver(download_dir=app.config['DOWNLOAD_FOLDER'])
        archiver.run_batch(urls, callback=job_callback)
        job_state["status"] = "completed"
    except Exception as e:
        job_state["status"] = "error"
        job_state["logs"].append(f"Critical Error: {str(e)}")

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/archive', methods=['POST'])
def start_archive():
    data = request.json
    urls = [u.strip() for u in data.get('urls', '').split('\n') if u.strip()]
    
    if not urls:
        return jsonify({"status": "error", "message": "No URLs provided"}), 400
        
    if job_state["status"] == "processing":
        return jsonify({"status": "error", "message": "Job already running"}), 409

    # Start Thread
    thread = threading.Thread(target=run_archive_job, args=(urls,))
    thread.daemon = True
    thread.start()
    
    return jsonify({"status": "success", "message": "Started", "job_id": job_state["job_id"]})

@app.route('/api/status')
def get_status():
    return jsonify(job_state)

@app.route('/api/files')
def list_files():
    if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
        return jsonify([])
    files = sorted(os.listdir(app.config['DOWNLOAD_FOLDER']), reverse=True)
    files = [f for f in files if f.endswith('.pdf')]
    return jsonify(files)

import zipfile
import io

# ... existing imports ...

@app.route('/api/download_all')
def download_all():
    if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
        return jsonify({"status": "error", "message": "No files found"}), 404
        
    # In-memory zip
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        files = os.listdir(app.config['DOWNLOAD_FOLDER'])
        for f in files:
            if f.endswith('.pdf'):
                file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f)
                zf.write(file_path, arcname=f)
    
    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='smart_archive_all.zip'
    )

@app.route('/api/download_batch')
def download_batch():
    if not job_state["results"]:
        return jsonify({"status": "error", "message": "No batch results found"}), 404
        
    memory_file = io.BytesIO()
    with zipfile.ZipFile(memory_file, 'w', zipfile.ZIP_DEFLATED) as zf:
        added_count = 0
        for item in job_state["results"]:
            filename = item.get("filename")
            if filename:
                file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
                if os.path.exists(file_path):
                    zf.write(file_path, arcname=filename)
                    added_count += 1
    
    if added_count == 0:
        return jsonify({"status": "error", "message": "Files no longer exist"}), 404

    memory_file.seek(0)
    
    return send_file(
        memory_file,
        mimetype='application/zip',
        as_attachment=True,
        download_name='smart_archive_batch.zip'
    )

@app.route('/api/files/<filename>', methods=['DELETE'])
def delete_file(filename):
    file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], filename)
    if os.path.exists(file_path):
        os.remove(file_path)
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "File not found"}), 404

@app.route('/api/files', methods=['DELETE'])
def delete_all_files():
    if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
        return jsonify({"status": "success", "message": "Nothing to delete"})
        
    for f in os.listdir(app.config['DOWNLOAD_FOLDER']):
        file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f)
        if f.endswith('.pdf'):
            os.remove(file_path)
    
    # Reset job state results if needed, or just keep them as history?
    # Better to clear results so batch download doesn't fail
    job_state["results"] = []
    
    return jsonify({"status": "success"})

if __name__ == '__main__':
    # Ensure download folder exists
    if not os.path.exists(app.config['DOWNLOAD_FOLDER']):
        os.makedirs(app.config['DOWNLOAD_FOLDER'])
    
    # Run on port 5004 (Voice=5003, Book=5002)
    app.run(host='0.0.0.0', port=5004, debug=True)
