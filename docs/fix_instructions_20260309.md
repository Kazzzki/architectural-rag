# バグ修正指示書

**作成日:** 2026-03-09  
**対象リポジトリ:** antigravity RAG システム（建築意匠ナレッジRAG）  
**調査・修正担当:** Genspark AI  
**コミット:** `be096e6`

---

## 概要

コードレビューにより、**サーバー起動を完全にブロックする致命的なバグ 2件** を発見・修正した。  
いずれもコミット `50cd7fd`（Phase 2/3/4 リファクタリング、2026-03-07）で導入されたもの。

| # | 重大度 | ファイル | エラー種別 | 症状 |
|---|--------|----------|------------|------|
| 1 | 🔴 致命的 | `dense_indexer.py` | `ImportError` | サーバーが起動しない |
| 2 | 🔴 致命的 | `requirements.txt` | `ModuleNotFoundError` | 新環境で起動しない |

---

## バグ詳細

---

### Bug #1 ─ `get_chroma_client` が public export されていない

#### エラーメッセージ

```
ImportError: cannot import name 'get_chroma_client' from 'dense_indexer'
(/path/to/dense_indexer.py). Did you mean: '_get_chroma_client'?
```

#### 発生箇所（import している側）

| ファイル | 行 | コード |
|----------|----|--------|
| `indexer.py` | 36 | `from dense_indexer import get_chroma_client` |
| `retriever.py` | 25 | `from dense_indexer import get_chroma_client` |
| `run_batch.py` | 4 | `from indexer import get_chroma_client, ...` |
| `scripts/diagnose_metadata.py` | 11 | `from indexer import get_chroma_client, ...` |
| `scripts/fix_source_pdf_metadata.py` | 97 | `from indexer import get_chroma_client, ...` |
| `scripts/repair_source_pdf_hash.py` | 11 | `from indexer import get_chroma_client, ...` |
| `scripts/sync_drive_ids.py` | 19 | `from indexer import get_chroma_client, ...` |
| `test_phase2_runner.py` | 15 | `from indexer import get_chroma_client, ...` |
| `test_pipeline_e2e.py` | 7 | `from indexer import get_chroma_client` |
| `verify_chunks.py` | 3 | `from indexer import get_chroma_client, ...` |
| `verify_index.py` | 1 | `from indexer import get_chroma_client, ...` |

#### 波及する起動エラー

`indexer.py` → `retriever.py` → `routers/chat.py` → `server.py` と連鎖するため、
**FastAPI サーバー自体が起動不能**になる。

#### 原因

リファクタリング（`50cd7fd`）で `get_chroma_client()` を `dense_indexer.py` に移した際、
関数名の先頭に `_` が付いた **プライベート関数** `_get_chroma_client()` として定義された。  
しかし呼び出し側のコードはすべて **公開名 `get_chroma_client`** のままで更新されなかった。

```python
# ❌ 修正前 dense_indexer.py（プライベート定義のみ）
def _get_chroma_client(path=CHROMA_DB_DIR):   # ← アンダースコア付き
    ...
```

#### 修正内容

`dense_indexer.py` に **公開エイリアス関数** を追加する。

```python
# ✅ 修正後 dense_indexer.py（16〜18行目に追加）
def get_chroma_client(path=CHROMA_DB_DIR):
    """公開エイリアス: indexer.py / retriever.py から import されるパブリック関数"""
    return _get_chroma_client(path)

def _get_chroma_client(path=CHROMA_DB_DIR):   # ← 内部実装はそのまま残す
    ...
```

> **なぜエイリアス方式か：**  
> `_get_chroma_client` を単純に `get_chroma_client` にリネームすると、
> `DenseIndexer.__init__` 内部の `_get_chroma_client()` 呼び出しも一緒に変更が必要になる。
> エイリアス追加なら内部実装を触らず最小変更で済む。

---

### Bug #2 ─ `pypdf` が `requirements.txt` に未記載

#### エラーメッセージ

```
ModuleNotFoundError: No module named 'pypdf'
```

#### 発生箇所（`pypdf` を使用しているファイル）

| ファイル | 行 | コード |
|----------|----|--------|
| `ocr_processor.py` | 9 | `import pypdf` |
| `routers/pdf.py` | 99 | `import pypdf` |
| `manual_pdf_ocr.py` | 6 | `import pypdf` |
| `make_pdf.py` | 2 | `from pypdf import PdfWriter` |
| `create_checklist_folders.py` | 1 | `import pypdf` |

#### 原因

`pypdf` は `ocr_processor.py` 等で広く使われているにもかかわらず、
`requirements.txt` に記載が漏れていた。  
開発者のローカル環境では別途インストール済みのため気づかれず、
**クリーンな新規環境や CI/CD 環境ではインストールされず起動時にクラッシュ**する。

```text
# ❌ 修正前 requirements.txt（pypdf の記載なし）
PyMuPDF>=1.24.0
python-docx>=1.1.0
```

#### 修正内容

`requirements.txt` の `PyMuPDF` の次の行に `pypdf>=4.0.0` を追加する。

```text
# ✅ 修正後 requirements.txt
PyMuPDF>=1.24.0
pypdf>=4.0.0        ← 追加
python-docx>=1.1.0
```

> **バージョン指定の根拠：**  
> `pypdf` は v4 系から API が安定化されており、v3 以下との破壊的変更がある。
> `>=4.0.0` を指定することで安全な互換性範囲を確保する。

---

## 修正の適用手順

### 自動マージ（推奨）

本修正はすでにコミット `be096e6` として `main` ブランチに適用済み。  
ローカルリポジトリで以下を実行して取り込む：

```bash
git pull origin main
pip install -r requirements.txt   # pypdf を新規インストール
```

### 手動適用が必要な場合

#### Step 1: `dense_indexer.py` を編集

`_chroma_lock = Lock()` の直後（15行目付近）に以下を**挿入**する：

```python
def get_chroma_client(path=CHROMA_DB_DIR):
    """公開エイリアス: indexer.py / retriever.py から import されるパブリック関数"""
    return _get_chroma_client(path)
```

#### Step 2: `requirements.txt` を編集

`PyMuPDF>=1.24.0` の次の行に以下を**追加**する：

```
pypdf>=4.0.0
```

#### Step 3: 動作確認

```bash
pip install -r requirements.txt

python3 -c "
import os
os.environ['GEMINI_API_KEY'] = 'dummy_for_test'
from dense_indexer import get_chroma_client
from indexer import GeminiEmbeddingFunction
from retriever import search
print('✅ インポートチェック OK')
"
```

正常なら `✅ インポートチェック OK` と出力される。

---

## 再発防止策（推奨）

| 対策 | 理由 |
|------|------|
| `pip install -r requirements.txt` を CI に組み込み、インポートテストを実行する | 今回の Bug #2 のような記載漏れをすぐ検知できる |
| リファクタリング時は `grep -rn "関数名"` で全参照箇所を確認してから改名する | 今回の Bug #1 のような参照側との名前不一致を防ぐ |
| `python -m py_compile *.py routers/*.py` をコミット前フックに追加する | 構文エラー・インポートエラーの早期検知 |

---

## 修正ファイル一覧

```
modified:  dense_indexer.py     (+4 lines)
modified:  requirements.txt     (+1 line)
```

**commit:** `be096e6061aad9ad737ef2b94f738cb337d59d9f`  
**message:** `fix: add public get_chroma_client alias in dense_indexer and add pypdf to requirements`
