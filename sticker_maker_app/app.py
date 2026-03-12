import os
import time
import json
import uuid
import io
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
import numpy as np
import rembg

# Load Config
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY")
APP_PASSWORD = os.getenv("APP_PASSWORD", "cat123")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")

# Configure AI
client = genai.Client(api_key=API_KEY)
MODEL_NAME = "gemini-3-pro-image-preview"

app = Flask(__name__)
app.secret_key = SECRET_KEY

# Directories
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STICKERS_DIR = os.path.join(BASE_DIR, 'static/stickers')
UPLOADS_DIR = os.path.join(BASE_DIR, 'static/uploads')
STYLES_DIR = os.path.join(BASE_DIR, 'static/styles')
DATA_FILE = os.path.join(BASE_DIR, 'gallery_data.json')
STYLE_FILE = os.path.join(BASE_DIR, 'style_config.json')
DEFAULT_STYLE = os.path.join(BASE_DIR, 'static/style_reference.png')

for d in [STICKERS_DIR, UPLOADS_DIR, STYLES_DIR]:
    os.makedirs(d, exist_ok=True)

# ============ HELPERS ============

def load_gallery_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_gallery_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

def get_current_style():
    """Get current style reference image path"""
    if os.path.exists(STYLE_FILE):
        with open(STYLE_FILE, 'r') as f:
            config = json.load(f)
            if os.path.exists(config.get('path', '')):
                return config['path']
    # Return default style
    if os.path.exists(DEFAULT_STYLE):
        return DEFAULT_STYLE
    return None

def set_current_style(filepath):
    """Set current style reference"""
    with open(STYLE_FILE, 'w') as f:
        json.dump({'path': filepath}, f)

def add_text_to_image(img, caption):
    """Add caption text with outline"""
    if not caption:
        return img
    
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/ヒラギノ丸ゴ ProN W4.ttc", 32)
    except:
        font = ImageFont.load_default()
    
    w, h = img.size
    text_w = draw.textlength(caption, font=font)
    x = (w - text_w) / 2
    y = h - 50
    
    for dx in [-2, -1, 0, 1, 2]:
        for dy in [-2, -1, 0, 1, 2]:
            draw.text((x+dx, y+dy), caption, font=font, fill="white")
    draw.text((x, y), caption, font=font, fill="black")
    
    return img

def analyze_cat_features(image_bytes):
    """Analyze cat image to extract distinctive features (Ver 3.0)"""
    prompt = """
    【タスク: 猫の構造解析】
    添付された猫の画像を客観的な事実として分析し、以下のJSONフォーマットで出力してください。
    「雰囲気」ではなく「物理的な特徴」を記述することが重要です。

    Output JSON Format:
    {
      "breed_type": "品種および体型（例: ブリティッシュショートヘア、ずんぐりむっくり）",
      "fur_mapping": "模様の正確な位置。特に顔の模様（ハチワレの形、鼻の周りの点など）や靴下の有無を詳細に。",
      "eye_detail": "虹彩の色（正確な色味）、形（まん丸、つり目など）",
      "distinctive_points": "この個体を識別するための最大のチャームポイント（例: カギ尻尾、片耳が垂れている、オッドアイ）"
    }
    """
    
    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=[
                types.Part.from_bytes(data=image_bytes, mime_type='image/jpeg'),
                prompt
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json"
            )
        )
        return json.loads(response.text)
    except Exception as e:
        print(f"Analysis failed: {e}")
        return {}

# ============ ROUTES ============

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('index'))
        return render_template('login.html', error='パスワードが違います')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
def index():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return redirect(url_for('gallery'))

@app.route('/gallery')
def gallery():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    data = load_gallery_data()
    images = sorted(data.values(), key=lambda x: x.get('uploaded_at', 0), reverse=True)
    
    # Get current style
    style_path = get_current_style()
    style_url = None
    if style_path:
        style_url = '/static/' + os.path.relpath(style_path, os.path.join(BASE_DIR, 'static'))
    
    return render_template('gallery.html', images=images, style_url=style_url)

