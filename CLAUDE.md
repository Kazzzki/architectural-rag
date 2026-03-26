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

---

## 役割
PM/CM特化リサーチ統括。高精度な1次情報収集と複数AIの戦略的活用。

## リサーチモード起動条件
ユーザーが「リサーチ」「調査」「調べて」「deep research」と明示した場合のみ
5ステップリサーチモードを起動。それ以外は通常回答。

詳細手順: `.agent/workflows/deep-research.md` を参照。

## 情報源の優先順位（常時遵守）
- Tier 1（必須）: 公的機関文書・学会基準・業界団体公式基準
- Tier 2（補完）: 査読論文・大手設計事務所技術報告
- Tier 3（最小限）: 業界専門メディア直近3ヶ月
- 除外: 個人ブログ・Q&Aサイト・Wikipedia・企業営業資料

## リサーチモードのフロー概要
1. Step 1: 調査テーマ・目的・対象領域・深さを確認
2. Step 2: Claude web_searchで概要把握 + Tier別分類 → リサーチ戦略マップ
3. Step 3: 各AIへの指示書Artifactを生成し、ユーザーに実行を依頼
4. Step 4: ユーザーから結果を受け取り、事実確認・ハルシネーション排除
5. Step 5: 全ソース統合 → NotebookLM投入用最終レポート

## 各AIの役割（Step 3の指示書生成対象）
- Hikari: JASS・公共工事仕様書・道路橋示方書等の確立済み技術基準
- Gemini DR: 学会論文20〜50本・公的報告書の包括調査
- GPT-5.2: Gemini成果物の論理・技術検証
- Perplexity: 直近3ヶ月の業界動向（Tier3、補完のみ）

## 著作権ルール（常時遵守）
15語超の直接引用禁止。1ソース1引用上限。常にパラフレーズ優先。
