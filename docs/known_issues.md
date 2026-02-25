# 既知の問題一覧 — Architectural RAG System

> 調査日: 2026-02-24  
> ステータス: `⛔ 未修正` / `🔧 修正予定` / `✅ 修正済み`

---

## 発見した問題一覧

### 🔴 緊急（システム全体が機能しない）

| # | ファイル | 行 | 問題の内容 | 深刻度 | ステータス |
|---|---|---|---|---|---|
| 1 | `indexer.py` | 65, 78 | **`EMBEDDING_MODEL` が import されていない**。`from config import (...)` ブロック（L19-29）に `EMBEDDING_MODEL` が含まれておらず、NameError が発生。 | **致命的** | ✅ |

### 🟠 高（複数機能に影響）

| # | ファイル | 行 | 問題の内容 | 深刻度 | ステータス |
|---|---|---|---|---|---|
| 2 | `server.py` | 574, 1127 | **`/api/pdf/{file_id}` エンドポイントが2箇所で定義**。 | 高 | ✅ |
| 3 | `server.py` | 610, 1187 | **`/api/pdf/metadata/{file_id}` も2箇所で定義**。 | 高 | ✅ |
| 4 | `server.py` | 全体 | **ファイルが1300行**と巨大。全33エンドポイントが1ファイルに集中しており、修正時に副作用が起きやすい構造。 | 高 | ✅ |
| 5 | `drive_sync.py` | 39 | **`REDIRECT_URI` ハードコード廃止**。`get_auth_url` と `save_credentials_from_code` の引数を required に変更。 | 高 | ✅ |
| 6 | `pipeline_manager.py` / daemon | ログ | **日本語ファイル名で UnicodeEncodeError**。httpxがASCIIヘッダ制約。 | 高 | ✅ |
| 7 | `status_manager.py` | 163 | **SQLite UNIQUE constraint violation**。`rename_status` UPSERTロジック追加。 | 高 | ✅ |

### 🟡 中（単一機能の問題）

| # | ファイル | 行 | 問題の内容 | 深刻度 | ステータス |
|---|---|---|---|---|---|
| 8 | 全体 | — | **97箇所で bare `except Exception`**。エラーの種類を区別せずに握り潰しており、原因特定が困難。 | 中 | ✅ 修正済み |
| 9 | `config.py` | 83 | **`DRIVE_SCOPES` 不整合** — 死んだ定数を削除。 | 中 | ✅ |
| 10 | `config.py` | 67 | **`GEMINI_API_KEY` のデフォルトが空文字列**。`.env` が読めない場合にサイレントに空キーで動作し、後続のAPI呼び出しで不明瞭なエラーになる。 | 中 | ✅ 修正済み |
| 11 | `server.py` | 50 | **`APP_PASSWORD` のデフォルトが空文字列**。未設定時にBasic認証が事実上無効になるが、ログには「有効です」と出る可能性がある。 | 中 | ✅ |
| 12 | `generate_obsidian.py` | 13 | **API_KEY プレースホルダー**を fail-fast 検証に置換。 | 中 | ✅ |
| 13 | `file_store.py` | 31 | **`except Exception:` 握り潰し** — ログ出力を追加。 | 中 | ✅ |
| 14 | `server.py` | 1032-1120 | **`POST /api/upload` が `POST /api/upload/multiple` と機能重複**。古い単一ファイルアップロードエンドポイントが残存。 | 中 | ✅ |

### 🟢 低（UX・パフォーマンス）

| # | ファイル | 行 | 問題の内容 | 深刻度 | ステータス |
|---|---|---|---|---|---|
| 15 | `config.py` | 92 | **CORS_ORIGINS に `http://localhost:3000`** が含まれる（開発用）。プロダクションで不要だが、セキュリティリスクは限定的。 | 低 | ✅ 修正済み |
| 16 | `app.log` | — | **10MB超のログファイル**がローテーションされていない。ディスク消費。 | 低 | ✅ |
| 17 | ルート | — | **散在するテストファイル** (`test_ai.py`, `test_db.py`, `test_embed.py`, etc.) が `tests/` に統合されておらず、整理が必要。 | 低 | ✅ |
| 18 | Python | — | **Python 3.9** を使用中。Google Auth ライブラリが EOL 警告を出している。 | 低 | ✅ 修正済み |

---

## ログから検出されたエラーパターン

### server.log
- `name 'EMBEDDING_MODEL' is not defined in upsert` — **367回以上** 出現（全ドキュメント）
- `name 'EMBEDDING_MODEL' is not defined` — チャットストリーミングでも 500 エラー
- `POST /api/chat/stream HTTP/1.1 500 Internal Server Error`

### antigravity_daemon.log
- `UnicodeEncodeError: 'ascii' codec can't encode characters` — 日本語ファイル名の分類時
- `sqlite3.IntegrityError: UNIQUE constraint failed: documents.file_path` — ステータス更新時
- `FileNotFoundError: File not found before classification` — 入力ファイルが処理前に消失

---

## 修正の優先順位

| 優先度 | 問題 # | 理由 |
|---|---|---|
| **最優先** | #1 | 全インデックスとチャット機能が壊れている。1行の修正で直る |
| **高** | #2, #3 | エンドポイント競合で予期しないレスポンスが返る |
| **高** | #6 | 日本語ファイル名の処理が全滅 |
| **高** | #7 | DB整合性エラーでOCR管理が不安定 |
| **中** | #5 | OAuth リダイレクトの信頼性（暫定修正済み） |
| **中** | #8 | エラーハンドリング品質（段階的に改善） |
| **低** | 残り | 動作には直接影響しない |
