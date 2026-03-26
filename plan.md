# Plan: PDF参照ページ番号トラッキング修正

## 問題

RAG検索の結果にPDFのページ番号が含まれず、ユーザーが元PDFのどこを参照しているか追えない。

## 根本原因

`chunk_builder.py` の `_HEADER_SPLIT_RE` が `[[PAGE_N]]` マーカーを独立セクションに分割する。
この独立セクションは50文字未満のためスキップされ、後続セクション/リーフチャンクの `page_number` が全て `None` になる。

加えて `indexer.py` の `source_metadata` に `"page_no": 0`（フロントマター由来）が含まれており、全チャンクに無意味な値が伝播している。

## 変更対象ファイル

### 1. `chunk_builder.py` (コア修正)

- `_PAGE_MARKER_RE` 正規表現を追加
- `_merge_page_marker_sections()` メソッド追加: `[[PAGE_N]]` だけのセクションを消費し、ページ番号を後続セクションに引き継ぐ
- `_extract_page_number()` / `_scan_page_markers()` / `_resolve_page_at()` ヘルパー追加
- セクションチャンク: `page_number` にマーカーから抽出した値を設定
- リーフチャンク: セクション内のマーカー位置に基づきページ番号を割り当て
- セクション/リーフのコンテンツから `[[PAGE_N]]` マーカーを除去（メタデータに移行済みのためノイズ）

### 2. `indexer.py` (汚染除去)

- `source_metadata` から `"page_no": page_no` を削除

## 変更不要

- `retriever.py`: `get_source_files()` / `build_context()` は既に `page_number` メタデータ対応済み
- `frontend/app/components/SourceCard.tsx`: ページチップ表示は実装済み
- `frontend/app/components/PDFViewer.tsx`: ページナビゲーションは実装済み
- `frontend/app/page.tsx`: `[S1:p.12]` 形式のCitationBadgeは実装済み

## 検証方法

1. テストスクリプトで `[[PAGE_N]]` マーカー含むテキストから ChunkBuilder を実行
2. セクション/リーフチャンクの `page_number` が正しいことを確認
3. コンテンツから `[[PAGE_N]]` が除去されていることを確認

## リスク

- 既存のインデックス済みチャンクは `page_number: None` のまま → 再インデックスが必要
- ページマーカーのないMarkdownファイル（手動作成等）は引き続き `page_number: None` → 既存動作と同じ、退行なし

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | PASS | Hold scope. 2ファイルのバグ修正、スコープ明確。Two-way door。 |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | SKIP | UI変更なし |
| Eng Review | `/plan-eng-review` | Architecture & tests | 1 | PASS | 既存構造を変更せずメタデータ欠損を修正。エッジケースカバー済み。 |

**VERDICT:** APPROVED — 実装に進む
