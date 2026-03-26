# CLAUDE.md — architectural-rag プロジェクト指示書

## プロジェクト概要

建築PM/CM業務向けナレッジ検索・回答生成Webアプリケーション。
課題因果グラフ、マインドマップ、RAG検索、タスク管理、会議録音機能を含む。

## 技術スタック

- **Backend**: FastAPI + SQLite (raw SQL via SQLAlchemy `text()`) + ChromaDB + Gemini 3.1 flash-lite
- **Frontend**: Next.js 14 + React 18 + TypeScript + Tailwind CSS + ReactFlow v11
- **AI**: Gemini API (gemini-3.1-flash-lite) for issue capture, analysis, causal inference

## 開発フロー（gstack）

このプロジェクトではgstackスキルを使用する。主なフロー:

1. **`/autoplan`** — 新機能の計画時にCEO/Design/Engレビューを自動実行
2. **実装** — コーディング
3. **`/review`** — Pre-landing diffレビュー（チェックリスト準拠）
4. **`/ship`** — VERSION bump, CHANGELOG, PR作成
5. **`/land-and-deploy`** — マージ・デプロイ

その他のスキル:
- `/investigate` — バグの根本原因調査（修正前に必ず原因特定）
- `/qa` — Webアプリのブラウザテスト
- `/design-consultation` — デザインシステム策定
- `/office-hours` — 新機能のアイデア検討

## コマンド

```bash
# バックエンド起動
uvicorn server:app --reload --port 8000

# フロントエンド起動
cd frontend && npm run dev

# テスト（テストフレームワーク未導入）
# TODO: pytest + jest/vitest 導入
```

## 重要なファイル構造

```
routers/issues.py          — 課題因果グラフAPI（27エンドポイント）
mindmap/router.py          — マインドマップAPI
database.py                — SQLiteスキーマ + idempotent migrations
frontend/app/issues/       — 課題因果グラフUI
frontend/app/mindmap/      — マインドマップUI
frontend/components/issues/ — 課題関連コンポーネント（18ファイル）
frontend/lib/issue_types.ts — TypeScript型定義
```

## DB マイグレーション

`database.py` の `_run_migrations()` にidempotentなDDLを追加する。
サーバー起動時（`server.py` lifespan）に自動実行。
`ALTER TABLE ADD COLUMN` は「already exists」エラーを自動スキップ。

## コーディング規約

- バックエンド: raw SQL via `text()`, Pydantic モデル, `Literal` 型でenum バリデーション
- フロントエンド: `'use client'` ディレクティブ, `authFetch` for API calls, Tailwind utility classes
- エッジのSELECTは `SELECT *` を使用（`_edge_row_to_dict` が5列/7列を自動判別）
- 課題のSELECTは `ISSUE_SELECT_COLS` を明示的に使用

## 既知の問題（対応中）

- B2/B3: Gemini APIエラー時のフロントエンド表示が不十分
- P2: IssueNode の React.memo が関数参照の変更で無効化されている
- P5: NoteTimeline の issueId 切替時に古いデータが一瞬表示される
- P6: EdgeLabelEditor が作成済みだが DeletableEdge に未接続
- P7/P8: useInteractionMode / useOptimisticMutation が未統合
