import os
import tempfile
import time
import subprocess
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from dotenv import load_dotenv
from datetime import datetime
from functools import wraps
import google.generativeai as genai
import whisper

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY', 'voice-memo-secret-key-2024')

# Set ffmpeg path for Whisper
FFMPEG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ffmpeg')
os.environ['PATH'] = os.path.dirname(FFMPEG_PATH) + ':' + os.environ.get('PATH', '')

# Load Whisper model (medium for better Japanese accuracy)
whisper_model = whisper.load_model("medium")

# Gemini API
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

# Password Protection
APP_PASSWORD = os.getenv('APP_PASSWORD', 'memo123')

# Obsidian Vault Path
OBSIDIAN_PATH = os.getenv('OBSIDIAN_VAULT_PATH', './notes')
os.makedirs(OBSIDIAN_PATH, exist_ok=True)

# Login required decorator
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

@app.route('/api/save', methods=['POST'])
def save_note():
    data = request.json
    content = data.get('content', '')
    title = data.get('title', '')
    
    if not content.strip():
        return jsonify({"status": "error", "message": "内容が空です"}), 400
    
    # Generate filename
    timestamp = datetime.now().strftime('%Y-%m-%d_%H%M%S')
    if title:
        filename = f"{title}.md"
    else:
        filename = f"音声メモ_{timestamp}.md"
    
    filepath = os.path.join(OBSIDIAN_PATH, filename)
    
    # Add YAML frontmatter for Obsidian
    frontmatter = f"""---
created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
tags: [voice-memo, 音声入力]
---

"""
    
    full_content = frontmatter + content
    
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(full_content)
        return jsonify({
            "status": "success", 
            "path": filepath,
            "filename": filename
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/transcribe', methods=['POST'])
@login_required
def transcribe_audio():
    """Transcribe audio using Gemini 3 Flash Native Audio directly"""
    if not GEMINI_API_KEY:
        return jsonify({"status": "error", "message": "Gemini API key not configured"}), 500
    
    if 'audio' not in request.files:
        return jsonify({"status": "error", "message": "音声ファイルがありません"}), 400
    
    audio_file = request.files['audio']
    
    try:
        # Save to temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.webm') as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name
        
        # Upload to Gemini (Gemini accepts .webm directly)
        uploaded_file = genai.upload_file(tmp_path, mime_type="audio/webm")
        
        # Wait for processing
        while uploaded_file.state.name == "PROCESSING":
            time.sleep(1)
            uploaded_file = genai.get_file(uploaded_file.name)
        
        if uploaded_file.state.name == "FAILED":
            os.unlink(tmp_path)
            return jsonify({"status": "error", "message": "音声ファイルの処理に失敗しました"}), 500
        
        # Transcribe with Gemini 3 Flash Preview (Native Audio)
        # Gemini 3 Flash is multimodal and can process audio directly with high accuracy
        model = genai.GenerativeModel('gemini-3-flash-preview')
        
        # Enhanced prompt for natural transcription (removing stammers/corrections)
        prompt = """この音声ファイルを、読みやすい自然な日本語テキストに書き起こしてください。
        
【整形ルール】
1. **言い直しの処理**: 発言の訂正（「今日、いや明日は」）がある場合、訂正後の内容（「明日は」）のみを残してください。
2. **無意味な繰り返し削除**: 「あの、あの」のように意味なく繰り返される言葉は1つにまとめてください。
3. **フィラーの完全削除**: 「えー」「あー」「そのー」「えっと」などの埋め草言葉はすべて削除してください。
4. **文脈の維持**: 上記以外の、意味のある言葉は勝手に要約せずに残してください。
5. **句読点と段落**: 読みやすく適切な句読点を打ち、話の区切りで段落を変えてください。
6. **出力**: テキストのみを出力してください。"""
        
        response = model.generate_content([prompt, uploaded_file])
        transcript = response.text.strip()
        
        # Get token usage
        input_tokens = 0
        output_tokens = 0
        if hasattr(response, 'usage_metadata'):
            input_tokens = getattr(response.usage_metadata, 'prompt_token_count', 0)
            output_tokens = getattr(response.usage_metadata, 'candidates_token_count', 0)
        
        # Estimate cost
        input_cost = (input_tokens / 1_000_000) * 0.10
        output_cost = (output_tokens / 1_000_000) * 0.40
        total_cost = input_cost + output_cost
        
        # Cleanup
        os.unlink(tmp_path)
        genai.delete_file(uploaded_file.name)
        
        return jsonify({
            "status": "success",
            "transcript": transcript,
            "tokens": {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens
            },
            "cost_usd": round(total_cost, 6)
        })
        
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/notes', methods=['GET'])
def list_notes():
    """List recent voice memos"""
    try:
        files = []
        for f in os.listdir(OBSIDIAN_PATH):
            if f.endswith('.md') and '音声メモ' in f:
                filepath = os.path.join(OBSIDIAN_PATH, f)
                files.append({
                    "name": f,
                    "modified": os.path.getmtime(filepath)
                })
        # Sort by modified time, newest first
        files.sort(key=lambda x: x['modified'], reverse=True)
        return jsonify({"status": "success", "notes": files[:10]})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5003)
