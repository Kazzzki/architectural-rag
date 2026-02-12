# indexer.py - ファイルスキャン・インデックス作成（Webアプリ版）

import os
import json
import hashlib
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import fitz  # PyMuPDF
from docx import Document
import google.generativeai as genai
import chromadb
from chromadb import EmbeddingFunction

from config import (
    KNOWLEDGE_BASE_DIR,
    CHROMA_DB_DIR,
    FILE_INDEX_PATH,
    SUPPORTED_EXTENSIONS,
    CHUNK_SIZE,
    CHUNK_OVERLAP,
    EMBEDDING_MODEL,
    COLLECTION_NAME,
    EXCLUDE_FOLDERS,
    GEMINI_API_KEY,
)

# Gemini API設定
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)


class GeminiEmbeddingFunction(EmbeddingFunction):
    """Gemini Embedding APIを使用するカスタムEmbeddingFunction"""
    
    def __call__(self, input: List[str]) -> List[List[float]]:
        embeddings = []
        for text in input:
            result = genai.embed_content(
                model=EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document"
            )
            embeddings.append(result['embedding'])
        return embeddings


def get_query_embedding(text: str) -> List[float]:
    """検索クエリ用のEmbedding取得"""
    result = genai.embed_content(
        model=EMBEDDING_MODEL,
        content=text,
        task_type="retrieval_query"
    )
    return result['embedding']


def scan_files(base_dir: Path = KNOWLEDGE_BASE_DIR) -> List[Dict[str, Any]]:
    """
    ナレッジDBフォルダを再帰的にスキャンし、ファイルメタデータを収集
    """
    files = []
    base_path = Path(base_dir)
    
    if not base_path.exists():
        base_path.mkdir(parents=True, exist_ok=True)
        return files
    
    raw_files = []
    for filepath in base_path.rglob("*"):
        if filepath.is_dir():
            continue
        
        # 除外フォルダをスキップ
        rel_path = filepath.relative_to(base_path)
        if any(exclude in str(rel_path) for exclude in EXCLUDE_FOLDERS):
            continue
        
        # サポート対象の拡張子のみ
        if filepath.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        
        # パス構造を解析
        parts = rel_path.parts
        category = parts[0] if len(parts) > 1 else ""
        subcategory = parts[1] if len(parts) > 2 else ""
        sub_subcategory = parts[2] if len(parts) > 3 else ""
        
        file_info = {
            "filename": filepath.name,
            "full_path": str(filepath),
            "rel_path": str(rel_path),
            "category": category,
            "subcategory": subcategory,
            "sub_subcategory": sub_subcategory,
            "file_type": filepath.suffix.lower().lstrip('.'),
            "file_size_kb": round(filepath.stat().st_size / 1024, 2),
            "modified_at": datetime.fromtimestamp(filepath.stat().st_mtime).isoformat(),
        }
        raw_files.append(file_info)

    # Markdown優先ロジック: 同名のMDがある場合、PDFを除外し、MDにPDFパスを紐付ける
    file_map = {f['rel_path']: f for f in raw_files}
    processed_paths = set()
    
    final_files = []
    
    # まずMarkdownと他の非PDFファイルを処理
    for f in raw_files:
        if f['file_type'] == 'md':
            # 同名のPDFを探す
            pdf_rel_path = str(Path(f['rel_path']).with_suffix('.pdf'))
            if pdf_rel_path in file_map:
                f['source_pdf'] = pdf_rel_path
                processed_paths.add(pdf_rel_path)  # PDFは処理済みとする
            
            final_files.append(f)
            processed_paths.add(f['rel_path'])

    # 残りのファイル（PDF含む）を追加
    for f in raw_files:
        if f['rel_path'] not in processed_paths:
            final_files.append(f)
    
    return final_files


def extract_text(filepath: str) -> List[Dict[str, Any]]:
    """ファイルからテキストを抽出"""
    path = Path(filepath)
    ext = path.suffix.lower()
    
    try:
        if ext == '.pdf':
            return _extract_pdf(filepath)
        elif ext in ['.md', '.txt']:
            return _extract_text_file(filepath)
        elif ext == '.docx':
            return _extract_docx(filepath)
        else:
            return []
    except Exception as e:
        print(f"テキスト抽出エラー ({filepath}): {e}")
        return []


