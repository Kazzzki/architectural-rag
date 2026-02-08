import pypdf
import os
import re
from pathlib import Path

# PDFパス
PDF_PATH = "/Users/kkk/Library/Mobile Documents/com~apple~CloudDocs/antigravity/architectural_rag/data/knowledge_base/uploads/基本設計段階チェックリスト（設計者／CMr）S造研修所.pdf"

# ターゲット（絶対パス推奨）
BASE_DIR = Path("/Users/kkk/Library/Mobile Documents/com~apple~CloudDocs/antigravity/architectural_rag/data/knowledge_base")

def extract_hierarchy(pdf_path):
    if not os.path.exists(pdf_path):
        print(f"PDF not found: {pdf_path}")
        return []

    reader = pypdf.PdfReader(pdf_path)
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    
    lines = text.split('\n')
    
    # 階層パターン
    # レベル1: "1. 意匠設計"
    # レベル2: "1-1. 設計与条件の確認"
    # レベル3: "1-3-1. 宿泊棟"
    
    re_level1 = re.compile(r'^(\d+)\.\s+(.*)')
    re_level2 = re.compile(r'^(\d+)-(\d+)\.\s+(.*)')
    re_level3 = re.compile(r'^(\d+)-(\d+)-(\d+)\.\s+(.*)')
    
    current_l1 = None
    current_l2 = None
    
    unique_paths = []
    seen = set()

    for line in lines:
        line = line.strip()
        if not line: continue
        
        # Level 3
        m3 = re_level3.match(line)
        if m3:
            # フォルダ名に使えない文字を除去
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', m3.group(4))
            name = f"{m3.group(1)}-{m3.group(2)}-{m3.group(3)}_{safe_name}"
            
            if current_l1 and current_l2:
                full_path = current_l1 / current_l2 / name
                if str(full_path) not in seen:
                    unique_paths.append(full_path)
                    seen.add(str(full_path))
            continue

        # Level 2
        m2 = re_level2.match(line)
        if m2:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', m2.group(3))
            name = f"{m2.group(1)}-{m2.group(2)}_{safe_name}"
            
            if current_l1:
                current_l2 = name
                full_path = current_l1 / name
                if str(full_path) not in seen:
                    unique_paths.append(full_path)
                    seen.add(str(full_path))
            continue
            
        # Level 1
        m1 = re_level1.match(line)
        if m1:
            safe_name = re.sub(r'[\\/:*?"<>|]', '_', m1.group(2))
            name = f"{m1.group(1)}_{safe_name}"
            
            current_l1 = Path(name)
            current_l2 = None
            
            if str(current_l1) not in seen:
                unique_paths.append(current_l1)
                seen.add(str(current_l1))
            continue
            
    return unique_paths

def create_folders():
    folders = extract_hierarchy(PDF_PATH)
    print(f"作成予定のフォルダ数: {len(folders)}")
    
    if not folders:
        print("フォルダ構造を抽出できませんでした。")
        return

    for f in folders:
        path = BASE_DIR / f
        print(f"作成: {path.relative_to(BASE_DIR)}")
        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            print(f"エラー: {e}")

if __name__ == "__main__":
    create_folders()