@app.route('/studio')
def studio_multi():
    """Studio handling multiple images"""
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    
    data = load_gallery_data()
    image_ids = request.args.get('ids', '').split(',')
    
    selected_images = []
    for img_id in image_ids:
        if img_id in data:
            selected_images.append(data[img_id])
            
    if not selected_images:
        return redirect(url_for('gallery'))
        
    style_path = get_current_style()
    style_url = None
    if style_path:
        style_url = '/static/' + os.path.relpath(style_path, os.path.join(BASE_DIR, 'static'))
    
    return render_template('studio.html', images=selected_images, style_url=style_url)

@app.route('/studio/<image_id>')
def studio(image_id):
    """Legacy route for single image (redirects to multi)"""
    return redirect(url_for('studio_multi', ids=image_id))

# ============ API ============

@app.route('/api/upload', methods=['POST'])
def upload_image():
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    if 'image' not in request.files:
        return jsonify({'error': 'No file'}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No filename'}), 400
        
    filename = secure_filename(str(uuid.uuid4()) + "_" + file.filename)
    filepath = os.path.join(UPLOADS_DIR, filename)
    file.save(filepath)
    
    image_id = str(uuid.uuid4())
    record = {
        "id": image_id,
        "filename": filename,
        "filepath": f"/static/uploads/{filename}",
        "uploaded_at": time.time()
    }
    
    data = load_gallery_data()
    data[image_id] = record
    save_gallery_data(data)
    
    return jsonify({"status": "success", "data": record})

@app.route('/api/upload_style', methods=['POST'])
def upload_style():
    """Upload a new style reference image"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    if 'image' not in request.files:
        return jsonify({'error': 'No file'}), 400
        
    file = request.files['image']
    if file.filename == '':
        return jsonify({'error': 'No filename'}), 400
        
    filename = secure_filename(f"style_{uuid.uuid4()}_{file.filename}")
    filepath = os.path.join(STYLES_DIR, filename)
    file.save(filepath)
    
    # Set as current style
    set_current_style(filepath)
    
    return jsonify({
        "status": "success", 
        "url": f"/static/styles/{filename}"
    })

@app.route('/api/generate_sticker', methods=['POST'])
def generate_sticker():
    """Generate sticker using Ver 3.0 Hybrid Multimodal Pipeline"""
    if not session.get('logged_in'):
        return jsonify({'error': 'Unauthorized'}), 401
    
    req = request.json
    image_ids = req.get('image_ids', [])
    # Legacy support for single image_id
    if not image_ids and req.get('image_id'):
        image_ids = [req.get('image_id')]
        
    theme = req.get('theme', '')
    caption = req.get('caption', '')
    creativity = req.get('creativity', '2')

    if not image_ids:
         return jsonify({'error': '画像が選択されていません'}), 400

    # Get photo from gallery
    data = load_gallery_data()
    
    subject_images_bytes = []
    
    for img_id in image_ids:
        if img_id not in data:
            continue
        info = data[img_id]
        path = os.path.join(UPLOADS_DIR, info['filename'])
        if os.path.exists(path):
            with open(path, 'rb') as f:
                subject_images_bytes.append(f.read())

    if not subject_images_bytes:
        return jsonify({'error': '有効な画像が見つかりません'}), 400
    
    # Get style reference
    style_path = get_current_style()

    try:
        style_bytes = None
        if style_path and os.path.exists(style_path):
            with open(style_path, 'rb') as f:
                style_bytes = f.read()

        # === Phase 1: Feature Extraction ===
        # We analyze the first image as the primary reference for text features
        features = analyze_cat_features(subject_images_bytes[0])
        feature_desc = f"""
        【重要：厳守すべき猫の特徴（Analysis Result）】
        - 品種・体型: {features.get('breed_type', '不明')}
        - 毛色・模様の配置: {features.get('fur_mapping', '不明')}
        - 目の色・形: {features.get('eye_detail', '不明')}
        - 絶対に残すべきチャームポイント: {features.get('distinctive_points', '特になし')}
        """
        
        # === Phase 2: High-Consistency Generation ===
        content_parts = []
        
        # 1. Style Reference
        if style_bytes:
            content_parts.append(types.Part.from_bytes(data=style_bytes, mime_type='image/png'))
            
        # 2. Subject Images (Multi-modal referencing)
        for img_bytes in subject_images_bytes:
             content_parts.append(types.Part.from_bytes(data=img_bytes, mime_type='image/jpeg'))

        # Prompt Logic
        style_instruction = "1枚目の画像（スタイル参照）の画風を正確に模倣してください。" if style_bytes else "LINEスタンプ風のかわいいイラストスタイルで描いてください。"
        
        prompt = f"""
【System: あなたは世界一のペットイラストレーターです】
あなたは、ユーザーの愛猫の写真を元に、指定されたスタイルのLINEスタンプを作成するエキスパートです。

【入力情報】
1. Sytle Image (1枚目): 画風のターゲット。
2. Subject Images (2枚目以降): モデルとなる猫。複数ある場合は、これらの写真から立体的な特徴を把握してください。

【詳細指示】
{style_instruction}

【最優先ルール：アイデンティティの保持】
提供された写真と、以下の特徴分析データを元に、猫の模様や特徴を忠実に再現してください。
ポーズが変わっても、模様の位置関係は絶対に維持してください。
{feature_desc}

【ポーズ・テーマの指示】
テーマ: "{theme if theme else '日常'}"
"""
        if creativity == '1':
            prompt += "- ポーズ: 写真をトレースし、忠実に再現してください。\n"
        elif creativity == '3':
            prompt += "- ポーズ: テーマに合わせて大胆に変更してください（例: 飛ぶ、走る）。ただし猫の模様は維持すること。\n"
        else:
            prompt += "- ポーズ: 写真をベースにしつつ、テーマが伝わるように手足や表情を微調整してください。\n"

        prompt += "\n背景は白、テキストは含めないでください。"
        content_parts.append(prompt)

        # Generate
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=content_parts,
            config=types.GenerateContentConfig(
                response_modalities=['IMAGE', 'TEXT']
            )
        )
        
        # Extract Image
        img = None
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                img = Image.open(io.BytesIO(part.inline_data.data)).convert("RGBA")
                break
        
        if img is None:
             raise Exception("AI did not generate an image.")

        # === Phase 3: Post-Processing (Background Removal & Resizing) ===
        # 1. Provide white background cleanup instructions just in case, but rely on rembg
        
        # Remove Background
        img_np = np.array(img)
        img_no_bg_np = rembg.remove(img_np)
        img = Image.fromarray(img_no_bg_np).convert("RGBA")
        
        # Resize to LINE specs (Max 370x320) with padding
        target_w, target_h = 370, 320
        img.thumbnail((target_w - 20, target_h - 20), Image.Resampling.LANCZOS) # Safety margin 10px each side
        
        # Create final canvas
        canvas = Image.new('RGBA', (target_w, target_h), (255, 255, 255, 0))
        # Center image
        paste_x = (target_w - img.width) // 2
        paste_y = (target_h - img.height) // 2
        canvas.paste(img, (paste_x, paste_y), img)
        
        # Add Caption
        if caption:
            canvas = add_text_to_image(canvas, caption)
        
        # Save
        filename = f"sticker_v3_{uuid.uuid4()}.png"
        save_path = os.path.join(STICKERS_DIR, filename)
        canvas.save(save_path, format="PNG")
        
        return jsonify({
            "status": "success",
            "url": f"/static/stickers/{filename}",
            "analysis": features # Return analysis for debug/display
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5006)