def _extract_pdf(filepath: str) -> List[Dict[str, Any]]:
    """PDFからテキストを抽出"""
    pages = []
    doc = fitz.open(filepath)
    
    for page_num, page in enumerate(doc, start=1):
        text = page.get_text()
        if text.strip():
            pages.append({"text": text, "page_number": page_num})
    
    doc.close()
    return pages


def _extract_text_file(filepath: str) -> List[Dict[str, Any]]:
    """テキスト/Markdownファイルからテキストを抽出"""
    with open(filepath, 'r', encoding='utf-8') as f:
        text = f.read()
    return [{"text": text, "page_number": None}] if text.strip() else []

def parse_frontmatter(filepath: str) -> Dict[str, Any]:
    """MarkdownファイルのFrontmatterを解析"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if content.startswith("---"):
            import yaml
            parts = content.split("---", 2)
            if len(parts) >= 3:
                fm = yaml.safe_load(parts[1])
                return fm if isinstance(fm, dict) else {}
    except Exception as e:
        print(f"Frontmatter parsing error ({filepath}): {e}")
    return {}


def _extract_docx(filepath: str) -> List[Dict[str, Any]]:
    """DOCXファイルからテキストを抽出"""
    doc = Document(filepath)
    text = "\n".join([para.text for para in doc.paragraphs])
    return [{"text": text, "page_number": None}] if text.strip() else []


def chunk_text(text: str, metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    """テキストを意味的な単位でチャンクに分割 (Semantic Chunking & Page Aware)"""
    chunks = []
    if not text or not text.strip():
        return chunks

    import re
    
    # ページ分割: [[PAGE_X]] マーカーで分割
    # ただし、単純にsplitするとテキストの連続性が失われる可能性があるが、
    # 基本的にページまたぎのコンテキストはセクションが変わることが多いので許容する。
    # もしページまたぎの文がある場合は、前後のページに重複挿入するか、
    # あるいはストリーム処理的にチャンクを作る必要がある。
    # ここでは簡易的に「ページごとに処理」する。
    
    page_splits = re.split(r'(\[\[PAGE_\d+\]\])', text)
    
    current_page_num = None
    
    # 最初のセグメントがページマーカーでない場合（冒頭のFrontmatterなど）
    # デフォルト1ページ目とするか、Noneとする
    if page_splits and not page_splits[0].startswith('[[PAGE_'):
        pass # そのまま処理
        
    # 再構築しながら処理
    current_processing_text = ""
    # page_splitsのリズム: [text, marker, text, marker, text...]
    
    all_segments = []
    temp_page_num = 1
    
    for i, segment in enumerate(page_splits):
        if not segment.strip(): continue
        
        match = re.match(r'\[\[PAGE_(\d+)\]\]', segment)
        if match:
            temp_page_num = int(match.group(1))
        else:
            all_segments.append({
                "text": segment,
                "page": temp_page_num
            })
            
    # 各セグメント（ページ）ごとにチャンク分割
    global_chunk_index = 0
    
    for segment in all_segments:
        seg_text = segment["text"]
        seg_page = segment["page"]
        
        # --- ここから Semantic Chunking Logic (再利用) ---
        final_chunks_text = []
        current_chunk = ""
        paragraphs = seg_text.split("\n\n")
        
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 <= CHUNK_SIZE:
                current_chunk += "\n\n" + para if current_chunk else para
            else:
                if current_chunk: final_chunks_text.append(current_chunk)
                if len(para) > CHUNK_SIZE:
                     sub_parts = re.split(r'([。、\.\!\?])', para)
                     sub_chunk = ""
                     for part in sub_parts:
                         if len(sub_chunk) + len(part) <= CHUNK_SIZE:
                             sub_chunk += part
                         else:
                             if sub_chunk: final_chunks_text.append(sub_chunk)
                             sub_chunk = part
                     if sub_chunk: current_chunk = sub_chunk
                     else: current_chunk = ""
                else:
                    current_chunk = para
        if current_chunk: final_chunks_text.append(current_chunk)
        # --- Code End ---
        
        for c_text in final_chunks_text:
            if not c_text.strip(): continue
            meta = metadata.copy()
            meta["chunk_index"] = global_chunk_index
            meta["page_number"] = seg_page # ページ番号付与
            chunks.append({"text": c_text, "metadata": meta})
            global_chunk_index += 1

    return chunks


def generate_doc_id(filepath: str, chunk_index: int) -> str:
    """ドキュメントIDを生成"""
    key = f"{filepath}_{chunk_index}"
    return hashlib.md5(key.encode()).hexdigest()


def load_file_index() -> Dict[str, Any]:
    """file_index.jsonを読み込み"""
    if os.path.exists(FILE_INDEX_PATH):
        with open(FILE_INDEX_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {"files": {}, "last_updated": None}


def save_file_index(index: Dict[str, Any]):
    """file_index.jsonを保存"""
    index["last_updated"] = datetime.now().isoformat()
    os.makedirs(os.path.dirname(FILE_INDEX_PATH), exist_ok=True)
    with open(FILE_INDEX_PATH, 'w', encoding='utf-8') as f:
        json.dump(index, f, ensure_ascii=False, indent=2)


def build_index(force_rebuild: bool = False) -> Dict[str, int]:
    """ファイルをスキャンしてChromaDBにインデックスを構築"""
    print("ファイルをスキャン中...")
    files = scan_files()
    print(f"発見したファイル数: {len(files)}")
    
    file_index = load_file_index()
    indexed_files = file_index.get("files", {})
    
    # ChromaDB接続
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    
    embedding_function = GeminiEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )
    
    stats = {
        "total_files": len(files),
        "indexed": 0,
        "skipped": 0,
        "errors": 0,
        "chunks": 0,
    }
    
    for file_info in files:
        rel_path = file_info["rel_path"]
        
        if not force_rebuild and rel_path in indexed_files:
            existing = indexed_files[rel_path]
            if existing.get("modified_at") == file_info["modified_at"]:
                stats["skipped"] += 1
                continue
        
        try:
            pages = extract_text(file_info["full_path"])
            
            if not pages:
                stats["skipped"] += 1
                continue
            
            # Frontmatterからメタデータを取得 (.mdの場合)
            frontmatter = {}
            if file_info["file_type"] == "md":
                frontmatter = parse_frontmatter(file_info["full_path"])

            for page in pages:
                metadata = {
                    "filename": file_info["filename"],
                    "rel_path": rel_path,
                    "category": frontmatter.get("primary_category") or file_info["category"], # Frontmatter優先
                    "subcategory": file_info["subcategory"],
                    "sub_subcategory": file_info["sub_subcategory"],
                    "page_number": page.get("page_number"),
                    "source_pdf": file_info.get("source_pdf"),
                    "file_type": file_info.get("file_type", ""),
                    "modified_at": file_info.get("modified_at", ""),
                    "tags_str": ",".join(frontmatter.get("tags", [])) # ChromaDB用 (リストが非推奨の場合の保険)
                }
                
                # リストも保存 (ChromaDBがサポートしていれば)
                # ただしメタデータフィルタリングでリスト型は一部制限があるため、文字列化しておくのが無難
                # 検索時に文字列として取得してPython側でパースする
                
                chunks = chunk_text(page["text"], metadata)
                
                for chunk in chunks:
                    doc_id = generate_doc_id(rel_path, chunk["metadata"]["chunk_index"])
                    collection.upsert(
                        ids=[doc_id],
                        documents=[chunk["text"]],
                        metadatas=[chunk["metadata"]],
                    )
                    stats["chunks"] += 1
            
            file_info["last_indexed_at"] = datetime.now().isoformat()
            indexed_files[rel_path] = file_info
            stats["indexed"] += 1
            
        except Exception as e:
            print(f"エラー ({rel_path}): {e}")
            stats["errors"] += 1
    
    file_index["files"] = indexed_files
    save_file_index(file_index)
    
    print(f"インデックス完了: {stats['indexed']}ファイル, {stats['chunks']}チャンク")
    return stats


def index_file(filepath: str) -> Dict[str, Any]:
    """
    単一ファイルをインデックスに追加・更新
    """
    path = Path(filepath)
    if not path.exists():
        return {"error": "File not found"}
        
    print(f"単一ファイルインデックス開始: {path.name}")
    
    # メタデータ作成
    # scan_filesのロジックを簡易的に再利用
    # 実際には引数でメタデータを受け取る形でも良いが、ここではパスから自動生成する
    from config import KNOWLEDGE_BASE_DIR, EXCLUDE_FOLDERS, SUPPORTED_EXTENSIONS
    
    base_path = Path(KNOWLEDGE_BASE_DIR)
    try:
        rel_path = path.relative_to(base_path)
    except ValueError:
        # KNOWLEDGE_BASE_DIR外のファイルはインデックスできない
        return {"error": "File is outside knowledge base dir"}
        
    parts = rel_path.parts
    category = parts[0] if len(parts) > 1 else ""
    subcategory = parts[1] if len(parts) > 2 else ""
    sub_subcategory = parts[2] if len(parts) > 3 else ""
    
    file_info = {
        "filename": path.name,
        "full_path": str(path),
        "rel_path": str(rel_path),
        "category": category,
        "subcategory": subcategory,
        "sub_subcategory": sub_subcategory,
        "file_type": path.suffix.lower().lstrip('.'),
        "file_size_kb": round(path.stat().st_size / 1024, 2),
        "modified_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
    }
    
    # ソースPDFの解決（Markdownの場合）
    if file_info['file_type'] == 'md':
        pdf_path = path.with_suffix('.pdf')
        if pdf_path.exists():
            file_info['source_pdf'] = str(pdf_path.relative_to(base_path))
            
    # ChromaDB接続
    os.makedirs(CHROMA_DB_DIR, exist_ok=True)
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    
    embedding_function = GeminiEmbeddingFunction()
    collection = client.get_or_create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedding_function,
    )
    
    # 既存の当該ファイルのチャンクを削除（上書きのため）
    # doc_idはハッシュなので、whereフィルターでメタデータから削除する必要がある
    # しかしChromaDBのdeleteはids指定が基本。metadata filterも使える。
    try:
        collection.delete(where={"rel_path": str(rel_path)})
    except Exception as e:
        print(f"既存インデックス削除エラー (無視可能): {e}")

    stats = {"chunks": 0, "indexed": False}
    
    try:
        pages = extract_text(str(path))
        if not pages:
            return {"error": "No text extracted"}
        
        # Frontmatterからメタデータを取得 (.mdの場合)
        frontmatter = {}
        if file_info["file_type"] == "md":
            frontmatter = parse_frontmatter(str(path))

        for page in pages:
            metadata = {
                "filename": file_info["filename"],
                "rel_path": str(rel_path),
                "category": frontmatter.get("primary_category") or file_info["category"],
                "subcategory": file_info["subcategory"],
                "sub_subcategory": file_info["sub_subcategory"],
                "page_number": page.get("page_number"),
                "source_pdf": file_info.get("source_pdf"),
                "file_type": file_info.get("file_type", ""),
                "modified_at": file_info.get("modified_at", ""),
                "tags_str": ",".join(frontmatter.get("tags", []))
            }
            
            chunks = chunk_text(page["text"], metadata)
            
            # バッチサイズを考慮してinsertした方が良いが、単一ファイルなら一括でもいけるか
            # エラー回避のため少しずつ入れる
            for chunk in chunks:
                doc_id = generate_doc_id(str(rel_path), chunk["metadata"]["chunk_index"])
                collection.upsert(
                    ids=[doc_id],
                    documents=[chunk["text"]],
                    metadatas=[chunk["metadata"]],
                )
                stats["chunks"] += 1
                
        # file_index.jsonの更新
        file_index = load_file_index()
        file_info["last_indexed_at"] = datetime.now().isoformat()
        file_index["files"][str(rel_path)] = file_info
        save_file_index(file_index)
        
        stats["indexed"] = True
        print(f"単一ファイルインデックス完了: {stats['chunks']}チャンク")
        
    except Exception as e:
        print(f"インデックスエラー: {e}")
        return {"error": str(e)}
        
    return stats


def delete_from_index(rel_path: str) -> bool:
    """インデックスからファイルを削除"""
    print(f"インデックス削除開始: {rel_path}")
    
    # ChromaDB接続
    try:
        os.makedirs(CHROMA_DB_DIR, exist_ok=True)
        client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
        )
        
        # 削除実行
        collection.delete(where={"rel_path": rel_path})
    except Exception as e:
        print(f"ChromaDB削除エラー: {e}")
        # DBエラーでもファイルインデックスからは削除したいので続行
        
    # file_index.jsonから削除
    try:
        file_index = load_file_index()
        if rel_path in file_index["files"]:
            del file_index["files"][rel_path]
            save_file_index(file_index)
            print(f"インデックス削除完了: {rel_path}")
            return True
        else:
             print(f"インデックスに見つかりません: {rel_path}")
             return False
    except Exception as e:
        print(f"file_index削除エラー: {e}")
        return False


if __name__ == "__main__":
    build_index()
