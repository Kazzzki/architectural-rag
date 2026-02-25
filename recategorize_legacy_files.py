import os
import shutil
import time
from pathlib import Path
from tqdm import tqdm

from config import REFERENCE_DIR, SEARCH_MD_DIR, DB_PATH
from classifier import DocumentClassifier
import file_store

def read_md_content(md_path: Path):
    """
    Reads a Markdown file and separates frontmatter from body text.
    Returns (frontmatter_dict, full_body_text).
    """
    if not md_path.exists():
        return None, ""
        
    with open(md_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    # Basic frontmatter parser matching --- boundaries
    parts = content.split('---')
    if len(parts) >= 3 and content.startswith('---'):
        frontmatter_str = parts[1]
        body = '---'.join(parts[2:]).strip()
        
        # Super simple key-value parser for known fields
        fm_dict = {}
        for line in frontmatter_str.split('\n'):
            if ':' in line:
                key = line.split(':')[0].strip()
                val = line.split(':', 1)[1].strip()
                fm_dict[key] = val
                
        return fm_dict, body
    return {}, content
    
def write_md_with_frontmatter(md_path: Path, frontmatter_str: str, body: str):
    """Writes the updated AI frontmatter and original body back to file"""
    full_text = frontmatter_str + "\n" + body
    with open(md_path, 'w', encoding='utf-8') as f:
        f.write(full_text)

def process_unclassified_files():
    print("Initializing Document Classifier (Gemini)...")
    classifier = DocumentClassifier()
    
    # 1. Look for unclassified MDs (either in uploads/ or straight in 20_検索MD)
    md_dir = Path(SEARCH_MD_DIR)
    pdf_dir = Path(REFERENCE_DIR)
    
    # Target all root files and files strictly inside uploads/
    candidates = []
    
    for md_path in md_dir.rglob("*.md"):
        rel_path = md_path.relative_to(md_dir)
        parts = rel_path.parts
        
        # Consider it unclassified if it's in the root of SEARCH_MD_DIR or in 'uploads'
        if len(parts) == 1 or parts[0] == 'uploads':
            candidates.append(md_path)
            
    print(f"Found {len(candidates)} potentially unclassified Markdown files.")
    
    if not candidates:
        print("No files to re-categorize.")
        return

    moved_count = 0
    error_count = 0
    
    db_conn = file_store.get_db()
    
    with db_conn as conn:
        for md_path in tqdm(candidates, desc="Re-categorizing files"):
            try:
                # 2. Extract Text
                fm_dict, body_text = read_md_content(md_path)
                if not body_text:
                    continue
                
                # We limit to first 5000 chars as the classifier expects
                text_sample = body_text[:5000]
                
                # 3. Call Gemini Classifier
                meta = {'title': md_path.stem}
                result = classifier.classify(text_sample, meta)
                
                new_category = result.get('primary_category', 'uploads')
                
                # If AI says it belongs in uploads, skip moving it
                if new_category == 'uploads':
                    continue
                    
                print(f"\n[AI Decision] {md_path.name} -> {new_category}")
                
                # 4. Create new category dirs
                target_md_dir = md_dir / new_category
                target_pdf_dir = pdf_dir / new_category
                target_md_dir.mkdir(parents=True, exist_ok=True)
                target_pdf_dir.mkdir(parents=True, exist_ok=True)
                
                # 5. Build paths
                new_md_path = target_md_dir / md_path.name
                
                # 6. Rewrite MD with new Frontmatter
                new_fm = classifier.generate_frontmatter(result)
                write_md_with_frontmatter(md_path, new_fm, body_text)
                
                # 7. Move MD File
                shutil.move(str(md_path), str(new_md_path))
                
                # 8. Identify & Move corresponding PDF
                pdf_name = md_path.with_suffix('.pdf').name
                
                # It might be in PDF uploads/ or root PDF dir
                pdf_source = pdf_dir / 'uploads' / pdf_name
                if not pdf_source.exists():
                    pdf_source = pdf_dir / pdf_name
                    
                if pdf_source.exists():
                    new_pdf_path = target_pdf_dir / pdf_name
                    shutil.move(str(pdf_source), str(new_pdf_path))
                    
                    # 9. Update SQLite Record
                    # The file_store tracks the currently active path. We need to find the record by current_path and update it
                    conn.execute(
                        "UPDATE files SET current_path = ? WHERE current_path = ?",
                        (str(new_pdf_path), str(pdf_source))
                    )
                
                moved_count += 1
                
                # Avoid hitting Gemini rate limits
                time.sleep(2)
                
            except Exception as e:
                print(f"Error processing {md_path.name}: {e}")
                error_count += 1

    print(f"\nMigration Complete! Moved {moved_count} files (Errors: {error_count}).")
    print("Please run an Index Rebuild to update ChromaDB with the new database pointers.")

if __name__ == "__main__":
    process_unclassified_files()
